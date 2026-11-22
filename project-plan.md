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
- [x] M4 — Publish: MIT license, release v0.1.0 tagged, install from GitHub verified.
- [ ] M5 — Replace the ai.memention.net/setup process with `ast` + `epatel/ast-repo`. An
      agent is still started by a URL; the page tells it to install `ast` and follow
      `ast prompt setup epatel/ast-repo`.
  - [ ] M5.1 — Bootstrap page (ADOPT.md style): check for `ast`, install with consent,
        run the setup prompt. A test version is written as `site/setup-ast` in
        `../ai-setup` (to be served at ai.memention.net/setup-ast), not yet published.
  - [x] M5.2 — Set `memention-setup` in `ast-repo`: the tools that /setup copies
        (review-agentic-setup, standing-defaults card, agent-docs checker script + command).
  - [x] M5.3 — The patterns as org prompts in `ast-repo/prompts/`, one per pattern, each
        including its pattern text from `cards/` with `{{include}}`. Not yet tried on a
        real project.
  - [x] M5.4 — `ast prompt setup <repo>` appends the repo's `prompts/setup.md`; prompts can
        include files from their repo.
  - [ ] M5.5 — Changelog on update: the update prompt reads the org repo's changelog
        between the old and new org commit.
  - [ ] M5.6 — Migration: `ast prompt adopt` recognises a project set up by /setup and
        retires `.claude/agent-setup.json`.
  - [ ] M5.7 — Tag `ast-repo`, run the whole flow on one real project, then switch /setup.
  - [ ] M5.8 — Outside these repos: `review-agentic-setup` and `check-agent-docs.py` read
        `agent-setup.json`; both must learn `ast.lock`.

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
`epatel/project-setup` at `latest-tag`. Public on GitHub, released as v0.1.0. M5 is in
progress: steps 2 to 4 are done and uncommitted work may sit in `../ast-repo`.

## Open questions
- Publish to PyPI? The name `ai-setup-tool` is unchecked. Today it installs from GitHub.
- M5: where does the bootstrap page live: a file in `ast-repo` (raw GitHub URL), or
  ai.memention.net/setup itself?
- M5: `ast-repo`'s `default` set installs every pattern card into each project. The
  patterns are now prompts; should only `standing-defaults` stay a card?
- M5: drop the applied/declined record? An agent can see applied patterns from the files,
  but a declined pattern may be offered again.
- M5: the cards and the checker exist on the site and in `ast-repo`. Which is the source?
- Hooks need `settings.json` entries to do anything. Copy-only is safe; is merge support wanted?
- Should a set be able to pin a different ref of a source than the org default?
