from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aisetup import gitrepo
from aisetup.cli import main


def git(cwd: Path, *args: str) -> str:
    cmd = ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args]
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, files: dict[str, str | None], tag: str | None = None) -> str:
    """Write files (None deletes), commit, optionally tag. Returns the commit id."""
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q", "-b", "main")
    for name, content in files.items():
        path = repo / name
        if content is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    if tag:
        git(repo, "tag", tag)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AST_CACHE_DIR", str(tmp_path / "cache"))
    gitrepo._fetched.clear()


@pytest.fixture
def ast(capsys):
    """Run the CLI like a new process would; returns (exit code, stdout, stderr)."""

    def run(cwd: Path, *argv: str):
        gitrepo._fetched.clear()
        code = main(["-C", str(cwd), *argv])
        out = capsys.readouterr()
        return code, out.out, out.err

    return run


@pytest.fixture
def source(tmp_path) -> Path:
    """A tool repo with two skills, an agent, a command and a script."""
    repo = tmp_path / "tools"
    commit(
        repo,
        {
            "alpha/SKILL.md": "alpha v1\n",
            "alpha/references/notes.md": "notes\n",
            "skills/beta/SKILL.md": "beta v1\n",
            "agents/reviewer.md": "reviewer\n",
            "commands/ship.md": "ship\n",
            "scripts/check.sh": "#!/bin/sh\n",
            "cards/defaults.md": "# Defaults\n\n## Problem\n\nTeams pick different defaults.\n\nMore text.\n",
            "cards/naming.md": "# Naming\n\nHow we name things.\n",
            "CARDS.md": "# Cards\n\n- [defaults](cards/defaults.md) — choosing a default for a new service\n",
            "README.md": "not a tool\n",
            "prompts/tidy.md": "# Tidy the repo\n\nTidy $ARGUMENTS now.\n",
        },
    )
    return repo


@pytest.fixture
def project(tmp_path, ast) -> Path:
    path = tmp_path / "project"
    path.mkdir()
    assert ast(path, "init")[0] == 0
    return path
