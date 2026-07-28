"""Offline tests for the _board_snapshot mtime gate (issue #12).

Run: python3 test_snapshot_gate_offline.py

Builds a throwaway board in a temp dir, counts how often the JSON loaders
actually run, and asserts the gate skips the re-parse while nothing changes.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="snapgate-"))
os.environ["AGENT_PROJECT_DIR"] = str(_TMP)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server as S  # noqa: E402

MEM = _TMP / ".agent-mem"


def _fresh_board(memories=1, tickets=1):
    """Reset the board on disk and clear the process-level snapshot cache."""
    shutil.rmtree(MEM, ignore_errors=True)
    (MEM / "tickets").mkdir(parents=True)
    _write_mem([{"id": f"m{i}", "memory_type": "progress", "title": "t",
                 "content": "c", "agent_name": "a"} for i in range(memories)])
    S._save_ticket_index([{"id": f"TK-{i}", "status": "open"} for i in range(tickets)])
    S._SNAPSHOT_CACHE["key"] = None
    S._SNAPSHOT_CACHE["snap"] = None


def _write_mem(entries):
    (MEM / "memories.json").write_text(json.dumps({"entries": entries}))


class _Counter:
    """Wrap the two loaders so we can see whether a parse really happened."""

    def __enter__(self):
        self.n = {"mem": 0, "idx": 0}
        self._m, self._i = S._load_mem, S._load_ticket_index

        def mem():
            self.n["mem"] += 1
            return self._m()

        def idx():
            self.n["idx"] += 1
            return self._i()

        S._load_mem, S._load_ticket_index = mem, idx
        return self

    def __exit__(self, *exc):
        S._load_mem, S._load_ticket_index = self._m, self._i


def test_unchanged_board_parses_once():
    """The parked-listener case: many ticks, one parse."""
    _fresh_board()
    with _Counter() as c:
        for _ in range(25):
            S._board_snapshot()
        assert c.n == {"mem": 1, "idx": 1}, c.n


def test_cache_hit_returns_same_object():
    _fresh_board()
    assert S._board_snapshot() is S._board_snapshot()


def test_memory_write_invalidates():
    _fresh_board(memories=1)
    first = S._board_snapshot()
    _write_mem([{"id": "m0", "memory_type": "progress", "title": "t",
                 "content": "c", "agent_name": "a"},
                {"id": "m1", "memory_type": "progress", "title": "t",
                 "content": "c", "agent_name": "a"}])
    with _Counter() as c:
        second = S._board_snapshot()
        assert c.n["mem"] == 1, c.n
    assert second is not first
    assert "m1" in second["memories"]


def test_ticket_write_invalidates():
    _fresh_board(tickets=1)
    first = S._board_snapshot()
    S._save_ticket_index([{"id": "TK-0", "status": "claimed"}])
    second = S._board_snapshot()
    assert second is not first
    assert second["tickets"]["TK-0"]["status"] == "claimed"


def test_same_size_edit_still_invalidates():
    """A rewrite that keeps the byte count must not be mistaken for no-op."""
    _fresh_board()
    _write_mem([{"id": "m0", "memory_type": "progress", "title": "aaa",
                 "content": "c", "agent_name": "a"}])
    first = S._board_snapshot()
    _write_mem([{"id": "m0", "memory_type": "progress", "title": "bbb",
                 "content": "c", "agent_name": "a"}])
    second = S._board_snapshot()
    assert second["memories"]["m0"]["title"] == "bbb"


def test_missing_files_do_not_raise():
    _fresh_board()
    S._board_snapshot()
    (MEM / "memories.json").unlink()
    snap = S._board_snapshot()
    assert snap["memories"] == {}


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as exc:
            failed.append(name)
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
