import pytest
from conftest import commit, git


@pytest.fixture
def org(tmp_path, ast, source):
    """An org repo built with ast itself: default set, and proj-fenix that extends it."""
    repo = tmp_path / "org"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    assert ast(repo, "init", "--org")[0] == 0
    commit(repo, {"skills/house-style/SKILL.md": "house style\n"})
    assert ast(repo, "source", "add", source.as_uri(), "--name", "tools")[0] == 0
    assert ast(repo, "source", "add", ".", "--name", "org")[0] == 0
    assert ast(repo, "add", "alpha", "beta", "house-style")[0] == 0  # goes to set 'default'
    assert ast(repo, "set", "new", "proj-fenix", "--extends", "default", "--description", "Fenix")[0] == 0
    assert ast(repo, "add", "reviewer", "--set", "proj-fenix")[0] == 0
    assert ast(repo, "disable", "beta", "--set", "proj-fenix")[0] == 0
    commit(repo, {})
    return repo


def test_org_repo_is_managed_with_ast(ast, org):
    config = (org / "ast-org.toml").read_text()
    assert "[sets.proj-fenix]" in config and 'extends = [' in config and '"tools:skill/beta"' in config
    code, out, _ = ast(org, "status")
    assert code == 0 and "proj-fenix: 3 tools" in out and "default: 3 tools" in out
    _, out, _ = ast(org, "list", "--set", "proj-fenix")
    assert "tools:skill/alpha      from default" in out and "excluded: tools:skill/beta" in out

    code, _, err = ast(org, "rm", "alpha", "--set", "proj-fenix")
    assert code == 2 and "inherited" in err
    code, _, err = ast(org, "set", "rm", "default")
    assert code == 2 and "extended by" in err
    assert ast(org, "enable", "beta", "--set", "proj-fenix")[0] == 0
    assert "proj-fenix: 4 tools" in ast(org, "status")[1]


def test_project_uses_and_selects_a_set(ast, project, org):
    code, out, _ = ast(project, "use", "../org")
    assert code == 0 and "pick a set" in out and "proj-fenix" in out
    assert not (project / ".claude").exists()

    code, out, _ = ast(project, "select", "proj-fenix")
    assert code == 0
    assert (project / ".claude/skills/alpha/SKILL.md").exists()
    assert (project / ".claude/skills/house-style/SKILL.md").read_text() == "house style\n"
    assert (project / ".claude/agents/reviewer.md").exists()
    assert not (project / ".claude/skills/beta").exists()
    assert "*  proj-fenix" in ast(project, "select")[1]
    _, out, _ = ast(project, "list")
    assert "set:default" in out and "set:proj-fenix" in out

    assert ast(project, "select", "default")[0] == 0
    assert (project / ".claude/skills/beta").exists()
    assert not (project / ".claude/agents/reviewer.md").exists()


def test_project_adjusts_its_set_locally(ast, project, org):
    ast(project, "use", "../org", "--set", "default")
    code, _, err = ast(project, "rm", "alpha")
    assert code == 2 and "ast disable" in err
    assert ast(project, "disable", "alpha")[0] == 0
    assert not (project / ".claude/skills/alpha").exists()
    assert ast(project, "add", "ship")[0] == 0  # a tool outside the set, from an org source
    assert (project / ".claude/commands/ship.md").exists()
    config = (project / "ast.toml").read_text()
    assert '"tools:command/ship"' in config and '"tools:skill/alpha"' in config
    assert ast(project, "add", "alpha")[0] == 0  # adding a disabled set tool re-enables it
    assert (project / ".claude/skills/alpha").exists()


def test_org_changes_reach_projects_on_update(ast, project, org):
    ast(project, "use", "../org", "--set", "default")
    ast(org, "rm", "beta")
    ast(org, "add", "ship")
    commit(org, {"skills/house-style/SKILL.md": "house style v2\n"})

    code, out, _ = ast(project, "status")
    assert code == 0 and "updates available" in out
    assert "install  tools:command/ship" in out and "remove   tools:skill/beta" in out
    assert (project / ".claude/skills/beta").exists()  # nothing changes until update

    assert ast(project, "update")[0] == 0
    assert not (project / ".claude/skills/beta").exists()
    assert (project / ".claude/commands/ship.md").exists()
    assert (project / ".claude/skills/house-style/SKILL.md").read_text() == "house style v2\n"


def test_use_remove_uninstalls_set_tools(ast, project, org):
    ast(project, "use", "../org", "--set", "default")
    assert ast(project, "use", "--remove")[0] == 0
    assert not (project / ".claude").exists()
    assert "[org]" not in (project / "ast.toml").read_text()


def test_list_tree_shows_set_inheritance(ast, project, org):
    code, out, _ = ast(org, "list", "--tree")
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("default  (3 tools)")
    assert "│   + tools:skill/alpha" in lines
    assert any(line.startswith("└── proj-fenix  (3 tools)  Fenix") for line in lines)
    assert "        + tools:agent/reviewer" in lines and "        - tools:skill/beta" in lines

    assert ast(project, "list", "--tree")[0] == 2  # no org in use yet
    ast(project, "use", "../org", "--set", "proj-fenix")
    assert "proj-fenix  (3 tools)  Fenix  <- selected" in ast(project, "list", "--tree")[1]
