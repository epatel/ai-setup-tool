"""Work out which tools a project should have (the plan) and make its files match."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .cardindex import SOURCE_INDEX_FILES, source_triggers, summary, write_index
from .catalog import Tool, discover
from .config import ORG_FILE, OrgConfig, ProjectConfig, migrate, resolve_set
from .errors import AstError
from .gitrepo import Repo, is_local, normalize_repo

LOCK_FILE = "ast.lock"
LOCK_MIGRATIONS: list = []  # same contract as config.MIGRATIONS, for ast.lock

_IGNORED = {"__pycache__", ".DS_Store"}  # files tools create at run time; never count as changes


class Lock:
    """ast.lock: the exact commits and content the project's installed tools came from."""

    def __init__(self, path: Path):
        self.path = path
        self.org: dict | None = None
        self.sources: dict[str, dict] = {}
        self.tools: dict[str, dict] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError as e:
                raise AstError(f"{path}: {e}") from None
            migrate(data, str(path), LOCK_MIGRATIONS)
            self.org = data.get("org")
            self.sources = data.get("sources", {})
            self.tools = data.get("tools", {})

    def save(self) -> None:
        data = {"version": len(LOCK_MIGRATIONS) + 1, "sources": self.sources, "tools": self.tools}
        if self.org:
            data["org"] = self.org
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


@dataclass
class Source:
    name: str
    spec: str  # the repo as written in the config file
    ref: str | None
    commit: str
    label: str  # what the ref resolved to, for display: a tag, a branch, or HEAD
    origin: str  # "org" or "project"
    repo: Repo


@dataclass
class Plan:
    org: dict | None = None
    org_config: OrgConfig | None = None
    sources: dict[str, Source] = field(default_factory=dict)
    catalog: dict[str, Tool] = field(default_factory=dict)  # every tool the sources offer
    set_tools: dict[str, str] = field(default_factory=dict)  # tool id -> contributing set
    origins: dict[str, str] = field(default_factory=dict)  # wanted tool id -> "set:x"/"project"
    tools: dict[str, Tool] = field(default_factory=dict)  # wanted, enabled and found
    trees: dict[str, str] = field(default_factory=dict)  # tool id -> git object id
    missing: list[str] = field(default_factory=list)  # wanted but not offered by any source


def _pin(repo: Repo, spec: str, ref: str | None, locked: dict | None, refresh: bool):
    """Use the locked commit while repo and ref are unchanged; otherwise resolve the ref."""
    if locked and not refresh and locked.get("repo") == spec and locked.get("ref") == ref:
        commit = locked["commit"]
        if not repo.has_commit(commit):
            repo.fetch()
        if repo.has_commit(commit):
            return commit, locked.get("label") or ref or "HEAD"
    return repo.resolve(ref)


def build_plan(
    cfg: ProjectConfig,
    lock: Lock,
    *,
    refresh: bool | set[str] = False,
    offline: bool = False,
    strict: bool = True,
) -> Plan:
    """Resolve org, sources and tools. `refresh` re-resolves refs (all, or the named sources)."""
    plan = Plan()
    repos: dict[str, Repo] = {}

    def source(name: str, entry: dict, origin: str) -> Source:
        spec, ref = entry.get("repo"), entry.get("ref")
        if not spec:
            raise AstError(f"source '{name}' has no repo")
        if origin == "org" and is_local(spec):
            raise AstError(f"org source '{name}': only '.' may be used as a local repo path")
        url = normalize_repo(spec, cfg.root)
        repo = repos.setdefault(url, Repo(url, offline))
        fresh = refresh is True or (refresh is not False and name in refresh)
        commit, label = _pin(repo, spec, ref, lock.sources.get(name), fresh)
        return Source(name, spec, ref, commit, label, origin, repo)

    org = cfg.org
    if org:
        spec, ref = org.get("repo"), org.get("ref")
        if not spec:
            raise AstError("[org] has no repo")
        url = normalize_repo(spec, cfg.root)
        repo = repos.setdefault(url, Repo(url, offline))
        commit, label = _pin(repo, spec, ref, lock.org, refresh is True)
        text = repo.read(commit, ORG_FILE)
        if text is None:
            raise AstError(f"{spec} has no {ORG_FILE} at {label}; it is not an ast org repo")
        plan.org_config = OrgConfig.loads(text, f"{spec}:{ORG_FILE}")
        plan.org = {"repo": spec, "ref": ref, "commit": commit, "label": label}
        if org.get("set"):
            plan.org["set"] = org["set"]
            plan.set_tools = resolve_set(plan.org_config.sets, org["set"])
        for name, entry in plan.org_config.sources.items():
            if entry.get("repo") == ".":  # tools kept in the org repo itself
                plan.sources[name] = Source(name, ".", ref, commit, label, "org", repo)
            else:
                plan.sources[name] = source(name, entry, "org")
    for name, entry in cfg.sources.items():
        plan.sources[name] = source(name, entry, "project")

    for src in plan.sources.values():
        for tool in discover(src.name, src.repo.files(src.commit)):
            plan.catalog[tool.id] = tool

    for tool_id, set_name in plan.set_tools.items():
        plan.origins[tool_id] = f"set:{set_name}"
    for tool_id in cfg.added:
        plan.origins.setdefault(tool_id, "project")
    disabled = set(cfg.disabled)
    dests: dict[str, str] = {}
    for tool_id in plan.origins:
        if tool_id in disabled:
            continue
        tool = plan.catalog.get(tool_id)
        if tool is None:
            plan.missing.append(tool_id)
            continue
        if tool.dest in dests:
            raise AstError(f"{tool_id} and {dests[tool.dest]} would both install to {tool.dest}")
        dests[tool.dest] = tool_id
        src = plan.sources[tool.source]
        plan.tools[tool_id] = tool
        plan.trees[tool_id] = src.repo.tree_id(src.commit, tool.path)
    if strict and plan.missing:
        lines = [f"  {t} ({plan.origins[t]})" for t in plan.missing]
        raise AstError(
            "tools not found in their source:\n" + "\n".join(lines)
            + "\nRemove them with `ast rm` / `ast disable`, or fix the source ref."
        )  # fmt: skip
    return plan


def tree_hash(path: Path) -> str:
    """Content hash of an installed file or directory, to detect local edits."""
    digest = hashlib.sha256()

    def add(p: Path, rel: str) -> None:
        if p.is_symlink():
            digest.update(f"L {rel}\0{os.readlink(p)}\0".encode())
            return
        data = p.read_bytes()
        mode = "x" if p.stat().st_mode & stat.S_IXUSR else "-"
        digest.update(f"F {rel} {mode} {len(data)}\0".encode())
        digest.update(data)

    if path.is_symlink() or path.is_file():
        add(path, "")
    else:
        for p in sorted(path.rglob("*")):
            rel = p.relative_to(path)
            if _IGNORED.intersection(rel.parts) or (p.is_dir() and not p.is_symlink()):
                continue
            add(p, rel.as_posix())
    return "sha256:" + digest.hexdigest()


def installed_state(root: Path, entry: dict) -> str:
    """ok, modified (edited locally since install) or missing."""
    dest = root / entry["dest"]
    if not os.path.lexists(dest):
        return "missing"
    return "ok" if tree_hash(dest) == entry["hash"] else "modified"


def _remove(root: Path, dest: Path) -> None:
    if dest.is_dir() and not dest.is_symlink():
        shutil.rmtree(dest)
    elif os.path.lexists(dest):
        dest.unlink()
    parent = dest.parent
    while parent != root and root in parent.parents and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def apply(plan: Plan, root: Path, lock: Lock, force: bool = False):
    """Install, update and remove files to match the plan, then update the lock in memory.

    Returns (actions, blocked): what was done as (verb, tool id) pairs, and what was left
    alone as (tool id, reason) pairs because it would overwrite local changes.
    """
    actions: list[tuple[str, str]] = []
    blocked: list[tuple[str, str]] = []
    tools: dict[str, dict] = {}

    for tool_id, entry in lock.tools.items():
        wanted = plan.tools.get(tool_id)
        if wanted and wanted.dest == entry["dest"]:
            continue
        state = installed_state(root, entry)
        if state == "modified" and not force:
            blocked.append((tool_id, f"not removed: {entry['dest']} has local changes"))
            tools[tool_id] = entry
            continue
        _remove(root, root / entry["dest"])
        actions.append(("removed", tool_id))

    with tempfile.TemporaryDirectory(prefix="ast-") as tmp:
        for number, (tool_id, tool) in enumerate(plan.tools.items()):
            entry = lock.tools.get(tool_id)
            if entry and entry["dest"] != tool.dest:
                if tool_id in tools:  # removal of the old location was blocked above
                    continue
                entry = None
            dest, tree, src = root / tool.dest, plan.trees[tool_id], plan.sources[tool.source]
            if root.resolve() not in dest.resolve().parents:
                raise AstError(f"{tool_id} would install outside the project: {tool.dest}")
            if entry:
                state = installed_state(root, entry)
                if entry["tree"] == tree and state == "ok":
                    tools[tool_id] = entry
                    continue
                if state == "modified" and not force:
                    if entry["tree"] == tree:
                        actions.append(("modified", tool_id))
                    else:
                        blocked.append((tool_id, f"not updated: {tool.dest} has local changes"))
                    tools[tool_id] = entry
                    continue
                verb = "updated" if entry["tree"] != tree else "restored"
            else:
                verb = "installed"
            staged = src.repo.export(src.commit, tool.path, Path(tmp) / str(number))
            content = tree_hash(staged)
            if not entry and os.path.lexists(dest) and not force:
                if tree_hash(dest) != content:
                    blocked.append((tool_id, f"not installed: {tool.dest} exists and ast does not manage it"))
                    continue
                verb = "adopted"  # already there with identical content
            else:
                _remove(root, dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(staged, dest)
            tools[tool_id] = {
                "path": tool.path, "dest": tool.dest, "commit": src.commit,
                "tree": tree, "hash": content,
            }  # fmt: skip
            actions.append((verb, tool_id))

    # Cards: record each one's index line (from the source's index, else the card's first
    # paragraph), then rewrite the ast block in CARDS.md so agents can find the cards.
    triggers: dict[str, dict[str, str]] = {}
    cards = []
    for tool_id, entry in tools.items():
        if Tool.from_id(tool_id).kind != "card" or not (root / entry["dest"]).exists():
            continue
        tool = plan.tools.get(tool_id)
        if tool and entry["tree"] == plan.trees[tool_id]:  # not a blocked, older copy
            src = plan.sources[tool.source]
            if src.name not in triggers:
                texts = [src.repo.read(src.commit, name) for name in SOURCE_INDEX_FILES]
                triggers[src.name] = source_triggers([t for t in texts if t])
            entry["trigger"] = triggers[src.name].get(tool.name) or summary(root / entry["dest"])
        name = Tool.from_id(tool_id).name
        cards.append((name, entry["dest"], entry.get("trigger") or summary(root / entry["dest"])))
    actions += write_index(root, cards)

    lock.org = plan.org
    lock.sources = {
        s.name: {"repo": s.spec, "ref": s.ref, "commit": s.commit, "label": s.label}
        for s in plan.sources.values()
    }
    lock.tools = tools
    return actions, blocked


def pending(plan: Plan, lock: Lock) -> list[tuple[str, str]]:
    """What applying the plan would change, as (verb, tool id) pairs."""
    changes = []
    for tool_id in plan.tools:
        entry = lock.tools.get(tool_id)
        if entry is None:
            changes.append(("install", tool_id))
        elif entry["tree"] != plan.trees[tool_id]:
            changes.append(("update", tool_id))
    changes += [("remove", t) for t in lock.tools if t not in plan.tools]
    return changes
