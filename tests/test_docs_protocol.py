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
        "templates/agent-rules.md",
        "hooks/cursor-session-start.sh",
        "hooks/claude-code-session-start.sh",
        "hooks/codex-session-start.sh",
    ]
    for path in files:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert "<on_board_protocol>" in text, path
        assert "<required_first_call>memory_onboard</required_first_call>" in text, path


def test_setup_uses_shared_agent_rules_template():
    setup = (REPO_ROOT / "setup-project.sh").read_text(encoding="utf-8")
    template = (REPO_ROOT / "templates/agent-rules.md").read_text(encoding="utf-8")

    assert "templates/agent-rules.md" in setup
    assert "RULES_NOTE=\"$(cat \"$RULES_TEMPLATE\")\"" in setup
    assert "Re-join after every off-board action" in template
    assert "memory_submit_ticket" in template
    assert "Cloudflare Pages" not in template
    assert "netlea" not in template.lower()


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

    assert re.search(r'^version = "3\.5\.2"$', pyproject, re.MULTILINE)
    assert first_header.startswith("## v3.5.2")
    assert "Context Dir Template" in first_header
    for expected in ["uv run", "configs/uv-mcp.json", "AGENT_MEM_CONTEXT_DIRS", "context directories"]:
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
    assert "AGENT_MEM_CONTEXT_DIRS" in readme
    assert '"AGENT_MEM_CONTEXT_DIRS"' in template
