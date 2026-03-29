import os
import requests
import json
import concurrent.futures
import time
from litellm import completion

def get_file_content(repo_name, path, github_token):
    """
    Obtiene el contenido de un archivo específico desde GitHub.
    """
    url = f"https://api.github.com/repos/{repo_name}/contents/{path}"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3.raw'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener el contenido del archivo {path}: {e}", flush=True)
        return None

def get_repo_logs(repo_name, github_token):
    """
    Obtiene el contenido de los archivos en la carpeta .logs para contexto de arquitectura.
    """
    url = f"https://api.github.com/repos/{repo_name}/contents/.logs"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            print("Carpeta .logs no encontrada. Se procederá sin contexto de arquitectura adicionales.", flush=True)
            return ""
        response.raise_for_status()
        
        logs_content = []
        files = response.json()
        
        for item in files:
            if item['type'] == 'file' and item['name'].endswith(('.md', '.txt')):
                content = get_file_content(repo_name, item['path'], github_token)
                if content:
                    logs_content.append(f"--- Archivo: {item['name']} ---\n{content}\n")
        
        return "\n".join(logs_content)
    except requests.exceptions.RequestException as e:
        print(f"Aviso: No se pudo obtener el contexto de .logs: {e}", flush=True)
        return ""

def detect_stack(repo_name, github_token):
    """
    Detecta el stack tecnológico del repositorio listando los archivos en la raíz.
    """
    url = f"https://api.github.com/repos/{repo_name}/contents/"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        files = [item['name'] for item in response.json()]

        if 'requirements.txt' in files or 'pyproject.toml' in files or 'Pipfile' in files or 'setup.py' in files:
            return 'python'
        
        if 'package.json' in files:
            package_json_content = get_file_content(repo_name, 'package.json', github_token)
            if package_json_content:
                dependencies = json.loads(package_json_content).get('dependencies', {})
                if 'react' in dependencies:
                    return 'frontend'
                if 'vue' in dependencies or 'nuxt' in dependencies:
                    return 'frontend'
                if '@nestjs/core' in dependencies:
                    return 'backend'
        
        return 'backend' # Default a backend si no se detecta nada específico
    except requests.exceptions.RequestException as e:
        print(f"Error al detectar el stack del repositorio: {e}", flush=True)
        return 'backend' # Default a backend en caso de error

def get_pr_diff(repo_name, pr_number, github_token):
    """
    Obtiene el diff de un Pull Request específico desde GitHub en formato de texto.
    """
    base_sha = None
    head_sha = None
    try:
        pr_url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"
        headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
        response = requests.get(pr_url, headers=headers)
        response.raise_for_status()
        pr_data = response.json()
        base_sha = pr_data['base']['sha']
        head_sha = pr_data['head']['sha']
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener los detalles del PR: {e}", flush=True)
        return None

    if not base_sha or not head_sha:
        print("No se pudieron obtener los SHAs de base y cabeza del PR.", flush=True)
        return None

    compare_url = f"https://api.github.com/repos/{repo_name}/compare/{base_sha}...{head_sha}"
    diff_headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3.diff'}
    try:
        response = requests.get(compare_url, headers=diff_headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener el diff de comparación: {e}", flush=True)
        return None

def parse_diff_by_file(diff_text):
    """
    Analiza el diff y agrupa todo el contenido del diff por archivo, omitiendo archivos de prueba.
    """
    if not diff_text:
        return {}
    files = {}
    current_file = None
    # Lista de patrones a ignorar
    ignore_patterns = ['.lock', 'package.json', 'package-lock.json', '.gitignore']
    
    for line in diff_text.split('\n'):
        if line.startswith('diff --git a/'):
            try:
                current_file = line.split(' b/')[1]
                
                # Comprobar si el archivo debe ser ignorado
                if any(pattern in current_file for pattern in ignore_patterns) or \
                   '/tests/' in current_file or '.test.' in current_file:
                    current_file = None
                    continue
                    
                if current_file not in files:
                    files[current_file] = []
            except IndexError:
                current_file = None
            continue
        
        if current_file and not line.startswith(('index ', '---', '+++')):
            files[current_file].append(line)
            
    for file_path, lines in files.items():
        files[file_path] = "\n".join(lines)
        
    return files

def load_rules():
    """
    Carga el único archivo de reglas consolidado.
    """
    rules = ""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    rule_filename = "rules.md"
    file_path = os.path.join(script_dir, 'rules', rule_filename)

    print(f"Cargando archivo de reglas: {file_path}", flush=True)

    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                rules = f.read()
        else:
            print(f"Error: No se encontró el archivo de regla '{rule_filename}'", flush=True)
            return ""
    except Exception as e:
        print(f"Error al cargar el archivo de reglas '{rule_filename}': {e}", flush=True)
        return ""
    return rules

def get_ai_review_for_file(file_path, file_diff, rules, stack, previous_comments, repo_logs, llm_model="gemini/gemini-3.0-pro-preview"):
    """
    Envía el diff de un archivo, las reglas y los comentarios previos al modelo de IA 
    para obtener un resumen de violaciones en formato JSON.
    """
    if not file_diff or not file_diff.strip():
        return None

    try:
        arch_context = ""
        if repo_logs:
            arch_context = f"""
        **Contexto de Arquitectura y Decisiones Técnicas (.logs):**
        Usa la siguiente información de la carpeta `.logs` del repositorio como contexto de las decisiones técnicas y de arquitectura que se deben respetar:
        ---
        {repo_logs}
        ---
        """

        prompt = f"""
        Actúa como un revisor de código de software experto y extremadamente conciso.

        **Contexto del Stack Tecnológico:**
        Este es un proyecto de tipo '{stack}'. Aplica las reglas correspondientes a este contexto.
        {arch_context}
        **Tarea Principal:**
        1.  **Validación de Comentarios Anteriores:** Revisa los `Comentarios Anteriores` y compáralos con el `Diff del Archivo`. Si una sugerencia anterior ya fue corregida en el diff actual, identifícala.
        2.  **Detección de Nuevas Violaciones:** Encuentra TODAS las violaciones de las `Reglas de Codificación` en las líneas que comienzan con `+`. Las líneas que no comienzan con `+` son solo para darte contexto y NO deben ser revisadas.
        3.  **Asignación de Criticidad:** Para cada nueva violación, asigna una puntuación de criticidad del 1 al 10, donde 10 es la más crítica.
        4.  **Idioma:** TODO TU FEEDBACK (`violation` y `suggestion`) debe estar redactado en Español Neutro fluido y profesional.
        5.  **Restricciones:** NO sugieras instalar nuevas dependencias o librerías.

        **Formato de Respuesta Estricto (JSON):**
        -   Responde con un objeto JSON que contenga dos claves principales: `"resolved_feedback"` y `"new_violations"`.
        -   `"resolved_feedback"`: Debe ser una lista de strings, donde cada string es una copia exacta de la sugerencia del comentario anterior que ya ha sido corregida.
        -   `"new_violations"`: Debe ser una lista de objetos, donde cada objeto representa una nueva violación encontrada.
        -   Cada objeto en `"new_violations"` debe tener las siguientes claves EXACTAS: `"violation"`, `"line"`, `"suggestion"`, `"criticism"`.
        -   El valor de `"criticism"` debe ser un número entero entre 1 y 10.
        -   Si no encuentras feedback resuelto o nuevas violaciones, las listas correspondientes deben estar vacías.
        -   La respuesta debe ser únicamente el objeto JSON, sin ningún texto adicional, explicaciones o formato markdown.

        **Ejemplo de formato de respuesta JSON:**
        ```json
        {{
            "resolved_feedback": [
                "Considera usar un nombre más descriptivo para la variable, como `max_retries`."
            ],
            "new_violations": [
                {{
                    "violation": "Uso de una función obsoleta",
                    "line": "old_function();",
                    "suggestion": "La función `old_function` está obsoleta. Utiliza `new_function` en su lugar.",
                    "criticism": 8
                }}
            ]
        }}
        ```

        **Comentarios Anteriores en este PR (para evitar duplicados y validar correcciones):**
        ---
        {previous_comments}
        ---

        **Reglas de Codificación para '{stack}':**
        ---
        {rules}
        ---

        **Archivo a Revisar:**
        Ruta: {file_path}

        **Diff del Archivo:**
        ---
        {file_diff}
        ---
        """
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = completion(
                    model=llm_model,
                    messages=[{"role": "user", "content": prompt}]
                )
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RateLimitError" in err_str or "Quota" in err_str:
                    if attempt < max_retries - 1:
                        sleep_time = 30 + (attempt * 30) # 30s, then 60s
                        print(f"⚠️ Rate Limit alcanzado para {file_path}. Esperando {sleep_time}s antes de reintentar...", flush=True)
                        time.sleep(sleep_time)
                        continue
                print(f"Error al conectar con LLM para {file_path}: {e}", flush=True)
                return None, None
        text_response = response.choices[0].message.content.strip()

        # Limpiar la respuesta para asegurarse de que sea un JSON válido
        if text_response.startswith("```json"):
            text_response = text_response[7:-3].strip()
        elif text_response.startswith("```"):
            text_response = text_response[3:-3].strip()

        try:
            review_data = json.loads(text_response)
        except json.JSONDecodeError:
            print(f"Error: La respuesta de la IA no es un JSON válido para el archivo {file_path}:\n{text_response}", flush=True)
            return None, None

        if not review_data:
            return None, None

        resolved_feedback = review_data.get("resolved_feedback", [])
        new_violations = review_data.get("new_violations", [])

        if not resolved_feedback and not new_violations:
            return None, None

        # Determinar el umbral de criticidad según la existencia de comentarios previos
        # Si previous_comments está vacío, es la primera ejecución: mostrar 9 y 10.
        # Si previous_comments tiene contenido, es una ejecución subsecuente: mostrar solo 10.
        
        has_previous_comments = bool(previous_comments and previous_comments.strip())
        
        filtered_violations = []
        for v in new_violations:
            criticism = v.get("criticism")
            if not isinstance(criticism, int):
                continue
                
            if has_previous_comments:
                # Ejecuciones subsecuentes: solo criticidad 9 o mayor
                if criticism >= 9:
                    filtered_violations.append(v)
            else:
                # Primera ejecución: criticidad 8 o mayor
                if criticism >= 8:
                    filtered_violations.append(v)

        if not resolved_feedback and not filtered_violations:
            return None, None
        
        return resolved_feedback, filtered_violations
        
    except Exception as e:
        print(f"Error al obtener la revisión de la IA para el archivo {file_path}: {e}", flush=True)
        return None, None

def get_pr_comments(repo_name, pr_number, github_token):
    """
    Obtiene los comentarios de un Pull Request, filtrando los del bot.
    """
    comments_url = f"https://api.github.com/repos/{repo_name}/issues/{pr_number}/comments"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        response = requests.get(comments_url, headers=headers)
        response.raise_for_status()
        comments = response.json()
        bot_comments = [
            comment['body'] for comment in comments 
            if "Voight-Kampff Code Review" in comment['body']
        ]
        return "\n".join(bot_comments)
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener los comentarios del PR: {e}", flush=True)
        return ""

def post_pr_review_comment(repo_name, pr_number, body, github_token):
    """
    Publica un comentario general en la conversación del Pull Request.
    """
    url = f"https://api.github.com/repos/{repo_name}/issues/{pr_number}/comments"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    data = {"body": body}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"¡Éxito! Se ha publicado el resumen de la revisión en el PR #{pr_number}.", flush=True)
    except requests.exceptions.RequestException as e:
        print(f"Error al publicar el comentario de revisión: {e}", flush=True)
        if e.response is not None:
            print(f"Respuesta de la API de GitHub: {e.response.json()}", flush=True)

def approve_pr(repo_name, pr_number, body, github_token):
    """
    Aprueba el Pull Request como reviewer oficial usando la API de GitHub.
    """
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}/reviews"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    data = {
        "body": body,
        "event": "APPROVE"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"✅ ¡Éxito! El PR #{pr_number} ha pasado la prueba Voight-Kampff.", flush=True)
    except requests.exceptions.RequestException as e:
        print(f"Error al aprobar el PR: {e}", flush=True)
        if e.response is not None:
            print(f"Respuesta de la API de GitHub: {e.response.json()}", flush=True)

def get_ai_review_for_all_files_pr(files_to_review, rules, stack, previous_comments, repo_logs, llm_model="gemini/gemini-1.5-pro-preview"):
    """
    Envía todos los diffs del PR, las reglas y los comentarios previos al modelo de IA en 1 sola petición,
    para obtener un resumen de violaciones en formato JSON.
    """
    if not files_to_review:
        return None, None

    valid_files = {path: diff for path, diff in files_to_review.items() if '+' in diff}
    if not valid_files:
        return None, None

    arch_context = ""
    if repo_logs:
        arch_context = f"""
        **Contexto de Arquitectura y Decisiones Técnicas (.logs):**
        Usa la siguiente información de la carpeta `.logs` del repositorio como contexto de las decisiones técnicas y de arquitectura que se deben respetar:
        ---
        {repo_logs}
        ---
        """

    combined_diffs = ""
    for file_path, file_diff in valid_files.items():
        combined_diffs += f"\n--- Archivo: {file_path} ---\n{file_diff}\n"

    prompt = f"""
    Actúa como un revisor de código de software experto y extremadamente conciso.

    **Contexto del Stack Tecnológico:**
    Este es un proyecto de tipo '{stack}'. Aplica las reglas correspondientes a este contexto.
    {arch_context}
    **Tarea Principal:**
    1.  **Validación de Comentarios Anteriores:** Revisa los `Comentarios Anteriores` y compáralos con todos los diffs. Si una sugerencia anterior ya fue corregida, identifícala.
    2.  **Detección de Nuevas Violaciones:** Encuentra TODAS las violaciones de las `Reglas de Codificación` en TODOS los archivos listados en `Archivos a Revisar`. Las líneas que no comienzan con `+` son solo contexto y NO deben ser reportadas como nuevas violaciones.
    3.  **Asignación de Criticidad:** Para cada nueva violación, asigna una puntuación de criticidad del 1 al 10, donde 10 es la más crítica.
    4.  **Idioma:** TODO TU FEEDBACK (`violation` y `suggestion`) debe estar redactado en Español Neutro fluido y profesional.
    5.  **Restricciones:** NO sugieras instalar nuevas dependencias o librerías.

    **Formato de Respuesta Estricto (JSON):**
    - Responde EXCLUSIVAMENTE con un objeto JSON (sin texto adicional) que contenga dos claves: `"resolved_feedback"` y `"new_violations"`.
    - `"resolved_feedback"`: Debe ser una lista de strings con las sugerencias anteriores corregidas.
    - `"new_violations"`: Lista de objetos representando nuevas violaciones.
    - Cada objeto en `"new_violations"` debe tener estas claves EXACTAS: `"file"`, `"violation"`, `"line"`, `"suggestion"`, `"criticism"`.
    - `"file"` debe ser la ruta exacta del archivo analizado, tal como se listó en las cabeceras (ej 'src/main.py').
    
    **Comentarios Anteriores en este PR:**
    ---
    {previous_comments}
    ---

    **Reglas de Codificación para '{stack}':**
    ---
    {rules}
    ---

    **Archivos a Revisar (Diffs combinados):**
    {combined_diffs}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = completion(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}]
            )
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RateLimitError" in err_str or "Quota" in err_str:
                if attempt < max_retries - 1:
                    sleep_time = 30 + (attempt * 30)
                    print(f"⚠️ Rate Limit alcanzado en MODO UNIFICADO. Esperando {sleep_time}s antes de reintentar...", flush=True)
                    time.sleep(sleep_time)
                    continue
            print(f"Error al conectar con LLM: {e}", flush=True)
            return None, None

    text_response = response.choices[0].message.content.strip()

    if text_response.startswith("```json"):
        text_response = text_response[7:-3].strip()
    elif text_response.startswith("```"):
        text_response = text_response[3:-3].strip()

    try:
        review_data = json.loads(text_response)
    except json.JSONDecodeError:
        print(f"Error: La respuesta de la IA no es un JSON válido:\n{text_response}", flush=True)
        return None, None

    resolved_feedback = review_data.get("resolved_feedback", [])
    new_violations = review_data.get("new_violations", [])

    has_previous_comments = bool(previous_comments and previous_comments.strip())
    
    grouped_violations = {}
    for v in new_violations:
        criticism = v.get("criticism")
        file_path = v.get("file")
        if not file_path or not isinstance(criticism, int):
            continue
            
        threshold = 9 if has_previous_comments else 8
        if criticism >= threshold:
            if file_path not in grouped_violations:
                grouped_violations[file_path] = []
            grouped_violations[file_path].append(v)

    return resolved_feedback, grouped_violations

def main():
    """
    Función principal que orquesta el proceso de revisión de código.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass

    llm_model = os.getenv("LLM_MODEL", "gemini/gemini-1.5-pro-preview")
    print(f"[DEBUG] MODELO SELECCIONADO: '{llm_model}'", flush=True)

    repo_name = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    github_token = os.getenv("GITHUB_TOKEN")

    if not all([repo_name, pr_number, github_token]):
        print("Error: Asegúrate de que las variables de entorno GITHUB_REPOSITORY, PR_NUMBER y GITHUB_TOKEN están definidas.", flush=True)
        return

    pr_number = int(pr_number)
    print(f"Iniciando revisión para el PR #{pr_number} en el repositorio {repo_name}...", flush=True)

    stack = detect_stack(repo_name, github_token)
    print(f"Stack detectado: {stack}", flush=True)

    rules = load_rules()
    if not rules:
        print("No se pudieron cargar las reglas. Abortando revisión.", flush=True)
        return

    # Obtener contexto adicional de arquitectura si existe
    repo_logs = get_repo_logs(repo_name, github_token)

    diff = get_pr_diff(repo_name, pr_number, github_token)
    if not diff:
        return

    files_to_review = parse_diff_by_file(diff)
    if not files_to_review:
        print("No se encontraron archivos modificados para revisar.", flush=True)
        return

    previous_comments = get_pr_comments(repo_name, pr_number, github_token)
    
    final_review_body = "## 🕵️‍♂️ R. Deckard - Voight-Kampff Code Review\n\n"
    all_resolved_feedback = []
    files_with_violations = {}
    total_added_lines = 0


    # Contar líneas añadidas para el cálculo de deuda técnica
    for file_path, file_diff in files_to_review.items():
        if '+' in file_diff:
            for line in file_diff.split('\n'):
                if line.startswith('+') and not line.startswith('+++'):
                    total_added_lines += 1

    single_request_mode = os.getenv("SINGLE_REQUEST_MODE", "true").lower() == "true"

    if single_request_mode:
        print("🚄 [Modo Ahorro] Consolidando PR en 1 sola llamada a la IA...", flush=True)
        try:
            resolved, new_violations = get_ai_review_for_all_files_pr(files_to_review, rules, stack, previous_comments, repo_logs, llm_model)
            if resolved:
                all_resolved_feedback.extend(resolved)
            if new_violations:
                files_with_violations = new_violations
                print(f"Detectadas violaciones en {len(files_with_violations)} archivos.", flush=True)
            else:
                print(f"✅ No se detectaron violaciones superando el umbral.", flush=True)
        except Exception as exc:
            print(f"Error crítico en modo unificado PR: {exc}", flush=True)
    else:
        max_workers = int(os.getenv("MAX_CONCURRENT_REVIEWS", "5"))
        print(f"⚡ [Modo Paralelo] Lanzando concurrentemente (hilos: {max_workers})...", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(get_ai_review_for_file, file_path, file_diff, rules, stack, previous_comments, repo_logs, llm_model): file_path
                for file_path, file_diff in files_to_review.items()
                if '+' in file_diff
            }

            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    resolved, new_violations = future.result()
                    
                    if resolved:
                        all_resolved_feedback.extend(resolved)
                    
                    if new_violations:
                        files_with_violations[file_path] = new_violations
                        print(f"Nuevas violaciones encontradas en {file_path}.", flush=True)
                    else:
                        print(f"✅ No se encontraron nuevas violaciones en {file_path}.", flush=True)

                except Exception as exc:
                    print(f"Error al procesar el archivo {file_path}: {exc}", flush=True)

    if all_resolved_feedback:
        final_review_body += "### ✅ Anomalías Retiradas\n\nHe verificado el sector. Los siguientes elementos anómalos han sido retirados con éxito:\n"
        for item in set(all_resolved_feedback): # Usar set para evitar duplicados
            final_review_body += f"- ~{item}~\n"
        final_review_body += "\n---\n\n"

    if files_with_violations:
        final_review_body += "### 🚨 Anomalías Detectadas\n\nHe aplicado la prueba al código. He detectado las siguientes anomalías que deben ser retiradas:\n\n"
        
        total_critical_violations = 0
        
        for file_path, violations in files_with_violations.items():
            final_review_body += f"### 📄 Archivo: `{file_path}`\n\n"
            for v in violations:
                total_critical_violations += 1
                final_review_body += f"**- Violación:** {v['violation']}\n"
                final_review_body += f"  - **Línea:** `{v['line']}`\n"
                final_review_body += f"  - **Sugerencia:** {v['suggestion']}\n"
                final_review_body += f"  - **Criticidad:** {v['criticism']}\n\n"
            final_review_body += "---\n\n"

        # Cálculo de Deuda Técnica
        technical_debt_percentage = 0
        if total_added_lines > 0:
            technical_debt_percentage = (total_critical_violations / total_added_lines) * 100
        
        final_review_body += f"### 📉 Deuda Técnica del PR: {technical_debt_percentage:.2f}%\n"
        final_review_body += "(Calculado como: Sugerencias Críticas / Líneas de Código Añadidas)\n\n"

        final_review_body += "\nEs hora de vivir. Arregla esto o tendré que retirarlo yo mismo."
        post_pr_review_comment(repo_name, pr_number, final_review_body, github_token)
    elif all_resolved_feedback:
        # Si solo hubo feedback corregido y no hay nuevas violaciones - APROBAR PR
        final_review_body += "\nHe visto cosas que no creerías... pero este código está limpio. Eres humano. Buen trabajo."
        approve_pr(repo_name, pr_number, final_review_body, github_token)
    else:
        # Si no hay ni feedback corregido ni nuevas violaciones - APROBAR PR
        print("\n🎉 Prueba superada. No hay violaciones. El código es humano.", flush=True)
        success_body = "## 🕵️‍♂️ R. Deckard - Voight-Kampff Code Review\n\nHe terminado la prueba. No he encontrado nada artificial aquí. El código está limpio. Buen trabajo."
        approve_pr(repo_name, pr_number, success_body, github_token)


    print("\nRevisión completada.", flush=True)

if __name__ == "__main__":
    main()
