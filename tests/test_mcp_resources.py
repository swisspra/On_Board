"""Read native project resources through the real SDK on synthetic projects."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import uuid

from mcp import Client, MCPError
import pytest

ROOT = Path(__file__).resolve().parents[1]
URIS = {"onboard://project", "onboard://tickets", "onboard://memory/summary"}
_IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


@pytest.fixture
def resource_server(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AGENT_PROJECT_DIR", str(project))
    monkeypatch.setenv("AGENT_MEM_VECTOR_BACKEND", "none")
    monkeypatch.delenv("CURSOR_PROJECT_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.syspath_prepend(str(ROOT))
    spec = importlib.util.spec_from_file_location(f"resource_server_{uuid.uuid4().hex}", ROOT / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, project


async def resource_json(client, uri):
    result = await client.read_resource(uri)
    assert result.contents[0].mime_type == "application/json"
    return json.loads(result.contents[0].text)


def seed(project, *, tickets=None, memories=None):
    memory = project / ".agent-mem"
    (memory / "tickets").mkdir(parents=True)
    (memory / "project.json").write_text(json.dumps({"description": "synthetic project", "tech_stack": "Python"}), encoding="utf-8")
    (memory / "tickets" / "_index.json").write_text(json.dumps({"tickets": tickets or []}), encoding="utf-8")
    (memory / "memories.json").write_text(json.dumps({"entries": memories or []}), encoding="utf-8")
    return memory


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_resource_reads_do_not_initialize_a_project(resource_server, mode):
    server, project = resource_server

    async def exercise():
        async with Client(server.mcp, mode=mode) as client:
            listed = await client.list_resources()
            assert URIS <= {str(item.uri) for item in listed.resources}
            for uri in sorted(URIS):
                payload = await resource_json(client, uri)
                assert payload["initialized"] is False

    asyncio.run(exercise())
    assert list(project.iterdir()) == []


def test_resources_return_new_file_state_without_mutating_board(resource_server):
    server, project = resource_server
    memory = seed(project, tickets=[{"id": "TK-000000000001", "title": "one", "status": "open", "priority": "high", "timestamp": 1}])
    before = {p.relative_to(memory).as_posix(): p.read_bytes() for p in memory.rglob("*") if p.is_file()}

    async def exercise():
        async with Client(server.mcp) as client:
            project_data = await resource_json(client, "onboard://project")
            assert project_data == {"initialized": True, "description_preview": "synthetic project", "tech_stack_preview": "Python"}
            first = await resource_json(client, "onboard://tickets")
            assert first["open_total"] == 1
            assert first["open_items"][0]["id"] == "TK-000000000001"
            changed = {"tickets": [{"id": "TK-000000000001", "title": "one", "status": "closed", "priority": "high", "timestamp": 2}]}
            (memory / "tickets" / "_index.json").write_text(json.dumps(changed), encoding="utf-8")
            expected = {**before, "tickets/_index.json": (memory / "tickets" / "_index.json").read_bytes()}
            second = await resource_json(client, "onboard://tickets")
            assert second["open_total"] == 0
            assert second["counts"] == {"closed": 1}
            assert {p.relative_to(memory).as_posix(): p.read_bytes() for p in memory.rglob("*") if p.is_file()} == expected

    asyncio.run(exercise())


def test_resource_projection_bounds_preserve_whole_board_totals(resource_server):
    server, project = resource_server
    tickets = [{"id": f"TK-{i:012x}", "title": f"ticket {i}", "status": "open" if i < 57 else "closed", "priority": "medium", "timestamp": i} for i in range(60)]
    entries = [{"id": f"m-{i}", "title": f"memory {i}", "memory_type": "progress", "pinned": i < 3, "timestamp": i, "content": "never return this raw body"} for i in range(12)]
    seed(project, tickets=tickets, memories=entries)

    async def exercise():
        async with Client(server.mcp) as client:
            ticket_data = await resource_json(client, "onboard://tickets")
            assert ticket_data["total"] == 60
            assert ticket_data["open_total"] == 57
            assert ticket_data["counts"] == {"open": 57, "closed": 3}
            assert len(ticket_data["open_items"]) == 50
            assert ticket_data["open_items"][0]["id"] == "TK-000000000038"
            assert ticket_data["truncated"] is True
            memory_data = await resource_json(client, "onboard://memory/summary")
            assert memory_data["total"] == 12
            assert memory_data["pinned"] == 3
            assert memory_data["by_type"] == {"progress": 12}
            assert [item["id"] for item in memory_data["latest"]] == [f"m-{i}" for i in range(11, 1, -1)]
            assert memory_data["truncated"] is True
            assert all("content" not in item for item in memory_data["latest"])

    asyncio.run(exercise())


def test_malformed_board_files_are_an_error_not_an_empty_board(resource_server):
    """A damaged file must surface, never read back as a fabricated empty board."""
    server, project = resource_server
    memory = project / ".agent-mem"
    (memory / "tickets").mkdir(parents=True)
    (memory / "project.json").write_text('{"description": "synthetic project", "tech_stack": "Python"}', encoding="utf-8")
    (memory / "tickets" / "_index.json").write_text("{not json", encoding="utf-8")
    (memory / "memories.json").write_text('{"entries": "not a list"}', encoding="utf-8")

    async def exercise():
        async with Client(server.mcp) as client:
            with pytest.raises(MCPError):
                await client.read_resource("onboard://tickets")
            with pytest.raises(MCPError):
                await client.read_resource("onboard://memory/summary")
            # The healthy resource next to the damaged ones still reads.
            payload = await resource_json(client, "onboard://project")
            assert payload["description_preview"] == "synthetic project"

    asyncio.run(exercise())


def test_extreme_payload_is_refused_instead_of_streamed(resource_server):
    """A board row larger than the response cap is an error, not a giant read."""
    server, project = resource_server
    seed(project, tickets=[{"id": "x" * 70_000, "title": "huge", "status": "open", "priority": "high", "timestamp": 1}])

    async def exercise():
        async with Client(server.mcp) as client:
            with pytest.raises(MCPError):
                await client.read_resource("onboard://tickets")

    asyncio.run(exercise())


@pytest.mark.skipif(_IS_ROOT, reason="root bypasses file modes")
def test_unreadable_board_file_surfaces_the_read_error(resource_server):
    server, project = resource_server
    memory = seed(project, memories=[{"id": "m-1", "title": "one", "memory_type": "progress", "timestamp": 1}])
    unreadable = memory / "memories.json"
    unreadable.chmod(0o000)

    async def exercise():
        async with Client(server.mcp) as client:
            with pytest.raises(MCPError):
                await client.read_resource("onboard://memory/summary")

    try:
        asyncio.run(exercise())
    finally:
        unreadable.chmod(0o644)


def test_static_catalogs_are_cacheable_and_board_reads_are_not(resource_server):
    """Hints a client actually acts on: catalog lists may be held, board reads may not."""
    server, project = resource_server
    seed(project, tickets=[{"id": "TK-000000000001", "title": "one", "status": "open", "priority": "high", "timestamp": 1}])

    async def exercise():
        async with Client(server.mcp) as client:
            listed = await client.list_resources()
            assert listed.cache_scope == "private"
            assert listed.ttl_ms == 60_000
            read = await client.read_resource("onboard://tickets")
            assert read.cache_scope == "private"
            assert read.ttl_ms == 0

    asyncio.run(exercise())


@pytest.mark.parametrize("uri, relative", [
    ("onboard://project", "project.json"),
    ("onboard://tickets", "tickets/_index.json"),
    ("onboard://memory/summary", "memories.json"),
])
def test_board_path_that_is_a_directory_is_an_error_not_empty_data(resource_server, uri, relative):
    server, project = resource_server
    memory = seed(project)
    invalid = memory / relative
    invalid.unlink()
    invalid.mkdir()

    async def exercise():
        async with Client(server.mcp) as client:
            with pytest.raises(MCPError):
                await client.read_resource(uri)

    asyncio.run(exercise())
