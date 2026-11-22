"""The `ast` command line."""

from __future__ import annotations

import argparse
import os
import sys
from importlib import metadata
from pathlib import Path

from .catalog import Tool, discover, match, resolve_id
from .config import (
    ORG_FILE,
    ORG_TEMPLATE,
    PROJECT_FILE,
    PROJECT_TEMPLATE,
    OrgConfig,
    ProjectConfig,
    resolve_set,
)
from .engine import LOCK_FILE, Lock, apply, build_plan, installed_state, pending
from .errors import AstError
from .gitrepo import Repo, default_name, is_local, normalize_repo

# ---------------------------------------------------------------- shared helpers


def table(rows: list[list[str]], indent: str = "  ") -> None:
    if not rows:
        return
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        print(indent + "  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())


def find_root(args) -> tuple[str, Path]:
    """Walk up from the working directory to the nearest ast.toml or ast-org.toml."""
    org_only = args.org or bool(getattr(args, "set", None))
    start = Path(args.directory or ".").resolve()
    for directory in (start, *start.parents):
        if not org_only and (directory / PROJECT_FILE).exists():
            return "project", directory
        if (directory / ORG_FILE).exists():
            return "org", directory
    if org_only:
        raise AstError(f"no {ORG_FILE} found here or in a parent directory (run `ast init --org`)")
    raise AstError(f"no {PROJECT_FILE} found here or in a parent directory (run `ast init`)")


def load_project(args) -> tuple[ProjectConfig, Lock]:
    mode, root = find_root(args)
    if mode != "project":
        raise AstError(f"this command works in a project, but {root} is an org repo")
    return ProjectConfig.load(root), Lock(root / LOCK_FILE)


def sync(cfg: ProjectConfig, lock: Lock, args, refresh: bool | set[str] = False) -> int:
    """Apply the config to the project's files, then save config and lock."""
    plan = build_plan(cfg, lock, refresh=refresh, offline=args.offline)
    before = {name: s.get("commit") for name, s in lock.sources.items()}
    actions, blocked = apply(plan, cfg.root, lock, force=getattr(args, "force", False))
    cfg.save()
    lock.save()
    for src in plan.sources.values():
        old = before.get(src.name)
        if old and old != src.commit:
            print(f"{src.name}: {old[:7]} -> {src.label} ({src.commit[:7]})")
    for verb, tool_id in actions:
        note = "  (local changes kept)" if verb == "modified" else ""
        print(f"{verb:<10} {tool_id}{note}")
    for tool_id, why in blocked:
        print(f"blocked    {tool_id}: {why} (use --force to overwrite)", file=sys.stderr)
    if not actions and not blocked:
        print("up to date")
    return 1 if blocked else 0


def walk_files(root: Path) -> list[str]:
    files = []
    for directory, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        files += [(Path(directory) / n).relative_to(root).as_posix() for n in names]
    return files


def org_catalog(org: OrgConfig, offline: bool) -> tuple[dict[str, Tool], list[list[str]]]:
    """Tools offered by an org repo's sources, read from the working tree for source '.'."""
    catalog: dict[str, Tool] = {}
    rows = []
    for name, entry in org.sources.items():
        spec, ref = entry.get("repo", ""), entry.get("ref")
        if spec == ".":
            files, where = walk_files(org.root), "working tree"
        elif is_local(spec):
            raise AstError(f"org source '{name}': only '.' may be used as a local repo path")
        else:
            repo = Repo(normalize_repo(spec, org.root), offline)
            commit, label = repo.resolve(ref)
            files, where = repo.files(commit), f"{label} ({commit[:7]})"
        for tool in discover(name, files):
            catalog[tool.id] = tool
        rows.append([name, spec, where])
    return catalog, rows


def org_set(org: OrgConfig, args) -> tuple[str, dict]:
    name = args.set or "default"
    sets = org.sets
    if name not in sets:
        raise AstError(f"unknown set '{name}'; sets: {', '.join(sorted(sets)) or 'none'}")
    return name, sets[name]


# ---------------------------------------------------------------- commands


def cmd_init(args) -> int:
    root = Path(args.directory or ".").resolve()
    name, template = (ORG_FILE, ORG_TEMPLATE) if args.org else (PROJECT_FILE, PROJECT_TEMPLATE)
    path = root / name
    if path.exists():
        raise AstError(f"{path} already exists")
    path.write_text(template)
    print(f"created {path}")
    if args.org:
        print("next: `ast source add <repo>`, then `ast add <tool> --set default`")
    else:
        print("next: `ast use <org repo>` or `ast source add <repo>`, then `ast list --available`")
    return 0


def cmd_source(args) -> int:
    mode, root = find_root(args)
    cfg = OrgConfig.load(root) if mode == "org" else ProjectConfig.load(root)
    if args.action == "list":
        if mode == "org":
            table(org_catalog(cfg, args.offline)[1])
        else:
            plan = build_plan(cfg, Lock(root / LOCK_FILE), offline=args.offline, strict=False)
            table([
                [s.name, s.spec, f"{s.label} ({s.commit[:7]})", s.origin]
                for s in plan.sources.values()
            ])  # fmt: skip
        return 0
    if args.action == "add":
        name = args.name or default_name(args.repo)
        if name in cfg.sources:
            raise AstError(f"source '{name}' already exists (pick another with --name)")
        cfg.add_source(name, args.repo, args.ref)
    else:
        name = args.name
        if name not in cfg.sources:
            raise AstError(f"no source '{name}' in {cfg.path.name}")
        if mode == "org":
            users = [t for s in cfg.sets.values() for t in s["tools"] + s["exclude"]]
        else:
            users = cfg.added
        users = sorted({t for t in users if t.startswith(name + ":")})
        if users:
            raise AstError(f"source '{name}' is still used by: {', '.join(users)}")
        cfg.remove_source(name)
    if mode == "project":
        return sync(cfg, Lock(root / LOCK_FILE), args)
    catalog, _ = org_catalog(cfg, args.offline)  # proves the source is reachable before saving
    cfg.save()
    if args.action == "add":
        count = sum(1 for t in catalog.values() if t.source == name)
        print(f"added source '{name}' ({count} tools)")
    else:
        print(f"removed source '{name}'")
    return 0


def cmd_use(args) -> int:
    cfg, lock = load_project(args)
    if args.remove:
        cfg.clear_org()
        return sync(cfg, lock, args)
    if not args.repo:
        raise AstError("give the org repo: `ast use <repo>` (or `ast use --remove`)")
    previous = (cfg.org or {}).get("set")
    cfg.set_org(args.repo, args.ref)
    plan = build_plan(cfg, lock, offline=args.offline, strict=False)
    sets = plan.org_config.sets
    chosen = args.pick or (previous if previous in sets else None)
    chosen = chosen or (next(iter(sets)) if len(sets) == 1 else None)
    if chosen and chosen not in sets:
        raise AstError(f"unknown set '{chosen}'; sets: {', '.join(sorted(sets)) or 'none'}")
    cfg.select_set(chosen)
    code = sync(cfg, lock, args)
    if chosen:
        print(f"using set '{chosen}' from {args.repo}")
    else:
        print(f"using {args.repo}; pick a set with `ast select <set>`:")
        table([[name, s["description"]] for name, s in sets.items()])
    return code


def cmd_select(args) -> int:
    cfg, lock = load_project(args)
    if not cfg.org:
        raise AstError("no org repo in use (run `ast use <org repo>` first)")
    plan = build_plan(cfg, lock, offline=args.offline, strict=False)
    sets = plan.org_config.sets
    if not args.name:
        current = cfg.org.get("set")
        table([
            ["*" if name == current else " ", name, f"{len(resolve_set(sets, name))} tools", s["description"]]
            for name, s in sets.items()
        ], indent="")  # fmt: skip
        return 0
    if args.name not in sets:
        raise AstError(f"unknown set '{args.name}'; sets: {', '.join(sorted(sets)) or 'none'}")
    cfg.select_set(args.name)
    return sync(cfg, lock, args)


def cmd_list(args) -> int:
    mode, root = find_root(args)
    if mode == "org":
        return list_org(OrgConfig.load(root), args)
    cfg, lock = ProjectConfig.load(root), Lock(root / LOCK_FILE)
    plan = build_plan(cfg, lock, offline=args.offline, strict=False)
    rows = []
    for tool_id, origin in plan.origins.items():
        if tool_id in plan.tools:
            entry = lock.tools.get(tool_id)
            rows.append([tool_id, origin, installed_state(root, entry) if entry else "pending"])
        elif tool_id in plan.missing:
            rows.append([tool_id, origin, "not found in source"])
    if rows:
        print("Active:")
        table(rows)
    else:
        print("No active tools. Add one with `ast add <tool>`.")
    disabled = cfg.disabled
    if disabled:
        print("Disabled:")
        table([[t, plan.origins.get(t, "")] for t in disabled])
    if args.available:
        rest = [[t] for t in plan.catalog if t not in plan.origins]
        print("Available:" if rest else "Available: nothing more")
        table(rest)
    return 0


def list_org(org: OrgConfig, args) -> int:
    sets = org.sets
    catalog, _ = org_catalog(org, args.offline)
    used: set[str] = set()
    for name in [args.set] if args.set else sets:
        resolved = resolve_set(sets, name)
        used.update(resolved)
        extends = sets[name]["extends"]
        print(f"{name}" + (f" (extends {', '.join(extends)})" if extends else "") + ":")
        table([
            [t, "" if origin == name else f"from {origin}", "" if t in catalog else "not found in source"]
            for t, origin in resolved.items()
        ] or [["(empty)"]])  # fmt: skip
        if sets[name]["exclude"]:
            print("  excluded: " + ", ".join(sets[name]["exclude"]))
    if args.available:
        rest = [[t] for t in catalog if t not in used]
        print("Available:" if rest else "Available: nothing more")
        table(rest)
    return 0


def cmd_add(args) -> int:
    mode, root = find_root(args)
    if mode == "org":
        org = OrgConfig.load(root)
        name, current = org_set(org, args)
        catalog, _ = org_catalog(org, args.offline)
        for query in args.tools:
            tool_id = match(catalog, query).id
            if tool_id in current["exclude"]:
                current["exclude"].remove(tool_id)
            if tool_id not in resolve_set(org.sets, name) and tool_id not in current["tools"]:
                current["tools"].append(tool_id)
            org.set_lists(name, current["tools"], current["exclude"])
            print(f"{tool_id} is in set '{name}'")
        org.save()
        return 0
    cfg, lock = ProjectConfig.load(root), Lock(root / LOCK_FILE)
    plan = build_plan(cfg, lock, offline=args.offline, strict=False)
    added, disabled = cfg.added, cfg.disabled
    for query in args.tools:
        tool_id = match(plan.catalog, query).id
        if tool_id in disabled:
            disabled.remove(tool_id)
        if tool_id not in plan.set_tools and tool_id not in added:
            added.append(tool_id)
    cfg.set_tools(added, disabled)
    return sync(cfg, lock, args)


def cmd_rm(args) -> int:
    mode, root = find_root(args)
    if mode == "org":
        org = OrgConfig.load(root)
        name, current = org_set(org, args)
        catalog, _ = org_catalog(org, args.offline)
        for query in args.tools:
            tool_id = resolve_id(query, catalog, set(resolve_set(org.sets, name)) | set(current["tools"]))
            if tool_id not in current["tools"]:
                if tool_id in resolve_set(org.sets, name):
                    raise AstError(
                        f"{tool_id} is inherited by '{name}'; exclude it with `ast disable {query} --set {name}`"
                    )
                raise AstError(f"{tool_id} is not in set '{name}'")
            current["tools"].remove(tool_id)
            org.set_lists(name, current["tools"], current["exclude"])
            print(f"removed {tool_id} from set '{name}'")
        org.save()
        return 0
    cfg, lock = ProjectConfig.load(root), Lock(root / LOCK_FILE)
    plan = build_plan(cfg, lock, offline=args.offline, strict=False)
    added, disabled = cfg.added, cfg.disabled
    for query in args.tools:
        tool_id = resolve_id(query, plan.catalog, set(plan.origins) | set(disabled))
        if tool_id not in added:
            if tool_id in plan.set_tools:
                raise AstError(
                    f"{tool_id} comes from set '{plan.set_tools[tool_id]}'; "
                    f"turn it off for this project with `ast disable {query}`"
                )
            raise AstError(f"{tool_id} was not added to this project")
        added.remove(tool_id)
        if tool_id in disabled and tool_id not in plan.set_tools:
            disabled.remove(tool_id)
    cfg.set_tools(added, disabled)
    return sync(cfg, lock, args)


def cmd_toggle(args) -> int:
    """`ast enable` and `ast disable`: per project, or as a set's exclude list in an org repo."""
    enable = args.command == "enable"
    mode, root = find_root(args)
    if mode == "org":
        org = OrgConfig.load(root)
        name, current = org_set(org, args)
        catalog, _ = org_catalog(org, args.offline)
        inherited: dict[str, str] = {}
        for parent in current["extends"]:
            inherited.update(resolve_set(org.sets, parent))
        for query in args.tools:
            tool_id = resolve_id(query, catalog, set(inherited) | set(current["exclude"]))
            if enable:
                if tool_id not in current["exclude"]:
                    raise AstError(f"{tool_id} is not excluded from set '{name}'")
                current["exclude"].remove(tool_id)
            elif tool_id not in inherited:
                raise AstError(f"{tool_id} is not inherited by set '{name}' (use `ast rm --set {name}`)")
            elif tool_id not in current["exclude"]:
                current["exclude"].append(tool_id)
            org.set_lists(name, current["tools"], current["exclude"])
            print(f"{tool_id} {'included in' if enable else 'excluded from'} set '{name}'")
        org.save()
        return 0
    cfg, lock = ProjectConfig.load(root), Lock(root / LOCK_FILE)
    plan = build_plan(cfg, lock, offline=args.offline, strict=False)
    added, disabled = cfg.added, cfg.disabled
    for query in args.tools:
        tool_id = resolve_id(query, plan.catalog, set(plan.origins) | set(disabled))
        if tool_id not in plan.origins:
            raise AstError(f"{tool_id} is not part of this project (add it with `ast add {query}`)")
        if enable and tool_id in disabled:
            disabled.remove(tool_id)
        elif not enable and tool_id not in disabled:
            disabled.append(tool_id)
    cfg.set_tools(added, disabled)
    return sync(cfg, lock, args)


def cmd_sync(args) -> int:
    cfg, lock = load_project(args)
    return sync(cfg, lock, args)


def cmd_update(args) -> int:
    cfg, lock = load_project(args)
    if args.sources:
        known = build_plan(cfg, lock, offline=args.offline, strict=False).sources
        unknown = [s for s in args.sources if s not in known]
        if unknown:
            raise AstError(f"unknown source: {', '.join(unknown)}; sources: {', '.join(known) or 'none'}")
    return sync(cfg, lock, args, refresh=set(args.sources) or True)


def cmd_status(args) -> int:
    mode, root = find_root(args)
    if mode == "org":
        return status_org(OrgConfig.load(root), args)
    cfg, lock = ProjectConfig.load(root), Lock(root / LOCK_FILE)
    plan = build_plan(cfg, lock, offline=args.offline, strict=False)
    drift = False
    if plan.org:
        chosen = plan.org.get("set") or "none selected (run `ast select`)"
        print(f"org: {plan.org['repo']} @ {plan.org['label']} ({plan.org['commit'][:7]}), set: {chosen}")
    if plan.sources:
        print("sources:")
        table([[s.name, s.spec, f"{s.label} ({s.commit[:7]})"] for s in plan.sources.values()])
    if lock.tools:
        print("tools:")
        rows = []
        for tool_id, entry in lock.tools.items():
            state = installed_state(root, entry)
            drift |= state != "ok"
            rows.append([state, tool_id, entry["dest"]])
        table(rows)
    else:
        print("no tools installed")
    changes = pending(plan, lock)
    if changes or plan.missing:
        drift = True
        print("pending (run `ast sync`):")
        table([list(c) for c in changes] + [["not found", t] for t in plan.missing])
    if not args.offline:
        try:
            fresh = build_plan(cfg, lock, refresh=True, strict=False)
        except AstError as e:
            print(f"could not check for updates: {e}", file=sys.stderr)
        else:
            rows = []
            if plan.org and fresh.org["commit"] != plan.org["commit"]:
                rows.append(["org", f"{plan.org['commit'][:7]} -> {fresh.org['commit'][:7]}"])
            for name, src in fresh.sources.items():
                old = plan.sources.get(name)
                if old and old.commit != src.commit and src.spec != ".":
                    rows.append([name, f"{old.label} ({old.commit[:7]}) -> {src.label} ({src.commit[:7]})"])
            for tool_id in fresh.tools:
                if tool_id not in plan.tools:
                    rows.append(["install", tool_id])
                elif fresh.trees[tool_id] != plan.trees[tool_id]:
                    rows.append(["update", tool_id])
            rows += [["remove", t] for t in plan.tools if t not in fresh.tools]
            if rows:
                print("updates available (run `ast update`):")
                table(rows)
            else:
                print("no updates available")
    return 1 if drift else 0


def status_org(org: OrgConfig, args) -> int:
    catalog, rows = org_catalog(org, args.offline)
    print("sources:")
    table(rows or [["(none)"]])
    problems = 0
    print("sets:")
    for name in org.sets:
        resolved = resolve_set(org.sets, name)
        absent = [t for t in resolved if t not in catalog]
        problems += len(absent)
        print(f"  {name}: {len(resolved)} tools" + ("" if not absent else f", {len(absent)} not found:"))
        table([[t] for t in absent], indent="    ")
    return 1 if problems else 0


def cmd_set(args) -> int:
    args.org = True
    _, root = find_root(args)
    org = OrgConfig.load(root)
    sets = org.sets
    if args.action == "list":
        table([
            [name, f"{len(resolve_set(sets, name))} tools", ", ".join(s["extends"]), s["description"]]
            for name, s in sets.items()
        ], indent="")  # fmt: skip
        return 0
    if args.action == "new":
        if args.name in sets:
            raise AstError(f"set '{args.name}' already exists")
        extends = [e for e in (args.extends or "").split(",") if e]
        unknown = [e for e in extends if e not in sets]
        if unknown:
            raise AstError(f"cannot extend unknown set: {', '.join(unknown)}")
        org.add_set(args.name, extends, args.description or "")
        org.save()
        print(f"created set '{args.name}'")
        return 0
    if args.name not in sets:
        raise AstError(f"unknown set '{args.name}'; sets: {', '.join(sorted(sets)) or 'none'}")
    users = [n for n, s in sets.items() if args.name in s["extends"]]
    if users:
        raise AstError(f"set '{args.name}' is extended by: {', '.join(users)}")
    org.remove_set(args.name)
    org.save()
    print(f"removed set '{args.name}'")
    return 0


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    try:
        version = metadata.version("ai-setup-tool")
    except metadata.PackageNotFoundError:
        version = "unknown"
    parser = argparse.ArgumentParser(
        prog="ast",
        description="AI setup tool: manage a project's agentic tools (skills, agents, commands, "
        "scripts) from referenced repos and org-wide sets.",
    )
    parser.add_argument("--version", action="version", version=f"ast {version}")
    parser.add_argument("-C", dest="directory", metavar="DIR", help="run as if started in DIR")
    parser.add_argument("--org", action="store_true", help="act on the org repo (ast-org.toml)")
    parser.add_argument("--offline", action="store_true", help="do not fetch from remotes")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    def command(name: str, func, help: str, *, tools=False, set_=False, force=False):
        p = sub.add_parser(name, help=help, description=help)
        p.set_defaults(func=func)
        # the global flags are also accepted after the command name
        p.add_argument("--org", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        p.add_argument("--offline", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        if tools:
            p.add_argument("tools", nargs="+", metavar="tool", help="name, kind/name or source:kind/name")
        if set_:
            p.add_argument("--set", metavar="SET", help="in an org repo: the set to act on (default: default)")
        if force:
            p.add_argument("--force", action="store_true", help="overwrite local changes to installed tools")
        return p

    command("init", cmd_init, "create ast.toml here (or ast-org.toml with --org)")

    p = command("source", cmd_source, "add, remove or list the repos that tools come from")
    actions = p.add_subparsers(dest="action", required=True, metavar="action")
    a = actions.add_parser("add", help="reference a repo that holds tools")
    a.add_argument("repo", help="git URL, GitHub owner/repo, or a local path starting with ./ ../ / or ~")
    a.add_argument("--name", help="name for the source (default: from the repo)")
    a.add_argument("--ref", help="tag, branch, commit, or 'latest-tag' (default: the default branch)")
    a = actions.add_parser("rm", help="drop a source")
    a.add_argument("name")
    actions.add_parser("list", help="list sources and the commit each is at")

    p = command("use", cmd_use, "import an org repo's sets into this project", force=True)
    p.add_argument("repo", nargs="?", help="org repo: git URL, GitHub owner/repo, or local path")
    p.add_argument("--ref", help="tag, branch, commit, or 'latest-tag'")
    p.add_argument("--set", dest="pick", metavar="SET", help="select this set right away")
    p.add_argument("--remove", action="store_true", help="stop using the org repo")

    p = command("select", cmd_select, "select a set from the org repo (no name: list the sets)", force=True)
    p.add_argument("name", nargs="?")

    p = command("list", cmd_list, "list active tools", set_=True)
    p.add_argument("-a", "--available", action="store_true", help="also list tools not in use")

    command("add", cmd_add, "add tools to the project (or to a set in an org repo)", tools=True, set_=True, force=True)
    command("rm", cmd_rm, "remove tools you added (or from a set in an org repo)", tools=True, set_=True, force=True)
    command("enable", cmd_toggle, "turn a disabled tool back on", tools=True, set_=True, force=True)
    command("disable", cmd_toggle, "turn a tool off without removing it from the config", tools=True, set_=True, force=True)
    command("status", cmd_status, "show installed tools, local changes and available updates")
    command("sync", cmd_sync, "make installed files match ast.toml and ast.lock", force=True)
    p = command("update", cmd_update, "move sources to the newest commit of their ref and reinstall", force=True)
    p.add_argument("sources", nargs="*", metavar="source", help="only these sources (default: all, and the org repo)")

    p = command("set", cmd_set, "manage sets in an org repo")
    actions = p.add_subparsers(dest="action", required=True, metavar="action")
    actions.add_parser("list", help="list sets")
    a = actions.add_parser("new", help="create a set")
    a.add_argument("name")
    a.add_argument("--extends", metavar="SET[,SET]", help="sets this one builds on")
    a.add_argument("--description")
    a = actions.add_parser("rm", help="delete a set")
    a.add_argument("name")

    def cmd_help(args) -> int:
        target = sub.choices.get(args.topic) if args.topic else parser
        if target is None:
            raise AstError(f"unknown command '{args.topic}'; commands: {', '.join(sub.choices)}")
        target.print_help()
        return 0

    p = command("help", cmd_help, "show help for ast, or for one command")
    p.add_argument("topic", nargs="?", metavar="command")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except AstError as e:
        print(f"ast: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
