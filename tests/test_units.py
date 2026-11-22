import pytest

from aisetup.catalog import Tool, discover, match
from aisetup.config import ProjectConfig, resolve_set
from aisetup.errors import AstError
from aisetup.gitrepo import default_name, normalize_repo, version_key


def test_discover_finds_each_kind_and_ignores_the_rest():
    files = [
        "alpha/SKILL.md", "alpha/references/x.md",
        "skills/beta/SKILL.md",
        ".claude/skills/alpha/SKILL.md",  # a second copy: the root one wins
        "deep/er/gamma/SKILL.md",  # not in a known place
        "agents/reviewer.md", "commands/ship.md", "commands/sub/nested.md",
        "scripts/check.sh", "README.md", "cards/defaults.md", "cards/notes.txt",
    ]  # fmt: skip
    tools = {t.id: t for t in discover("src", files)}
    assert set(tools) == {
        "src:skill/alpha", "src:skill/beta", "src:agent/reviewer", "src:command/ship", "src:script/check.sh", "src:card/defaults",
    }  # fmt: skip
    assert tools["src:skill/alpha"].path == "alpha"
    assert tools["src:skill/beta"].dest == ".claude/skills/beta"
    assert tools["src:agent/reviewer"].dest == ".claude/agents/reviewer.md"
    assert tools["src:script/check.sh"].dest == ".claude/scripts/check.sh"
    assert tools["src:card/defaults"].dest == "cards/defaults.md"


def test_match_accepts_short_and_full_names():
    catalog = {t.id: t for t in [Tool("a", "skill", "x"), Tool("b", "skill", "x"), Tool("a", "agent", "y")]}
    assert match(catalog, "y").id == "a:agent/y"
    assert match(catalog, "b:x").id == "b:skill/x"
    assert match(catalog, "a:skill/x").id == "a:skill/x"
    with pytest.raises(AstError, match="ambiguous"):
        match(catalog, "x")
    with pytest.raises(AstError, match="no tool matches"):
        match(catalog, "zzz")


def _set(tools=(), extends=(), exclude=()):
    return {"description": "", "tools": list(tools), "extends": list(extends), "exclude": list(exclude)}


def test_resolve_set_extends_adds_and_excludes():
    sets = {
        "default": _set(["s:skill/a", "s:skill/b"]),
        "fenix": _set(["s:skill/c"], extends=["default"], exclude=["s:skill/b"]),
        "fenix-web": _set(["s:skill/b"], extends=["fenix"]),
    }
    assert resolve_set(sets, "fenix") == {"s:skill/a": "default", "s:skill/c": "fenix"}
    assert list(resolve_set(sets, "fenix-web")) == ["s:skill/a", "s:skill/c", "s:skill/b"]


def test_resolve_set_reports_cycles_and_unknown_sets():
    with pytest.raises(AstError, match="cycle"):
        resolve_set({"a": _set(extends=["b"]), "b": _set(extends=["a"])}, "a")
    with pytest.raises(AstError, match="unknown set 'nope'"):
        resolve_set({"a": _set(extends=["nope"])}, "a")


def test_version_key_sorts_release_tags():
    tags = ["v2026.11.14", "v2026.11.14.2", "v2026.9.30", "v2026.12.1"]
    assert sorted(tags, key=version_key) == ["v2026.9.30", "v2026.11.14", "v2026.11.14.2", "v2026.12.1"]


def test_repo_specs(tmp_path):
    assert normalize_repo("epatel/agent-skills", tmp_path) == "https://github.com/epatel/agent-skills.git"
    assert normalize_repo("../x", tmp_path / "p") == str((tmp_path / "x").resolve())
    assert normalize_repo("git@host:team/tools.git", tmp_path) == "git@host:team/tools.git"
    assert default_name("git@host:team/tools.git") == "tools"
    assert default_name("https://github.com/epatel/agent-skills/") == "agent-skills"


def test_config_from_newer_ast_is_refused(tmp_path):
    (tmp_path / "ast.toml").write_text("version = 99\n")
    with pytest.raises(AstError, match="upgrade ast"):
        ProjectConfig.load(tmp_path)


def test_help_command(ast, tmp_path):
    code, out, _ = ast(tmp_path, "help")
    assert code == 0 and "usage: ast" in out and "select" in out
    code, out, _ = ast(tmp_path, "help", "update")
    assert code == 0 and "usage: ast update" in out
    code, _, err = ast(tmp_path, "help", "nope")
    assert code == 2 and "unknown command 'nope'" in err
