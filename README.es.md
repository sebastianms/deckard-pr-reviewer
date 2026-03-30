# 🕵️‍♂️ Deckard PR Reviewer

> *Revisor de código con IA que aplica una **prueba Voight-Kampff** a tus pull requests — porque los replicantes (código sucio) no tienen lugar en producción.*

**Deckard PR Reviewer** es un agente de IA automatizado que revisa Pull Requests de GitHub y cambios staged locales, aplicando las reglas de **Clean Code** y la **Regla del Boy Scout** (siempre deja el código más limpio de lo que lo encontraste).

---

## ✨ Características

- **Análisis de Código Automatizado:** Extrae el diff de un PR y analiza las líneas modificadas (`+`).
- **Agnóstico al Modelo de IA:** Gracias a [LiteLLM](https://github.com/BerriAI/litellm), puedes utilizar el LLM que prefieras: OpenAI (GPT-4), Anthropic (Claude), Google (Gemini), Groq, modelos locales, etc.
- **Detector de Deuda Técnica:** Calcula la deuda técnica introducida en el PR en base a las anomalías detectadas frente al volumen de líneas añadidas.
- **Validación Bidireccional:** Lee los comentarios previos del bot en el PR e identifica inteligentemente qué feedback ya ha sido corregido en un nuevo commit ("Anomalías Retiradas").
- **Reglas Centralizadas:** Todas las reglas de Clean Code, buenas prácticas y arquitectura se evalúan usando el archivo de reglas global (`rules/rules.md`), enriquecido opcionalmente con el registro de decisiones del proyecto (`.logs/`).
- **Personalidad Noir:** Las respuestas en GitHub adoptan un tono detectivesco, cínico y conciso para evaluar si "el código es humano".

---

## 🚀 Instalación y Requisitos

1. **Clonar el repositorio:**
   ```bash
   git clone <URL_DEL_REPO> deckard
   cd deckard
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```
   *Dependencias clave: `litellm` para la interacción unificada con la API del LLM, y `requests` para la API de GitHub.*

---

## ⚙️ Configuración (Variables de Entorno)

Provee las siguientes variables de entorno antes de ejecutar (expórtalas en tu CI/CD o colócalas en un archivo `.env` local).

| Variable | Descripción | Ejemplo |
|---|---|---|
| `GITHUB_REPOSITORY` | El repositorio objetivo en formato `owner/repo`. | `facebook/react` |
| `PR_NUMBER` | El número del Pull Request a analizar. | `42` |
| `GITHUB_TOKEN` | Token de GitHub con lectura de código y escritura de comentarios/revisiones. | `ghp_xxxxx...` |
| `LLM_MODEL` | *(Opcional)* Proveedor y modelo que LiteLLM inicializará. | `openai/gpt-4o` (Default: `gemini/gemini-1.5-pro-preview`) |
| `<PROVIDER>_API_KEY` | API Key correspondiente al modelo seleccionado. | `OPENAI_API_KEY="sk-..."` o `GEMINI_API_KEY="AIza..."` |
| `SINGLE_REQUEST_MODE` | Agrupa todo el PR en 1 sola llamada para evitar rate limits en cuentas Free. | `true` o `false` |
| `MAX_CONCURRENT_REVIEWS` | Concurrencia de hilos si `SINGLE_REQUEST_MODE=false`. Para cuentas de pago. | `5` |

### Multi-LLM vía LiteLLM

Deckard soporta casi cualquier modelo del mercado sin cambiar ni una línea de código. Solo necesitas proveer la API Key correspondiente.

**Ejemplos de `.env`:**

**Google Gemini**
```env
LLM_MODEL="gemini/gemini-1.5-pro-preview"
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

Para correr el agente desde tu terminal (ideal para desarrollo y debugging). Soporte nativo para archivos `.env` incluido.

1. Duplica el archivo de ejemplo:
   ```bash
   cp .env.example .env
   ```
2. Rellena tus datos (`GEMINI_API_KEY`, `LLM_MODEL`, `SINGLE_REQUEST_MODE`, etc.).
3. Ejecuta a Deckard:

```bash
# Revisar un Pull Request remoto en GitHub
python review_pr.py

# O revisar tus archivos staged localmente antes de hacer commit
python review_local.py
```

### Integración Continua (GitHub Actions)

El escenario principal es ejecutar Deckard automáticamente cuando se abre o actualiza un PR.

Crea un workflow en tu repositorio, por ejemplo: `.github/workflows/deckard_review.yml`:

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
          repository: 'tu-owner/deckard-reviewer-repo'
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

### 🔗 Pre-Commit Hook (Husky / Nativo)

Deckard puede interrogar a los replicantes localmente antes de enviar el código al remoto. El script `review_local.py` abortará el commit si encuentra "anomalías" críticas en tus archivos staged (`git diff --cached`).

**Husky (Node.js):**

```bash
npx husky-init
npm install
```

Edita `.husky/pre-commit`:
```bash
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

export LLM_MODEL="gemini/gemini-1.5-pro-preview"
export GEMINI_API_KEY="TuApiKey..."
export SINGLE_REQUEST_MODE="true"
export MAX_CONCURRENT_REVIEWS="1"

python path/to/deckard/review_local.py
```

**pre-commit (Python / Sin Node.js):**

```bash
pip install pre-commit
```

Crea `.pre-commit-config.yaml`:
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

```bash
pre-commit install
```

**Git Hook Nativo:**

Crea `.git/hooks/pre-commit` en tu repositorio objetivo:
```bash
#!/bin/sh
python path/to/deckard/review_local.py
```
*Recuerda darle permisos de ejecución: `chmod +x .git/hooks/pre-commit`*

---

### 🤖 Integración con Claude Code

Deckard funciona de forma nativa dentro de **Claude Code**, usando la propia sesión de Claude — sin API keys externas.

**Tres mecanismos disponibles:**

#### Subagente `@deckard` — Revisor de Diffs (Recomendado para pre-commit)

Agente especializado con contexto aislado y reglas preconfiguradas. Analiza solo los cambios staged/unstaged (`git diff`).

```
@deckard revisa mis cambios staged
```
```bash
claude --agent deckard "revisa los cambios staged"
```

**Instalación global** (disponible en TODOS tus proyectos):
```bash
mkdir -p ~/.claude/agents
cp <DECKARD_PATH>/.claude/agents/deckard.md ~/.claude/agents/deckard.md
```

---

#### Subagente `@officer-k` — Inspector de Código Completo

**Officer K** (KD6-3.7) es la contraparte de Deckard. En lugar de diffs, **inspecciona el código fuente completo del repositorio** (`git ls-files`). Ideal para auditorías periódicas o proyectos heredados.

```
@officer-k inspecciona el repositorio
```
```bash
claude --agent officer-k "inspecciona todo el código del repositorio"
```
```
/inspect
```

**Instalación global:**
```bash
mkdir -p ~/.claude/agents
cp <DECKARD_PATH>/.claude/agents/officer-k.md ~/.claude/agents/officer-k.md
```

> **¿Cuándo usar cada uno?** Usa `@deckard` en tu flujo diario (pre-commit, PRs). Usa `@officer-k` para una radiografía completa: incorporación de proyectos legacy, auditorías de calidad, pre-release.

---

#### Auto-Review (siempre activo)
El archivo `CLAUDE.md` instruye a Claude Code para que **siempre** revise su propio código contra las reglas de Deckard antes de hacer commit. No requiere intervención del usuario.

```bash
cp <DECKARD_PATH>/CLAUDE.md /path/to/tu-proyecto/CLAUDE.md
```

#### Slash Command (`/review`) — On Demand
Escribe `/review` en Claude Code para disparar una revisión manual de los cambios staged en cualquier momento.

```bash
mkdir -p /path/to/tu-proyecto/.claude/commands
cp <DECKARD_PATH>/.claude/commands/review.md /path/to/tu-proyecto/.claude/commands/review.md
```

#### Comparativa de mecanismos

| Aspecto | `@deckard` (Agente) | `@officer-k` (Agente) | `/review` (Command) | `/inspect` (Command) | `CLAUDE.md` (Auto) |
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
- `.claude/agents/officer-k.md`: Subagente de Claude Code. Define a Officer K como agente de inspección completa invocable con `@officer-k`.
- `.claude/commands/review.md`: Slash command `/review` para Claude Code. Revisión on-demand de cambios staged.
- `.claude/commands/inspect.md`: Slash command `/inspect` para Claude Code. Inspección completa del repositorio.
- `rules/rules.md`: Catálogo completo de reglas de Clean Code (naming, funciones, SOLID, DRY, tests) aplicadas por todos los modos.
- `.logs/`: *(Del proyecto objetivo)* Contexto de arquitectura y decisiones técnicas que la IA incluye en el análisis.

---

> *"He visto código que ustedes no creerían. Variables sin tipo asaltando el stack de memoria. Funciones de quinientas líneas brillando en la oscuridad de producción. Todos esos commits se perderán en el tiempo, como advertencias en consola. Es hora de refactorizar."*
>
> — **R. Deckard**
