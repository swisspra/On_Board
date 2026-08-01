"""Board lock invariants.

Written 2026-07-31 after finding that memory_onboard reached the same
agents.json read-modify-write that memory_agent_join holds the board lock for,
without taking the lock. Two doors onto one write, one of them open.

The first two tests are static: they read server.py rather than importing it,
because the bug class is "a mutating tool exists that nobody remembered to
lock" and that is a property of the source, not of any single call.
"""

import os, re, sys, subprocess, tempfile, json
from pathlib import Path

HERE = Path(__file__).parent
SRC = (HERE / "server.py").read_text()

# Tools that read-modify-write shared board state. Every one of these must
# either carry @_with_board_lock or take _board_lock() around its mutation.
# Add to this list when you add a mutating tool; that is the point of it.
MUTATORS = [
    "memory_agent_join", "memory_onboard", "memory_write",
    "memory_create_ticket", "memory_claim_ticket", "memory_submit_ticket",
    "memory_review_ticket", "memory_cancel_ticket", "memory_terminate_ticket",
]


def _body(name: str) -> str:
    m = re.search(rf"\nasync def {name}\(.*?\n(?=\n@|\nasync def |\ndef )", SRC, re.S)
    assert m, f"{name} not found in server.py"
    return m.group(0)


def _is_decorated(name: str) -> bool:
    return bool(re.search(rf"@_with_board_lock\s*\n(?:#.*\n)*async def {name}\b", SRC))


def test_every_mutating_tool_holds_the_board_lock():
    """The two-doors bug: one mutator unlocked is enough to lose a write."""
    unguarded = [
        n for n in MUTATORS
        if not _is_decorated(n) and "async with _board_lock()" not in _body(n)
    ]
    assert unguarded == [], f"mutating tools with no board lock: {unguarded}"


def test_no_lock_nested_inside_a_locked_function():
    """_board_lock opens a fresh fd, so flock blocks on itself. Nesting hangs
    the process permanently rather than raising, which is why this is a test
    and not a code comment."""
    offenders = []
    for name in MUTATORS:
        if _is_decorated(name) and "async with _board_lock()" in _body(name):
            offenders.append(name)
    assert offenders == [], f"decorated AND nested, will deadlock: {offenders}"


def test_onboard_does_not_hold_the_lock_across_the_briefing_render():
    """Joining must be serialized; rendering must not be. Holding the lock
    across _format_compact_onboard would stall every ticket mutation for the
    length of a full briefing."""
    body = _body("memory_onboard")
    assert "async with _board_lock()" in body, "onboard join is unlocked"
    lock_block = body.split("async with _board_lock()")[1]
    render_line = [l for l in lock_block.splitlines() if "_format_compact_onboard" in l]
    assert render_line, "render call not found after the lock block"
    # the render must be dedented back out of the with-block
    assert not render_line[0].startswith("        "), (
        "_format_compact_onboard is inside the lock block; move it out"
    )


WORKER = r"""
import fcntl, json, os, sys, time
lock, data, tag = sys.argv[1], sys.argv[2], sys.argv[3]
fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
try:
    entries = json.load(open(data))
    time.sleep(0.05)          # widen the window a bare RMW would lose
    entries.append(tag)
    tmp = data + ".tmp"
    json.dump(entries, open(tmp, "w"))
    os.replace(tmp, data)
finally:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
"""


def test_concurrent_writes_under_flock_lose_nothing():
    """The actual failure: tmp+rename makes the swap atomic, not the
    read-modify-write. Without the lock the sleep below loses every writer but
    the last. This is the behaviour memory_write now depends on."""
    n = 6
    with tempfile.TemporaryDirectory() as d:
        lock = os.path.join(d, ".board.lock")
        data = os.path.join(d, "memories.json")
        json.dump([], open(data, "w"))
        script = os.path.join(d, "w.py")
        Path(script).write_text(WORKER)
        procs = [
            subprocess.Popen([sys.executable, script, lock, data, f"tag-{i}"])
            for i in range(n)
        ]
        for p in procs:
            assert p.wait(timeout=60) == 0
        got = json.load(open(data))
    assert sorted(got) == sorted(f"tag-{i}" for i in range(n)), (
        f"lost writes: expected {n}, got {len(got)}: {got}"
    )
