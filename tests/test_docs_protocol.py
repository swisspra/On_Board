import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_source_repo_has_no_generated_project_files():
    generated_paths = [
        ".agent-mem",
        ".agent-mem-hooks",
        ".codex",
        ".cursor",
        ".claude",
        ".agent",
        "AGENTS.md",
        "CLAUDE.md",
        ".cursorrules",
    ]
    for path in generated_paths:
        assert not (REPO_ROOT / path).exists(), path

    subprocess.run(
        ["bash", "doctor.sh", "--self"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def _registry_tool_names(tmp_path):
    """The server's real tool registry, imported away from any real board.

    AGENT_PROJECT_DIR (and the fallbacks server.py reads) are pinned to a
    throwaway project BEFORE the import, because the memory root is resolved at
    import time, and restored afterwards so this cannot touch a user's board.
    """
    keys = ("AGENT_PROJECT_DIR", "CURSOR_PROJECT_DIR", "CLAUDE_PROJECT_DIR",
            "AGENT_MEM_VECTOR_BACKEND")
    saved = {key: os.environ.get(key) for key in keys}
    os.environ["AGENT_PROJECT_DIR"] = str(tmp_path)
    os.environ.pop("CURSOR_PROJECT_DIR", None)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    os.environ["AGENT_MEM_VECTOR_BACKEND"] = "none"
    sys.path.insert(0, str(REPO_ROOT))
    try:
        name = f"docs_protocol_server_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {tool.name for tool in asyncio.run(module.mcp.list_tools())}
    finally:
        sys.path.remove(str(REPO_ROOT))
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_plugin_manifest_matches_the_registry(tmp_path):
    """The public tool list is a contract: the machine-readable LobeHub plugin
    manifest must advertise exactly the tools the server registers.

    It drifted once already (it advertised a tool the server did not have), so
    the manifest is held to the real registry rather than to human prose.
    """
    actual = _registry_tool_names(tmp_path)
    manifest = json.loads((REPO_ROOT / "lhm.plugin.json").read_text(encoding="utf-8"))
    advertised = {tool["name"] for tool in manifest["tools"]}
    assert advertised == actual, (
        f"lhm.plugin.json missing {sorted(actual - advertised)}; "
        f"advertising unknown {sorted(advertised - actual)}")
