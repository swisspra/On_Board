"""Consumer-visible safety of the standalone project configuration helper."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills" / "onboard" / "scripts" / "setup.py"
SUPPORTED_SETUP = pytest.mark.skipif(sys.version_info < (3, 11), reason="setup helper requires Python 3.11+")
NEEDS_GIT = pytest.mark.skipif(shutil.which("git") is None, reason="requires the git executable")
NEEDS_SYMLINKS = pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
NEEDS_BACKSLASHES = pytest.mark.skipif(os.name == "nt", reason="POSIX file names may contain backslashes")


def invoke(project, client, command=None, *, check=False):
    args = [sys.executable, str(HELPER), "--project", str(project), "--client", client]
    if command is not None:
        args.extend(["--command", str(command)])
    if check:
        args.append("--check")
    return subprocess.run(args, text=True, capture_output=True, timeout=15)


def invoke_raw(argv):
    return subprocess.run([sys.executable, str(HELPER), *argv], text=True, capture_output=True, timeout=15)


def executable(tmp_path):
    path = tmp_path / "runtime's Unicode Ω" / ("onboard-memory-mcp.exe" if os.name == "nt" else "onboard-memory-mcp")
    path.parent.mkdir()
    path.write_bytes(b"configuration target; never executed by setup\n")
    path.chmod(0o755)
    return path


def snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def outside_snapshot(root):
    """Like snapshot(), but ignores Git's own bookkeeping files."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def git(project, *args):
    return subprocess.run(["git", "-C", str(project), *args], text=True, capture_output=True, timeout=30)


def load_helper():
    spec = importlib.util.spec_from_file_location("onboard_skill_setup", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@SUPPORTED_SETUP
@pytest.mark.parametrize("client, relative", [("claude-code", ".mcp.json"), ("cursor", ".cursor/mcp.json")])
def test_json_setup_preserves_other_servers_memory_and_repeated_bytes(tmp_path, client, relative):
    project = tmp_path / "project's Unicode Ω"
    project.mkdir()
    config = project / relative
    config.parent.mkdir(parents=True, exist_ok=True)
    original = {"mcpServers": {"unrelated": {"command": "other-command", "env": {"KEEP": "value"}}}, "custom": {"keep": True}}
    config.write_text(json.dumps(original), encoding="utf-8")
    memory = project / ".agent-mem"
    (memory / "archive").mkdir(parents=True)
    (memory / "archive" / "sentinel.json").write_bytes(b'{"private": "unchanged"}\n')
    (memory / "watch-worker.json").write_bytes(b'{"snapshot": {}}\n')
    before_memory = snapshot(memory)
    command = executable(tmp_path)

    first = invoke(project, client, command)
    assert first.returncode == 0, first.stdout + first.stderr
    report = json.loads(first.stdout)
    assert report["status"] == "configured"
    actual = json.loads(config.read_text(encoding="utf-8"))
    assert actual["custom"] == {"keep": True}
    assert actual["mcpServers"]["unrelated"] == original["mcpServers"]["unrelated"]
    assert actual["mcpServers"]["agent-memory"] == {"command": str(command), "env": {"AGENT_PROJECT_DIR": str(project)}}
    assert snapshot(memory) == before_memory

    before_repeat = snapshot(project)
    second = invoke(project, client, command)
    assert second.returncode == 0, second.stdout + second.stderr
    assert json.loads(second.stdout)["status"] == "unchanged"
    assert snapshot(project) == before_repeat


@SUPPORTED_SETUP
def test_codex_setup_preserves_existing_model_comments_and_other_servers(tmp_path):
    import tomllib

    project = tmp_path / "codex project"
    config = project / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    original = '# keep this comment\nmodel = "existing-model"\n\n[mcp_servers.other]\ncommand = "other-command"\n'
    config.write_text(original, encoding="utf-8")
    command = executable(tmp_path)

    result = invoke(project, "codex", command)
    assert result.returncode == 0, result.stdout + result.stderr
    raw = config.read_text(encoding="utf-8")
    assert raw.startswith(original)
    actual = tomllib.loads(raw)
    assert actual["model"] == "existing-model"
    assert actual["mcp_servers"]["other"] == {"command": "other-command"}
    assert actual["mcp_servers"]["agent-memory"] == {"command": str(command), "env": {"AGENT_PROJECT_DIR": str(project)}}
    before_repeat = snapshot(project)
    again = invoke(project, "codex", command)
    assert again.returncode == 0, again.stdout + again.stderr
    assert snapshot(project) == before_repeat


@SUPPORTED_SETUP
def test_check_on_empty_project_does_not_create_files(tmp_path):
    project = tmp_path / "empty project"
    project.mkdir()
    result = invoke(project, "claude-code", check=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "needs_configuration"
    assert list(project.iterdir()) == []


@SUPPORTED_SETUP
def test_conflicting_server_does_not_change_configuration_or_memory(tmp_path):
    project = tmp_path / "conflict project"
    project.mkdir()
    config = project / ".mcp.json"
    config.write_text(json.dumps({"mcpServers": {"agent-memory": {"command": "custom", "env": {"AGENT_PROJECT_DIR": "/other/project"}}}}), encoding="utf-8")
    command = executable(tmp_path)
    before = snapshot(project)
    result = invoke(project, "claude-code", command)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert snapshot(project) == before


@pytest.mark.skipif(sys.version_info >= (3, 11), reason="exercises the unsupported interpreter")
def test_old_python_reports_prerequisite_without_creating_files(tmp_path):
    result = invoke(tmp_path, "codex", check=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "error"
    assert list(tmp_path.iterdir()) == []


@NEEDS_BACKSLASHES
@SUPPORTED_SETUP
def test_awkward_paths_round_trip_exactly_for_json_and_toml(tmp_path):
    import tomllib

    project = tmp_path / "proj's Ω back\\slash"
    project.mkdir()
    command = executable(tmp_path)

    json_result = invoke(project, "claude-code", command)
    assert json_result.returncode == 0, json_result.stdout + json_result.stderr
    raw = (project / ".mcp.json").read_text(encoding="utf-8")
    assert "Ω" in raw and "\\" in raw, "UTF-8 and backslashes must survive the JSON encoding"
    assert json.loads(raw)["mcpServers"]["agent-memory"] == {
        "command": str(command),
        "env": {"AGENT_PROJECT_DIR": str(project)},
    }

    codex_result = invoke(project, "codex", command)
    assert codex_result.returncode == 0, codex_result.stdout + codex_result.stderr
    toml_raw = (project / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert tomllib.loads(toml_raw)["mcp_servers"]["agent-memory"] == {
        "command": str(command),
        "env": {"AGENT_PROJECT_DIR": str(project)},
    }


@SUPPORTED_SETUP
def test_existing_equivalent_binding_with_extra_env_and_args_is_untouched(tmp_path):
    project = tmp_path / "extra project"
    project.mkdir()
    command = executable(tmp_path)
    config = project / ".mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"agent-memory": {
            "command": str(command),
            "args": [],
            "env": {"AGENT_PROJECT_DIR": str(project), "KEEP": "1"},
        }}}),
        encoding="utf-8",
    )
    before = snapshot(project)
    result = invoke(project, "claude-code", command)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "unchanged"
    assert snapshot(project) == before


@SUPPORTED_SETUP
def test_cursor_workspace_variable_binding_is_a_no_op(tmp_path):
    project = tmp_path / "cursor workspace project"
    project.mkdir()
    command = executable(tmp_path)
    config = project / ".cursor" / "mcp.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps({"mcpServers": {"agent-memory": {
            "command": str(command),
            "args": ["--stdio"],
            "env": {"AGENT_PROJECT_DIR": "${workspaceFolder}"},
        }}}),
        encoding="utf-8",
    )
    before = snapshot(project)
    result = invoke(project, "cursor", check=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "configured"
    assert snapshot(project) == before


@SUPPORTED_SETUP
def test_check_keeps_a_working_source_based_binding(tmp_path):
    project = tmp_path / "clone project"
    project.mkdir()
    config = project / ".mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"agent-memory": {
            "command": "/usr/bin/uv",
            "args": ["run", "--directory", "/opt/onboard", "python", "server.py"],
            "env": {"AGENT_PROJECT_DIR": str(project)},
        }}}),
        encoding="utf-8",
    )
    before = snapshot(project)
    result = invoke(project, "claude-code", check=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "configured"
    assert snapshot(project) == before


@SUPPORTED_SETUP
def test_check_with_command_accepts_the_matching_launcher(tmp_path):
    project = tmp_path / "matching check project"
    project.mkdir()
    command = executable(tmp_path)
    config = project / ".mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"agent-memory": {
            "command": str(command),
            "env": {"AGENT_PROJECT_DIR": str(project)},
        }}}),
        encoding="utf-8",
    )
    before = snapshot(project)
    result = invoke(project, "claude-code", command, check=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "configured"
    assert snapshot(project) == before


@SUPPORTED_SETUP
def test_check_with_command_never_blesses_a_different_launcher(tmp_path):
    project = tmp_path / "clone check project"
    project.mkdir()
    command = executable(tmp_path)
    config = project / ".mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"agent-memory": {
            "command": "/usr/bin/uv",
            "args": ["run", "--directory", "/opt/onboard", "python", "server.py"],
            "env": {"AGENT_PROJECT_DIR": str(project)},
        }}}),
        encoding="utf-8",
    )
    before = snapshot(project)
    result = invoke(project, "claude-code", command, check=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert snapshot(project) == before


@SUPPORTED_SETUP
def test_check_reports_needs_configuration_for_unrelated_servers_only(tmp_path):
    project = tmp_path / "other servers project"
    project.mkdir()
    config = project / ".mcp.json"
    config.write_text(json.dumps({"mcpServers": {"unrelated": {"command": "other-command"}}}), encoding="utf-8")
    before = snapshot(project)
    result = invoke(project, "claude-code", check=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "needs_configuration"
    assert snapshot(project) == before


@SUPPORTED_SETUP
@pytest.mark.parametrize("client, relative, payload", [
    ("claude-code", ".mcp.json", "{not json"),
    ("claude-code", ".mcp.json", "[1, 2]"),
    ("claude-code", ".mcp.json", '{"mcpServers": []}\n'),
    ("claude-code", ".mcp.json", '{"mcpServers": {"agent-memory": "not an object"}}\n'),
    ("claude-code", ".mcp.json", '{"mcpServers": null}\n'),
    ("claude-code", ".mcp.json", '{"mcpServers": {"agent-memory": null}}\n'),
    ("codex", ".codex/config.toml", 'model = "unterminated\n'),
    ("codex", ".codex/config.toml", 'mcp_servers = "not a table"\n'),
    ("codex", ".codex/config.toml", 'mcp_servers = { other = { command = "x" } }\n'),
])
def test_unusable_documents_are_conflicts_and_are_left_untouched(tmp_path, client, relative, payload):
    project = tmp_path / "broken project"
    project.mkdir()
    config = project / relative
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(payload, encoding="utf-8")
    before = snapshot(project)
    result = invoke(project, client, executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "conflict"
    assert report["changed"] is False
    assert snapshot(project) == before


@SUPPORTED_SETUP
@pytest.mark.parametrize("payload", [
    'model = "m"\n\n[mcp_servers.agent-memory]\ncommand = "custom"\nenv = { AGENT_PROJECT_DIR = "/other/project" }\n',
    '[mcp_servers.agent-memory]\ncommand = "custom"\n',
])
def test_codex_different_project_binding_is_a_conflict(tmp_path, payload):
    project = tmp_path / "codex conflict project"
    project.mkdir()
    config = project / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(payload, encoding="utf-8")
    before = snapshot(project)
    result = invoke(project, "codex", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert snapshot(project) == before


@SUPPORTED_SETUP
def test_unresolved_project_interpolation_is_reported_not_rewritten(tmp_path):
    project = tmp_path / "interpolated project"
    project.mkdir()
    config = project / ".mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"agent-memory": {
            "command": "python3",
            "env": {"AGENT_PROJECT_DIR": "${env:ONBOARD_PROJECT}"},
        }}}),
        encoding="utf-8",
    )
    before = snapshot(project)
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "conflict"
    assert "ONBOARD_PROJECT" not in result.stdout, "existing configuration contents must not be echoed"
    assert snapshot(project) == before


@NEEDS_GIT
@SUPPORTED_SETUP
def test_git_tracked_configuration_stops_for_consent(tmp_path):
    project = tmp_path / "tracked project"
    project.mkdir()
    assert git(project, "init", "-q").returncode == 0
    config = project / ".mcp.json"
    config.write_text(json.dumps({"mcpServers": {"unrelated": {"command": "other-command"}}}), encoding="utf-8")
    assert git(project, "add", ".mcp.json").returncode == 0
    before = outside_snapshot(project)
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert outside_snapshot(project) == before


@NEEDS_GIT
@SUPPORTED_SETUP
def test_repository_configuration_is_ignored_but_its_ide_directory_is_not(tmp_path):
    project = tmp_path / "repository project"
    project.mkdir()
    assert git(project, "init", "-q").returncode == 0
    ignore = project / ".gitignore"
    ignore.write_text(".agent-mem/\n", encoding="utf-8")
    result = invoke(project, "cursor", executable(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "configured"
    assert ignore.read_text(encoding="utf-8").startswith(".agent-mem/\n"), "existing rules must be preserved"
    assert git(project, "check-ignore", "-q", "--", ".cursor").returncode == 1, "IDE directories must stay usable"
    assert git(project, "check-ignore", "-q", "--", ".cursor/mcp.json").returncode == 0
    assert git(project, "check-ignore", "-q", "--", ".agent-mem/").returncode == 0
    assert git(project, "check-ignore", "-q", "--", ".onboard/").returncode == 0


@NEEDS_GIT
@SUPPORTED_SETUP
def test_gitignore_preserves_existing_rules_and_ignores_generated_paths(tmp_path):
    project = tmp_path / "ignore project"
    project.mkdir()
    ignore = project / ".gitignore"
    ignore.write_text("# keep this\nnode_modules/\n.mcp.json\n", encoding="utf-8")
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    text = ignore.read_text(encoding="utf-8")
    assert text.startswith("# keep this\nnode_modules/\n.mcp.json\n"), "existing rules must be kept verbatim"
    assert git(project, "init", "-q").returncode == 0
    for path in (".mcp.json", ".agent-mem/", ".onboard/", "node_modules/"):
        assert git(project, "check-ignore", "-q", "--", path).returncode == 0, path


@NEEDS_SYMLINKS
@SUPPORTED_SETUP
def test_symlinked_configuration_file_outside_the_project_is_a_conflict(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_config = outside / "mcp.json"
    outside_config.write_text(json.dumps({"mcpServers": {"unrelated": {"command": "other-command"}}}), encoding="utf-8")
    project = tmp_path / "symlink project"
    project.mkdir()
    (project / ".mcp.json").symlink_to(outside_config)
    before = outside_config.read_bytes()
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert outside_config.read_bytes() == before
    assert (project / ".mcp.json").is_symlink()
    assert not (project / ".gitignore").exists()


@NEEDS_SYMLINKS
@SUPPORTED_SETUP
def test_symlinked_configuration_directory_outside_the_project_is_a_conflict(tmp_path):
    outside = tmp_path / "outside dir"
    outside.mkdir()
    project = tmp_path / "directory symlink project"
    project.mkdir()
    (project / ".cursor").symlink_to(outside, target_is_directory=True)
    result = invoke(project, "cursor", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert list(outside.iterdir()) == []
    assert not (project / ".gitignore").exists()


@SUPPORTED_SETUP
def test_stale_configuration_edit_is_refused_before_replacement(tmp_path):
    module = load_helper()
    target = tmp_path / "config.json"
    target.write_bytes(b'{"mcpServers": {}}\n')
    read_bytes = target.read_bytes()
    replacement = b'{"mcpServers": {"agent-memory": {}}}\n'

    assert module.replace_if_unchanged(target, replacement, read_bytes) is True
    assert target.read_bytes() == replacement

    stale = target.read_bytes()
    target.write_bytes(b'{"mcpServers": {"late": {}}}\n')
    assert module.replace_if_unchanged(target, b'{"mcpServers": {}}\n', stale) is False
    assert target.read_bytes() == b'{"mcpServers": {"late": {}}}\n'
    assert module.replace_if_unchanged(target, replacement, None) is False, "a file appearing mid-flight must not be overwritten"
    assert list(tmp_path.iterdir()) == [target], "no temporary files may be left behind"


@SUPPORTED_SETUP
def test_invalid_operational_inputs_report_error_without_writing(tmp_path):
    project = tmp_path / "input project"
    project.mkdir()
    command = executable(tmp_path)
    before = snapshot(project)

    relative_project = invoke_raw(["--project", "relative/project", "--client", "claude-code", "--command", str(command)])
    assert relative_project.returncode == 1, relative_project.stdout + relative_project.stderr
    assert json.loads(relative_project.stdout)["status"] == "error"

    missing_project = invoke_raw(["--project", str(project / "absent"), "--client", "claude-code", "--command", str(command)])
    assert missing_project.returncode == 1, missing_project.stdout + missing_project.stderr
    assert json.loads(missing_project.stdout)["status"] == "error"

    missing_command = invoke_raw(["--project", str(project), "--client", "claude-code"])
    assert missing_command.returncode == 1, missing_command.stdout + missing_command.stderr
    assert json.loads(missing_command.stdout)["status"] == "error"

    relative_command = invoke_raw(["--project", str(project), "--client", "claude-code", "--command", "onboard-memory-mcp"])
    assert relative_command.returncode == 1, relative_command.stdout + relative_command.stderr
    assert json.loads(relative_command.stdout)["status"] == "error"

    control_character = invoke_raw(["--project", str(project), "--client", "codex", "--command", f"{command}\n"])
    assert control_character.returncode == 1, control_character.stdout + control_character.stderr
    assert json.loads(control_character.stdout)["status"] == "error"

    assert snapshot(project) == before


@SUPPORTED_SETUP
def test_runtime_source_checkout_is_not_a_setup_target(tmp_path):
    checkout = tmp_path / "runtime checkout"
    checkout.mkdir()
    (checkout / "server.py").write_text("# the On Board runtime\n", encoding="utf-8")
    (checkout / "a2a_wait.py").write_text("# runtime module\n", encoding="utf-8")
    before = snapshot(checkout)
    result = invoke(checkout, "codex", executable(tmp_path))
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "error"
    assert snapshot(checkout) == before
    assert not (checkout / ".codex").exists()


@SUPPORTED_SETUP
@pytest.mark.parametrize("args", ["--stdio", ["--stdio"]])
def test_requested_packaged_binding_rejects_nonempty_or_string_args(tmp_path, args):
    project = tmp_path / "argument conflict"
    project.mkdir()
    command = executable(tmp_path)
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"agent-memory": {
        "command": str(command), "args": args, "env": {"AGENT_PROJECT_DIR": str(project)},
    }}}), encoding="utf-8")
    before = snapshot(project)
    result = invoke(project, "claude-code", command, check=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert snapshot(project) == before


@NEEDS_SYMLINKS
@SUPPORTED_SETUP
def test_external_gitignore_symlink_is_refused_before_any_project_write(tmp_path):
    outside = tmp_path / "external-private-ignore"
    outside.write_bytes(b"# synthetic outside data\n")
    project = tmp_path / "ignore link project"
    project.mkdir()
    ignore = project / ".gitignore"
    ignore.symlink_to(outside)
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert ignore.is_symlink()
    assert outside.read_bytes() == b"# synthetic outside data\n"
    assert not (project / ".mcp.json").exists()


@SUPPORTED_SETUP
def test_non_utf8_ignore_is_not_lossily_rewritten(tmp_path):
    project = tmp_path / "non utf8 ignore"
    project.mkdir()
    (project / ".gitignore").write_bytes(b"# existing \xff rule\n")
    before = snapshot(project)
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert snapshot(project) == before


@SUPPORTED_SETUP
@pytest.mark.parametrize("relative, status, code, changed", [
    (".mcp.json", "conflict", 2, False),
    (".gitignore", "error", 1, True),
])
def test_edit_during_temporary_file_flush_is_never_overwritten(tmp_path, monkeypatch, capsys, relative, status, code, changed):
    helper = load_helper()
    project = tmp_path / "concurrent edit"
    project.mkdir()
    config = project / ".mcp.json"
    config.write_bytes(b'{"mcpServers": {"original": {"command": "keep"}}}\n')
    ignore = project / ".gitignore"
    ignore.write_bytes(b"# original ignore\n")
    late = b'{"mcpServers": {"late": {"command": "keep"}}}\n' if relative == ".mcp.json" else b"# another writer\n"
    real_fsync = helper.os.fsync
    injected = False

    def flush_and_edit(fd):
        nonlocal injected
        real_fsync(fd)
        if not injected:
            injected = True
            (project / relative).write_bytes(late)

    monkeypatch.setattr(helper.os, "fsync", flush_and_edit)
    result = helper.main(["--project", str(project), "--client", "claude-code", "--command", str(executable(tmp_path))])
    report = json.loads(capsys.readouterr().out)
    assert result == code, report
    assert (report["status"], report["changed"]) == (status, changed)
    assert (project / relative).read_bytes() == late
    assert not list(project.glob("*.onboard-tmp"))
    if changed:
        assert "agent-memory" in json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    else:
        assert ignore.read_bytes() == b"# original ignore\n"


@SUPPORTED_SETUP
def test_ignore_commit_io_failure_reports_the_already_written_config(tmp_path, monkeypatch, capsys):
    helper = load_helper()
    project = tmp_path / "partial commit"
    project.mkdir()
    real_replace = helper.os.replace

    def fail_ignore_replace(source, destination):
        if Path(destination).name == ".gitignore":
            raise PermissionError("synthetic denied ignore replacement")
        return real_replace(source, destination)

    monkeypatch.setattr(helper.os, "replace", fail_ignore_replace)
    result = helper.main(["--project", str(project), "--client", "claude-code", "--command", str(executable(tmp_path))])
    report = json.loads(capsys.readouterr().out)
    assert result == 1, report
    assert (report["status"], report["changed"], report["config_path"]) == ("error", True, ".mcp.json")
    assert "agent-memory" in json.loads((project / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert not (project / ".gitignore").exists()
    assert not list(project.glob("*.onboard-tmp"))


@SUPPORTED_SETUP
def test_consumer_project_may_depend_on_onboard_without_being_its_runtime(tmp_path):
    project = tmp_path / "consumer"
    project.mkdir()
    metadata = b'[project]\nname = "consumer"\nversion = "1.0.0"\ndependencies = ["onboard-memory-mcp"]\n'
    (project / "pyproject.toml").write_bytes(metadata)
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / "pyproject.toml").read_bytes() == metadata
    assert "agent-memory" in json.loads((project / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


@NEEDS_GIT
@SUPPORTED_SETUP
def test_generated_configuration_is_ignored_after_an_existing_negation(tmp_path):
    project = tmp_path / "future repository"
    project.mkdir()
    (project / ".gitignore").write_bytes(b".mcp.json\n!.mcp.json\n")
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(project, "init", "-q").returncode == 0
    (project / ".agent-mem").mkdir()
    (project / ".onboard").mkdir()
    assert git(project, "check-ignore", "-q", "--", ".mcp.json").returncode == 0
    assert git(project, "check-ignore", "-q", "--", ".agent-mem").returncode == 0
    assert git(project, "check-ignore", "-q", "--", ".onboard").returncode == 0


@NEEDS_GIT
@SUPPORTED_SETUP
def test_deleted_but_tracked_configuration_is_not_recreated_without_consent(tmp_path):
    project = tmp_path / "tracked deletion"
    project.mkdir()
    assert git(project, "init", "-q").returncode == 0
    config = project / ".mcp.json"
    config.write_bytes(b'{"mcpServers": {}}\n')
    assert git(project, "add", ".mcp.json").returncode == 0
    config.unlink()
    before = outside_snapshot(project)
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert outside_snapshot(project) == before


@SUPPORTED_SETUP
def test_unknown_git_tracking_status_refuses_new_configuration(tmp_path):
    project = tmp_path / "unavailable repository"
    project.mkdir()
    (project / ".git").write_bytes(b"gitdir: missing-repository\n")
    before = snapshot(project)
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert snapshot(project) == before


@pytest.mark.skipif(os.name == "nt", reason="Windows does not use POSIX executable mode")
@SUPPORTED_SETUP
def test_non_executable_runtime_is_not_written_to_client_config(tmp_path):
    project = tmp_path / "non executable"
    project.mkdir()
    command = executable(tmp_path)
    command.chmod(0o644)
    result = invoke(project, "claude-code", command)
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "error"
    assert list(project.iterdir()) == []


@NEEDS_GIT
@SUPPORTED_SETUP
@pytest.mark.parametrize("foreign_routing", ["repository", "index"])
def test_inherited_git_routing_cannot_bypass_tracked_configuration(tmp_path, monkeypatch, foreign_routing):
    project = tmp_path / "selected repository"
    project.mkdir()
    assert git(project, "init", "-q").returncode == 0
    config = project / ".mcp.json"
    config.write_bytes(b'{"mcpServers": {"unrelated": {"command": "keep"}}}\n')
    assert git(project, "add", ".mcp.json").returncode == 0
    foreign = tmp_path / "foreign repository"
    foreign.mkdir()
    assert git(foreign, "init", "-q").returncode == 0
    before = outside_snapshot(project)
    if foreign_routing == "repository":
        monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(foreign))
    else:
        monkeypatch.setenv("GIT_INDEX_FILE", str(foreign / ".git" / "index"))
    result = invoke(project, "claude-code", executable(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "conflict"
    assert outside_snapshot(project) == before


@NEEDS_GIT
@SUPPORTED_SETUP
def test_unknown_git_ignore_status_blocks_writes(tmp_path):
    project = tmp_path / "unreadable ignore rules"
    project.mkdir()
    assert git(project, "init", "-q").returncode == 0
    exclude = project / ".git" / "info" / "exclude"
    exclude.unlink()
    exclude.mkdir()
    (project / ".mcp.json").write_bytes(b'{"mcpServers": {"other": {"command": "keep"}}}\n')
    (project / ".gitignore").write_bytes(b"*.log\n")
    memory = project / ".agent-mem"
    memory.mkdir()
    (memory / "watch-sentinel.json").write_bytes(b'{"cursor": "preserve"}\n')
    before = outside_snapshot(project)

    result = invoke(project, "claude-code", executable(tmp_path))

    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "conflict"
    assert report["changed"] is False
    assert outside_snapshot(project) == before
