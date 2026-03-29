import os
import sys
import subprocess
import json
import concurrent.futures
from shared_utils import (
    ReviewContext, call_llm_with_retry, strip_json_fences,
    parse_diff_by_file, load_rules, build_arch_context,
    MAX_API_RETRIES,
)

LOCAL_CRITICISM_THRESHOLD = 8


def get_file_content(path: str) -> str | None:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error al leer el archivo {path}: {e}")
        return None


def get_local_logs() -> str:
    logs_dir = ".logs"
    logs_content = []
    if os.path.exists(logs_dir) and os.path.isdir(logs_dir):
        for item in os.listdir(logs_dir):
            if item.endswith(('.md', '.txt')):
                content = get_file_content(os.path.join(logs_dir, item))
                if content:
                    logs_content.append(f"--- Archivo: {item} ---\n{content}\n")
        if logs_content:
            return "\n".join(logs_content)
    return ""


def detect_local_stack() -> str:
    files = os.listdir(".")
    if 'requirements.txt' in files or 'pyproject.toml' in files or 'Pipfile' in files or 'setup.py' in files:
        return 'python'
    if 'package.json' in files:
        content = get_file_content('package.json')
        if content:
            try:
                deps = json.loads(content).get('dependencies', {})
                if 'react' in deps:
                    return 'frontend'
                if 'vue' in deps or 'nuxt' in deps:
                    return 'frontend'
                if '@nestjs/core' in deps:
                    return 'backend'
            except json.JSONDecodeError:
                pass
    return 'backend'


def get_staged_diff() -> str:
    try:
        result = subprocess.run(['git', 'diff', '--cached'], capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error al obtener el git diff: {e}")
        return ""


def _build_single_file_prompt(file_path: str, file_diff: str, ctx: ReviewContext) -> str:
    arch_context = build_arch_context(ctx.repo_logs)
    return f"""
        Actúa como un revisor de código de software experto y extremadamente conciso.

        **Contexto del Stack Tecnológico:**
        Este es un proyecto de tipo '{ctx.stack}'. Aplica las reglas correspondientes a este contexto.
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
    {ctx.rules}
    ---

    **Archivos a Revisar:**
    {combined_diffs}
    """


def _parse_violations(text: str, label: str) -> list[dict] | None:
    cleaned = strip_json_fences(text)
    try:
        review_data = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"Error: La respuesta de la IA no es un JSON válido para {label}:\n{cleaned}", flush=True)
        return None
    return review_data.get("new_violations", []) if review_data else None


def get_ai_review_for_file(file_path: str, file_diff: str, ctx: ReviewContext) -> list[dict] | None:
    if not file_diff or not file_diff.strip():
        return None
    try:
        prompt = _build_single_file_prompt(file_path, file_diff, ctx)
        response = call_llm_with_retry(ctx.llm_model, [{"role": "user", "content": prompt}], file_path)
        violations = _parse_violations(response.choices[0].message.content.strip(), file_path)
        if violations is None:
            return None
        return [v for v in violations if isinstance(v.get("criticism"), int) and v["criticism"] >= LOCAL_CRITICISM_THRESHOLD]
    except Exception as e:
        print(f"Error fallido al conectar con el servidor LLM para {file_path}: {e}", flush=True)
        return None


def get_ai_review_for_all_files(files_to_review: dict[str, str], ctx: ReviewContext) -> dict[str, list] | None:
    valid_files = {path: diff for path, diff in files_to_review.items() if '+' in diff}
    if not valid_files:
        return {}

    combined_diffs = "".join(f"\n--- Archivo: {p} ---\n{d}\n" for p, d in valid_files.items())
    prompt = _build_all_files_prompt(combined_diffs, ctx)

    try:
        response = call_llm_with_retry(ctx.llm_model, [{"role": "user", "content": prompt}], "MODO UNIFICADO")
    except Exception as e:
        print(f"Error al conectar con el servidor LLM: {e}", flush=True)
        return None

    violations = _parse_violations(response.choices[0].message.content.strip(), "modo unificado")
    if violations is None:
        return {}

    grouped: dict[str, list] = {}
    for v in violations:
        criticism = v.get("criticism")
        fp = v.get("file")
        if not fp or not isinstance(criticism, int):
            continue
        if criticism >= LOCAL_CRITICISM_THRESHOLD:
            grouped.setdefault(fp, []).append(v)
    return grouped


def main() -> None:
    print("\n🕵️‍♂️ R. Deckard - Realizando prueba Voight-Kampff sobre el código preparado para el commit...", flush=True)

    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass

    llm_model = os.getenv("LLM_MODEL", "gemini/gemini-1.5-pro-preview")
    print(f"[DEBUG] MODELO SELECCIONADO: '{llm_model}'", flush=True)

    diff = get_staged_diff()
    if not diff:
        print("🤷‍♂️ No tienes archivos en el staging area para commitear. Fin de la inspección.")
        sys.exit(0)

    files_to_review = parse_diff_by_file(diff, skip_deletions=True)
    if not files_to_review:
        print("📁 Los archivos modificados no caen bajo mi jurisdicción (ej. tests o ignorados). Eres humano. Buen viaje.")
        sys.exit(0)

    stack = detect_local_stack()
    rules = load_rules()
    if not rules:
        print("⚠️ Anomalía interna: No encontré mi manual de reglas (rules/rules.md). Déjalo pasar.")
        sys.exit(0)

    repo_logs = get_local_logs()
    ctx = ReviewContext(rules=rules, stack=stack, repo_logs=repo_logs, llm_model=llm_model)

    total_added_lines = sum(
        1 for diff in files_to_review.values()
        for line in diff.split('\n')
        if line.startswith('+') and not line.startswith('+++')
    )

    single_request_mode = os.getenv("SINGLE_REQUEST_MODE", "true").lower() == "true"
    api_failed = False
    files_with_violations: dict[str, list] = {}

    if single_request_mode:
        print("🚄 [Modo Ahorro] Consolidando todos los archivos en 1 sola llamada a la IA...", flush=True)
        try:
            result = get_ai_review_for_all_files(files_to_review, ctx)
            if result is None:
                api_failed = True
            else:
                files_with_violations = result
        except Exception as exc:
            print(f"Error crítico en modo unificado: {exc}", flush=True)
            api_failed = True
    else:
        max_workers = int(os.getenv("MAX_CONCURRENT_REVIEWS", "5"))
        print(f"⚡ [Modo Paralelo] Lanzando peticiones concurrentes (hilos: {max_workers})...", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(get_ai_review_for_file, fp, fd, ctx): fp
                for fp, fd in files_to_review.items()
                if '+' in fd
            }
            for future in concurrent.futures.as_completed(future_to_file):
                fp = future_to_file[future]
                try:
                    violations = future.result()
                    if violations is None:
                        api_failed = True
                    elif violations:
                        files_with_violations[fp] = violations
                except Exception as exc:
                    print(f"Error crítico al inspeccionar el sector {fp}: {exc}", flush=True)
                    api_failed = True

    if api_failed and not files_with_violations:
        print("\n⚠️ La IA (LiteLLM) colapsó o hubo un error de red. El commit continuará tu flujo de todas formas (Fail-Open) para no bloquearte.", flush=True)
        sys.exit(0)

    if files_with_violations:
        print("\n\n=== 🚨 ANOMALÍAS DETECTADAS ===")
        print("He aplicado la prueba al código y este no es humano. Se han detectado réplicas infiltradas:\n")
        for fp, violations in files_with_violations.items():
            print(f"📄 Archivo: \033[93m{fp}\033[0m")
            for v in violations:
                print(f"  ❌ \033[91mViolación:\033[0m {v['violation']}")
                print(f"     Línea que me delata: {v['line'].strip()}")
                print(f"     Sugerencia: {v['suggestion']}")
                print(f"     Criticidad: \033[91m[{v['criticism']}/10]\033[0m")
            print("-" * 50)
        print("\n💥 Es hora de vivir. Arregla estas incidencias o el commit será retirado.")
        sys.exit(1)
    else:
        print("\n✅ He visto cosas que no creerías... pero este código está limpio. Eres humano. Buen trabajo.")
        sys.exit(0)


if __name__ == "__main__":
    main()
