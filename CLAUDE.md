# ast - AI setup tool

Always read @project-plan.md before starting — it holds the shared goal and current state.

## About this project

`ast` is a command-line tool that installs and tracks a project's agentic tools (skills,
agents, commands, scripts) from referenced git repos, and lets an organisation publish named
sets of them from one repo. Python 3.11+, one dependency (`tomlkit`), git via subprocess.
The package is `aisetup` (`src/aisetup/`) because `ast` is a stdlib module; the command is `ast`.

This repo manages its own skills with `ast`: see `ast.toml`, `ast.lock` and `.claude/skills/`.

## Commands

- Setup: `make setup` (uv sync into `.venv/`)
- Test: `make test` (one test: `uv run pytest tests/test_org.py -k selects`)
- Lint: `make lint` — format: `make format`
- Run the tool from the working tree: `uv run ast <command>`

Project setup lives in setup-todo-list.md. Don't run setup doctor unless asked; suggest it if a failure looks like missing tooling.

## Cards

### Architecture
- [architecture](cards/architecture.md) — changing how modules call each other, adding a command, or finding where a behaviour lives

### Features
- [sync-rules](cards/sync-rules.md) — touching install/update/remove, the lock file, `--force`, or anything that writes into a project
- [org-sets](cards/org-sets.md) — touching `ast use`/`select`, set inheritance, `ast-org.toml`, or org-mode commands

### Decisions
- [tool-discovery-by-convention](cards/tool-discovery-by-convention.md) — adding a tool kind, changing where tools are found or installed, or considering a manifest file in source repos

### Standing defaults
- [standing-defaults](cards/standing-defaults.md) — installing a Python dependency, or changing the schema of `ast.toml`, `ast-org.toml` or `ast.lock`

When you commit a change that adds non-obvious logic, settles an architectural choice,
or makes a card above wrong, update or add the card in that commit and keep this index
in sync. Proposed diffs and answers need no card edits. Cards stay self-contained: no
card links to another.
