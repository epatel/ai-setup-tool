---
setup-format: 1
project: ai-setup-tool
---

# Project setup

> **Agents:** set this project up by working through the steps below in order.
> Record progress in `setup-todo-list.local.md` (gitignored), one line per step:
> `- <id>: done @rev<N> <date>`, or `skipped` / `failed` with a reason.
> Respect each step's `gate`: `auto` = just run it, `approve` = show the commands
> and wait for a yes, `input` = ask for the listed values first. Run a step's
> `check` first; if it passes, the step is already done (for `input` steps,
> still confirm the value). Never write secrets into either file. To re-check
> later ("doctor"), compare the progress lines with this file by id and `rev`,
> and re-run the checks.
>
> **Humans:** every step below is plain instructions. Follow them by hand if you prefer.

## [git] Install git 2.28 or newer
- required: yes
- gate: approve
- rev: 1
- check: `[ "$(printf '%s\n' 2.28 "$(git --version | awk '{print $3}')" | sort -V | head -n1)" = 2.28 ]`

`ast` reads source repos with git, and the tests create temporary repos with
`git init -b`, which needs git 2.28. On macOS: `xcode-select --install` or
`brew install git`. On Debian/Ubuntu: `sudo apt install git`.

## [uv] Install uv 0.4.27 or newer
- required: yes
- gate: approve
- rev: 1
- check: `[ "$(printf '%s\n' 0.4.27 "$(uv --version | awk '{print $2}')" | sort -V | head -n1)" = 0.4.27 ]`

uv creates the virtual environment and installs dependencies from `uv.lock`. It needs
0.4.27 for the `[dependency-groups]` table in `pyproject.toml`. Install it with
`brew install uv`, or see https://docs.astral.sh/uv/getting-started/installation/.

You do not need to install Python yourself. The project needs Python 3.11.4 or newer, and
uv downloads a matching interpreter when the machine has none.

## [deps] Create .venv and install dependencies
- required: yes
- gate: auto
- rev: 1
- depends: uv
- check: `{ .venv/bin/python -c "import aisetup, tomlkit, pytest" && .venv/bin/ruff --version || .venv/Scripts/python -c "import aisetup, tomlkit, pytest"; } >/dev/null 2>&1`

Run `make setup` (or `uv sync`) in the repo root. This creates the gitignored `.venv/`,
installs `tomlkit`, `pytest` and `ruff` at the versions in `uv.lock`, and installs the
`ast` command from the working tree as `.venv/bin/ast`.

Nothing else needs setup: the agent skills in `.claude/skills/` are committed with the
repo. Afterwards `make test` runs the tests and `uv run ast --help` runs the tool.
