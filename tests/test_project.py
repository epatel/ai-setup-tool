import json

from conftest import commit


def lock(project):
    return json.loads((project / "ast.lock").read_text())


def test_add_installs_files_and_writes_config_and_lock(ast, project, source):
    assert ast(project, "source", "add", "../tools")[0] == 0
    code, out, _ = ast(project, "add", "alpha", "reviewer", "ship", "check.sh")
    assert code == 0 and "installed  tools:skill/alpha" in out
    assert (project / ".claude/skills/alpha/SKILL.md").read_text() == "alpha v1\n"
    assert (project / ".claude/skills/alpha/references/notes.md").exists()
    assert (project / ".claude/agents/reviewer.md").exists()
    assert (project / ".claude/commands/ship.md").exists()
    assert (project / ".claude/scripts/check.sh").exists()
    config = (project / "ast.toml").read_text()
    assert 'repo = "../tools"' in config and '"tools:skill/alpha"' in config
    data = lock(project)
    assert set(data["tools"]) == {
        "tools:skill/alpha", "tools:agent/reviewer", "tools:command/ship", "tools:script/check.sh",
    }  # fmt: skip
    assert data["sources"]["tools"]["commit"] == data["tools"]["tools:skill/alpha"]["commit"]
    assert ast(project, "status")[0] == 0


def test_list_shows_active_and_available(ast, project, source):
    ast(project, "source", "add", "../tools")
    ast(project, "add", "alpha")
    _, out, _ = ast(project, "list", "--available")
    active, available = out.split("Available:")
    assert "tools:skill/alpha" in active and "project" in active and "ok" in active
    assert "tools:skill/beta" in available and "tools:skill/alpha" not in available


def test_disable_enable_and_rm(ast, project, source):
    ast(project, "source", "add", "../tools")
    ast(project, "add", "alpha")
    skill = project / ".claude/skills/alpha"

    assert ast(project, "disable", "alpha")[0] == 0
    assert not skill.exists() and not (project / ".claude").exists()  # empty parents are cleaned up
    assert '"tools:skill/alpha"' in (project / "ast.toml").read_text()
    assert "Disabled:" in ast(project, "list")[1]

    assert ast(project, "enable", "alpha")[0] == 0
    assert skill.exists()

    assert ast(project, "rm", "alpha")[0] == 0
    assert not skill.exists() and "alpha" not in (project / "ast.toml").read_text()
    assert lock(project)["tools"] == {}


def test_sources_stay_locked_until_update(ast, project, source):
    ast(project, "source", "add", "../tools")
    ast(project, "add", "alpha")
    commit(source, {"alpha/SKILL.md": "alpha v2\n", "skills/beta/SKILL.md": "beta v2\n"})
    skill = project / ".claude/skills/alpha/SKILL.md"

    code, out, _ = ast(project, "status")
    assert code == 0 and "updates available" in out and "update  tools:skill/alpha" in out
    ast(project, "add", "beta")  # a later add must not move the locked source
    assert skill.read_text() == "alpha v1\n"
    assert (project / ".claude/skills/beta/SKILL.md").read_text() == "beta v1\n"

    code, out, _ = ast(project, "update")
    assert code == 0 and "updated    tools:skill/alpha" in out
    assert skill.read_text() == "alpha v2\n"
    assert "no updates available" in ast(project, "status")[1]


def test_local_changes_are_reported_and_never_overwritten_without_force(ast, project, source):
    ast(project, "source", "add", "../tools")
    ast(project, "add", "alpha")
    skill = project / ".claude/skills/alpha/SKILL.md"
    skill.write_text("my edit\n")

    code, out, _ = ast(project, "status")
    assert code == 1 and "modified  tools:skill/alpha" in out
    assert ast(project, "sync")[0] == 0  # nothing new upstream: the edit is simply kept
    assert skill.read_text() == "my edit\n"

    commit(source, {"alpha/SKILL.md": "alpha v2\n"})
    code, _, err = ast(project, "update")
    assert code == 1 and "not updated" in err and skill.read_text() == "my edit\n"
    code, _, err = ast(project, "rm", "alpha")
    assert code == 1 and "not removed" in err and skill.exists()

    ast(project, "add", "alpha")
    assert ast(project, "update", "--force")[0] == 0
    assert skill.read_text() == "alpha v2\n"


def test_existing_unmanaged_files_are_not_overwritten(ast, project, source):
    mine = project / ".claude/skills/alpha/SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("hand written\n")
    ast(project, "source", "add", "../tools")
    code, _, err = ast(project, "add", "alpha")
    assert code == 1 and "ast does not manage it" in err
    assert mine.read_text() == "hand written\n" and lock(project)["tools"] == {}


def test_sync_restores_deleted_files(ast, project, source):
    ast(project, "source", "add", "../tools")
    ast(project, "add", "alpha")
    (project / ".claude/skills/alpha/SKILL.md").unlink()
    assert ast(project, "status")[0] == 1
    code, out, _ = ast(project, "sync", "--force")
    assert code == 0 and "restored" in out
    assert (project / ".claude/skills/alpha/SKILL.md").exists()


def test_latest_tag_follows_releases_not_main(ast, project, source):
    commit(source, {"alpha/SKILL.md": "alpha released\n"}, tag="v2026.1.9")
    commit(source, {"alpha/SKILL.md": "alpha unreleased\n"})
    ast(project, "source", "add", "../tools", "--ref", "latest-tag")
    ast(project, "add", "alpha")
    skill = project / ".claude/skills/alpha/SKILL.md"
    assert skill.read_text() == "alpha released\n"
    assert lock(project)["sources"]["tools"]["label"] == "v2026.1.9"

    commit(source, {"alpha/SKILL.md": "alpha next\n"}, tag="v2026.1.10")
    code, out, _ = ast(project, "update", "tools")
    assert code == 0 and "v2026.1.10" in out and skill.read_text() == "alpha next\n"


def test_errors_are_explained(ast, project, source, tmp_path):
    assert ast(tmp_path, "list")[0] == 2
    ast(project, "source", "add", "../tools")
    code, _, err = ast(project, "add", "alpah")
    assert code == 2 and "did you mean alpha" in err
    code, _, err = ast(project, "source", "add", "../tools", "--name", "bad", "--ref", "nope")
    assert code == 2 and "ref 'nope' not found" in err
    assert "bad" not in (project / "ast.toml").read_text()  # a failed command changes nothing
    ast(project, "add", "alpha")
    code, _, err = ast(project, "source", "rm", "tools")
    assert code == 2 and "still used by" in err


def test_tool_removed_upstream_can_be_removed_from_project(ast, project, source):
    ast(project, "source", "add", "../tools")
    ast(project, "add", "beta")
    commit(source, {"skills/beta/SKILL.md": None})
    code, _, err = ast(project, "update")
    assert code == 2 and "not found in their source" in err
    assert ast(project, "rm", "beta")[0] == 0
    assert not (project / ".claude/skills/beta").exists()


def test_cards_get_an_index_that_claude_md_imports(ast, project, source):
    (project / "CLAUDE.md").write_text("# My project\n")
    ast(project, "source", "add", "../tools")
    code, out, _ = ast(project, "add", "defaults", "naming")
    assert code == 0 and "indexed    CARDS.md" in out and "linked     CLAUDE.md" in out
    index = (project / "CARDS.md").read_text()
    # the trigger comes from the source's index, or else from the card's first paragraph
    assert "- [defaults](cards/defaults.md) — choosing a default for a new service" in index
    assert "- [naming](cards/naming.md) — How we name things." in index
    assert (project / "CLAUDE.md").read_text() == "# My project\n\n## Cards\n\n@CARDS.md\n"
    assert lock(project)["tools"]["tools:card/defaults"]["trigger"] == "choosing a default for a new service"

    # text outside the markers is kept, and a second sync changes nothing
    (project / "CARDS.md").write_text(index + "\n- [mine](cards/mine.md) — my own card\n")
    assert "up to date" in ast(project, "sync")[1]
    assert ast(project, "disable", "naming")[0] == 0
    index = (project / "CARDS.md").read_text()
    assert "naming" not in index and "defaults" in index and "[mine](cards/mine.md)" in index
    assert (project / "CLAUDE.md").read_text().count("@CARDS.md") == 1

    commit(source, {"CARDS.md": "- [defaults](cards/defaults.md) — a better trigger\n"})
    ast(project, "update")
    assert "— a better trigger" in (project / "CARDS.md").read_text()
    ast(project, "rm", "defaults")
    assert "defaults" not in (project / "CARDS.md").read_text()


def test_prompt_prints_instructions_for_an_agent(ast, project, source, tmp_path):
    code, out, _ = ast(tmp_path, "prompt", "setup", "acme/setup")  # works outside a project
    assert code == 0 and "Run `ast use acme/setup`." in out and "ast select <set>" in out
    assert "ask the user for the organisation's setup repo" in ast(tmp_path, "ai", "setup")[1]
    assert "ast update" in ast(project, "prompt", "update")[1]
    assert "adopted" in ast(tmp_path, "prompt", "adopt")[1]
    out = ast(tmp_path, "prompt", "org", "../app", "../docs")[1]
    assert "Look at these projects: ../app, ../docs." in out and "{" not in out
    assert "Ask the user which projects" in ast(tmp_path, "prompt", "org")[1]

    ast(project, "source", "add", "../tools")
    _, out, _ = ast(project, "prompt")
    assert "setup" in out and "built in" in out and "from tools" in out and "Tidy the repo" in out
    assert "Tidy the docs folder now." in ast(project, "prompt", "tidy", "the", "docs", "folder")[1]
    code, _, err = ast(project, "prompt", "nope")
    assert code == 2 and "unknown prompt 'nope'" in err and "tidy" in err
