import base64
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

# setup/update run against a throwaway copy of the repo: no .git (so update.sh
# cannot pull) and a .venv python symlinked to this interpreter (so no real
# dependency sync is needed or wanted). Hooks, configs, templates, docs,
# setup-project.sh and doctor.sh stay the real files from the tree.
SOURCE_SKIP = shutil.ignore_patterns(
    ".git", ".venv", ".pytest_cache", "__pycache__", ".work", ".onboard", "tests",
)

# Files every deployed copy needs to import and render. update.sh must refuse to
# overwrite any destination when one of them is missing from the source checkout.
MANDATORY_PAYLOAD = (
    "server.py",
    "a2a_wait.py",
    "ticket_roles.py",
    "thrift_compress.py",
    "docs/assets/on-board-icon.png",
)

OLD_DEPLOYED_FILES = {
    "server.py": b"old server\n",
    "a2a_wait.py": b"old a2a\n",
    "ticket_roles.py": b"old roles\n",
    "thrift_compress.py": b"old thrift\n",
    "docs/assets/on-board-icon.png": b"old icon\n",
}

DEST_IMPORT_SCRIPT = """
import asyncio
import json
import sys

dest = sys.argv[1]
sys.path.insert(0, dest)

import a2a_wait
import server
import thrift_compress
import ticket_roles

icons = server._server_icons()
print(json.dumps({
    "tools": len(asyncio.run(server.mcp.list_tools())),
    "files": {
        "server.py": server.__file__,
        "a2a_wait.py": a2a_wait.__file__,
        "ticket_roles.py": ticket_roles.__file__,
        "thrift_compress.py": thrift_compress.__file__,
    },
    "icon_path": str(server._ICON_PATH),
    "icon_b64": icons[0].src.split(",", 1)[1] if icons else "",
}))
"""


def link_runtime(checkout):
    """Give a checkout a usable .venv pointing at this interpreter's packages.

    Nothing is installed: python is a symlink to the running interpreter and the
    site-packages directory is a symlink to the running interpreter's, so any
    code that runs `"$CHECKOUT/.venv/bin/python"` gets the same runtime the tests
    run under.
    """
    venv = checkout / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").symlink_to(sys.executable)
    site_packages = venv / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    site_packages.parent.mkdir(parents=True, exist_ok=True)
    site_packages.symlink_to(sysconfig.get_paths()["purelib"])
    pyvenv_cfg = Path(sys.prefix) / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        shutil.copy2(pyvenv_cfg, venv / "pyvenv.cfg")
    else:
        (venv / "pyvenv.cfg").write_text(
            f"home = {Path(sys.executable).resolve().parent}\ninclude-system-site-packages = true\n",
            encoding="utf-8",
        )


def make_source(tmp_path, name="source's copy"):
    """Copy the repo to a temporary source checkout with no .git and a runtime.

    The default directory name carries an apostrophe: every setup/doctor/update
    run has to pass the checkout path to Python without splicing it into Python
    source, so a quote in the path is a deliberate regression case.
    """
    src = tmp_path / name
    shutil.copytree(REPO_ROOT, src, ignore=SOURCE_SKIP, symlinks=True)
    link_runtime(src)
    return src


def fake_uv(tmp_path, exit_code=0):
    """Deterministic stand-in for uv: never touches the network or any venv."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    uv = bin_dir / "uv"
    uv.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    uv.chmod(0o755)
    return bin_dir


def make_env(tmp_path, *, uv_exit=0, without_uv=False):
    env = os.environ.copy()
    env["ONBOARD_REGISTRY_FILE"] = str(tmp_path / "linked-projects.json")
    env["AGENT_PROJECT_DIR"] = str(tmp_path / "runtime-project")
    env.pop("PYTHONPATH", None)
    if without_uv:
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    else:
        env["PATH"] = f"{fake_uv(tmp_path, uv_exit)}:{env['PATH']}"
    return env


def run(src, args, env, check=True):
    return subprocess.run(
        ["bash", *args],
        cwd=src,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def make_deployed_copy(tmp_path, *, with_runtime=True, name="onboard-copy"):
    deployed = tmp_path / name
    (deployed / "docs" / "assets").mkdir(parents=True)
    (deployed / "pyproject.toml").write_text('name = "onboard-memory-mcp"\n', encoding="utf-8")
    for rel, old in OLD_DEPLOYED_FILES.items():
        (deployed / rel).write_bytes(old)
    if with_runtime:
        link_runtime(deployed)
    return deployed


def import_from_destination(deployed):
    """Import the deployed modules with the deployed runtime, isolated from cwd."""
    env = dict(os.environ, AGENT_PROJECT_DIR=str(deployed.parent / "import-project"))
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            str(deployed / ".venv" / "bin" / "python"),
            "-I",
            "-c",
            DEST_IMPORT_SCRIPT,
            str(deployed),
        ],
        cwd=deployed.parent,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_mini_brief_handles_malformed_shapes_and_hard_cap(tmp_path):
    src = make_source(tmp_path)
    mem_dir = tmp_path / ".agent-mem"
    (mem_dir / "tickets").mkdir(parents=True)
    (mem_dir / "project.json").write_text("[]", encoding="utf-8")
    (mem_dir / "agents.json").write_text("[]", encoding="utf-8")
    (mem_dir / "memories.json").write_text("[]", encoding="utf-8")
    (mem_dir / "tickets" / "_index.json").write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    env["AGENT_MEM_DIR"] = str(mem_dir)
    env["ONBOARD_HOOK_MAX_CHARS"] = "20"
    result = subprocess.run(
        [sys.executable, "hooks/onboard-mini-brief.py"],
        cwd=src,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert len(result.stdout.rstrip("\n")) <= 20
    assert result.returncode == 0


def test_cursor_start_hook_uses_workspace_folder_from_input(tmp_path):
    src = make_source(tmp_path)
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
        ["bash", str(src / "hooks/cursor-session-start.sh")],
        input=payload,
        text=True,
        capture_output=True,
        check=True,
    )
    output = json.loads(result.stdout)

    assert "Cursor path project" in output["additional_context"]
    assert output["env"]["AGENT_PROJECT_DIR"] == str(tmp_path)


def test_setup_project_generates_dashboard_and_doctor_passes(tmp_path):
    src = make_source(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    registry = tmp_path / "linked-projects.json"
    env = make_env(tmp_path)

    setup = run(src, ["setup-project.sh", str(project)], env)
    doctor = run(src, ["doctor.sh", str(project)], env)
    linked = run(src, ["setup-project.sh", "--list-linked"], env)
    linked_doctor = run(src, ["doctor.sh", "--all-linked"], env)
    linked_update = run(src, ["update.sh", "--list-linked"], env)

    generated = project / ".onboard" / "mcp.generated.json"
    control = project / ".onboard" / "AGENT_CONTROL.md"
    dashboard = project / ".onboard" / "run-dashboard.sh"
    registry_data = json.loads(registry.read_text(encoding="utf-8"))
    generated_config = json.loads(generated.read_text(encoding="utf-8"))
    server_config = generated_config["mcpServers"]["agent-memory"]

    assert generated.exists()
    assert control.exists()
    assert dashboard.exists()
    assert registry.exists()
    assert os.access(dashboard, os.X_OK)
    assert "server import OK (30 tools)" in setup.stdout
    assert "Server import OK (30 tools)" in doctor.stdout
    assert "0 failed" in doctor.stdout
    assert str(project) in linked.stdout
    assert str(project) in linked_update.stdout
    assert "Checking linked project" in linked_doctor.stdout
    assert registry_data["projects"][0]["path"] == str(project)
    assert registry_data["projects"][0]["hook_mode"] == "safe"
    assert server_config["command"] == "python3"
    assert server_config["args"] == [str(src / "onboard_server.py")]
    assert "setup-project.sh" in control.read_text(encoding="utf-8")
    assert str(project) in control.read_text(encoding="utf-8")
    assert str(project) in dashboard.read_text(encoding="utf-8")


def test_doctor_does_not_loop_setup_for_manual_cleanup_failures(tmp_path):
    src = make_source(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    env = make_env(tmp_path)

    run(src, ["setup-project.sh", str(project)], env)

    mcp_json = project / ".onboard" / "mcp.json"
    config = json.loads(mcp_json.read_text(encoding="utf-8"))
    config["mcpServers"]["agent-memory"]["env"]["AGENT_PROJECT_DIR"] = str(tmp_path / "old-project")
    mcp_json.write_text(json.dumps(config), encoding="utf-8")

    cursor_hooks = project / ".cursor" / "hooks.json"
    cursor_hooks.write_text(json.dumps({"hooks": {"Stop": []}}), encoding="utf-8")

    doctor = run(src, ["doctor.sh", str(project)], env, check=False)

    assert doctor.returncode == 1
    assert "Manual cleanup is required for existing custom files" in doctor.stdout
    assert "Agent-assisted fix:" in doctor.stdout
    assert "fix only the listed On Board config/hook issues" in doctor.stdout
    assert "do not change .agent-mem/" in doctor.stdout
    assert "Do not rerun setup-project.sh for these failures" in doctor.stdout
    assert f'bash "{src / "setup-project.sh"}" "{project}"' not in doctor.stdout


def test_setup_project_hook_modes_are_explicit_and_idempotent(tmp_path):
    src = make_source(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    env = make_env(tmp_path)

    run(src, ["setup-project.sh", str(project), "--hooks", "safe"], env)
    assert (project / ".cursor" / "hooks.json").exists()
    assert (project / ".claude" / "settings.json").exists()
    assert (project / ".codex" / "hooks.json").exists()

    run(src, ["setup-project.sh", str(project), "--hooks", "off"], env)
    settings = json.loads((project / ".onboard" / "settings.json").read_text(encoding="utf-8"))
    show = run(src, ["setup-project.sh", str(project), "--show-hooks"], env)
    doctor = run(src, ["doctor.sh", str(project)], env)
    run(src, ["setup-project.sh", "--all-linked"], env)
    settings_after_linked = json.loads((project / ".onboard" / "settings.json").read_text(encoding="utf-8"))
    guard = run(src, ["setup-project.sh", str(project), "--hooks", "guard"], env, check=False)

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
    src = make_source(tmp_path)
    project = tmp_path / "project"
    mem_dir = project / ".agent-mem"
    tickets_dir = mem_dir / "tickets"
    env = make_env(tmp_path)
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

    setup = run(src, ["setup-project.sh", str(project)], env)
    doctor = run(src, ["doctor.sh", str(project)], env)
    report = json.loads((project / ".onboard" / "migration-report.json").read_text(encoding="utf-8"))
    onboard_readme = (project / ".onboard" / "README.md").read_text(encoding="utf-8")

    assert "old project" in (mem_dir / "project.json").read_text(encoding="utf-8")
    assert "Keep old memory" in (mem_dir / "memories.json").read_text(encoding="utf-8")
    assert "TK-old" in (tickets_dir / "_index.json").read_text(encoding="utf-8")
    assert report["existing_memory_detected"] is True
    assert report["core_unchanged"] is True
    assert "Existing memory was detected and verified unchanged" in setup.stdout
    assert "memory_onboard, then memory_doctor" in setup.stdout
    assert "Call memory_bootstrap" not in setup.stdout
    assert "Call memory_onboard for this project, then memory_doctor." in onboard_readme
    assert "Call memory_bootstrap" not in onboard_readme
    assert "0 failed" in doctor.stdout


def test_setup_project_existing_memory_in_whitelist_repo_stays_ignored(tmp_path):
    src = make_source(tmp_path)
    project = tmp_path / "project"
    mem_dir = project / ".agent-mem"
    mem_dir.mkdir(parents=True)
    (project / ".gitignore").write_text(
        "\n".join([
            "/*",
            "!/.gitignore",
            "!/README.md",
            ".agent-mem/",
            "",
        ]),
        encoding="utf-8",
    )
    (mem_dir / "project.json").write_text(json.dumps({"description": "existing"}), encoding="utf-8")
    (mem_dir / "agents.json").write_text("{}", encoding="utf-8")
    (mem_dir / "memories.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
    (mem_dir / "state.json").write_text("{}", encoding="utf-8")
    env = make_env(tmp_path)

    before = {
        path.relative_to(mem_dir).as_posix(): path.read_bytes()
        for path in mem_dir.rglob("*")
        if path.is_file()
    }
    run(src, ["setup-project.sh", str(project)], env)
    doctor = run(src, ["doctor.sh", str(project)], env)
    after = {
        path.relative_to(mem_dir).as_posix(): path.read_bytes()
        for path in mem_dir.rglob("*")
        if path.is_file()
    }
    gitignore = (project / ".gitignore").read_text(encoding="utf-8")

    assert before == after
    assert "0 failed" in doctor.stdout
    for entry in [
        ".agent-mem/",
        ".onboard/",
        ".agent-mem-hooks/",
        ".codex/",
        ".cursor/",
        ".claude/",
        ".agent/",
        "AGENTS.md",
        "CLAUDE.md",
        ".cursorrules",
    ]:
        assert entry in gitignore
    assert json.loads((project / ".onboard" / "migration-report.json").read_text(encoding="utf-8"))["core_unchanged"] is True


def test_update_skips_unrelated_target(tmp_path):
    src = make_source(tmp_path)
    env = make_env(tmp_path, without_uv=True)

    unrelated = tmp_path / "not-onboard"
    unrelated.mkdir()
    unrelated_server = unrelated / "server.py"
    unrelated_server.write_text("keep me\n", encoding="utf-8")

    skipped = run(src, ["update.sh", str(unrelated)], env)

    assert "Not an On Board checkout" in skipped.stdout
    assert unrelated_server.read_text(encoding="utf-8") == "keep me\n"
    assert list(unrelated.glob(".onboard-update-backup-*")) == []


def test_update_deploys_runtime_payload_and_backs_up_previous_files(tmp_path):
    src = make_source(tmp_path)
    env = make_env(tmp_path)
    deployed = make_deployed_copy(tmp_path)

    updated = run(src, ["update.sh", str(deployed)], env)

    installed = import_from_destination(deployed)
    assert f"Updated ({installed['tools']} tools)" in updated.stdout
    assert "uv synced without pruning extras (30 tools)" in updated.stdout

    for rel, old in OLD_DEPLOYED_FILES.items():
        assert (deployed / rel).read_bytes() == (src / rel).read_bytes(), rel
        backups = list(deployed.glob(f".onboard-update-backup-*/{rel}"))
        assert len(backups) == 1, rel
        assert backups[0].read_bytes() == old, rel

    for rel, module_file in installed["files"].items():
        assert Path(module_file).resolve() == (deployed / rel).resolve(), rel
    assert Path(installed["icon_path"]).resolve() == (deployed / "docs" / "assets" / "on-board-icon.png").resolve()

    icon_bytes = base64.b64decode(installed["icon_b64"])
    assert icon_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert icon_bytes == (src / "docs" / "assets" / "on-board-icon.png").read_bytes()


@pytest.mark.parametrize("missing", MANDATORY_PAYLOAD)
def test_update_refuses_to_overwrite_when_mandatory_source_file_is_missing(tmp_path, missing):
    src = make_source(tmp_path)
    env = make_env(tmp_path)
    deployed = make_deployed_copy(tmp_path)
    (src / missing).unlink()

    result = run(src, ["update.sh", str(deployed)], env, check=False)

    assert result.returncode != 0
    assert missing in result.stdout
    assert "No destination was modified" in result.stdout
    for rel, old in OLD_DEPLOYED_FILES.items():
        assert (deployed / rel).read_bytes() == old, rel
    assert list(deployed.glob(".onboard-update-backup-*")) == []


def test_update_reports_copied_source_without_runtime(tmp_path):
    src = make_source(tmp_path)
    env = make_env(tmp_path, uv_exit=1)
    deployed = make_deployed_copy(tmp_path, with_runtime=False)

    result = run(src, ["update.sh", str(deployed)], env, check=False)

    assert result.returncode != 0
    assert "runtime unavailable" in result.stdout
    assert "✅ Updated" not in result.stdout
    assert "(? tools)" not in result.stdout
    assert (deployed / "server.py").read_bytes() == (src / "server.py").read_bytes()
    assert (deployed / "docs" / "assets" / "on-board-icon.png").read_bytes() == (
        src / "docs" / "assets" / "on-board-icon.png"
    ).read_bytes()


def test_update_fails_when_deployed_copy_cannot_import(tmp_path):
    src = make_source(tmp_path)
    env = make_env(tmp_path)
    (src / "ticket_roles.py").write_text("def broken(:\n", encoding="utf-8")
    deployed = make_deployed_copy(tmp_path)

    result = run(src, ["update.sh", str(deployed)], env, check=False)

    assert result.returncode != 0
    assert "the local server failed to import" in result.stdout
    assert "failed to import" in result.stdout
    assert "SyntaxError" in result.stdout
    assert "✅ Updated" not in result.stdout
    assert "(? tools)" not in result.stdout
    assert (deployed / "ticket_roles.py").read_text(encoding="utf-8") == "def broken(:\n"


@pytest.mark.parametrize("source_name", ["source", "source's copy"])
def test_update_auto_detects_pyproject_only_copy_from_isolated_home(tmp_path, source_name):
    src = make_source(tmp_path, name=source_name)
    env = make_env(tmp_path)
    home = tmp_path / "isolated home"
    env["HOME"] = str(home)
    deployed = make_deployed_copy(tmp_path, name="deployed's copy")
    config = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({
        "mcpServers": {"agent-memory": {"command": "python3", "args": [
            str(deployed / "server.py"),
        ]}},
    }), encoding="utf-8")

    run(src, ["update.sh"], env)

    installed = import_from_destination(deployed)
    assert installed["tools"] == 30
    assert Path(installed["files"]["server.py"]).resolve() == (deployed / "server.py").resolve()
    assert base64.b64decode(installed["icon_b64"]).startswith(b"\x89PNG\r\n\x1a\n")
    backups = list(deployed.glob(".onboard-update-backup-*/server.py"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == OLD_DEPLOYED_FILES["server.py"]
