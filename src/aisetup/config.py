"""The committed config files: ast.toml (a project) and ast-org.toml (an org repo of sets)."""

from __future__ import annotations

import re
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError

from .errors import AstError

PROJECT_FILE = "ast.toml"
ORG_FILE = "ast-org.toml"

# Schema migrations for both config files. MIGRATIONS[i] upgrades a parsed document from
# version i+1 to i+2 in place. Never edit a step that has shipped; append a new one.
MIGRATIONS: list = []
VERSION = len(MIGRATIONS) + 1

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

PROJECT_TEMPLATE = """\
# ast (AI setup tool) config. Commit this file and ast.lock with the project.
version = 1
"""

ORG_TEMPLATE = """\
# ast org repo: tool sources and named sets.
# Projects pick a set with `ast use <this repo>` and `ast select <set>`.
version = 1

[sets.default]
description = "Baseline for every project"
tools = []
"""


def migrate(data, label: str, migrations: list = MIGRATIONS) -> None:
    current = len(migrations) + 1
    version = data.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise AstError(f"{label}: version must be a positive integer")
    if version > current:
        raise AstError(
            f"{label} is version {version}, but this ast knows only up to {current}: upgrade ast"
        )
    for step in migrations[version - 1:]:
        step(data)
    data["version"] = current


def check_name(name: str, what: str) -> str:
    if not _NAME.fullmatch(name):
        raise AstError(f"invalid {what} name '{name}' (use letters, digits, '.', '_' and '-')")
    return name


def _array(values: list[str]):
    arr = tomlkit.array()
    arr.extend(values)
    arr.multiline(bool(values))
    return arr


def _strings(value) -> list[str]:
    return [value] if isinstance(value, str) else list(value or [])


class _Config:
    file = ""

    def __init__(self, doc, path: Path | None):
        self.doc = doc
        self.path = path

    @classmethod
    def loads(cls, text: str, label: str, path: Path | None = None):
        try:
            doc = tomlkit.parse(text)
        except TOMLKitError as e:
            raise AstError(f"{label}: {e}") from None
        migrate(doc, label)
        return cls(doc, path)

    @classmethod
    def load(cls, directory: Path):
        path = directory / cls.file
        return cls.loads(path.read_text(), str(path), path)

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def data(self) -> dict:
        return self.doc.unwrap()

    def save(self) -> None:
        self.path.write_text(tomlkit.dumps(self.doc))

    def _child(self, key: str, name: str | None = None):
        """Get or create the table `[key]`, or `[key.name]` when a name is given."""
        if key not in self.doc:
            self.doc[key] = tomlkit.table(is_super_table=name is not None)
        if name is None:
            return self.doc[key]
        if name not in self.doc[key]:
            self.doc[key][name] = tomlkit.table()
        return self.doc[key][name]

    def _drop(self, key: str, name: str | None = None) -> None:
        if name is not None and name in self.doc.get(key, {}):
            del self.doc[key][name]
        if key in self.doc and (name is None or not self.doc[key]):
            del self.doc[key]

    @property
    def sources(self) -> dict[str, dict]:
        return dict(self.data.get("sources", {}))

    def add_source(self, name: str, repo: str, ref: str | None) -> None:
        self._drop("sources", check_name(name, "source"))
        table = self._child("sources", name)
        table["repo"] = repo
        if ref:
            table["ref"] = ref

    def remove_source(self, name: str) -> None:
        self._drop("sources", name)


class ProjectConfig(_Config):
    file = PROJECT_FILE

    @property
    def org(self) -> dict | None:
        return self.data.get("org") or None

    def set_org(self, repo: str, ref: str | None) -> None:
        self._drop("org")
        table = self._child("org")
        table["repo"] = repo
        if ref:
            table["ref"] = ref

    def select_set(self, name: str | None) -> None:
        if name:
            self._child("org")["set"] = name
        elif "set" in self.doc.get("org", {}):
            del self.doc["org"]["set"]

    def clear_org(self) -> None:
        self._drop("org")

    @property
    def added(self) -> list[str]:
        return _strings(self.data.get("tools", {}).get("add"))

    @property
    def disabled(self) -> list[str]:
        return _strings(self.data.get("tools", {}).get("disable"))

    def set_tools(self, added: list[str], disabled: list[str]) -> None:
        self._drop("tools")
        for key, values in (("add", added), ("disable", disabled)):
            if values:
                self._child("tools")[key] = _array(values)


class OrgConfig(_Config):
    file = ORG_FILE

    @property
    def sets(self) -> dict[str, dict]:
        return {
            name: {
                "description": s.get("description", ""),
                "extends": _strings(s.get("extends")),
                "tools": _strings(s.get("tools")),
                "exclude": _strings(s.get("exclude")),
            }
            for name, s in self.data.get("sets", {}).items()
        }

    def add_set(self, name: str, extends: list[str], description: str) -> None:
        table = self._child("sets", check_name(name, "set"))
        if description:
            table["description"] = description
        if extends:
            table["extends"] = _array(extends)
        table["tools"] = _array([])

    def remove_set(self, name: str) -> None:
        self._drop("sets", name)

    def set_lists(self, name: str, tools: list[str], exclude: list[str]) -> None:
        table = self._child("sets", name)
        table["tools"] = _array(tools)
        if exclude:
            table["exclude"] = _array(exclude)
        elif "exclude" in table:
            del table["exclude"]


def resolve_set(sets: dict[str, dict], name: str) -> dict[str, str]:
    """Tools of a set, in order, mapped to the set that contributes each one.

    A set is everything its `extends` parents resolve to, plus its own `tools`,
    minus its own `exclude`.
    """

    def walk(current: str, stack: tuple[str, ...]) -> dict[str, str]:
        if current in stack:
            raise AstError(f"sets extend each other in a cycle: {' -> '.join((*stack, current))}")
        if current not in sets:
            via = f" (extended by '{stack[-1]}')" if stack else ""
            known = ", ".join(sorted(sets)) or "none"
            raise AstError(f"unknown set '{current}'{via}; sets: {known}")
        result: dict[str, str] = {}
        for parent in sets[current]["extends"]:
            result.update(walk(parent, (*stack, current)))
        for tool_id in sets[current]["tools"]:
            result[tool_id] = current
        for tool_id in sets[current]["exclude"]:
            result.pop(tool_id, None)
        return result

    return walk(name, ())
