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
        "hooks/onboard-mini-brief.py",
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
    assert "joins the session and returns the briefing in one call" in template
    assert "target_url" in template
    assert "required_fields" in template
    assert "description" in template
    assert "5000" in template
    assert "memory_read since_minutes=30" in template
    assert "Commit carefully in shared working trees" in template
    assert "memory_submit_ticket" in template
    assert "Cloudflare Pages" not in template
    assert "netlea" not in template.lower()
    assert "migration" not in template.lower()


def test_start_hooks_point_agents_to_memory_onboard():
    hook_text = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in [
            "hooks/cursor-session-start.sh",
            "hooks/claude-code-session-start.sh",
            "hooks/codex-session-start.sh",
        ]
    )
    helper = (REPO_ROOT / "hooks/onboard-mini-brief.py").read_text(encoding="utf-8")

    assert "onboard-mini-brief.py" in hook_text
    assert "memory_onboard" in helper
    assert "MAX_CHARS" in helper
    assert "PINNED_LIMIT" in helper
    assert "AGENTS_LIMIT" in helper
    assert "Do not write memory every turn" in helper
    assert "memory_agent_join → memory_get_briefing" not in hook_text


def test_stop_hooks_are_not_installed_or_memory_writing_by_default():
    configs = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in [
            "configs/claude-code-settings.json",
            "configs/codex-hooks.json",
            "configs/cursor-hooks.json",
        ]
    )
    stop_scripts = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in [
            "hooks/claude-code-stop.sh",
            "hooks/codex-stop.sh",
            "hooks/cursor-session-end.sh",
        ]
    )

    assert '"Stop"' not in configs
    assert '"stop"' not in configs
    assert "Turn-scoped Stop hook is still configured" in (REPO_ROOT / "doctor.sh").read_text(encoding="utf-8")
    assert "status\"] = \"kia\"" not in stop_scripts
    assert "memory_type" not in stop_scripts
    assert "legacy no-op" in stop_scripts


def test_release_materials_match_current_version():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    first_header = next(line for line in changelog.splitlines() if line.startswith("## v"))
    release_notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    assert re.search(r'^version = "3\.6\.0"$', pyproject, re.MULTILINE)
    assert first_header.startswith("## v3.6.0")
    assert "Safer Setup And Updates" in first_header
    for expected in ["linked-projects.json", "--refresh-linked", ".venv/bin/python", "startup mini-brief"]:
        assert expected in release_notes


def test_uv_install_docs_and_template_are_present():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    setup = (REPO_ROOT / "setup-project.sh").read_text(encoding="utf-8")
    agent_setup = (REPO_ROOT / "AGENT_SETUP.md").read_text(encoding="utf-8")
    template = (REPO_ROOT / "configs/local-venv-mcp.json").read_text(encoding="utf-8")
    uv_run_template = (REPO_ROOT / "configs/uv-run-mcp.json").read_text(encoding="utf-8")

    assert "uv sync" in readme
    assert "uv sync --inexact" in readme
    assert ".venv/bin/python" in readme
    assert "startup timeouts" in readme
    assert "Option 1: Agent setup" in readme
    assert "Option 2: Script setup" in readme
    assert "Option 3: Advanced manual setup" in readme
    assert ".onboard/mcp.generated.json" in readme
    assert ".onboard/mcp.generated.json" in setup
    assert ".onboard/AGENT_CONTROL.md" in setup
    assert ".onboard/AGENT_CONTROL.md" in (REPO_ROOT / "templates/agent-rules.md").read_text(encoding="utf-8")
    assert "Runtime memory after init" in setup
    assert ".cursorrules" in setup
    assert "doctor.sh" in readme
    assert (REPO_ROOT / "doctor.sh").exists()
    assert "run-dashboard.sh" in readme
    assert "AGENT_CONTROL.md" in agent_setup
    assert "memory_bootstrap" in agent_setup
    assert "Do not silently edit global" in agent_setup
    assert "Do not use turn-scoped `Stop`" in agent_setup
    assert "uvx" in agent_setup
    assert "uvx" not in template
    assert '"command": "/full/path/to/On_Board/.venv/bin/python"' in template
    assert "/full/path/to/On_Board/server.py" in template
    assert '"command": "uv"' in uv_run_template
    assert '"--directory"' in uv_run_template
    assert "AGENT_MEM_CONTEXT_DIRS" in readme
    assert '"AGENT_MEM_CONTEXT_DIRS"' in template


def test_readme_keeps_roadmap_notes_out_of_front_page():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    a2a_note = (REPO_ROOT / "docs/A2A.md").read_text(encoding="utf-8")

    assert "Honest gaps" not in readme
    assert "Q3 templates" not in readme
    assert "A2A" not in readme
    assert "TASK_STATE_REJECTED" in a2a_note
    assert "Last checked: 2026-07-16" in a2a_note
