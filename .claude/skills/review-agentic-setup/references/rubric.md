# Review rubric

Checks per asset type. Every check names the finding class it usually produces (ROT / REDUNDANT / GAP / QUESTION).

## Universal (all instruction files)

- **Dead referents** — every mentioned path, binary, script, URL, env var: verify it exists/runs. Missing → ROT. Absolute paths into other repos or venvs are high-risk. Check them all.
- **Model naming** — references to specific model names/IDs: are they current-generation? Instructions like "use Opus for X" written for an older family → ROT (update) or QUESTION (if it encodes a cost preference).
- **Superseded tool guidance** — instructions that describe workarounds for limitations the current harness no longer has → ROT. Examples: manual context tricks, "you cannot do X", output-format hacks for old renderers.
- **Native-behavior narration** — step-by-step guidance for things the current model does unprompted → REDUNDANT. Examples: how to plan, how to search a codebase, "think carefully", generic code-quality sermons. One sentence of project-specific constraint beats a page of generic method.
- **Duplication** — same fact in 2+ files → REDUNDANT everywhere except its canonical home. Replace it with a pointer.
- **Contradictions** — two files giving conflicting instructions → QUESTION unless one side is provably rot.
- **Date rot** — relative dates ("recently", "the new X"), stale status sections ("currently migrating…") older than a few months → QUESTION.

## CLAUDE.md / AGENTS.md

- **Context budget** — loaded every session. Anything only needed for specific tasks → GAP: move to a card/skill with a routing line.
- **`@` imports** — resolve each one. Broken import → ROT. Imports nest at most four hops deep. Relative paths resolve from the importing file, not the cwd. A chain deeper than four, or a path written relative to the cwd → ROT. `@` inside code spans and fenced blocks is not an import.
- **AGENTS.md** — Claude Code reads it natively only when no CLAUDE.md exists in the working directory or above. If both exist and AGENTS.md holds shared content, CLAUDE.md must `@AGENTS.md` it, or that content never loads → ROT. Content duplicated in both → REDUNDANT.
- **Routing quality** — the project can have a card index (or another routing manifest such as `AGENT_FILES/`). Then check that every entry links to a real file. Also check that each entry names a *trigger situation* rather than a topic. Dead link or orphan card → ROT. Topic-style trigger → GAP. Large doc pile with no index → GAP.
- **Eager imports of lazy docs** — an `@path` reference to a card, `CLAUDE_full.md`, or any other file meant to load on demand is an import. It loads that file every session → ROT. Replace it with a plain path or markdown link plus a "read when…" condition.
- **Known stack** — a card that only restates a mainstream framework, library or design pattern used the standard way → REDUNDANT. Examples: how go_router works, what a singleton is. Replace the card with one line in a "Known stack" section of CLAUDE.md. The line names the concept, its paths, and any local twist. A Known stack line that needs a paragraph to be accurate → GAP: promote it to a card. Show the user each card before deleting it.
- **Hooks vs prose** — "always/never/before each X" behavioral rules in prose that the harness could enforce via hooks or permission settings → GAP. Note it. Implement it only if it is mechanical.

## Skills (SKILL.md)

- **Frontmatter** — `name` (kebab-case, matches dir), `description` present and trigger-rich: says *when to use*, covers indirect phrasings, mentions the trigger command if any. Vague one-liner → GAP.
- **Progressive disclosure** — the SKILL.md body should be scannable (roughly a screen or two). Long templates, question banks, and checklists belong in sibling files that the body references. Monolith → REDUNDANT (restructure).
- **Runnability** — commands in the skill: run the cheap ones (`--help`, `--version`). Broken invocation → ROT. Hard-coded interpreter/venv paths → ROT-prone. Prefer project-relative or documented setup.
- **Overlap with built-ins** — a local skill duplicating a built-in or plugin skill that now exists → QUESTION (deprecate?).
- **Orphan skills** — skill for a feature/workflow the project no longer has → QUESTION.

## Agents (.claude/agents/*.md)

- Frontmatter valid (`name`, `description`, optional `tools`, `model`). The description states delegation criteria clearly.
- `model` pins to an old model → ROT (update or remove to inherit).
- `tools` lists tools that no longer exist or omits ones the agent's task now needs → ROT/GAP.
- Agent whose job the main loop now does well solo → QUESTION.

## Commands (.claude/commands/*.md)

- Commands are the legacy mechanism. Skills supersede them for anything with logic. Non-trivial command → GAP: convert to a skill. Trivial prompt-alias → leave.

## Settings & hooks (.claude/settings*.json)

- Valid JSON, and hook scripts exist and are executable → else ROT.
- **Path rules** — every file-editing tool checks `Edit(...)` rules. Claude Code accepts `Write(...)` and `NotebookEdit(...)` path rules but never consults them → ROT: rewrite as `Edit(...)`. `../` is not a documented path form → ROT: use an absolute `//path` in `settings.local.json`, or a hook that resolves the path.
- **Skill symlinks** — a project `.claude/skills/<name>` can be a symlink into a home directory. It breaks for collaborators and fresh clones → ROT: replace with a committed copy.
- Hooks calling moved/renamed binaries (e.g. command wrappers or proxies the hook rewrites through) → verify with `which`.
- Permission allowlist entries for tools/commands no longer used → REDUNDANT (list them, do not silently remove — QUESTION if unsure).
- MCP servers configured but unreachable → QUESTION (may be environment-specific).

## Skill placement

- A project that depends on a skill found only in `~/.claude/skills/` → GAP: copy it into `.claude/skills/` (committed). A plugin the project needs that is installed only at user scope → GAP: propose enabling it with `--scope project`. Report the personal copy as redundant. Never change `~/.claude/`.
