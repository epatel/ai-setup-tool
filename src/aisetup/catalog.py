"""Find the tools a source repo offers, and match user input against them."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from .errors import AstError

# kind -> where a tool of that kind is installed in a project
DESTS = {
    "skill": ".claude/skills/{name}",
    "agent": ".claude/agents/{name}.md",
    "command": ".claude/commands/{name}.md",
    "script": ".claude/scripts/{name}",
}

# Places a source repo may keep tools, in order of precedence when a name appears twice.
_SKILL_ROOTS = ("", "skills/", ".claude/skills/")
_FILE_ROOTS = {
    "agent": ("agents/", ".claude/agents/"),
    "command": ("commands/", ".claude/commands/"),
    "script": ("scripts/",),
}


@dataclass(frozen=True)
class Tool:
    source: str
    kind: str
    name: str
    path: str = ""  # file or directory inside the source repo

    @property
    def id(self) -> str:
        return f"{self.source}:{self.kind}/{self.name}"

    @property
    def dest(self) -> str:
        return DESTS[self.kind].format(name=self.name)

    @classmethod
    def from_id(cls, tool_id: str) -> Tool:
        source, sep, rest = tool_id.partition(":")
        kind, sep2, name = rest.partition("/")
        if not (sep and sep2 and source and name) or kind not in DESTS:
            raise AstError(f"'{tool_id}' is not a tool id (expected source:kind/name)")
        return cls(source, kind, name)


def discover(source: str, files: list[str]) -> list[Tool]:
    """List the tools in a repo, given the paths of all its files."""
    found: dict[tuple[str, str], Tool] = {}

    def offer(kind: str, name: str, path: str) -> None:
        if name and not name.startswith("."):
            found.setdefault((kind, name), Tool(source, kind, name, path))

    for root in _SKILL_ROOTS:
        for f in files:
            rest = f[len(root):] if f.startswith(root) else ""
            parts = rest.split("/")
            if len(parts) == 2 and parts[1] == "SKILL.md":
                offer("skill", parts[0], root + parts[0])
    for kind, roots in _FILE_ROOTS.items():
        for root in roots:
            for f in files:
                rest = f[len(root):] if f.startswith(root) else ""
                if not rest or "/" in rest:
                    continue
                if kind == "script":
                    offer(kind, rest, f)
                elif rest.endswith(".md"):
                    offer(kind, rest[:-3], f)
    return sorted(found.values(), key=lambda t: t.id)


def match(catalog: dict[str, Tool], query: str) -> Tool:
    """Resolve `name`, `kind/name`, `source:name` or `source:kind/name` to exactly one tool."""
    source, sep, rest = query.partition(":")
    if not sep:
        source, rest = "", query
    kind, sep, name = rest.partition("/")
    if not sep:
        kind, name = "", rest
    hits = [
        t for t in catalog.values()
        if t.name == name and (not source or t.source == source) and (not kind or t.kind == kind)
    ]  # fmt: skip
    if len(hits) == 1:
        return hits[0]
    if hits:
        options = ", ".join(sorted(t.id for t in hits))
        raise AstError(f"'{query}' is ambiguous: {options}")
    close = difflib.get_close_matches(name, sorted({t.name for t in catalog.values()}), n=3)
    hint = f" (did you mean {', '.join(close)}?)" if close else " (see `ast list --available`)"
    raise AstError(f"no tool matches '{query}'{hint}")


def resolve_id(query: str, catalog: dict[str, Tool], known: set[str]) -> str:
    """Like match, but also finds tools named in config that the sources no longer offer."""
    pool = dict(catalog)
    for tool_id in known:
        pool.setdefault(tool_id, Tool.from_id(tool_id))
    return match(pool, query).id
