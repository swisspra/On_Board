import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(cmd, **kwargs):
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
        **kwargs,
    )


def test_mini_brief_handles_malformed_shapes_and_hard_cap(tmp_path):
    mem_dir = tmp_path / ".agent-mem"
    (mem_dir / "tickets").mkdir(parents=True)
    (mem_dir / "project.json").write_text("[]", encoding="utf-8")
    (mem_dir / "agents.json").write_text("[]", encoding="utf-8")
    (mem_dir / "memories.json").write_text("[]", encoding="utf-8")
    (mem_dir / "tickets" / "_index.json").write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    env["AGENT_MEM_DIR"] = str(mem_dir)
    env["ONBOARD_HOOK_MAX_CHARS"] = "20"
    result = run([sys.executable, "hooks/onboard-mini-brief.py"], env=env)

    assert len(result.stdout.rstrip("\n")) <= 20
    assert result.returncode == 0


def test_cursor_start_hook_uses_workspace_folder_from_input(tmp_path):
    mem_dir = tmp_path / ".agent-mem"
    mem_dir.mkdir()
    (mem_dir / "project.json").write_text(
        json.dumps({"description": "Cursor path project", "tech_stack": "Python"}),
        encoding="utf-8",
    )
    (mem_dir / "agents.json").write_text("{}", encoding="utf-8")
    (mem_dir / "memories.json").write_text(json.dumps({"entries": []}), encoding="utf-8")

    payload = json.dumps({"workspaceFolder": str(tmp_path), "session_id": "test-session"})
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "hooks/cursor-session-start.sh")],
        input=payload,
        text=True,
        capture_output=True,
        check=True,
    )
    output = json.loads(result.stdout)

    assert "Cursor path project" in output["additional_context"]
    assert output["env"]["AGENT_PROJECT_DIR"] == str(tmp_path)


def test_setup_project_generates_dashboard_and_doctor_passes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    registry = tmp_path / "linked-projects.json"
    env = os.environ.copy()
    env["ONBOARD_REGISTRY_FILE"] = str(registry)

    run(["bash", "setup-project.sh", str(project)], env=env)
    doctor = run(["bash", "doctor.sh", str(project)], env=env)
    linked = run(["bash", "setup-project.sh", "--list-linked"], env=env)
    linked_doctor = run(["bash", "doctor.sh", "--all-linked"], env=env)
    linked_update = run(["bash", "update.sh", "--list-linked"], env=env)

    generated = project / ".onboard" / "mcp.generated.json"
    control = project / ".onboard" / "AGENT_CONTROL.md"
    dashboard = project / ".onboard" / "run-dashboard.sh"
    registry_data = json.loads(registry.read_text(encoding="utf-8"))

    assert generated.exists()
    assert control.exists()
    assert dashboard.exists()
    assert registry.exists()
    assert os.access(dashboard, os.X_OK)
    assert "0 failed" in doctor.stdout
    assert str(project) in linked.stdout
    assert str(project) in linked_update.stdout
    assert "Checking linked project" in linked_doctor.stdout
    assert registry_data["projects"][0]["path"] == str(project)
    assert registry_data["projects"][0]["hook_mode"] == "safe"
    assert "setup-project.sh" in control.read_text(encoding="utf-8")
    assert str(project) in control.read_text(encoding="utf-8")
    assert str(project) in dashboard.read_text(encoding="utf-8")


def test_setup_project_does_not_prune_existing_test_extras():
    setup = (REPO_ROOT / "setup-project.sh").read_text(encoding="utf-8")
    update = (REPO_ROOT / "update.sh").read_text(encoding="utf-8")

    assert "uv sync --inexact" in setup
    assert "uv sync --inexact" in update


def test_setup_project_hook_modes_are_explicit_and_idempotent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    env = os.environ.copy()
    env["ONBOARD_REGISTRY_FILE"] = str(tmp_path / "linked-projects.json")

    run(["bash", "setup-project.sh", str(project), "--hooks", "safe"], env=env)
    assert (project / ".cursor" / "hooks.json").exists()
    assert (project / ".claude" / "settings.json").exists()
    assert (project / ".codex" / "hooks.json").exists()

    run(["bash", "setup-project.sh", str(project), "--hooks", "off"], env=env)
    settings = json.loads((project / ".onboard" / "settings.json").read_text(encoding="utf-8"))
    show = run(["bash", "setup-project.sh", str(project), "--show-hooks"], env=env)
    doctor = run(["bash", "doctor.sh", str(project)], env=env)
    run(["bash", "setup-project.sh", "--all-linked"], env=env)
    settings_after_linked = json.loads((project / ".onboard" / "settings.json").read_text(encoding="utf-8"))
    guard = subprocess.run(
        ["bash", "setup-project.sh", str(project), "--hooks", "guard"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert settings["hook_mode"] == "off"
    assert settings_after_linked["hook_mode"] == "off"
    assert not (project / ".cursor" / "hooks.json").exists()
    assert not (project / ".claude" / "settings.json").exists()
    assert not (project / ".codex" / "hooks.json").exists()
    assert "Current hook mode: off" in show.stdout
    assert "0 failed" in doctor.stdout
    assert guard.returncode != 0
    assert "planned but not implemented" in guard.stdout


def test_setup_project_migration_preserves_existing_memory(tmp_path):
    project = tmp_path / "project"
    mem_dir = project / ".agent-mem"
    tickets_dir = mem_dir / "tickets"
    env = os.environ.copy()
    env["ONBOARD_REGISTRY_FILE"] = str(tmp_path / "linked-projects.json")
    tickets_dir.mkdir(parents=True)
    (mem_dir / "project.json").write_text(json.dumps({"description": "old project"}), encoding="utf-8")
    (mem_dir / "agents.json").write_text(json.dumps({
        "old": {
            "agent_name": "old-coder",
            "agent_platform": "codex",
            "agent_role": "coder",
            "status": "active",
        }
    }), encoding="utf-8")
    (mem_dir / "memories.json").write_text(json.dumps({
        "entries": [
            {
                "id": "m-old",
                "agent_name": "old-coder",
                "memory_type": "decision",
                "title": "Keep old memory",
                "content": "Do not delete this during setup.",
                "timestamp": 1,
            }
        ]
    }), encoding="utf-8")
    (tickets_dir / "_index.json").write_text(json.dumps({
        "tickets": [
            {
                "id": "TK-old",
                "title": "Old ticket",
                "status": "open",
                "priority": "medium",
                "created_by": "old-coder",
                "claimed_by": None,
                "target_url": "local",
                "scope": "READ-ONLY",
                "required_fields": ["result"],
            }
        ]
    }), encoding="utf-8")

    run(["bash", "setup-project.sh", str(project)], env=env)
    doctor = run(["bash", "doctor.sh", str(project)], env=env)

    assert "old project" in (mem_dir / "project.json").read_text(encoding="utf-8")
    assert "Keep old memory" in (mem_dir / "memories.json").read_text(encoding="utf-8")
    assert "TK-old" in (tickets_dir / "_index.json").read_text(encoding="utf-8")
    assert "0 failed" in doctor.stdout


def test_update_skips_unrelated_target_and_backs_up_onboard_files(tmp_path):
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    env["ONBOARD_REGISTRY_FILE"] = str(tmp_path / "linked-projects.json")

    unrelated = tmp_path / "not-onboard"
    unrelated.mkdir()
    unrelated_server = unrelated / "server.py"
    unrelated_server.write_text("keep me\n", encoding="utf-8")

    skipped = run(["bash", "update.sh", str(unrelated)], env=env)

    assert "Not an On Board checkout" in skipped.stdout
    assert unrelated_server.read_text(encoding="utf-8") == "keep me\n"

    deployed = tmp_path / "onboard-copy"
    deployed.mkdir()
    (deployed / "pyproject.toml").write_text('name = "onboard-memory-mcp"\n', encoding="utf-8")
    (deployed / "server.py").write_text("old server\n", encoding="utf-8")

    updated = run(["bash", "update.sh", str(deployed)], env=env)

    backups = list(deployed.glob(".onboard-update-backup-*/server.py"))
    assert "Updated (" in updated.stdout
    assert (deployed / "server.py").read_text(encoding="utf-8") == (REPO_ROOT / "server.py").read_text(encoding="utf-8")
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old server\n"
