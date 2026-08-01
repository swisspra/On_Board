# v4.0.2 — the lock on the front door

Patch release. Two fixes, both found by running the board rather than reading
it.

- **`memory_onboard` wrote the agent record without holding the board lock.**
  It and `memory_agent_join` call the same helper, and only `agent_join` was
  locked — so the unlocked path was the one every session opens first. Two
  doors onto one write, and the open one was the front door. `_board_lock()`
  is now a context manager that `_with_board_lock` is built from; onboard holds
  it across the join and *not* across the briefing render, so a slow briefing
  cannot block the board.

- **A new test file that can actually fail.** `test_board_lock.py` checks the
  invariants instead of the symptom: every mutating tool holds the lock, onboard
  does not hold it across the render, and `_join_agent_session` calls no locked
  tool — nesting would deadlock permanently, since `flock` is per open file
  description. It includes a six-process concurrent-write test, and the static
  check was negative-controlled: removing the lock in a scratch copy makes it
  fail with the right message.

- **Test fixtures no longer carry a real username or real ticket ids.** They
  needed realistic-looking values because the property under test is that the
  compressor preserves paths and IDs verbatim, and real ones had been used
  instead of invented ones. `pyproject.toml` packages `["."]`, so they shipped
  in the wheel. Now `/Users/example/...` and `TK-000000000000`.

Upgrading is a drop-in: no schema change, no migration, no config change.
