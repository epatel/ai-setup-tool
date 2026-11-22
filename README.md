# ast - AI setup tool

`ast` keeps a project's agentic tools (skills, agents, commands, scripts, cards) in step with the
repos they come from. The project commits a small config (`ast.toml`), a lock file
(`ast.lock`) and the installed files, so every clone and worktree has the same setup, and
`ast status` / `ast update` show and apply what changed upstream.

An organisation can keep one repo of named **sets** (a default, plus per-project sets that
extend it), and each project selects a set. The same `ast` commands manage that repo.

## Install

Needs Python 3.11.4+ and git.

```sh
uv tool install git+<this repo>     # or: pipx install git+<this repo>
```

## A project on its own

```sh
ast init                                            # creates ast.toml
ast source add epatel/agent-skills --ref latest-tag # reference a repo that holds tools
ast list --available                                # see what it offers
ast add double-check makefile-actions               # install into .claude/
ast status                                          # local changes + upstream updates
ast update                                          # move to the newest release, reinstall
git add ast.toml ast.lock .claude && git commit
```

A repo is a git URL, a GitHub `owner/repo`, or a local path that starts with `./`, `../`,
`/` or `~`. A ref is a tag, branch or commit; `latest-tag` follows the highest version tag;
no ref means the default branch.

## With an org repo

```sh
ast use my-org/ai-setup          # import the org's sources and sets
ast select                       # list the sets
ast select proj-fenix            # install that set
ast disable some-skill           # turn one of the set's tools off for this project
ast add other-skill              # add a tool the set does not have
```

## Managing an org repo

```sh
ast init --org                                   # creates ast-org.toml with a 'default' set
ast source add epatel/agent-skills --ref v2026.11.14
ast source add . --name org                      # tools kept in the org repo itself
ast add double-check house-style                 # into the 'default' set
ast set new proj-fenix --extends default --description "Fenix team"
ast add state-machines --set proj-fenix          # extra tool
ast disable double-check --set proj-fenix        # exclude an inherited tool
ast list                                         # every set, resolved
ast status                                       # checks that every tool still exists
```

Commit and push; projects pick the change up with `ast update`.

A set is everything its `extends` parents resolve to, plus its own `tools`, minus its own
`exclude`.

```toml
# ast-org.toml
version = 1

[sources.agent-skills]
repo = "epatel/agent-skills"
ref = "v2026.11.14"

[sets.default]
tools = ["agent-skills:skill/double-check"]

[sets.proj-fenix]
extends = ["default"]
tools = ["agent-skills:skill/state-machines"]
exclude = ["agent-skills:skill/double-check"]
```

## Commands

| Command | Does |
| --- | --- |
| `ast init [--org]` | Create `ast.toml`, or `ast-org.toml` for an org repo. |
| `ast source add <repo> [--name N] [--ref R]` / `rm <name>` / `list` | Manage the repos tools come from. |
| `ast use <org repo> [--ref R] [--set S]` / `--remove` | Import an org repo's sets, or stop using it. |
| `ast select [set]` | Select a set; with no name, list the sets. |
| `ast list [-a]` | Active tools and their state; `-a` adds what else is available. |
| `ast add <tool>...` | Add tools to the project (or to a set: `--set S`). |
| `ast rm <tool>...` | Remove tools you added (or from a set: `--set S`). |
| `ast disable <tool>...` / `ast enable <tool>...` | Turn a tool off or on, keeping it in the config. In an org repo: a set's `exclude` list. |
| `ast status` | Installed tools, local changes, pending config changes, upstream updates. Exits 1 when local files differ from the lock. |
| `ast sync` | Make installed files match `ast.toml` and `ast.lock`. |
| `ast update [source]...` | Re-resolve refs (all sources and the org repo, or just the named ones) and reinstall. |
| `ast set new <name> [--extends A,B]` / `rm <name>` / `list` | Manage sets in an org repo. |
| `ast help [command]` | Show help for `ast`, or for one command. |

Name a tool as `name`, `kind/name`, `source:name` or `source:kind/name`; the short forms work
while they are unambiguous. Global flags: `-C DIR`, `--offline`, `--org` (act on
`ast-org.toml` when a directory has both files).

## What counts as a tool

`ast` finds tools in a source repo by where they are:

| Kind | In the source repo | Installed to |
| --- | --- | --- |
| skill | `<name>/SKILL.md`, `skills/<name>/SKILL.md`, `.claude/skills/<name>/SKILL.md` | `.claude/skills/<name>/` |
| agent | `agents/<name>.md`, `.claude/agents/<name>.md` | `.claude/agents/<name>.md` |
| command | `commands/<name>.md`, `.claude/commands/<name>.md` | `.claude/commands/<name>.md` |
| script | `scripts/<file>` | `.claude/scripts/<file>` |
| card | `cards/<name>.md` | `cards/<name>.md` |

A card is a context card: a short reference file that `CLAUDE.md` links to. `ast` copies the
file; you add the index line to `CLAUDE.md` yourself.

## Safety rules

- Sources stay at their locked commit until `ast update`. Adding a tool never moves others.
- `ast` never overwrites or deletes an installed tool you edited, or a file it did not
  install, unless you pass `--force`. Such tools are reported as `blocked` and the command
  exits 1.
- A command that fails leaves `ast.toml` and `ast.lock` as they were.
- Repos are cached as bare clones in `~/.cache/ast` (`AST_CACHE_DIR` or `XDG_CACHE_HOME`
  to move it).

## Develop

Setup steps live in [`setup-todo-list.md`](setup-todo-list.md). An AI agent can run them, and every step also reads as plain manual instructions.
With Claude Code: `/project-setup` (set up) · `/project-setup doctor` (re-check after a pull that changed the list).
With any other agent: *"Set up this project using setup-todo-list.md"*.

By hand: install git 2.28+ and [uv](https://docs.astral.sh/uv/) 0.4.27+, then:

```sh
make setup   # uv sync into .venv/ (uv fetches Python 3.11.4+ if needed)
make test
make lint
make link    # put this checkout's ast on your PATH: ~/.local/bin/ast -> .venv/bin/ast
```
