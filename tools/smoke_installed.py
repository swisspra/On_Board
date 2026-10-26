#!/usr/bin/env python3
"""Exercise a wheel-installed runtime outside its source checkout.

Native imports, CLI identity, the three native resources and an ordinary stdio
shutdown, all bound to a throwaway project with no real board.

The resources are read over real `onboard-memory-mcp` stdio subprocesses in both
protocol eras the installed SDK negotiates (`auto` -> modern 2026-07-28, `legacy`
-> the initialize handshake), and a write made by a *separate* process is
observed through a real `subscriptions/listen` stream. The proof is therefore the
wire - an installed console process and the installed client SDK - not an
in-process `Client(server.mcp)` call.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


SMOKE = r'''
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import a2a_wait
import board_resources
import board_subscriptions
import server
import thrift_compress
import ticket_roles

prefix = Path(sys.prefix).resolve()
for module in (server, a2a_wait, ticket_roles, thrift_compress, board_resources, board_subscriptions):
    assert Path(module.__file__).resolve().is_relative_to(prefix), module.__file__

installed_version = importlib.metadata.version("onboard-memory-mcp")
command = Path(sys.executable).parent / ("onboard-memory-mcp.exe" if os.name == "nt" else "onboard-memory-mcp")
reported = subprocess.run([str(command), "--version"], text=True, capture_output=True, timeout=15)
assert reported.returncode == 0, reported.stderr
assert reported.stdout.strip() == f"onboard-memory-mcp {installed_version}", reported.stdout

icons = server._server_icons()
assert icons and icons[0].src.startswith("data:image/png;base64,"), "installed icon missing"
tools = asyncio.run(server.mcp.list_tools())
prompts = asyncio.run(server.mcp.list_prompts())
assert len(tools) == 30 and len(prompts) == 2, (len(tools), len(prompts))

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.client.subscriptions import ResourceUpdated
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS

URIS = ("onboard://project", "onboard://tickets", "onboard://memory/summary")
TICKETS_URI = "onboard://tickets"
TICKET = {"id": "TK-0000000000A1", "title": "synthetic wire ticket", "status": "open", "priority": "high", "timestamp": 1}
TICKET_PROJECTION = {"id": TICKET["id"], "title_preview": TICKET["title"], "status": "open", "priority": "high", "assigned_to": None, "claimed_by": None}

# Another On Board process never writes a board file in place: it writes a
# sibling and renames over the target, which is what the watcher has to catch.
# `mkdir(parents=True)` is what turns an uninitialized project into a board.
_WRITER = (
    "from pathlib import Path; import sys; "
    "p=Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True); "
    "t=p.with_suffix('.external'); t.write_text(sys.argv[2], encoding='utf-8'); t.replace(p)"
)


def child_env(project):
    """The child board sees only this synthetic project, never a workstation override."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("CURSOR_PROJECT_DIR", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env["AGENT_PROJECT_DIR"] = str(project)
    env["AGENT_MEM_VECTOR_BACKEND"] = "none"
    return env


def parameters(project):
    return StdioServerParameters(command=str(command), args=[], env=child_env(project), cwd=str(project))


async def read_json(client, uri):
    result = await asyncio.wait_for(client.read_resource(uri), timeout=20)
    assert result.contents[0].mime_type == "application/json", uri
    return json.loads(result.contents[0].text)


async def assert_empty_project(project, mode):
    """List and read the three resources over a real stdio process; create nothing."""
    async with Client(parameters(project), mode=mode) as client:
        version = client.protocol_version
        expected = MODERN_PROTOCOL_VERSIONS if mode == "auto" else HANDSHAKE_PROTOCOL_VERSIONS
        assert version in expected, (mode, version)
        listed = await asyncio.wait_for(client.list_resources(), timeout=20)
        assert {str(item.uri) for item in listed.resources} == set(URIS)
        for uri in URIS:
            payload = await read_json(client, uri)
            assert payload["initialized"] is False, (uri, payload)
        return version


async def observe_external_write(project):
    """A write from another process must arrive as a ResourceUpdated over the wire."""
    index = project / ".agent-mem" / "tickets" / "_index.json"
    async with Client(parameters(project), mode="auto") as client:
        async with client.listen(resource_subscriptions=[TICKETS_URI]) as subscription:
            assert list(subscription.honored.resource_subscriptions) == [TICKETS_URI]
            before = await read_json(client, TICKETS_URI)
            assert before["initialized"] is False and before["open_total"] == 0, before
            subprocess.run(
                [sys.executable, "-B", "-c", _WRITER, str(index), json.dumps({"tickets": [TICKET]})],
                check=True, timeout=15,
            )
            event = await asyncio.wait_for(anext(subscription), timeout=20)
            assert isinstance(event, ResourceUpdated) and event.uri == TICKETS_URI, event
            after = await read_json(client, TICKETS_URI)
            assert after["open_total"] == 1 and after["total"] == 1, after
            assert after["open_items"][0] == TICKET_PROJECTION, after["open_items"][0]


async def refetch_current_state(project):
    """A reconnect reads current state; nothing here claims the event is replayed."""
    async with Client(parameters(project), mode="auto") as client:
        current = await read_json(client, TICKETS_URI)
        assert current["open_total"] == 1 and current["open_items"][0] == TICKET_PROJECTION, current


with tempfile.TemporaryDirectory(prefix="onboard-stdio-project-") as directory:
    project = Path(directory)
    modern = asyncio.run(assert_empty_project(project, "auto"))
    legacy = asyncio.run(assert_empty_project(project, "legacy"))
    assert modern != legacy, (modern, legacy)
    assert list(project.iterdir()) == [], "resource read initialized a board"
    asyncio.run(observe_external_write(project))
    asyncio.run(refetch_current_state(project))

result = subprocess.run([str(command)], input="", text=True, capture_output=True, timeout=15)
assert result.returncode == 0, result.stderr
print(f"Installed runtime passed: {len(tools)} tools, {len(prompts)} prompts, "
      f"{len(URIS)} resources over stdio in {modern} and {legacy} eras, version {installed_version}, "
      f"icon and console entrypoint")
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("python", type=Path, help="Python executable in the wheel-only virtual environment")
    python = parser.parse_args().python.absolute()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="onboard-installed-smoke-") as directory:
        env["AGENT_PROJECT_DIR"] = directory
        result = subprocess.run([str(python), "-I", "-c", SMOKE], cwd=directory, env=env, timeout=180)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
