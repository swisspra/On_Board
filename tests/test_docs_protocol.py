from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_skill_uses_significant_action_protocol():
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "significant action" in skill
    assert "EVERY action" not in skill


def test_docs_make_memory_onboard_the_primary_agent_entrypoint():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    server = (REPO_ROOT / "server.py").read_text(encoding="utf-8")

    assert "memory_onboard" in readme
    assert "memory_onboard" in skill
    assert "ticket mutation" in skill
    assert "platform-model-date" not in server


def test_rules_and_hooks_wrap_protocol_in_xml_tags():
    files = [
        "SKILL.md",
        "setup-project.sh",
        "hooks/cursor-session-start.sh",
        "hooks/claude-code-session-start.sh",
        "hooks/codex-session-start.sh",
    ]
    for path in files:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert "<on_board_protocol>" in text, path
        assert "<required_first_call>memory_onboard</required_first_call>" in text, path


def test_start_hooks_point_agents_to_memory_onboard():
    hook_text = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in [
            "hooks/cursor-session-start.sh",
            "hooks/claude-code-session-start.sh",
            "hooks/codex-session-start.sh",
        ]
    )

    assert "memory_onboard" in hook_text
    assert "memory_agent_join → memory_get_briefing" not in hook_text


def test_release_materials_match_current_version():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    first_header = next(line for line in changelog.splitlines() if line.startswith("## v"))
    release_notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    assert re.search(r'^version = "3\.5\.1"$', pyproject, re.MULTILINE)
    assert first_header.startswith("## v3.5.1")
    assert "uv Setup Templates" in first_header
    for expected in ["uv sync", "uv run", "configs/uv-mcp.json", "uv.lock", "console script"]:
        assert expected in release_notes


def test_uv_install_docs_and_template_are_present():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    template = (REPO_ROOT / "configs/uv-mcp.json").read_text(encoding="utf-8")

    assert "uv sync" in readme
    assert "uv run" in readme
    assert "uvx" not in template
    assert '"command": "uv"' in template
    assert '"--directory"' in template
    assert '"python"' in template
    assert '"server.py"' in template
