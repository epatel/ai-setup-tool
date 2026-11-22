# org-sets

How an org repo's sets reach a project, and how inheritance resolves.

## Files

An org repo has `ast-org.toml` with `[sources.<name>]` tables (same shape as in a project)
and `[sets.<name>]` tables with `description`, `extends`, `tools` and `exclude`. Tool
entries are full ids: `source:kind/name`.

A project that uses it has `[org]` in `ast.toml` with `repo`, optional `ref`, and `set`.

## Resolving a set

`config.resolve_set(sets, name)` returns an ordered map of tool id → the set that
contributes it:

1. Resolve each parent in `extends`, in order, and merge.
2. Add the set's own `tools`.
3. Remove the set's own `exclude`.

Exclusion is applied at the level that declares it, so a child of a set can add an excluded
tool back through its own `tools`. Cycles and unknown parents raise `AstError`.

## From org repo to project

1. `build_plan` pins the org repo to a commit (locked, like a source) and reads
   `ast-org.toml` **from that commit**, not from any working tree.
2. Org sources are added to the project's sources. A project source with the same name
   replaces the org one.
3. An org source with `repo = "."` means the org repo itself, at the org commit.
4. Wanted tools = resolved set + the project's `tools.add` − the project's `tools.disable`.

Org sources other than `.` must not be local paths: a set has to resolve the same way on
every machine. Tests use `file://` URLs for this.

## Who may change what

| Action | In a project | In an org repo (`--set S`, default `default`) |
| --- | --- | --- |
| `add` | appends to `tools.add`; un-disables a set tool | appends to the set's `tools` |
| `rm` | only tools in `tools.add`; a set tool gives an error that points to `disable` | only the set's own `tools`; an inherited tool points to `disable --set` |
| `disable` | appends to `tools.disable` | appends to the set's `exclude` (inherited tools only) |
| `enable` | removes from `tools.disable` | removes from the set's `exclude` |

A project never edits the org's sets. Org changes reach a project only on `ast update`,
because the org commit is locked; `ast status` previews them as install/update/remove.

`ast use <repo>` keeps the selected set when the new repo still has it, and selects
automatically when the repo has exactly one set.
