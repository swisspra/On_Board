"""Offline tests for the _board_snapshot mtime gate (issue #12).

Run: python -m pytest test_snapshot_gate_offline.py

Builds a throwaway board per test and verifies that memory/ticket edits,
same-size rewrites, and file removal are visible in the next snapshot.
Each test imports server.py under a unique module name and restores the
environment, so combined collection cannot bind tests to another board.
"""

import importlib.util
import json
import os
import shutil
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def load_server(tmp_path):
    """Import server.py bound to tmp_path, leaving the environment as we found it."""
    previous_project = os.environ.get("AGENT_PROJECT_DIR")
    previous_backend = os.environ.get("AGENT_MEM_VECTOR_BACKEND")
    os.environ["AGENT_PROJECT_DIR"] = str(tmp_path)
    os.environ["AGENT_MEM_VECTOR_BACKEND"] = "none"
    try:
        module_name = f"server_snapshot_gate_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous_project is None:
            os.environ.pop("AGENT_PROJECT_DIR", None)
        else:
            os.environ["AGENT_PROJECT_DIR"] = previous_project
        if previous_backend is None:
            os.environ.pop("AGENT_MEM_VECTOR_BACKEND", None)
        else:
            os.environ["AGENT_MEM_VECTOR_BACKEND"] = previous_backend
    module._ensure()
    return module


def _write_mem(mem_dir, entries):
    (mem_dir / "memories.json").write_text(json.dumps({"entries": entries}))


def _fresh_board(server, memories=1, tickets=1):
    """Reset the board on disk and clear the process-level snapshot cache."""
    mem = server.MEMORY_DIR
    shutil.rmtree(mem, ignore_errors=True)
    (mem / "tickets").mkdir(parents=True)
    _write_mem(mem, [{"id": f"m{i}", "memory_type": "progress", "title": "t",
                      "content": "c", "agent_name": "a"} for i in range(memories)])
    server._save_ticket_index([{"id": f"TK-{i}", "status": "open"} for i in range(tickets)])
    server._SNAPSHOT_CACHE["key"] = None
    server._SNAPSHOT_CACHE["snap"] = None




def test_memory_write_invalidates(tmp_path):
    server = load_server(tmp_path)
    _fresh_board(server, memories=1)
    server._board_snapshot()
    _write_mem(server.MEMORY_DIR, [
        {"id": "m0", "memory_type": "progress", "title": "t",
         "content": "c", "agent_name": "a"},
        {"id": "m1", "memory_type": "progress", "title": "t",
         "content": "c", "agent_name": "a"},
    ])
    second = server._board_snapshot()
    assert "m1" in second["memories"]


def test_ticket_write_invalidates(tmp_path):
    server = load_server(tmp_path)
    _fresh_board(server, tickets=1)
    server._board_snapshot()
    server._save_ticket_index([{"id": "TK-0", "status": "claimed"}])
    second = server._board_snapshot()
    assert second["tickets"]["TK-0"]["status"] == "claimed"


def test_same_size_edit_still_invalidates(tmp_path):
    """A rewrite that keeps the byte count must not be mistaken for no-op."""
    server = load_server(tmp_path)
    _fresh_board(server)
    _write_mem(server.MEMORY_DIR, [{"id": "m0", "memory_type": "progress", "title": "aaa",
                                    "content": "c", "agent_name": "a"}])
    server._board_snapshot()
    _write_mem(server.MEMORY_DIR, [{"id": "m0", "memory_type": "progress", "title": "bbb",
                                    "content": "c", "agent_name": "a"}])
    second = server._board_snapshot()
    assert second["memories"]["m0"]["title"] == "bbb"


def test_missing_files_do_not_raise(tmp_path):
    server = load_server(tmp_path)
    _fresh_board(server)
    server._board_snapshot()
    (server.MEMORY_DIR / "memories.json").unlink()
    snap = server._board_snapshot()
    assert snap["memories"] == {}
