"""SDK 2.x contract for the On Board server (mcp 2.3.0 / mcp_types 2.3.0).

Exercises the real `MCPServer` surface the server now registers on: annotation
semantics surviving the v1 -> v2 migration, and workflows driven through the
SDK's own argument validation and result conversion against a temporary board.
Tool/prompt inventory and the declared icon are covered by the existing
`test_docs_protocol.py` / `test_server_workflows.py` checks. No MCP client,
connection, or real board is involved.
"""

import asyncio
import importlib.util
import os
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_server(tmp_path):
    # The memory root is resolved at import time, so pin a throwaway project and
    # restore the caller's environment afterwards — even if the import raises.
    keys = ("AGENT_PROJECT_DIR", "AGENT_MEM_VECTOR_BACKEND")
    saved = {key: os.environ.get(key) for key in keys}
    os.environ["AGENT_PROJECT_DIR"] = str(tmp_path)
    os.environ["AGENT_MEM_VECTOR_BACKEND"] = "none"
    module_name = f"server_under_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "server.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        module._ensure()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def _tools_by_name(server):
    return {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}


def test_every_tool_keeps_its_annotation_hints(tmp_path):
    """Annotations are client-visible behaviour hints; a dropped one is a regression.

    A dict that never reached `ToolAnnotations` (or a hint left unset) would
    silently tell a client the wrong thing about a tool, so check every tool and
    the camelCase wire spelling clients actually receive.
    """
    server = load_server(tmp_path)
    for name, tool in _tools_by_name(server).items():
        annotations = tool.annotations
        assert annotations is not None, f"{name} lost its annotations"
        assert annotations.title, f"{name} lost its annotation title"
        for hint in (annotations.read_only_hint, annotations.destructive_hint,
                     annotations.idempotent_hint, annotations.open_world_hint):
            assert hint is not None, f"{name} lost an annotation hint"
        wire = tool.model_dump(by_alias=True, mode="json", exclude_none=True)["annotations"]
        assert set(wire) == {"title", "readOnlyHint", "destructiveHint",
                             "idempotentHint", "openWorldHint"}, (name, wire)


def test_annotation_semantics_survive_the_migration(tmp_path):
    """The hint split clients see: read-only reads, one destructive, one open world."""
    server = load_server(tmp_path)
    tools = _tools_by_name(server)

    assert [n for n, t in tools.items() if t.annotations.destructive_hint] == ["memory_terminate_ticket"]
    assert [n for n, t in tools.items() if t.annotations.open_world_hint] == ["memory_compact"]
    assert sum(1 for t in tools.values() if t.annotations.read_only_hint) == 14
    assert tools["memory_search"].annotations.read_only_hint is True
    assert tools["memory_write"].annotations.read_only_hint is False
    assert tools["memory_checkpoint"].annotations.read_only_hint is False


def test_sdk_call_tool_runs_a_validated_workflow_on_a_temp_board(tmp_path):
    """The SDK validates arguments and converts results for a real tool call."""
    from mcp_types import CallToolResult

    server = load_server(tmp_path)

    init = asyncio.run(server.mcp.call_tool(
        "memory_init", {"params": {"description": "sdk board", "tech_stack": "python"}}))
    assert isinstance(init, CallToolResult)
    assert "Initialized" in init.content[0].text
    assert (server.MEMORY_DIR / "project.json").is_file()

    joined = asyncio.run(server.mcp.call_tool(
        "memory_agent_join",
        {"params": {"agent_name": "sdk-agent", "agent_platform": "codex"}}))
    assert "sdk-agent" in joined.content[0].text

    written = asyncio.run(server.mcp.call_tool(
        "memory_write",
        {"params": {"agent_name": "sdk-agent", "memory_type": "decision",
                    "title": "sdk write", "content": "through the SDK"}}))
    assert "Saved" in written.content[0].text
    assert [m["title"] for m in server._load_mem()] == ["sdk write"]


def test_sdk_call_tool_rejects_invalid_arguments(tmp_path):
    """Argument validation runs before the tool body, as clients rely on."""
    server = load_server(tmp_path)

    with pytest.raises(Exception) as excinfo:
        asyncio.run(server.mcp.call_tool(
            "memory_write", {"params": {"agent_name": "nobody"}}))

    assert "validation error" in str(excinfo.value).lower()
    assert server._load_mem() == []
