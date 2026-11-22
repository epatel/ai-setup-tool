"""Cached bare clones of source repos, read with plain git commands."""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

from .errors import AstError

LATEST_TAG = "latest-tag"

_fetched: set[str] = set()  # URLs fetched in this process, so each is fetched at most once


def cache_dir() -> Path:
    if os.environ.get("AST_CACHE_DIR"):
        return Path(os.environ["AST_CACHE_DIR"])
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "ast"


def is_local(spec: str) -> bool:
    return spec in (".", "..") or spec.startswith(("./", "../", "/", "~"))


def normalize_repo(spec: str, base: Path) -> str:
    """Turn a repo as written in a config file into something git can clone."""
    if is_local(spec):
        return str((base / Path(spec).expanduser()).resolve())
    if re.fullmatch(r"[\w.-]+/[\w.-]+", spec):
        return f"https://github.com/{spec}.git"
    return spec


def default_name(spec: str) -> str:
    name = spec.rstrip("/").removesuffix(".git").replace(":", "/").split("/")[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "source"


def version_key(tag: str) -> list:
    """Sort key that orders v2026.11.14 < v2026.11.14.2 < v2026.12.1, like `sort -V`."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", tag)]


def _git(*args: str, git_dir: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["git"]
    if git_dir is not None:
        cmd += ["--git-dir", str(git_dir)]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.run([*cmd, *args], capture_output=True, env=env, check=False)
    except FileNotFoundError:
        raise AstError("git is not installed or not on PATH") from None
    if check and proc.returncode:
        detail = proc.stderr.decode(errors="replace").strip()
        raise AstError(f"git {' '.join(args)} failed: {detail}")
    return proc


class Repo:
    def __init__(self, url: str, offline: bool = False):
        self.url = url
        self.offline = offline
        digest = hashlib.sha256(url.encode()).hexdigest()[:12]
        self.dir = cache_dir() / "repos" / f"{default_name(url)}-{digest}"

    def _ensure(self) -> None:
        if self.dir.exists():
            return
        if self.offline:
            raise AstError(f"{self.url} is not in the cache and --offline was given")
        tmp = self.dir.with_name(self.dir.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--quiet", "--bare", self.url, str(tmp))
        tmp.rename(self.dir)
        _fetched.add(self.url)

    def fetch(self) -> None:
        self._ensure()
        if self.offline or self.url in _fetched:
            return
        _git(
            "fetch", "--quiet", "--prune", "--tags", "--force", "origin",
            "+refs/heads/*:refs/heads/*",
            git_dir=self.dir,
        )  # fmt: skip
        _fetched.add(self.url)

    def has_commit(self, commit: str) -> bool:
        self._ensure()
        return _git("cat-file", "-e", f"{commit}^{{commit}}", git_dir=self.dir, check=False).returncode == 0

    def resolve(self, ref: str | None) -> tuple[str, str]:
        """Fetch, then return (commit, label) for a tag, branch, commit, `latest-tag`, or HEAD."""
        self.fetch()
        label = ref or "HEAD"
        if ref == LATEST_TAG:
            tags = _git("tag", "--list", git_dir=self.dir).stdout.decode().split()
            if not tags:
                raise AstError(f"{self.url} has no tags, so ref '{LATEST_TAG}' cannot be resolved")
            label = max(tags, key=version_key)
        proc = _git("rev-parse", "--verify", "--quiet", f"{label}^{{commit}}", git_dir=self.dir, check=False)
        if proc.returncode:
            raise AstError(f"ref '{label}' not found in {self.url}")
        return proc.stdout.decode().strip(), label

    def files(self, commit: str) -> list[str]:
        out = _git("ls-tree", "-r", "--name-only", "-z", commit, git_dir=self.dir).stdout.decode()
        return [p for p in out.split("\0") if p]

    def tree_id(self, commit: str, path: str) -> str:
        """Git object id of a file or directory at a commit: changes when its content does."""
        return _git("rev-parse", f"{commit}:{path}", git_dir=self.dir).stdout.decode().strip()

    def read(self, commit: str, path: str) -> str | None:
        proc = _git("show", f"{commit}:{path}", git_dir=self.dir, check=False)
        return None if proc.returncode else proc.stdout.decode()

    def export(self, commit: str, path: str, target: Path) -> Path:
        """Extract a file or directory at a commit under `target`; return where it landed."""
        data = _git("archive", "--format=tar", commit, "--", path, git_dir=self.dir).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(target, filter="data")
        return target / path
