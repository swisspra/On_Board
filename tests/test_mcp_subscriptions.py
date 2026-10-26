"""Native invalidation must observe writes from another real process."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import anyio
from mcp import Client, MCPError
import pytest

ROOT = Path(__file__).resolve().parents[1]
URIS = ["onboard://project", "onboard://tickets", "onboard://memory/summary"]
_IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0

# Another On Board process never writes a board file in place: it writes a
# sibling and renames over the target, which is what the watcher has to catch.
_WRITER = (
    "from pathlib import Path; import sys; "
    "p=Path(sys.argv[1]); t=p.with_suffix('.external'); "
    "t.write_text(sys.argv[2], encoding='utf-8'); t.replace(p)"
)


def write_externally(path, payload):
    subprocess.run([sys.executable, "-B", "-c", _WRITER, str(path), json.dumps(payload)], check=True, timeout=10)


@pytest.fixture
def subscription_server(tmp_path, monkeypatch):
    project = tmp_path / "project"
    memory = project / ".agent-mem"
    (memory / "tickets").mkdir(parents=True)
    (memory / "project.json").write_text('{"description":"synthetic"}', encoding="utf-8")
    (memory / "tickets" / "_index.json").write_text('{"tickets":[]}', encoding="utf-8")
    (memory / "memories.json").write_text('{"entries":[]}', encoding="utf-8")
    monkeypatch.setenv("AGENT_PROJECT_DIR", str(project))
    monkeypatch.setenv("AGENT_MEM_VECTOR_BACKEND", "none")
    monkeypatch.delenv("CURSOR_PROJECT_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.syspath_prepend(str(ROOT))
    spec = importlib.util.spec_from_file_location(f"subscription_server_{uuid.uuid4().hex}", ROOT / "server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    return server, memory


def test_subscriber_observes_external_atomic_ticket_write(subscription_server):
    server, memory = subscription_server
    index = memory / "tickets" / "_index.json"
    payload = {"tickets": [{"id": "TK-000000000001", "title": "external change", "status": "open", "priority": "high", "timestamp": 1}]}

    async def exercise():
        async with Client(server.mcp) as client:
            async with client.listen(resource_subscriptions=["onboard://tickets"]) as subscription:
                assert list(subscription.honored.resource_subscriptions) == ["onboard://tickets"]
                write_externally(index, payload)
                event = await asyncio.wait_for(anext(subscription), timeout=6)
                assert event.uri == "onboard://tickets"
                result = await client.read_resource(event.uri)
                actual = json.loads(result.contents[0].text)
                assert actual["open_items"][0]["id"] == "TK-000000000001"
                assert actual["open_total"] == 1

    asyncio.run(exercise())


def test_subscription_delivers_only_the_resource_it_honored(subscription_server):
    """A memory write is not a ticket event, and the watcher keeps running after it."""
    server, memory = subscription_server
    index = memory / "tickets" / "_index.json"

    async def exercise():
        async with Client(server.mcp) as client:
            async with client.listen(resource_subscriptions=["onboard://tickets"]) as subscription:
                write_externally(memory / "memories.json", {"entries": [{"id": "m-1", "title": "t", "memory_type": "progress", "timestamp": 1}]})
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(anext(subscription), timeout=3.5)
                # Positive control: the same watcher still reports the watched resource.
                write_externally(index, {"tickets": [{"id": "TK-000000000002", "title": "later", "status": "open", "priority": "low", "timestamp": 2}]})
                event = await asyncio.wait_for(anext(subscription), timeout=6)
                assert event.uri == "onboard://tickets"

    asyncio.run(exercise())


def test_unwatched_board_files_never_invalidate_a_resource(subscription_server):
    """agents.json churns on every heartbeat; it must not wake a resource listener."""
    server, memory = subscription_server

    async def exercise():
        async with Client(server.mcp) as client:
            async with client.listen(resource_subscriptions=URIS) as subscription:
                write_externally(memory / "agents.json", {"a1": {"agent_name": "a1", "status": "active", "last_activity": 1}})
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(anext(subscription), timeout=3.5)

    asyncio.run(exercise())


def test_watcher_reports_each_changed_resource_once_and_stops_at_shutdown(subscription_server):
    """One event per changed resource per scan; closing must join the watcher promptly."""
    import board_subscriptions

    server, memory = subscription_server
    index = memory / "tickets" / "_index.json"
    seen = []

    async def exercise():
        bus = board_subscriptions.BoardSubscriptionBus(memory, interval_s=0.05)
        with anyio.fail_after(2):
            async with bus.lifespan(server.mcp):
                unsubscribe = bus.subscribe(seen.append)
                write_externally(index, {"tickets": [{"id": "TK-000000000005", "title": "watched", "status": "open", "priority": "high", "timestamp": 5}]})
                await asyncio.sleep(0.3)
                unsubscribe()
        assert [event.uri for event in seen] == ["onboard://tickets"]
        write_externally(index, {"tickets": []})
        await asyncio.sleep(0.2)
        assert len(seen) == 1

    asyncio.run(exercise())


def test_watcher_reports_nothing_before_the_first_listener(subscription_server):
    """No scan without listeners, a baseline taken at the first subscribe, and no replay."""
    import board_subscriptions

    server, memory = subscription_server
    index = memory / "tickets" / "_index.json"
    seen = []

    async def exercise():
        bus = board_subscriptions.BoardSubscriptionBus(memory, interval_s=0.05)
        async with bus.lifespan(server.mcp):
            write_externally(index, {"tickets": [{"id": "TK-000000000006", "title": "before", "status": "open", "priority": "high", "timestamp": 6}]})
            await asyncio.sleep(0.2)
            unsubscribe = bus.subscribe(seen.append)
            await asyncio.sleep(0.2)
            unsubscribe()
            unsubscribe()  # idempotent
            write_externally(index, {"tickets": []})
            await asyncio.sleep(0.2)
        assert seen == []

    asyncio.run(exercise())


@pytest.mark.skipif(_IS_ROOT, reason="root bypasses file modes")
def test_unreadable_watched_path_neither_kills_the_watcher_nor_fakes_data(subscription_server):
    server, memory = subscription_server
    index = memory / "tickets" / "_index.json"
    memories = memory / "memories.json"
    memories.chmod(0o000)

    async def exercise():
        async with Client(server.mcp) as client:
            async with client.listen(resource_subscriptions=URIS) as subscription:
                with pytest.raises(MCPError):
                    await client.read_resource("onboard://memory/summary")
                write_externally(index, {"tickets": [{"id": "TK-000000000004", "title": "still watched", "status": "open", "priority": "high", "timestamp": 4}]})
                event = await asyncio.wait_for(anext(subscription), timeout=6)
                assert event.uri == "onboard://tickets"

    try:
        asyncio.run(exercise())
    finally:
        memories.chmod(0o644)


@pytest.mark.parametrize("uri, relative, payload, expected", [
    ("onboard://project", "project.json", {"description": "recreated project"}, {"initialized": True, "description_preview": "recreated project"}),
    ("onboard://tickets", "tickets/_index.json", {"tickets": [{"id": "TK-000000000009", "title": "recreated", "status": "open", "timestamp": 9}]}, {"initialized": True, "total": 1, "open_total": 1}),
    ("onboard://memory/summary", "memories.json", {"entries": [{"id": "m-recreated", "title": "recreated", "memory_type": "progress", "timestamp": 9}]}, {"initialized": True, "total": 1}),
])
def test_watched_file_deletion_and_recreation_notify_after_initial_read(subscription_server, uri, relative, payload, expected):
    server, memory = subscription_server
    target = memory / relative

    async def exercise():
        async with Client(server.mcp) as client:
            async with client.listen(resource_subscriptions=[uri]) as subscription:
                assert list(subscription.honored.resource_subscriptions) == [uri]
                first = await client.read_resource(uri)
                assert json.loads(first.contents[0].text)["initialized"] is True
                subprocess.run(
                    [sys.executable, "-B", "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).unlink()", str(target)],
                    check=True, timeout=10,
                )
                removed = await asyncio.wait_for(anext(subscription), timeout=6)
                assert removed.uri == uri
                empty = json.loads((await client.read_resource(uri)).contents[0].text)
                if uri == "onboard://project":
                    assert empty["initialized"] is False
                else:
                    assert empty["total"] == 0
                write_externally(target, payload)
                recreated = await asyncio.wait_for(anext(subscription), timeout=6)
                assert recreated.uri == uri
                current = json.loads((await client.read_resource(uri)).contents[0].text)
                assert {key: current[key] for key in expected} == expected

    asyncio.run(exercise())
