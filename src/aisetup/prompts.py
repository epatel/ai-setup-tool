"""Prompts that `ast prompt <name>` prints for a coding agent to follow.

`ast` does the mechanical part of a setup. These prompts cover the part that needs
judgment: which set fits a project, what to do with a blocked file, whether an update
changed the instructions agents read.
"""

from __future__ import annotations

import re

from .errors import AstError

PROMPT_DIR = "prompts/"  # a source repo offers `prompts/<name>.md` as `ast prompt <name>`

_SETUP = """\
# Set up this project's agent tools with ast

You are a coding agent. Set up the agent tools (skills, commands, scripts, cards) of the
project in the current directory with the `ast` command. Do the steps in order. Do not
make a commit.

1. Run `ast status`.
   - If it says there is no `ast.toml`, run `ast init`.
   - If the project already uses ast, show the status to the user and keep the choices it
     has made. Continue with the steps that still apply.
2. {org_step}
3. Choose the set.
   - Run `ast list --tree`. It shows each set, its description, and what it adds and excludes.
   - Look at the project: the README, the manifest files (`pyproject.toml`, `package.json`,
     `Cargo.toml`, `pubspec.yaml`, ...) and the top-level folders.
   - Pick the set whose description fits the project. If two sets fit, or none fits
     clearly, ask the user. Tell the user which set you picked and why.
   - Run `ast select <set>`.
4. Read the output of that command. A line that starts with `blocked` means ast left an
   existing file alone. Do not use `--force`. Show each blocked file to the user and ask
   what to do.
5. Run `ast list --available`. Name the tools outside the set that match this project,
   and the tools in the set that clearly do not apply. Do not change anything yet: run
   `ast add <tool>` or `ast disable <tool>` only for what the user approves.
6. If cards were installed, check that `CLAUDE.md` contains `@CARDS.md`, and read
   `CARDS.md` so that you know when to open each card.
7. If this prompt has a section **Steps from the org repo** at the end, do that section now.
8. Run `ast status` again. It must exit 0 and list every tool as `ok`.
9. Report to the user: the set, the tools installed, anything blocked or skipped, and the
   files to commit (`ast.toml`, `ast.lock`, `.claude/`, `cards/`, `CARDS.md`, `CLAUDE.md`,
   and what the org steps made). Ask if you must make the commit.
"""

_ORG_GIVEN = "Run `ast use {repo}`. This imports the organisation's sources and sets."
_ORG_UNKNOWN = """\
If `ast status` shows no `org:` line, ask the user for the organisation's setup repo
   and run `ast use <repo>`. If there is none, ask which tool repos to reference, run
   `ast source add <repo>` for each, and go to step 5."""

_UPDATE = """\
# Update this project's agent tools with ast

You are a coding agent. Bring the agent tools of the project in the current directory up
to date with the `ast` command. Do the steps in order. Do not make a commit.

1. Run `ast status`.
   - If it reports `modified`, `missing` or `pending` tools, show them to the user and
     settle them first. `ast sync` applies pending changes and restores missing files.
     A `modified` tool has local edits: ask the user if the edits must stay.
   - If it says `no updates available`, tell the user and stop.
2. Show the user the list under `updates available`: the sources that moved, and each
   tool that the update will install, update or remove.
3. Run `ast update`. Do not use `--force`.
   - For each `blocked` line, show `git diff -- <path>` for that tool and ask the user:
     keep the local version, or overwrite it. Overwrite only the tools the user names.
4. Review what changed. The installed files are instructions that every agent in this
   project follows, so read them as a change to the project.
   - Run `git status --short` and `git diff --stat`.
   - Read the diff of each changed skill, command, script and card.
   - Summarise for the user what is different in behaviour. Call out anything that an
     agent will now do differently without being asked: new commands that it runs,
     installs or network access, removed checks, changed rules.
5. Run `ast status`. It must exit 0 and report `no updates available`.
6. Report to the user: the sources and tools that changed, your review, anything blocked.
   Suggest that the update goes on its own branch. Ask if you must make the commit.
"""

_ADOPT = """\
# Bring this project's existing agent tools under ast

You are a coding agent. The project in the current directory already has agent tools that
someone copied in by hand (`.claude/skills/`, `.claude/agents/`, `.claude/commands/`,
`.claude/scripts/`, `cards/`). Make `ast` manage the ones that come from a shared repo.
Do the steps in order. Do not make a commit, and do not use `--force`.

1. Run `ast status`. If there is no `ast.toml`, run `ast init`.
2. List the tools that are in the project now. For each one, find where it came from:
   a comment or link in the file, `.claude/agent-setup.json`, the README, the git log
   (`git log --diff-filter=A --format='%h %s' -- <path>`), or ask the user.
3. Make a table for the user: tool, kind, the repo you think it comes from, and how sure
   you are. Mark the tools that look written for this project only. Those stay as they are.
4. For each source repo the user confirms, run `ast source add <repo> --ref latest-tag`.
   If the repo has no tags, leave out `--ref`. Then run `ast list --available` to see the
   names that the repo offers.
5. Run `ast add <tool>` for each tool that the repo offers and the project has.
   - `adopted` means the copy in the project is the same as the source. ast manages it now.
   - `blocked ... exists and ast does not manage it` means the copy is different from the
     source. Do not overwrite it. Show the user the difference: the copy can be an older
     release, or it can have local edits. Let the user choose for each one: take the
     source version (`ast add <tool> --force`), or keep the copy outside ast.
6. Run `ast status`. Every tool that ast manages must be `ok`.
7. Report to the user: the tools adopted, the tools left alone and why, and the files to
   commit (`ast.toml`, `ast.lock`, and `CARDS.md` and `CLAUDE.md` if they changed). Ask if
   you must make the commit.
"""

_ORG = """\
# Start an org repo for ast

You are a coding agent. Make the current directory an ast org repo: one repo that names
the tool sources of an organisation and the sets of tools that its projects select.
Do the steps in order. Do not make a commit.

1. Run `ast init --org`. If `ast-org.toml` is there already, run `ast list --tree` and
   `ast status`, show both to the user, and continue with what is missing.
2. Find out what the sets must cover. {projects_step}
3. Add the sources. For each repo of tools, run `ast source add <repo> --ref latest-tag`
   (leave out `--ref` if the repo has no tags). If this repo will hold tools of its own
   (`skills/`, `agents/`, `commands/`, `scripts/`, `cards/`, `prompts/`), run
   `ast source add . --name org`. Run `ast list --available` to see every tool.
4. Propose the sets to the user before you make them:
   - `default`: the tools that every project must have. Keep it small.
   - one set for each kind of project, each with `--extends default`
   - a set for one project only when it really differs from its kind
   Show a table: set, what it extends, what it adds, what it excludes, which projects use it.
5. After the user approves, make the sets:
   - `ast add <tool>...` puts tools in `default`
   - `ast set new <name> --extends <parent> --description "<who it is for>"`
   - `ast add <tool>... --set <name>` adds tools to a set
   - `ast disable <tool> --set <name>` excludes a tool that the set gets from its parent
6. If the repo holds cards, write `CARDS.md` with one line for each card:
   `- [name](cards/name.md) — the situation in which an agent must read it`.
7. Run `ast list --tree` and `ast status`. `ast status` must exit 0.
8. Report to the user: the sources, the tree of sets, and how a project uses the repo
   (`ast use <this repo>`, then `ast select <set>`, after this repo has a commit that the
   project can reach). Ask if you must make the commit.
"""

_PROJECTS_GIVEN = """Look at these projects: {projects}.
   For each one, note its kind (language, framework, service or library or docs) and the
   agent tools that it has now (`.claude/`, `cards/`, `ast.toml`)."""
_PROJECTS_UNKNOWN = """Ask the user which projects will use the repo, and what
   kinds of projects they are. If the user names folders or repos, look at each one: its
   kind, and the agent tools that it has now (`.claude/`, `cards/`, `ast.toml`)."""


def setup(args: list[str], org_steps: str | None = None) -> str:
    step = _ORG_GIVEN.format(repo=args[0]) if args else _ORG_UNKNOWN
    text = _SETUP.format(org_step=step)
    if org_steps:
        text += f"\n---\n\n## Steps from the org repo\n\n{org_steps.strip()}\n"
    return text


def update(args: list[str], org_steps: str | None = None) -> str:
    return _UPDATE


def adopt(args: list[str], org_steps: str | None = None) -> str:
    return _ADOPT


def org(args: list[str], org_steps: str | None = None) -> str:
    step = _PROJECTS_GIVEN.format(projects=", ".join(args)) if args else _PROJECTS_UNKNOWN
    return _ORG.format(projects_step=step)


# name -> (one-line description, function that takes the extra arguments)
BUILTIN = {
    "setup": ("set up a project: pick the org set that fits it, install, report (argument: org repo)", setup),
    "adopt": ("bring tools that were copied in by hand under ast", adopt),
    "update": ("update the installed tools and review what changed in them", update),
    "org": ("start an org repo: sources and sets (arguments: projects to look at)", org),
}


def title(text: str, fallback: str) -> str:
    """One-line description of a prompt file: its first heading or first line."""
    for line in text.splitlines():
        if line.strip():
            return line.strip().lstrip("# ").strip() or fallback
    return fallback


_INCLUDE = re.compile(r"^\{\{include ([^}\n]+)\}\}[ \t]*$", re.MULTILINE)


def expand(text: str, read, where: str) -> str:
    """Replace each `{{include path}}` line with that file from the same repo (one level)."""

    def include(match: re.Match) -> str:
        path = match.group(1).strip()
        body = read(path)
        if body is None:
            raise AstError(f"{where}: included file '{path}' not found")
        return body.rstrip("\n")

    return _INCLUDE.sub(include, text)


def fill(text: str, args: list[str]) -> str:
    """Put the extra arguments where the prompt says `$ARGUMENTS`."""
    return text.replace("$ARGUMENTS", " ".join(args))
