import os
import requests
import json
import concurrent.futures
from shared_utils import (
    ReviewContext, call_llm_with_retry, strip_json_fences,
    parse_diff_by_file, load_rules, build_arch_context,
)

FIRST_RUN_THRESHOLD = 8
SUBSEQUENT_RUN_THRESHOLD = 9


def get_file_content(repo_name: str, path: str, github_token: str) -> str | None:
    url = f"https://api.github.com/repos/{repo_name}/contents/{path}"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3.raw'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener el contenido del archivo {path}: {e}", flush=True)
        return None


def get_repo_logs(repo_name: str, github_token: str) -> str:
    url = f"https://api.github.com/repos/{repo_name}/contents/.logs"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            print("Carpeta .logs no encontrada. Se procederá sin contexto de arquitectura adicionales.", flush=True)
            return ""
        response.raise_for_status()
        logs_content = []
        for item in response.json():
            if item['type'] == 'file' and item['name'].endswith(('.md', '.txt')):
                content = get_file_content(repo_name, item['path'], github_token)
                if content:
                    logs_content.append(f"--- Archivo: {item['name']} ---\n{content}\n")
        return "\n".join(logs_content)
    except requests.exceptions.RequestException as e:
        print(f"Aviso: No se pudo obtener el contexto de .logs: {e}", flush=True)
        return ""


def detect_stack(repo_name: str, github_token: str) -> str:
    url = f"https://api.github.com/repos/{repo_name}/contents/"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        files = [item['name'] for item in response.json()]
        if 'requirements.txt' in files or 'pyproject.toml' in files or 'Pipfile' in files or 'setup.py' in files:
            return 'python'
        if 'package.json' in files:
            content = get_file_content(repo_name, 'package.json', github_token)
            if content:
                deps = json.loads(content).get('dependencies', {})
                if 'react' in deps:
                    return 'frontend'
                if 'vue' in deps or 'nuxt' in deps:
                    return 'frontend'
                if '@nestjs/core' in deps:
                    return 'backend'
        return 'backend'
    except requests.exceptions.RequestException as e:
        print(f"Error al detectar el stack del repositorio: {e}", flush=True)
        return 'backend'


def get_pr_diff(repo_name: str, pr_number: int, github_token: str) -> str | None:
    pr_url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
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


def get_pr_comments(repo_name: str, pr_number: int, github_token: str) -> str:
    url = f"https://api.github.com/repos/{repo_name}/issues/{pr_number}/comments"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        bot_comments = [
            c['body'] for c in response.json()
            if "Voight-Kampff Code Review" in c['body']
        ]
        return "\n".join(bot_comments)
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener los comentarios del PR: {e}", flush=True)
        return ""


def post_pr_review_comment(repo_name: str, pr_number: int, body: str, github_token: str) -> None:
    url = f"https://api.github.com/repos/{repo_name}/issues/{pr_number}/comments"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        response = requests.post(url, headers=headers, json={"body": body})
        response.raise_for_status()
        print(f"¡Éxito! Se ha publicado el resumen de la revisión en el PR #{pr_number}.", flush=True)
    except requests.exceptions.RequestException as e:
        print(f"Error al publicar el comentario de revisión: {e}", flush=True)
        if e.response is not None:
            print(f"Respuesta de la API de GitHub: {e.response.json()}", flush=True)


def approve_pr(repo_name: str, pr_number: int, body: str, github_token: str) -> None:
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}/reviews"
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        response = requests.post(url, headers=headers, json={"body": body, "event": "APPROVE"})
        response.raise_for_status()
        print(f"✅ ¡Éxito! El PR #{pr_number} ha pasado la prueba Voight-Kampff.", flush=True)
    except requests.exceptions.RequestException as e:
        print(f"Error al aprobar el PR: {e}", flush=True)
        if e.response is not None:
            print(f"Respuesta de la API de GitHub: {e.response.json()}", flush=True)


def _build_single_file_prompt(file_path: str, file_diff: str, ctx: ReviewContext) -> str:
    arch_context = build_arch_context(ctx.repo_logs)
    return f"""
        Actúa como un revisor de código de software experto y extremadamente conciso.

        **Contexto del Stack Tecnológico:**
        Este es un proyecto de tipo '{ctx.stack}'. Aplica las reglas correspondientes a este contexto.
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
        {ctx.previous_comments}
        ---

        **Reglas de Codificación para '{ctx.stack}':**
        ---
        {ctx.rules}
        ---

        **Archivo a Revisar:**
        Ruta: {file_path}

        **Diff del Archivo:**
        ---
        {file_diff}
        ---
        """


def _build_all_files_prompt(combined_diffs: str, ctx: ReviewContext) -> str:
    arch_context = build_arch_context(ctx.repo_logs)
    return f"""
    Actúa como un revisor de código de software experto y extremadamente conciso.

    **Contexto del Stack Tecnológico:**
    Este es un proyecto de tipo '{ctx.stack}'. Aplica las reglas correspondientes a este contexto.
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
    {ctx.previous_comments}
    ---

    **Reglas de Codificación para '{ctx.stack}':**
    ---
    {ctx.rules}
    ---

    **Archivos a Revisar (Diffs combinados):**
    {combined_diffs}
    """


def _parse_pr_response(text: str, label: str) -> tuple[list, list] | tuple[None, None]:
    cleaned = strip_json_fences(text)
    try:
        review_data = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"Error: La respuesta de la IA no es un JSON válido para {label}:\n{cleaned}", flush=True)
        return None, None
    if not review_data:
        return None, None
    return review_data.get("resolved_feedback", []), review_data.get("new_violations", [])


def _filter_violations(violations: list[dict], has_previous_comments: bool) -> list[dict]:
    threshold = SUBSEQUENT_RUN_THRESHOLD if has_previous_comments else FIRST_RUN_THRESHOLD
    return [v for v in violations if isinstance(v.get("criticism"), int) and v["criticism"] >= threshold]


def get_ai_review_for_file(file_path: str, file_diff: str, ctx: ReviewContext) -> tuple[list, list] | tuple[None, None]:
    if not file_diff or not file_diff.strip():
        return None, None
    try:
        prompt = _build_single_file_prompt(file_path, file_diff, ctx)
        response = call_llm_with_retry(ctx.llm_model, [{"role": "user", "content": prompt}], file_path)
        resolved, violations = _parse_pr_response(response.choices[0].message.content.strip(), file_path)
        if resolved is None:
            return None, None
        has_previous = bool(ctx.previous_comments and ctx.previous_comments.strip())
        filtered = _filter_violations(violations or [], has_previous)
        if not resolved and not filtered:
            return None, None
        return resolved, filtered
    except Exception as e:
        print(f"Error al obtener la revisión de la IA para el archivo {file_path}: {e}", flush=True)
        return None, None


def get_ai_review_for_all_files_pr(files_to_review: dict[str, str], ctx: ReviewContext) -> tuple[list, dict] | tuple[None, None]:
    valid_files = {path: diff for path, diff in files_to_review.items() if '+' in diff}
    if not valid_files:
        return None, None

    combined_diffs = "".join(f"\n--- Archivo: {p} ---\n{d}\n" for p, d in valid_files.items())
    prompt = _build_all_files_prompt(combined_diffs, ctx)

    try:
        response = call_llm_with_retry(ctx.llm_model, [{"role": "user", "content": prompt}], "MODO UNIFICADO")
    except Exception as e:
        print(f"Error al conectar con LLM: {e}", flush=True)
        return None, None

    resolved, violations = _parse_pr_response(response.choices[0].message.content.strip(), "modo unificado PR")
    if resolved is None:
        return None, None

    has_previous = bool(ctx.previous_comments and ctx.previous_comments.strip())
    grouped: dict[str, list] = {}
    for v in _filter_violations(violations or [], has_previous):
        fp = v.get("file")
        if fp:
            grouped.setdefault(fp, []).append(v)

    return resolved, grouped


def _load_config() -> tuple[str, int, str, str] | None:
    repo_name = os.getenv("GITHUB_REPOSITORY")
    pr_number_str = os.getenv("PR_NUMBER")
    github_token = os.getenv("GITHUB_TOKEN")
    llm_model = os.getenv("LLM_MODEL", "gemini/gemini-1.5-pro-preview")

    if not all([repo_name, pr_number_str, github_token]):
        print("Error: Asegúrate de que las variables de entorno GITHUB_REPOSITORY, PR_NUMBER y GITHUB_TOKEN están definidas.", flush=True)
        return None
    return repo_name, int(pr_number_str), github_token, llm_model


def _count_added_lines(files_to_review: dict[str, str]) -> int:
    return sum(
        1 for diff in files_to_review.values()
        for line in diff.split('\n')
        if line.startswith('+') and not line.startswith('+++')
    )


def _build_review_body(files_with_violations: dict[str, list], all_resolved_feedback: list, total_added_lines: int) -> str:
    body = "## 🕵️‍♂️ R. Deckard - Voight-Kampff Code Review\n\n"

    if all_resolved_feedback:
        body += "### ✅ Anomalías Retiradas\n\nHe verificado el sector. Los siguientes elementos anómalos han sido retirados con éxito:\n"
        for item in set(all_resolved_feedback):
            body += f"- ~{item}~\n"
        body += "\n---\n\n"

    if files_with_violations:
        body += "### 🚨 Anomalías Detectadas\n\nHe aplicado la prueba al código. He detectado las siguientes anomalías que deben ser retiradas:\n\n"
        total_critical = 0
        for fp, violations in files_with_violations.items():
            body += f"### 📄 Archivo: `{fp}`\n\n"
            for v in violations:
                total_critical += 1
                body += f"**- Violación:** {v['violation']}\n"
                body += f"  - **Línea:** `{v['line']}`\n"
                body += f"  - **Sugerencia:** {v['suggestion']}\n"
                body += f"  - **Criticidad:** {v['criticism']}\n\n"
            body += "---\n\n"

        debt_pct = (total_critical / total_added_lines * 100) if total_added_lines > 0 else 0
        body += f"### 📉 Deuda Técnica del PR: {debt_pct:.2f}%\n"
        body += "(Calculado como: Sugerencias Críticas / Líneas de Código Añadidas)\n\n"
        body += "\nEs hora de vivir. Arregla esto o tendré que retirarlo yo mismo."

    return body


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass

    config = _load_config()
    if not config:
        return
    repo_name, pr_number, github_token, llm_model = config

    print(f"[DEBUG] MODELO SELECCIONADO: '{llm_model}'", flush=True)
    print(f"Iniciando revisión para el PR #{pr_number} en el repositorio {repo_name}...", flush=True)

    stack = detect_stack(repo_name, github_token)
    print(f"Stack detectado: {stack}", flush=True)

    rules = load_rules()
    if not rules:
        print("No se pudieron cargar las reglas. Abortando revisión.", flush=True)
        return

    repo_logs = get_repo_logs(repo_name, github_token)
    diff = get_pr_diff(repo_name, pr_number, github_token)
    if not diff:
        return

    files_to_review = parse_diff_by_file(diff)
    if not files_to_review:
        print("No se encontraron archivos modificados para revisar.", flush=True)
        return

    previous_comments = get_pr_comments(repo_name, pr_number, github_token)
    ctx = ReviewContext(
        rules=rules,
        stack=stack,
        repo_logs=repo_logs,
        llm_model=llm_model,
        previous_comments=previous_comments,
    )

    total_added_lines = _count_added_lines(files_to_review)
    all_resolved_feedback: list = []
    files_with_violations: dict[str, list] = {}

    single_request_mode = os.getenv("SINGLE_REQUEST_MODE", "true").lower() == "true"

    if single_request_mode:
        print("🚄 [Modo Ahorro] Consolidando PR en 1 sola llamada a la IA...", flush=True)
        try:
            resolved, violations = get_ai_review_for_all_files_pr(files_to_review, ctx)
            if resolved:
                all_resolved_feedback.extend(resolved)
            if violations:
                files_with_violations = violations
                print(f"Detectadas violaciones en {len(files_with_violations)} archivos.", flush=True)
            else:
                print("✅ No se detectaron violaciones superando el umbral.", flush=True)
        except Exception as exc:
            print(f"Error crítico en modo unificado PR: {exc}", flush=True)
    else:
        max_workers = int(os.getenv("MAX_CONCURRENT_REVIEWS", "5"))
        print(f"⚡ [Modo Paralelo] Lanzando concurrentemente (hilos: {max_workers})...", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(get_ai_review_for_file, fp, fd, ctx): fp
                for fp, fd in files_to_review.items()
                if '+' in fd
            }
            for future in concurrent.futures.as_completed(future_to_file):
                fp = future_to_file[future]
                try:
                    resolved, violations = future.result()
                    if resolved:
                        all_resolved_feedback.extend(resolved)
                    if violations:
                        files_with_violations[fp] = violations
                        print(f"Nuevas violaciones encontradas en {fp}.", flush=True)
                    else:
                        print(f"✅ No se encontraron nuevas violaciones en {fp}.", flush=True)
                except Exception as exc:
                    print(f"Error al procesar el archivo {fp}: {exc}", flush=True)

    if files_with_violations:
        review_body = _build_review_body(files_with_violations, all_resolved_feedback, total_added_lines)
        post_pr_review_comment(repo_name, pr_number, review_body, github_token)
    elif all_resolved_feedback:
        review_body = _build_review_body({}, all_resolved_feedback, total_added_lines)
        review_body += "\nHe visto cosas que no creerías... pero este código está limpio. Eres humano. Buen trabajo."
        approve_pr(repo_name, pr_number, review_body, github_token)
    else:
        print("\n🎉 Prueba superada. No hay violaciones. El código es humano.", flush=True)
        success_body = "## 🕵️‍♂️ R. Deckard - Voight-Kampff Code Review\n\nHe terminado la prueba. No he encontrado nada artificial aquí. El código está limpio. Buen trabajo."
        approve_pr(repo_name, pr_number, success_body, github_token)

    print("\nRevisión completada.", flush=True)


if __name__ == "__main__":
    main()
