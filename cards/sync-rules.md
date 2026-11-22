# sync-rules

What `engine.apply` may and may not do to files in a project, and what the lock records.

## The lock entry

`ast.lock` holds, per installed tool: `path` (in the source repo), `dest` (in the project),
`commit`, `tree` and `hash`. The last two answer different questions:

- `tree` is the git object id of the tool's path at the source commit. It changes when the
  **upstream** content changes. Comparing it needs no file export.
- `hash` is `engine.tree_hash` of the installed files. It changes when someone edits the
  **local** copy. It ignores `__pycache__` and `.DS_Store`, which tools create when they run.

Per source the lock holds `repo` and `ref` as written in the config, plus `commit` and
`label`. A locked commit is reused only while `repo` and `ref` still match the config, so
editing a ref by hand takes effect on the next sync.

## Decision table for one wanted tool

| Lock entry | Upstream (`tree`) | Local files | Result |
| --- | --- | --- | --- |
| none | — | dest absent | install |
| none | — | dest present, same content | adopt (lock it, copy nothing) |
| none | — | dest present, different | **blocked** unless `--force` |
| yes | same | ok | nothing |
| yes | same | modified | keep the edit, report `modified` (not an error) |
| yes | same | missing | restore |
| yes | changed | ok or missing | update |
| yes | changed | modified | **blocked** unless `--force` |

A locked tool that is no longer wanted is removed, unless its files are modified: then the
removal is **blocked** and the lock entry stays.

## The card index

After files are in place, `apply` rewrites the block between the `ast:cards` markers in
`CARDS.md` from the locked cards, every run. Only that block is `ast`'s; the rest of the
file is kept. When there are cards and neither `CLAUDE.md` nor `AGENTS.md` contains
`@CARDS.md`, one import line is appended (once). With no cards left the block is emptied;
the file and the import stay, so the import never dangles.

A card's `trigger` is refreshed from the source whenever the installed copy matches the
planned content, so a source can improve its index line without changing the card.

## Invariants

- Nothing with local edits, and nothing `ast` did not install, is overwritten or deleted
  without `--force`.
- A blocked tool keeps its old lock entry, so the next run sees the same situation. The
  command still applies everything else and exits 1.
- Removing a tool also removes parent directories it leaves empty, up to the project root.
- Every destination must resolve inside the project root.
- Two wanted tools that map to the same destination are an error before anything is written.
- Files are exported with `git archive` and extracted with tarfile's `data` filter, into a
  temporary directory, then moved into place.

## Exit codes

0 done or clean. 1 something was blocked (`sync`-type commands) or local files differ from
the lock (`status`). 2 an `AstError`: nothing was written.
