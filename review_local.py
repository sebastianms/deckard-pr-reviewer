import os
import sys
import subprocess
import json
import concurrent.futures
import time
from litellm import completion

def get_file_content(path):
    """
    Obtiene el contenido de un archivo local.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error al leer el archivo {path}: {e}")
        return None

def get_local_logs():
    """
    Obtiene el contenido de los archivos en la carpeta .logs local para contexto de arquitectura.
    """
    logs_dir = ".logs"
    logs_content = []
    
    if os.path.exists(logs_dir) and os.path.isdir(logs_dir):
        for item in os.listdir(logs_dir):
            if item.endswith(('.md', '.txt')):
                file_path = os.path.join(logs_dir, item)
                content = get_file_content(file_path)
                if content:
                    logs_content.append(f"--- Archivo: {item} ---\n{content}\n")
    
        if logs_content:
            return "\n".join(logs_content)
    
    return ""

def detect_local_stack():
    """
    Detecta el stack tecnológico localmente listando los archivos en la raíz.
    """
    files = os.listdir(".")
    if 'requirements.txt' in files or 'pyproject.toml' in files or 'Pipfile' in files or 'setup.py' in files:
        return 'python'
    
    if 'package.json' in files:
        package_json_content = get_file_content('package.json')
        if package_json_content:
            try:
                dependencies = json.loads(package_json_content).get('dependencies', {})
                if 'react' in dependencies:
                    return 'frontend'
                if 'vue' in dependencies or 'nuxt' in dependencies:
                    return 'frontend'
                if '@nestjs/core' in dependencies:
                    return 'backend'
            except json.JSONDecodeError:
                pass
    
    return 'backend' # Default a backend si no se detecta nada

def get_staged_diff():
    """
    Obtiene el diff de los archivos preparados para commit (staged).
    """
    try:
        result = subprocess.run(['git', 'diff', '--cached'], capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error al obtener el git diff: {e}")
        return ""

def parse_diff_by_file(diff_text):
    """
    Analiza el diff y agrupa todo el contenido del diff por archivo, omitiendo archivos de prueba.
    """
    if not diff_text:
        return {}
    files = {}
    current_file = None
    ignore_patterns = ['.lock', 'package.json', 'package-lock.json', '.gitignore']
    
    for line in diff_text.split('\n'):
        if line.startswith('diff --git a/'):
            try:
                current_file = line.split(' b/')[1]
                
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
            # Omitimos explícitamente las líneas eliminadas del diff antes de mandarlo a la IA
            # porque en revisión de adiciones (staged local), el código muerto genera falsos positivos
            if line.startswith('-'):
                continue
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

def get_ai_review_for_file(file_path, file_diff, rules, stack, repo_logs, llm_model="gemini/gemini-1.5-pro-preview"):
    """
    Pide a la IA revisar las líneas del diff según las reglas establecidas.
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
        1.  **Detección de Anomalías:** Encuentra TODAS las violaciones de las `Reglas de Codificación` en las líneas que comienzan con `+`. Las líneas que no comienzan con `+` son solo contexto y NO deben ser reportadas bajo ninguna circunstancia como violaciones. Ignora las líneas eliminadas (`-`).
        2.  **Asignación de Criticidad:** Para cada nueva violación, asigna una puntuación de criticidad del 1 al 10, donde 10 es la más crítica.
        3.  **Idioma:** TODO TU FEEDBACK (`violation` y `suggestion`) debe estar redactado en Español Neutro fluido y profesional.
        4.  **Restricciones:** NO sugieras instalar nuevas dependencias o librerías.

        **Formato de Respuesta Estricto (JSON):**
        - Responde EXCLUSIVAMENTE con un objeto JSON (sin texto adicional) que contenga la clave `"new_violations"`.
        - `"new_violations"` debe ser una lista de objetos.
        - Cada objeto debe tener estas claves EXACTAS: `"violation"`, `"line"`, `"suggestion"`, `"criticism"`.
        - `"criticism"` debe ser numérico entre 1 y 10.
        Si no hay violaciones destacables, envía: {{ "new_violations": [] }}

        **Reglas de Codificación:**
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
                raise e
        text_response = response.choices[0].message.content.strip()

        if text_response.startswith("```json"):
            text_response = text_response[7:-3].strip()
        elif text_response.startswith("```"):
            text_response = text_response[3:-3].strip()

        try:
            review_data = json.loads(text_response)
        except json.JSONDecodeError:
            print(f"Error: La respuesta de la IA no es un JSON válido para el archivo {file_path}:\n{text_response}", flush=True)
            return None

        if not review_data:
            return None

        new_violations = review_data.get("new_violations", [])
        
        filtered_violations = []
        for v in new_violations:
            criticism = v.get("criticism")
            if not isinstance(criticism, int):
                continue
            
            # Umbral en entorno local (siendo un pre-commit, se recomienda atajar 8 o superior).
            if criticism >= 8:
                filtered_violations.append(v)

        if not filtered_violations:
            return []
        
        return filtered_violations

    except Exception as e:
        print(f"Error fallido al conectar con el servidor LLM para {file_path}: {e}", flush=True)
        return None

def get_ai_review_for_all_files(files_to_review, rules, stack, repo_logs, llm_model="gemini/gemini-1.5-pro-preview"):
    """
    Agrupa todos los archivos modificados en un solo prompt para evaluarlos en 1 sola llamada
    a la API. Minimiza problemas de Rate Limit en capas gratuitas.
    """
    if not files_to_review:
        return {}

    valid_files = {path: diff for path, diff in files_to_review.items() if '+' in diff}
    if not valid_files:
        return {}

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
    1.  **Detección de Anomalías:** Encuentra TODAS las violaciones de las `Reglas de Codificación` en TODOS los archivos listados. Las líneas que no comienzan con `+` son solo contexto y NO deben ser reportadas bajo ninguna circunstancia como nuevas violaciones. Ignora por completo las líneas eliminadas (`-`).
    2.  **Asignación de Criticidad:** Para cada nueva violación, asigna una puntuación de criticidad del 1 al 10, donde 10 es la más crítica.
    3.  **Idioma:** TODO TU FEEDBACK (`violation` y `suggestion`) debe estar redactado en Español Neutro fluido y profesional.
    4.  **Restricciones:** NO sugieras instalar nuevas dependencias o librerías.

    **Formato de Respuesta Estricto (JSON):**
    - Responde EXCLUSIVAMENTE con un objeto JSON (sin texto adicional) que contenga la clave `"new_violations"`.
    - `"new_violations"` debe ser una lista de objetos.
    - Cada objeto debe tener estas claves EXACTAS: `"file"`, `"violation"`, `"line"`, `"suggestion"`, `"criticism"`.
    - `"file"` debe ser la ruta exacta del archivo donde encontraste la violación, tal como aparece en las cabeceras (ej: 'src/main.py').
    - `"criticism"` debe ser numérico entre 1 y 10.
    Si no hay violaciones destacables, envía: {{ "new_violations": [] }}

    **Reglas de Codificación:**
    ---
    {rules}
    ---

    **Archivos a Revisar:**
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
            print(f"Error al conectar con el servidor LLM: {e}", flush=True)
            return None

    text_response = response.choices[0].message.content.strip()

    if text_response.startswith("```json"):
        text_response = text_response[7:-3].strip()
    elif text_response.startswith("```"):
        text_response = text_response[3:-3].strip()

    try:
        review_data = json.loads(text_response)
    except json.JSONDecodeError:
        print(f"Error: La respuesta de la IA no es un JSON válido en modo unificado:\n{text_response}", flush=True)
        return {}

    new_violations = review_data.get("new_violations", [])
    grouped_violations = {}
    
    for v in new_violations:
        criticism = v.get("criticism")
        file_path = v.get("file")
        
        if not file_path or not isinstance(criticism, int):
            continue
            
        if criticism >= 8:
            if file_path not in grouped_violations:
                grouped_violations[file_path] = []
            grouped_violations[file_path].append(v)
            
    return grouped_violations

def main():
    print("\n🕵️‍♂️ R. Deckard - Realizando prueba Voight-Kampff sobre el código preparado para el commit...", flush=True)
    
    # Cargar variables del archivo .env automáticamente, sobreescribiendo el sistema
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass # Si python-dotenv no está instalado, fall back al entorno del sistema
        
    llm_model = os.getenv("LLM_MODEL", "gemini/gemini-1.5-pro-preview")
    print(f"[DEBUG] MODELO SELECCIONADO: '{llm_model}'", flush=True)
    
    # Check git staged files
    diff = get_staged_diff()
    if not diff:
        print("🤷‍♂️ No tienes archivos en el staging area para commitear. Fin de la inspección.")
        sys.exit(0)

    files_to_review = parse_diff_by_file(diff)
    if not files_to_review.keys():
        print("📁 Los archivos modificados no caen bajo mi jurisdicción (ej. tests o ignorados). Eres humano. Buen viaje.")
        sys.exit(0)

    stack = detect_local_stack()
    rules = load_rules()
    if not rules:
        print("⚠️ Anomalía interna: No encontré mi manual de reglas (rules/rules.md). Déjalo pasar.")
        sys.exit(0)

    repo_logs = get_local_logs()
    
    files_with_violations = {}
    total_added_lines = 0

    # Contar líneas añadidas para el cálculo de deuda técnica
    for file_path, file_diff in files_to_review.items():
        if '+' in file_diff:
            for line in file_diff.split('\n'):
                if line.startswith('+') and not line.startswith('+++'):
                    total_added_lines += 1

    single_request_mode = os.getenv("SINGLE_REQUEST_MODE", "true").lower() == "true"

    api_failed = False

    if single_request_mode:
        print("🚄 [Modo Ahorro] Consolidando todos los archivos en 1 sola llamada a la IA...", flush=True)
        try:
            files_with_violations = get_ai_review_for_all_files(files_to_review, rules, stack, repo_logs, llm_model)
            if files_with_violations is None:
                api_failed = True
        except Exception as exc:
            print(f"Error crítico en modo unificado: {exc}", flush=True)
            api_failed = True
    else:
        max_workers = int(os.getenv("MAX_CONCURRENT_REVIEWS", "5"))
        print(f"⚡ [Modo Paralelo] Lanzando peticiones concurrentes (hilos: {max_workers})...", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(get_ai_review_for_file, file_path, file_diff, rules, stack, repo_logs, llm_model): file_path
                for file_path, file_diff in files_to_review.items()
                if '+' in file_diff
            }

            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    new_violations = future.result()
                    if new_violations is None:
                        api_failed = True
                    elif new_violations:
                        files_with_violations[file_path] = new_violations
                except Exception as exc:
                    print(f"Error crítico al inspeccionar el sector {file_path}: {exc}", flush=True)
                    api_failed = True

    if api_failed and not files_with_violations:
        print("\n⚠️ La IA (LiteLLM) colapsó o hubo un error de red. El commit continuará tu flujo de todas formas (Fail-Open) para no bloquearte.", flush=True)
        sys.exit(0)

    if files_with_violations:
        print("\n\n=== 🚨 ANOMALÍAS DETECTADAS ===")
        print("He aplicado la prueba al código y este no es humano. Se han detectado réplicas infiltradas:\n")
        
        for file_path, violations in files_with_violations.items():
            print(f"📄 Archivo: \033[93m{file_path}\033[0m")
            for v in violations:
                print(f"  ❌ \033[91mViolación:\033[0m {v['violation']}")
                print(f"     Línea que me delata: {v['line'].strip()}")
                print(f"     Sugerencia: {v['suggestion']}")
                print(f"     Criticidad: \033[91m[{v['criticism']}/10]\033[0m")
            print("-" * 50)

        print("\n💥 Es hora de vivir. Arregla estas incidencias o el commit será retirado.")
        sys.exit(1) # Rompe el commit hook
        
    else:
        print("\n✅ He visto cosas que no creerías... pero este código está limpio. Eres humano. Buen trabajo.")
        sys.exit(0) # Pasa el commit hook

if __name__ == "__main__":
    main()
