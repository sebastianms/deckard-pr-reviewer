# 🕵️‍♂️ Deckard PR Reviewer

> *AI-powered code reviewer that runs a **Voight-Kampff test** on your pull requests — because replicants (bad code) have no place in production.*

**Deckard PR Reviewer** is an automated AI agent that reviews GitHub Pull Requests and local staged changes, enforcing **Clean Code** rules and the **Boy Scout Rule** (always leave the code cleaner than you found it).

---

## ✨ Features

- **Automated Code Analysis:** Extracts the PR diff and analyzes only the added lines (`+`).
- **LLM-Agnostic:** Powered by [LiteLLM](https://github.com/BerriAI/litellm) — use any model you prefer: OpenAI (GPT-4), Anthropic (Claude), Google (Gemini), Groq, local models, etc.
- **Technical Debt Detector:** Calculates the technical debt introduced in the PR based on detected anomalies vs. lines added.
- **Bidirectional Validation:** Reads previous bot comments on the PR and intelligently identifies which feedback has already been addressed in a new commit ("Retired Anomalies").
- **Centralized Rules:** All Clean Code rules, best practices and architecture checks are evaluated using the global rules file (`rules/rules.md`), optionally enriched with the project's decision log (`.logs/`).
- **Noir Personality:** GitHub comments adopt a cynical, detective-like tone to assess whether "the code is human."

---

## 🚀 Installation & Requirements

1. **Clone the repository:**
   ```bash
   git clone <REPO_URL> deckard
   cd deckard
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *Key dependencies: `litellm` for unified LLM API interaction, and `requests` for the GitHub API.*

---

## ⚙️ Configuration (Environment Variables)

Provide the following environment variables before running (export them in your CI/CD or place them in a local `.env` file).

| Variable | Description | Example |
|---|---|---|
| `GITHUB_REPOSITORY` | Target repository in `owner/repo` format. | `facebook/react` |
| `PR_NUMBER` | The Pull Request number to analyze. | `42` |
| `GITHUB_TOKEN` | GitHub PAT with read access to code and write access for comments/reviews. | `ghp_xxxxx...` |
| `LLM_MODEL` | *(Optional)* Provider and model for LiteLLM. | `openai/gpt-4o` (Default: `gemini/gemini-1.5-pro-preview`) |
| `<PROVIDER>_API_KEY` | API key for the selected model. | `OPENAI_API_KEY="sk-..."` or `GEMINI_API_KEY="AIza..."` |
| `SINGLE_REQUEST_MODE` | Bundle the entire PR into 1 call to avoid rate limits on free-tier accounts. | `true` or `false` |
| `MAX_CONCURRENT_REVIEWS` | Thread concurrency when `SINGLE_REQUEST_MODE=false`. For paid accounts. | `5` |

### Multi-LLM via LiteLLM

Deckard supports virtually any model on the market without changing a single line of code — just set the right API key for the model you choose.

**.env examples:**

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

## 🛠️ Usage

### Local Execution

Run the agent from your terminal (ideal for development and debugging). Native `.env` file support is included.

1. Copy the example env file:
   ```bash
   cp .env.example .env
   ```
2. Fill in your values (`GEMINI_API_KEY`, `LLM_MODEL`, `SINGLE_REQUEST_MODE`, etc.).
3. Run Deckard:

```bash
# Review a remote Pull Request on GitHub
python review_pr.py

# Or review your local staged files before committing
python review_local.py
```

### Continuous Integration (GitHub Actions)

The primary use case is running Deckard automatically when a PR is opened or updated.

Create a workflow file in your repository, e.g. `.github/workflows/deckard_review.yml`:

```yaml
name: Deckard PR Reviewer

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  voight_kampff_test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout reviewer code
        uses: actions/checkout@v3
        with:
          repository: 'your-owner/deckard-reviewer-repo'
          ref: 'main'

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run code review
        env:
          GITHUB_REPOSITORY: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          LLM_MODEL: "gemini/gemini-3.0-pro-preview"
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python review_pr.py
```

### 🔗 Pre-Commit Hook (Husky / Native)

Deckard can interrogate replicants locally before you push code to the remote. The `review_local.py` script will abort the commit if it finds critical "anomalies" in your staged files (`git diff --cached`).

**Husky (Node.js):**

```bash
npx husky-init
npm install
```

Edit `.husky/pre-commit`:
```bash
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

export LLM_MODEL="gemini/gemini-1.5-pro-preview"
export GEMINI_API_KEY="YourApiKey..."
export SINGLE_REQUEST_MODE="true"
export MAX_CONCURRENT_REVIEWS="1"

python path/to/deckard/review_local.py
```

**pre-commit (Python / No Node.js):**

```bash
pip install pre-commit
```

Create `.pre-commit-config.yaml`:
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

**Native Git Hook:**

Create `.git/hooks/pre-commit` in your target repository:
```bash
#!/bin/sh
python path/to/deckard/review_local.py
```
*Remember to make it executable: `chmod +x .git/hooks/pre-commit`*

---

### 🤖 Claude Code Integration

Deckard works natively inside **Claude Code**, using Claude's own session — no external API keys required.

**Three mechanisms are available:**

#### `@deckard` Sub-agent — Diff Reviewer (Recommended for pre-commit)

A specialized agent with its own isolated context and preconfigured rules. Analyzes only staged/unstaged changes (`git diff`).

```
@deckard review my staged changes
```
```bash
claude --agent deckard "review staged changes"
```

**Global installation** (available in ALL your projects):
```bash
mkdir -p ~/.claude/agents
cp <DECKARD_PATH>/.claude/agents/deckard.md ~/.claude/agents/deckard.md
```

---

#### `@officer-k` Sub-agent — Full Repository Inspector

**Officer K** (KD6-3.7) is Deckard's counterpart. Instead of diffs, it **inspects the entire source code** (`git ls-files`). Ideal for periodic audits or onboarding legacy projects.

```
@officer-k inspect the repository
```
```bash
claude --agent officer-k "inspect all repository code"
```
```
/inspect
```

**Global installation:**
```bash
mkdir -p ~/.claude/agents
cp <DECKARD_PATH>/.claude/agents/officer-k.md ~/.claude/agents/officer-k.md
```

> **When to use each?** Use `@deckard` in your daily flow (pre-commit, PRs). Use `@officer-k` for a full repository X-ray: legacy onboarding, quality audits, pre-release checks.

---

#### Auto-Review (always active)
`CLAUDE.md` instructs Claude Code to **always** review its own code against Deckard's rules before committing. No user intervention required.

```bash
cp <DECKARD_PATH>/CLAUDE.md /path/to/your-project/CLAUDE.md
```

#### Slash Command (`/review`) — On Demand
Type `/review` in Claude Code to trigger a manual review of staged changes at any time.

```bash
mkdir -p /path/to/your-project/.claude/commands
cp <DECKARD_PATH>/.claude/commands/review.md /path/to/your-project/.claude/commands/review.md
```

#### Mechanism Comparison

| Aspect | `@deckard` (Agent) | `@officer-k` (Agent) | `/review` (Command) | `/inspect` (Command) | `CLAUDE.md` (Auto) |
|---|---|---|---|---|---|
| **Invocation** | `@deckard` or `/review` | `@officer-k` or `/inspect` | `/review` in chat | `/inspect` in chat | Automatic pre-commit |
| **Scope** | Diffs only (staged/unstaged) | Full source code | Diffs only | Full source code | Diffs only |
| **Context** | Isolated & focused | Isolated & focused | Shared conversation | Shared conversation | Shared conversation |
| **Can fix code** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Requires external API key** | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| **Globally available** | ✅ With `~/.claude/agents/` | ✅ With `~/.claude/agents/` | ❌ Project only | ❌ Project only | ❌ Project only |

> **Note:** All mechanisms reference the rules in `<DECKARD_PATH>/rules/rules.md`. If you move the Deckard project, update the paths.

---

## 📂 Key Files

- `review_pr.py`: Main script for GitHub Actions PR review. Fetches remote diffs, calls the LLM via LiteLLM, and posts comments.
- `review_local.py`: Pre-commit hook script (Husky/native Git). Analyzes `git diff --cached` locally using LiteLLM.
- `CLAUDE.md`: Auto-review rule for Claude Code. Forces Claude to review its own code against the rules before committing.
- `.claude/agents/deckard.md`: Claude Code sub-agent. Defines Deckard as an autonomous agent invokable with `@deckard`. Analyzes diffs.
- `.claude/agents/officer-k.md`: Claude Code sub-agent. Defines Officer K as a full inspection agent invokable with `@officer-k`.
- `.claude/commands/review.md`: `/review` slash command for Claude Code. On-demand review of staged changes.
- `.claude/commands/inspect.md`: `/inspect` slash command for Claude Code. Full repository inspection.
- `rules/rules.md`: Complete Clean Code rules catalog (naming, functions, SOLID, DRY, tests) applied by all modes.
- `.logs/`: *(From the target project)* Architecture context and technical decisions included in the AI analysis.

---

> *"I've seen code you people wouldn't believe. Untyped variables attacking memory stacks. Five-hundred-line functions glittering in the dark of production. All those commits will be lost in time, like warnings in a console. Time to refactor."*
>
> — **R. Deckard**
