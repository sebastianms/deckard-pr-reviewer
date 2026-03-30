import os
import time
from dataclasses import dataclass
from litellm import completion

RETRY_BASE_SLEEP_SECONDS = 30
MAX_API_RETRIES = 3
DIFF_IGNORE_PATTERNS = ['.lock', 'package.json', 'package-lock.json', '.gitignore']


@dataclass
class ReviewContext:
    rules: str
    stack: str
    repo_logs: str
    llm_model: str = "gemini/gemini-1.5-pro-preview"
    previous_comments: str = ""


def call_llm_with_retry(model: str, messages: list[dict], context_label: str = "") -> object:
    for attempt in range(MAX_API_RETRIES):
        try:
            return completion(model=model, messages=messages)
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "RateLimitError" in err_str or "Quota" in err_str
            if is_rate_limit and attempt < MAX_API_RETRIES - 1:
                sleep_time = RETRY_BASE_SLEEP_SECONDS + (attempt * RETRY_BASE_SLEEP_SECONDS)
                label = f" para {context_label}" if context_label else ""
                print(f"⚠️ Rate Limit alcanzado{label}. Esperando {sleep_time}s antes de reintentar...", flush=True)
                time.sleep(sleep_time)
                continue
            raise


def strip_json_fences(text: str) -> str:
    if text.startswith("```json"):
        return text[7:-3].strip()
    if text.startswith("```"):
        return text[3:-3].strip()
    return text


def parse_diff_by_file(diff_text: str, skip_deletions: bool = False) -> dict[str, str]:
    """Agrupa el contenido del diff por archivo, omitiendo archivos de prueba y configuración."""
    if not diff_text:
        return {}
    files: dict[str, list] = {}
    current_file = None

    for line in diff_text.split('\n'):
        if line.startswith('diff --git a/'):
            try:
                current_file = line.split(' b/')[1]
                if any(p in current_file for p in DIFF_IGNORE_PATTERNS) or \
                   '/tests/' in current_file or '.test.' in current_file:
                    current_file = None
                    continue
                if current_file not in files:
                    files[current_file] = []
            except IndexError:
                current_file = None
            continue

        if line.startswith('deleted file mode'):
            if current_file and current_file in files:
                del files[current_file]
            current_file = None
            continue

        if current_file and not line.startswith(('index ', '---', '+++')):
            # Evita falsos positivos por código eliminado
            if skip_deletions and line.startswith('-'):
                continue
            files[current_file].append(line)

    return {path: "\n".join(lines) for path, lines in files.items()}


def load_rules() -> str:
    """Carga el archivo de reglas consolidado desde rules/rules.md."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, 'rules', 'rules.md')
    try:
        if not os.path.exists(file_path):
            print("Error: No se encontró el archivo de regla 'rules.md'", flush=True)
            return ""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error al cargar el archivo de reglas 'rules.md': {e}", flush=True)
        return ""


def build_arch_context(repo_logs: str) -> str:
    if not repo_logs:
        return ""
    return f"""
        **Contexto de Arquitectura y Decisiones Técnicas (.logs):**
        Usa la siguiente información de la carpeta `.logs` del repositorio como contexto de las decisiones técnicas y de arquitectura que se deben respetar:
        ---
        {repo_logs}
        ---
        """
