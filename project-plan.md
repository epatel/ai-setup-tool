# Project Plan: ast (AI setup tool)

## Goal
A project keeps its agentic setup (skills, agents, commands, scripts) as a committed config
that `ast` can install, check and update from the repos it references. An organisation can
publish named sets of tools from one repo, and projects select a set and adjust it locally.

## Non-goals
- Installing anything outside the project directory (no `~/.claude/`, no system tools).
- Wiring hooks or MCP servers into `settings.json` / `.mcp.json`. `ast` copies files only.
- Claude Code plugin marketplaces. They have their own install mechanism.
- Supporting agents other than Claude Code layouts (`.claude/...`) for now.

## Milestones
- [x] M1 — Project commands: init, source, add, rm, enable, disable, list, status, sync, update.
- [x] M2 — Org repos: `ast use`, `ast select`, sets with extends/exclude, org-mode commands.
- [x] M3 — This repo uses `ast` for its own skills and the ai.memention.net/setup patterns.
- [ ] M4 — Publish: tag a release, verify `uv tool install` from GitHub. (License: done.)
- [ ] M5 — Reflect on ai.memention.net/setup: which of its record fields and refresh steps
      `ast` should take over (see Open questions).

## Decisions
- 2026-11-22 — Python 3.11+ with uv, not Rust. The work is git, file copies and TOML. Locked.
- 2026-11-22 — Package is `aisetup`, command is `ast` (`ast` is a stdlib module). Locked.
- 2026-11-22 — `ast.toml` (TOML, hand-editable, comments kept) + `ast.lock` (JSON). Locked.
- 2026-11-22 — Installed files are committed with the project; the lock records the commit,
  the git tree id and a content hash per tool. Locked.
- 2026-11-22 — Tools are found by path convention in source repos, with no manifest file.
- 2026-11-22 — Sources move only on `ast update`; local edits are never overwritten without
  `--force`. Locked.
- 2026-11-22 — Org sources must be remote URLs or `.` (the org repo itself), so a set
  resolves the same on every machine.
- 2026-11-22 — MIT license. Public at github.com/epatel/ai-setup-tool; demo org repo at
  github.com/epatel/ast-repo.

## Current state / handoff
First implementation is complete: all commands of M1 and M2 work and are covered by tests
(`make test`, against temporary local git repos). A `card` tool kind was added for the demo
org repo. This repo's skills are installed with `ast` from `epatel/agent-skills` and
`epatel/project-setup` at `latest-tag`. The repo is public on GitHub; no release is tagged.

## Open questions
- Publish to PyPI? The name `ai-setup-tool` is unchecked. Today it installs from GitHub.
- Should `ast` also manage the non-skill parts of ai.memention.net/setup (cards copied from
  a URL, the `.claude/agent-setup.json` record)? Today both records exist side by side here.
- Hooks need `settings.json` entries to do anything. Copy-only is safe; is merge support wanted?
- Should a set be able to pin a different ref of a source than the org default?
