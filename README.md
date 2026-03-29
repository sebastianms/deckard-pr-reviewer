# 🕵️‍♂️ Deckard PR Reviewer

Bienvenido a **Deckard PR Reviewer**, una herramienta automatizada (Agente de IA) que actúa como un Revisor de Pull Requests para tu repositorio en GitHub. Inspirado en el icónico protagonista de *Blade Runner*, este script aplica una versión técnica de la *prueba Voight-Kampff* a tu código para asegurarse de que no haya "réplicas" (código de baja calidad o que incumpla las reglas) infiltradas en el sistema.

El objetivo principal es mantener la base de código limpia imponiendo las reglas del **Clean Code** y garantizando la **Regla del Boy Scout** (siempre deja el código más limpio de lo que lo encontraste).

---

## ✨ Características

- **Análisis de Código Automatizado:** Extrae el diff de un PR y analiza las líneas modificadas (`+`).
- **Agnóstico al Modelo de IA:** Gracias a [LiteLLM](https://github.com/BerriAI/litellm), puedes utilizar el LLM que prefieras: OpenAI (GPT-4), Anthropic (Claude), Google (Gemini), Groq, modelos locales, etc.
- **Detector de Deuda Técnica:** Calcula la deuda técnica introducida en el PR en base a las "Anomalías Detectadas" (violaciones críticas de codificación) frente al volumen de líneas añadidas.
- **Validación Bidireccional:** Lee los comentarios previos del bot en el PR e identifica inteligentemente qué feedback ya ha sido corregido por el desarrollador en un nuevo commit („Anomalías Retiradas”).
- **Reglas Centralizadas:** Todas las reglas de Clean Code, buenas prácticas y arquitectura se evalúan utilizando el archivo de reglas global (`rules/rules.md`), así como integrando el registro de toma de decisiones (`.logs/` del proyecto, si existe).
- **Personalidad Noir:** Las respuestas directas en GitHub adoptan un tono detectivesco, cínico y conciso para evaluar a qué nivel el "código es humano".

---

## 🚀 Instalación y Requisitos

1. **Clonar el Repositorio:**
   ```bash
   git clone <URL_DEL_REPO> deckard
   cd deckard
   ```

2. **Instalar Dependencias:**
   Usamos un entorno de Python básico. Instala las dependencias necesarias:
   ```bash
   pip install -r requirements.txt
   ```
   *Entre las dependencias clave se encuentran `litellm` para la interacción unificada con la API del LLM, y `requests` para utilizar la API de GitHub.*

---

## ⚙️ Configuración (Variables de Entorno)

Antes de ejecutar los scripts, debes proveer ciertas variables de entorno imprescindibles (ya sea exportándolas en tu CI/CD o colocándolas en un archivo `.env` en tu entorno local).

| Variable | Descripción | Ejemplo |
|---|---|---|
| `GITHUB_REPOSITORY` | El nombre del repositorio objetivo en formato `owner/repo`. | `facebook/react` |
| `PR_NUMBER` | El formato numérico del Pull Request a analizar. | `42` |
| `GITHUB_TOKEN` | Token de Acceso Personal (PAT) de GitHub con lectura de código y escritura de comentarios/revisiones en el repo. | `ghp_xxxxx...` |
| `LLM_MODEL` | *(Opcional)* El proveedor y modelo que LiteLLM deberá inicializar. | `openai/gpt-4o` (Default: `gemini/gemini-1.5-pro-preview`) |
| `<PROVIDER>_API_KEY` | La API Key nativa correspondiente al modelo seleccionado en `LLM_MODEL`. | `OPENAI_API_KEY="sk-..."` o `GEMINI_API_KEY="AIza..."` |
| `SINGLE_REQUEST_MODE` | Agrupa todo el PR en 1 sola llamada para evitar Rate Limits de cuentas Free. | `true` o `false` |
| `MAX_CONCURRENT_REVIEWS`| Concurrencia de hilos si `SINGLE_REQUEST_MODE=false`. Para cuentas de pago. | `5` |

### Multi-LLM vía LiteLLM

Este script usa **LiteLLM**, lo que significa que el agente "Deckard" soporta casi cualquier modelo del mercado sin cambiar ni una línea de código. 

Solo necesitas proveer la API Key correspondiente al nombre del modelo que pongas. Ejemplos de configuración para tu archivo `.env`:

**Google Gemini**
```env
LLM_MODEL="gemini/gemini-1.5-pro-preview" # (o gemini-2.5-flash)
GEMINI_API_KEY="AIza..."
```

**OpenAI**
```env
LLM_MODEL="openai/gpt-4o"
OPENAI_API_KEY="sk-..."
```

**Anthropic**
```env
LLM_MODEL="anthropic/claude-3-5-sonnet-20240620"
ANTHROPIC_API_KEY="sk-ant-..."
```

---

## 🛠️ Uso

### Ejecución Local

Para correr el agente desde tu terminal (ideal para desarrollo y debugging), ahora cuentas con soporte nativo para archivos `.env`.

1. Duplica el archivo de ejemplo para empezar:
   ```bash
   cp .env.example .env
   ```
2. Rellena tus datos (`GEMINI_API_KEY`, cambiar a tu modelo preferido en `LLM_MODEL`, configurar tu `SINGLE_REQUEST_MODE`, etc.) dentro de `.env`. El script se encargará de levantar y priorizar todo automáticamente sin que dependas de `export` en bash.
3. Ejecuta a nuestro Blade Runner:

```bash
# Para simular revisión sobre un Pull Request remoto en GitHub
python review_pr.py 

# O para revisar tus archivos "staged" localmente antes de hacer commit
python review_local.py
```

### Integración Continua (GitHub Actions)

El escenario principal para este agente es ejecutarse automáticamente cuando se abre o se actualiza un Pull Request en un repositorio.

Crea un archivo de workflow en tu repositorio, por ejemplo: `.github/workflows/deckard_review.yml`:

```yaml
name: Deckard PR Reviewer

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  voight_kampff_test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout del código del revisor
        uses: actions/checkout@v3
        with:
          repository: 'tu-owner/deckard-reviewer-repo' # Dónde guardas a Deckard
          ref: 'main'

      - name: Configurar Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Instalar dependencias
        run: pip install -r requirements.txt

      - name: Ejecutar la revisión de código
        env:
          GITHUB_REPOSITORY: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          LLM_MODEL: "gemini/gemini-3.0-pro-preview"
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python review_pr.py
```

### 🔗 Uso como Pre-Commit Hook (Husky / Native)

Deckard también está preparado para interrogar a los replicantes localmente antes de que envíes el código al repositorio remoto. Para esto, se provee el script `review_local.py` que abortará el commit si encuentra "anomalías" críticas en tus archivos preparados (*staged files*: `git diff --cached`).

**Configuración con Husky (Node.js):**

Si tu proyecto usa Node.js (o quisieras forzar el uso de `npm` en un repositorio vacío), instala y configura Husky:
```bash
# Si tu proyecto aún no tiene un package.json, debes crearlo primero:
# npm init -y

npx husky-init
npm install
```
Luego edita tu archivo `.husky/pre-commit` para que llame a Deckard:
```bash
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

# Si decides no utilizar el archivo .env, puedes exportar manualmente variables aquí:
export LLM_MODEL="gemini/gemini-1.5-pro-preview"
export GEMINI_API_KEY="TuApiKey..."
export SINGLE_REQUEST_MODE="true"
export MAX_CONCURRENT_REVIEWS="1"

# Adapta la siguiente ruta según dónde tengas guardado el script "deckard"
python path/to/deckard/review_local.py
```

**Configuración con pre-commit (Sin Node.js / Python / Go):**

Si tu proyecto no utiliza Node.js, el estándar de la industria equivalente a Husky es **`pre-commit`**.
Instálalo con Python:
```bash
pip install pre-commit
```
Crea un archivo `.pre-commit-config.yaml` en la raíz de tu proyecto:
```yaml
repos:
  - repo: local
    hooks:
      - id: deckard-review
        name: Deckard PR Reviewer
        entry: python path/to/deckard/review_local.py
        language: system
        pass_filenames: false
```
Por último, inicializa los hooks en tu repositorio:
```bash
pre-commit install
```

**Configuración Nativa (Git Hooks):**

Si no usas herramientas externas, puedes crear un archivo ejecutable directamente en `.git/hooks/pre-commit` dentro de tu repositorio objetivo.
```bash
#!/bin/sh

# Solo necesitas apuntar Deckard al archivo correspondiente si usas .env
# O exportar aquí si tu servidor Git no permite archivos .env
# export LLM_MODEL="gemini/gemini-1.5-pro-preview"
# export GEMINI_API_KEY="TuApiKey..."

python path/to/deckard/review_local.py
```
*Atención: ¡Asegúrate de darle permisos de ejecución (`chmod +x .git/hooks/pre-commit`) al archivo o fallará silenciosamente!*

### 🤖 Integración con Claude Code

Deckard puede funcionar de forma nativa dentro de **Claude Code**, usando la propia sesión de Claude sin necesidad de API keys externas. Claude Code lee las reglas directamente y las aplica con su propia inteligencia.

**Incluye tres mecanismos:**

#### Subagente `@deckard` — Revisor de Diffs (Recomendado para pre-commit)

El subagente es un agente especializado con su **propia personalidad, contexto aislado y reglas preconfiguradas**. Analiza únicamente los cambios staged/unstaged (`git diff`), ideal para revisiones antes de commit.

**Invocación desde Claude Code:**
```
@deckard revisa mis cambios staged
```

**Invocación desde la CLI:**
```bash
claude --agent deckard "revisa los cambios staged"
```

**Instalación a nivel proyecto** (solo disponible en este repositorio):
```bash
# Ya incluido en .claude/agents/deckard.md
```

**Instalación global** (disponible en TODOS tus proyectos):
```bash
mkdir -p ~/.claude/agents
cp <DECKARD_PATH>/.claude/agents/deckard.md ~/.claude/agents/deckard.md
```

---

#### Subagente `@officer-k` — Inspector de Código Completo

**Officer K** (KD6-3.7) es la contraparte de Deckard. En lugar de analizar diffs, **inspecciona el código fuente completo del repositorio** (`git ls-files`). Ideal para auditorías periódicas o cuando incorporas un proyecto heredado y quieres conocer su estado real.

**Invocación desde Claude Code:**
```
@officer-k inspecciona el repositorio
```

**Invocación desde la CLI:**
```bash
claude --agent officer-k "inspecciona todo el código del repositorio"
```

**Slash command equivalente:**
```
/inspect
```

**Instalación a nivel proyecto** (solo disponible en este repositorio):
```bash
# Ya incluido en .claude/agents/officer-k.md
```

**Instalación global** (disponible en TODOS tus proyectos):
```bash
mkdir -p ~/.claude/agents
cp <DECKARD_PATH>/.claude/agents/officer-k.md ~/.claude/agents/officer-k.md
```

> **¿Cuándo usar cada uno?** Usa `@deckard` en tu flujo diario (pre-commit, PRs). Usa `@officer-k` cuando quieras una radiografía completa del repositorio: incorporación de proyectos legacy, auditorías de calidad, antes de una release importante.

---

#### Auto-Review (siempre activo)
El archivo `CLAUDE.md` instruye a Claude Code para que **siempre** revise su propio código contra las reglas de Deckard antes de hacer commit. No requiere intervención del usuario.

Para usarlo en otro proyecto, copia o haz un symlink del `CLAUDE.md` a la raíz de tu proyecto:
```bash
cp <DECKARD_PATH>/CLAUDE.md /path/to/tu-proyecto/CLAUDE.md
```

#### Slash Command (`/review`) — On Demand
Escribe `/review` en Claude Code para disparar una revisión manual de los cambios staged en cualquier momento.

Para usarlo en otro proyecto, copia la carpeta `.claude/commands/`:
```bash
mkdir -p /path/to/tu-proyecto/.claude/commands
cp <DECKARD_PATH>/.claude/commands/review.md /path/to/tu-proyecto/.claude/commands/review.md
```

#### Comparativa de mecanismos

| Aspecto | `@deckard` (Subagente) | `@officer-k` (Subagente) | `/review` (Command) | `/inspect` (Command) | `CLAUDE.md` (Auto) |
|---|---|---|---|---|---|
| **Invocación** | `@deckard` o `/review` | `@officer-k` o `/inspect` | `/review` en chat | `/inspect` en chat | Automático pre-commit |
| **Scope** | Solo diffs (staged/unstaged) | Código fuente completo | Solo diffs | Código fuente completo | Solo diffs |
| **Contexto** | Aislado y enfocado | Aislado y enfocado | Comparte la conversación | Comparte la conversación | Comparte la conversación |
| **Puede corregir código** | ✅ Sí | ✅ Sí | ✅ Sí | ✅ Sí | ✅ Sí |
| **Requiere API key externa** | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| **Disponible globalmente** | ✅ Con `~/.claude/agents/` | ✅ Con `~/.claude/agents/` | ❌ Solo por proyecto | ❌ Solo por proyecto | ❌ Solo por proyecto |

> **Nota:** Todos los mecanismos referencian las reglas en `<DECKARD_PATH>/rules/rules.md`. Si mueves el proyecto Deckard, actualiza las rutas.

---

## 📂 Archivos Importantes

- `review_pr.py`: Script principal para revisión de PRs en GitHub Actions. Extrae diffs remotos, llama al LLM vía LiteLLM y publica comentarios.
- `review_local.py`: Script para pre-commit hooks (Husky/Git nativo). Analiza `git diff --cached` localmente usando LiteLLM.
- `CLAUDE.md`: Regla de auto-revisión para Claude Code. Fuerza a Claude a revisar su código contra las reglas antes de commitear.
- `.claude/agents/deckard.md`: Subagente de Claude Code. Define a Deckard como agente autónomo invocable con `@deckard`. Analiza diffs.
- `.claude/agents/officer-k.md`: Subagente de Claude Code. Define a Officer K como agente de inspección completa invocable con `@officer-k`. Analiza todo el código fuente.
- `.claude/commands/review.md`: Slash command `/review` para Claude Code. Revisión on-demand de cambios staged.
- `.claude/commands/inspect.md`: Slash command `/inspect` para Claude Code. Inspección completa del repositorio.
- `rules/rules.md`: Catálogo completo de reglas de Clean Code (naming, funciones, SOLID, DRY, tests) aplicadas por todos los modos.
- `.logs/`: *(Del proyecto objetivo)* Contexto de arquitectura y decisiones técnicas que la IA incluye en el análisis.

---

> *"He visto código que uds no creerían. Variables sin tipo asaltando el stack de memoria... Funciones de quinientas líneas brillando en la oscuridad de producción. Todos esos commits se perderán en el tiempo, como advertencias en consola. Es hora de refactorizar."*
> 
> — **R. Deckard**
