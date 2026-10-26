#!/usr/bin/env python3
"""Project configuration helper for the On Board install skill.

Merges one native MCP client entry (``mcpServers.agent-memory`` or
``[mcp_servers.agent-memory]``) into the selected project's own client file and
reports what happened as a single JSON object.  It deliberately never touches
global client configuration, ``.agent-mem/``, hooks, model/provider settings, or
commands found inside project configuration.

    python setup.py --project /abs/project --client claude-code|cursor|codex \\
        --command /abs/onboard-memory-mcp [--check]

Statuses: configured, unchanged, needs_configuration, conflict, error.
Exit codes: 0 configured/unchanged, 2 needs_configuration/conflict, 1 error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

MINIMUM_PYTHON = (3, 11)
PREREQUISITE = (
    "Python 3.11 or newer is required to configure a native client entry; "
    "the skill falls back to `uv run --no-project --python 3.12`."
)
SERVER_KEY = "agent-memory"
ENV_KEY = "AGENT_PROJECT_DIR"
RUNTIME_PACKAGE = "onboard-memory-mcp"
CURSOR_WORKSPACE_VAR = "${workspaceFolder}"
ONBOARD_IGNORE_ENTRIES = (".agent-mem/", ".onboard/")

CLIENTS = {
    "claude-code": {"path": ".mcp.json", "format": "json"},
    "cursor": {"path": ".cursor/mcp.json", "format": "json"},
    "codex": {"path": ".codex/config.toml", "format": "toml"},
}
CONTAINERS = {"json": "mcpServers", "toml": "mcp_servers"}
EXIT_CODES = {"configured": 0, "unchanged": 0, "needs_configuration": 2, "conflict": 2, "error": 1}
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
VARIABLE_REFERENCE = re.compile(r"\$\{")
GIT_TIMEOUT = 30


class Failure(Exception):
    """A refused operation carrying the machine-readable status to report."""

    def __init__(self, status: str, next_step: str, *, changed: bool = False, config_path: str | None = None) -> None:
        super().__init__(next_step)
        self.status = status
        self.next_step = next_step
        self.changed = changed
        self.config_path = config_path


# ---------------------------------------------------------------- reporting


def emit(status: str, client: str | None, config_path: str | None, changed: bool, next_step: str) -> int:
    report = {
        "status": status,
        "client": client,
        "config_path": config_path,
        "changed": changed,
        "next_step": next_step,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return EXIT_CODES[status]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="setup.py",
        description=(
            "Configure one project for the On Board agent-memory MCP server by merging a "
            "native client entry into that project's own client configuration."
        ),
    )
    parser.add_argument("--project", required=True, help="absolute path of the project to configure")
    parser.add_argument("--client", required=True, choices=sorted(CLIENTS), help="native client configuration to merge into")
    parser.add_argument(
        "--command",
        help="absolute path of the onboard-memory-mcp executable; required unless --check inspects an existing binding",
    )
    parser.add_argument("--check", action="store_true", help="report the current binding only; never writes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = CLIENTS[args.client]["path"]
    if sys.version_info < MINIMUM_PYTHON:
        return emit("error", args.client, config_path, False, PREREQUISITE)
    try:
        return run(args)
    except Failure as failure:
        return emit(
            failure.status,
            args.client,
            failure.config_path or config_path,
            failure.changed,
            failure.next_step,
        )
    except OSError as error:
        return emit("error", args.client, config_path, False, f"I/O failure: {error.strerror or error}")


# ------------------------------------------------------------ input checking


def resolve_project(raw: str) -> Path:
    if not raw or CONTROL_CHARS.search(raw):
        raise Failure("error", "--project must be a non-empty path without control characters.")
    path = Path(raw)
    if not path.is_absolute():
        raise Failure("error", f"--project must be an absolute path; got {raw!r}.")
    if not path.is_dir():
        raise Failure("error", f"--project {raw!r} is not an existing directory.")
    project = Path(os.path.realpath(path))
    if is_runtime_checkout(project):
        raise Failure(
            "error",
            f"--project {raw!r} looks like the On Board runtime itself, not a project to configure.",
        )
    return project


def is_runtime_checkout(project: Path) -> bool:
    """The runtime checkout and deployed copies are never setup targets.

    Package identity is read from parsed metadata, never scanned as a substring,
    so a consumer project that merely depends on onboard-memory-mcp still counts
    as a real project to configure.
    """
    if (project / "server.py").is_file() and (project / "a2a_wait.py").is_file():
        return True
    pyproject = project / "pyproject.toml"
    if not pyproject.is_file():
        return False
    import tomllib

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return False
    declared = data.get("project")
    if isinstance(declared, dict) and declared.get("name") == RUNTIME_PACKAGE:
        return True
    tool = data.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    return isinstance(poetry, dict) and poetry.get("name") == RUNTIME_PACKAGE


def resolve_command(raw: str) -> str:
    if not raw or CONTROL_CHARS.search(raw):
        raise Failure("error", "--command must be a non-empty path without control characters.")
    path = Path(raw)
    if not path.is_absolute():
        raise Failure("error", f"--command must be an absolute path to onboard-memory-mcp; got {raw!r}.")
    if not path.is_file():
        raise Failure("error", f"--command {raw!r} is not an existing file.")
    if os.name != "nt" and not stat.S_IMODE(path.stat().st_mode) & 0o111:
        raise Failure("error", f"--command {raw!r} is not executable.")
    return raw


def check_command_argument(raw: str) -> None:
    if CONTROL_CHARS.search(raw) or not Path(raw).is_absolute():
        raise Failure("error", f"--command must be an absolute path to onboard-memory-mcp; got {raw!r}.")


def require_inside_project(project: Path, target: Path, rel: str) -> None:
    real = os.path.realpath(target)
    if real != str(project) and not real.startswith(str(project) + os.sep):
        raise Failure(
            "conflict",
            f"{rel} resolves outside the project through a symlink; nothing was written.",
            config_path=rel,
        )


# ---------------------------------------------------------- configuration I/O


def read_document(data: bytes | None, fmt: str, rel: str) -> tuple[dict[str, Any] | None, str | None]:
    if data is None:
        return {}, None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"existing {rel} is not valid UTF-8; nothing was written."
    if fmt == "json":
        try:
            document = json.loads(text)
        except ValueError as error:
            return None, f"existing {rel} is not valid JSON ({error}); nothing was written."
        if not isinstance(document, dict):
            return None, f"existing {rel} is not a JSON object; nothing was written."
        return document, None
    import tomllib

    try:
        return tomllib.loads(text), None
    except tomllib.TOMLDecodeError as error:
        return None, f"existing {rel} is not valid TOML ({error}); nothing was written."


ABSENT = object()


def server_entry(document: dict[str, Any], fmt: str, rel: str) -> Any:
    """The existing agent-memory entry, or ABSENT when the container/key is absent.

    A key that is present but null is not absence: it is a malformed entry that
    must be refused rather than silently replaced.
    """
    container_key = CONTAINERS[fmt]
    if container_key not in document:
        return ABSENT
    container = document[container_key]
    if not isinstance(container, dict):
        kind = "JSON object" if fmt == "json" else "table"
        raise Failure(
            "conflict",
            f"{container_key} in {rel} is not a {kind}; nothing was written.",
            config_path=rel,
        )
    return container[SERVER_KEY] if SERVER_KEY in container else ABSENT


def render_json(document: dict[str, Any], expected: dict[str, Any]) -> bytes:
    merged = dict(document)
    servers = dict(merged.get("mcpServers") or {})
    servers[SERVER_KEY] = expected
    merged["mcpServers"] = servers
    return (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def append_toml_section(original: str, expected: dict[str, Any]) -> str:
    command = json.dumps(expected["command"], ensure_ascii=False)
    project = json.dumps(expected["env"][ENV_KEY], ensure_ascii=False)
    section = f"[mcp_servers.{SERVER_KEY}]\ncommand = {command}\nenv = {{ {ENV_KEY} = {project} }}\n"
    prefix = original if not original or original.endswith("\n") else original + "\n"
    separator = "\n" if prefix.strip() else ""
    return prefix + separator + section


def verify_toml(text: str, expected: dict[str, Any], original: dict[str, Any]) -> str | None:
    """Re-parse the candidate and prove every pre-existing value survived the append."""
    import tomllib

    try:
        candidate = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return (
            "appending [mcp_servers.agent-memory] to .codex/config.toml is not valid TOML "
            f"({error}); the existing file seals that table, so it was left untouched."
        )
    servers = candidate.get("mcp_servers")
    if not isinstance(servers, dict) or servers.get(SERVER_KEY) != expected:
        return "the appended [mcp_servers.agent-memory] table did not round-trip; nothing was written."
    restored = dict(candidate)
    remaining = {key: value for key, value in servers.items() if key != SERVER_KEY}
    if "mcp_servers" in original:
        restored["mcp_servers"] = remaining
    else:
        restored.pop("mcp_servers", None)
    if restored != original:
        return "appending the agent-memory table would change existing configuration; nothing was written."
    return None


def replace_if_unchanged(target: Path, data: bytes, expected: bytes | None) -> bool:
    """Atomically replace target, refusing when it no longer holds the bytes we read.

    The expected bytes must be the snapshot taken while planning; the target is
    reread only after the temporary file is flushed and fsynced, immediately
    before ``os.replace``, so a late edit is detected rather than clobbered.
    """
    mode = stat.S_IMODE(os.stat(target).st_mode) if target.is_file() else 0o600
    handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".onboard-tmp", dir=str(target.parent))
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        current = target.read_bytes() if target.is_file() else None
        if current != expected:
            os.unlink(temporary)
            return False
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return True


# -------------------------------------------------------------- Git handling

def _git_environment() -> dict[str, str]:
    # -C selects this project only if ambient routing cannot select another index.
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)
    return env


def git_repository(project: Path) -> bool | None:
    """True/False for a work tree, None when Git cannot answer reliably."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT, check=False,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        return None if has_git_dir(project) else False
    if result.returncode == 0:
        return True
    return None if has_git_dir(project) else False


def has_git_dir(project: Path) -> bool:
    return any((ancestor / ".git").exists() for ancestor in (project, *project.parents))


def git_state(project: Path, *args: str) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT, check=False,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0:
        return True
    return False if result.returncode == 1 else None


def plan_gitignore(project: Path, rel: str, repository: bool) -> tuple[bytes | None, bytes | None]:
    """New .gitignore bytes and its planning snapshot.

    Inside a Git work tree git's own ``check-ignore`` decides, asking about
    directories with their trailing slash so directory-only rules apply.  A
    project outside one has no effective ignore rules at all, so every entry is
    appended verbatim; that conservative exact entry is preferred over guessing
    at Gitignore semantics with a wildcard matcher.
    """
    ignore_path = project / ".gitignore"
    if ignore_path.is_symlink():
        raise Failure("conflict", ".gitignore in the project is a symlink; nothing was written.", config_path=rel)
    if os.path.lexists(ignore_path) and not ignore_path.is_file():
        raise Failure("conflict", ".gitignore in the project is not a regular file; nothing was written.", config_path=rel)
    try:
        original = ignore_path.read_bytes() if ignore_path.is_file() else None
    except OSError as error:
        raise Failure(
            "conflict",
            f".gitignore in the project cannot be read ({error.strerror or error}); nothing was written.",
            config_path=rel,
        )
    try:
        text = original.decode("utf-8") if original else ""
    except UnicodeDecodeError:
        raise Failure("conflict", ".gitignore in the project is not valid UTF-8; nothing was written.", config_path=rel)
    entries = (rel, *ONBOARD_IGNORE_ENTRIES)
    if repository:
        missing = []
        for entry in entries:
            ignored = git_state(project, "check-ignore", "-q", "--", entry)
            if ignored is None:
                raise Failure(
                    "conflict",
                    f"cannot determine whether {entry} is ignored by Git in this repository; nothing was written.",
                    config_path=rel,
                )
            if not ignored:
                missing.append(entry)
    else:
        missing = list(entries)
    if not missing:
        return None, original
    addition = "".join(f"{entry}\n" for entry in missing)
    prefix = text if (not text or text.endswith("\n")) else text + "\n"
    return (prefix + addition).encode("utf-8"), original


# ---------------------------------------------------------- binding analysis


def same_project(value: str, project: Path) -> bool:
    if value == str(project):
        return True
    if not os.path.isabs(value):
        return False
    return os.path.realpath(value) == str(project)


def same_command(existing: str, required: str) -> bool:
    if existing == required:
        return True
    if os.path.isabs(existing) and os.path.lexists(existing):
        return os.path.realpath(existing) == os.path.realpath(required)
    return False


def analyze_binding(
    entry: Any, project: Path, client: str, required_command: str | None
) -> tuple[str, str]:
    """Classify an existing agent-memory entry as 'match', 'different', or 'unresolved'."""
    if not isinstance(entry, dict):
        return "different", f"the existing {SERVER_KEY} entry is not an object; nothing was written."
    command = entry.get("command")
    if not isinstance(command, str) or not command.strip():
        return "different", f"the existing {SERVER_KEY} entry has no usable command; nothing was written."
    if "args" not in entry:
        args: list[str] = []
    elif isinstance(entry["args"], list) and all(isinstance(item, str) for item in entry["args"]):
        args = entry["args"]
    else:
        return "different", f"the existing {SERVER_KEY} entry has an unusable args value; nothing was written."
    if required_command is not None and args:
        return "different", (
            f"the existing {SERVER_KEY} entry passes launcher arguments to the packaged command; nothing was written."
        )
    env = entry.get("env")
    if not isinstance(env, dict):
        return "different", f"the existing {SERVER_KEY} entry has no env table binding {ENV_KEY}; nothing was written."
    value = env.get(ENV_KEY)
    if not isinstance(value, str) or not value.strip():
        return "different", f"the existing {SERVER_KEY} entry does not set {ENV_KEY}; nothing was written."
    if not (client == "cursor" and value == CURSOR_WORKSPACE_VAR):
        if VARIABLE_REFERENCE.search(value):
            return "unresolved", (
                f"the existing {SERVER_KEY} entry binds {ENV_KEY} through an unresolved variable "
                "reference; confirm it manually instead of rewriting it."
            )
        if not same_project(value, project):
            return "different", f"the existing {SERVER_KEY} entry binds {ENV_KEY} to a different project; nothing was written."
    if required_command is not None and not same_command(command, required_command):
        return "different", f"the existing {SERVER_KEY} entry runs a different command than {required_command!r}; nothing was written."
    return "match", ""


# -------------------------------------------------------------- entry points


def run(args: argparse.Namespace) -> int:
    spec = CLIENTS[args.client]
    project = resolve_project(args.project)
    rel = spec["path"]
    target = project / rel
    require_inside_project(project, target, rel)
    if args.check:
        return check_binding(args, spec, project, target)
    return configure(args, spec, project, target)


def check_binding(args: argparse.Namespace, spec: dict[str, str], project: Path, target: Path) -> int:
    rel = spec["path"]
    if args.command is not None:
        check_command_argument(args.command)
    if not os.path.lexists(target):
        return emit(
            "needs_configuration",
            args.client,
            rel,
            False,
            f"{rel} does not exist in the project; run this helper without --check to add the {SERVER_KEY} entry.",
        )
    if not target.is_file():
        raise Failure("conflict", f"{rel} exists in the project but is not a regular file.", config_path=rel)
    document, error = read_document(target.read_bytes(), spec["format"], rel)
    if error:
        raise Failure("conflict", error, config_path=rel)
    entry = server_entry(document, spec["format"], rel)
    if entry is ABSENT:
        return emit(
            "needs_configuration",
            args.client,
            rel,
            False,
            f"{rel} has no {SERVER_KEY} entry; run this helper without --check to add one.",
        )
    kind, detail = analyze_binding(entry, project, args.client, args.command)
    if kind == "match":
        return emit(
            "configured",
            args.client,
            rel,
            False,
            f"{rel} already binds {SERVER_KEY} to this project; nothing to write.",
        )
    raise Failure("conflict", detail, config_path=rel)


def configure(args: argparse.Namespace, spec: dict[str, str], project: Path, target: Path) -> int:
    rel = spec["path"]
    if args.command is None:
        raise Failure(
            "error",
            f"--command <absolute onboard-memory-mcp> is required to write {rel}; nothing was written.",
            config_path=rel,
        )
    command = resolve_command(args.command)
    existing = target.read_bytes() if target.is_file() else None
    if os.path.lexists(target) and existing is None:
        raise Failure("conflict", f"{rel} exists in the project but is not a regular file; nothing was written.", config_path=rel)
    if target.is_symlink():
        raise Failure("conflict", f"{rel} is a symlink; nothing was written.", config_path=rel)
    document, error = read_document(existing, spec["format"], rel)
    if error:
        raise Failure("conflict", error, config_path=rel)
    entry = server_entry(document, spec["format"], rel)
    expected = {"command": command, "env": {ENV_KEY: str(project)}}
    if entry is not ABSENT:
        kind, detail = analyze_binding(entry, project, args.client, command)
        if kind == "match":
            return emit(
                "unchanged",
                args.client,
                rel,
                False,
                f"{rel} already binds {SERVER_KEY} to this project; nothing changed.",
            )
        raise Failure("conflict", detail, config_path=rel)

    if spec["format"] == "json":
        data = render_json(document, expected)
    else:
        text = append_toml_section(existing.decode("utf-8") if existing else "", expected)
        error = verify_toml(text, expected, document)
        if error:
            raise Failure("conflict", error, config_path=rel)
        data = text.encode("utf-8")

    repository = git_repository(project)
    if repository is None:
        raise Failure(
            "conflict",
            f"cannot determine whether {rel} is Git-tracked in this repository; nothing was written.",
            config_path=rel,
        )
    if repository and git_state(project, "ls-files", "--error-unmatch", "--", rel) is not False:
        raise Failure(
            "conflict",
            f"{rel} is tracked by Git, so machine-specific paths need explicit consent; nothing was written.",
            config_path=rel,
        )
    ignore_plan, ignore_snapshot = plan_gitignore(project, rel, repository)

    target.parent.mkdir(parents=True, exist_ok=True)
    if not replace_if_unchanged(target, data, existing):
        raise Failure("conflict", f"{rel} changed while the helper was reading it; nothing was written.", config_path=rel)
    note = ""
    if ignore_plan is not None:
        ignore_path = project / ".gitignore"
        try:
            committed = replace_if_unchanged(ignore_path, ignore_plan, ignore_snapshot)
        except OSError as error:
            committed = False
            detail = f"updating .gitignore failed ({error.strerror or error})"
        else:
            detail = ".gitignore changed while it was being updated"
        if not committed:
            raise Failure(
                "error",
                f"{rel} was written, but {detail}; the generated configuration is in place and .gitignore was left unchanged.",
                changed=True,
                config_path=rel,
            )
        note = " .gitignore now keeps the generated configuration and On Board state untracked."
    next_step = f"Added the agent-memory MCP server for this project to {rel}; reload {args.client} to pick it up.{note}"
    return emit("configured", args.client, rel, True, next_step)


if __name__ == "__main__":
    raise SystemExit(main())
