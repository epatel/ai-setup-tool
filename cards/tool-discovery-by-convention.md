# tool-discovery-by-convention

Source repos need no manifest: `catalog.discover` finds tools from file paths alone.

## The choice

A tool is recognised by where it sits in the source repo, and its kind fixes where it is
installed (`catalog.DESTS`):

| Kind | Found at | Installed to |
| --- | --- | --- |
| skill | `<name>/SKILL.md`, `skills/<name>/SKILL.md`, `.claude/skills/<name>/SKILL.md` | `.claude/skills/<name>/` |
| agent | `agents/<name>.md`, `.claude/agents/<name>.md` | `.claude/agents/<name>.md` |
| command | `commands/<name>.md`, `.claude/commands/<name>.md` | `.claude/commands/<name>.md` |
| script | `scripts/<file>` | `.claude/scripts/<file>` |
| card | `cards/<name>.md` | `cards/<name>.md` |

Cards are the one kind installed outside `.claude/`. `ast` copies the card but does not
add its index line to `CLAUDE.md`.

When the same kind and name appears in two places, the earlier place in the table wins.
That matters for repos such as `epatel/agent-skills`, which keeps a skill at the root and
also an installed copy of it under `.claude/skills/`.

A tool id is `source:kind/name`. The config files always store full ids; `catalog.match`
lets users type `name`, `kind/name` or `source:name` while that is unambiguous.

## Alternatives considered

- A manifest file in each source repo listing its tools. More control, but existing skill
  repos would not work until their owners add one.
- Letting the project config give a path and a destination per tool. Flexible, but every
  project would repeat layout knowledge, and sets could not be shared safely.

## Why this won

Existing repos work unchanged, including ones the user does not control. The destination
is derived, never written in config, so a config file cannot direct a copy to an arbitrary
path.

## When to revisit

- A source needs tools in a place the table does not cover, and adding a root is not enough.
- A tool kind needs more than a copy (a hook that must be registered in `settings.json`,
  an MCP server).
- Two kinds need the same destination directory.

Adding a kind: add it to `DESTS` and to the discovery roots, extend the table in the README
and here. If a destination pattern ever changes, `engine.apply` already handles a locked
tool whose `dest` differs from the new one by removing the old location first.
