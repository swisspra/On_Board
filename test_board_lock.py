"""Board lock: the real thing, not a source grep.

Written 2026-07-31 after finding that memory_onboard reached the same
agents.json read-modify-write that memory_agent_join holds the board lock for,
without taking the lock. Two doors onto one write, one of them open.

The previous version of this file read server.py as text, grepped it for the
decorator, and ran a generic flock demo over a JSON array that never touched
the server. Both passed while the board could still lose writes, because
neither ran a board mutation. These tests run the actual tools in real
processes against a throwaway .agent-mem/: the lock is only real if two
processes racing one board keep every record.

Race window: workers sharing a rendezvous gate fire together (file handshake),
results are asserted after bounded deadlines. No test sleeps to *create* the
race, and no test sleeps to *detect* one.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent


WORKER = r'''
import asyncio, json, os, pathlib, sys, time

sys.path.insert(0, os.environ["ONBOARD_DIR"])
import server as S

SIG = pathlib.Path(os.environ["SIGNAL_DIR"])
PLAN = json.loads(sys.argv[1])
NAME = PLAN["agent_name"]
ROLE = PLAN.get("role", "worker")


def signal(name):
    (SIG / name).write_text("")


def wait_for(name, deadline_s=30.0):
    path = SIG / name
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if path.exists():
            return True
        time.sleep(0.01)
    return False


async def run():
    if PLAN.get("slow_render_s"):
        original = S._format_compact_onboard

        def slow_render(*args, **kwargs):
            signal("rendering")
            time.sleep(PLAN["slow_render_s"])
            return original(*args, **kwargs)

        S._format_compact_onboard = slow_render

    await S.memory_agent_join(S.AgentJoinInput(
        agent_name=NAME, agent_platform=PLAN.get("platform", "probe"), agent_role=ROLE))

    if PLAN.get("rendezvous"):
        signal("ready-" + NAME)
        wait_for("go")

    out = {}
    for step in PLAN["steps"]:
        op = step["op"]
        if op == "signal":
            signal(step["name"])
        elif op == "wait_signal":
            out["waited-" + step["name"]] = wait_for(step["name"])
        elif op == "snapshot_agents":
            out["agents_before"] = {
                a["agent_name"]: a.get("last_activity") for a in S._load_agt().values()}
        elif op == "write":
            out.setdefault("writes", []).append(await S.memory_write(S.MemoryWriteInput(
                agent_name=NAME, memory_type="progress", title=step["title"],
                content=step.get("content", "payload"))))
        elif op == "checkpoint":
            out.setdefault("checkpoints", []).append(await S.memory_checkpoint(
                S.CheckpointInput(agent_name=NAME, summary=step["summary"])))
        elif op == "unpin":
            out["unpin"] = await S.memory_unpin(
                S.MemoryUnpinInput(agent_name=NAME, memory_id=step["memory_id"]))
        elif op == "handoff":
            out["handoff"] = await S.memory_handoff(S.HandoffInput(
                agent_name=NAME, summary=step["summary"], next_steps=["continue"]))
        elif op == "compact":
            out["compact"] = await S.memory_compact(S.CompactInput(agent_name=NAME, force=True))
        elif op == "state":
            out.setdefault("state", []).append(await S.memory_update_state(
                S.UpdateStateInput(agent_name=NAME, key=step["key"], value=step["value"])))
        elif op == "onboard":
            out["onboard"] = await S.memory_onboard(S.OnboardInput(
                agent_name=NAME, agent_platform=PLAN.get("platform", "probe"),
                agent_role=ROLE, mode="brief", include_tickets=True, include_health=False))
        elif op == "list":
            out["list"] = await S.memory_list_tickets(S.ListTicketsInput())
        elif op == "briefing":
            out["briefing"] = await S.memory_get_briefing(S.BriefingInput(mode="brief"))
        elif op == "status":
            out["status"] = await S.memory_status()
        elif op == "create_claim_submit":
            created = await S.memory_create_ticket(S.CreateTicketInput(
                agent_name=NAME, title=step["title"], description="probe",
                target_url="http://local", scope="READ-ONLY",
                required_fields=["r"]))
            tid = [t["id"] for t in S._load_ticket_index() if t["title"] == step["title"]][0]
            claimed = await S.memory_claim_ticket(
                S.ClaimTicketInput(agent_name=NAME, ticket_id=tid))
            submitted = await S.memory_submit_ticket(S.SubmitTicketInput(
                agent_name=NAME, ticket_id=tid, summary="probe submit", stay_active=True))
            out["create_claim_submit"] = [created, claimed, submitted]
        elif op == "create_timed":
            started = time.monotonic()
            out["create"] = await S.memory_create_ticket(S.CreateTicketInput(
                agent_name=NAME, title=step["title"], description="probe",
                target_url="http://local", scope="READ-ONLY",
                required_fields=["r"], assigned_to=step.get("assigned_to")))
            out["create_elapsed"] = round(time.monotonic() - started, 3)
        elif op == "park":
            started = time.monotonic()
            out["park"] = await S.memory_wait_for_event(S.WaitForEventInput(
                agent_name=NAME, timeout_s=step["timeout_s"]))
            out["park_elapsed"] = round(time.monotonic() - started, 3)
        else:
            raise SystemExit("unknown op %r" % op)

    print(json.dumps(out))


asyncio.run(run())
'''


def _board(tmp_path) -> Path:
    return tmp_path / ".agent-mem"


def _env(tmp_path) -> dict:
    return dict(
        os.environ,
        AGENT_PROJECT_DIR=str(tmp_path),
        ONBOARD_DIR=str(REPO_ROOT),
        SIGNAL_DIR=str(tmp_path / "signals"),
        PYTHONDONTWRITEBYTECODE="1",
    )


def _wait_file(path: Path, deadline_s: float = 30.0) -> bool:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if path.exists():
            return True
        time.sleep(0.01)
    return False


def _init_board(tmp_path):
    code = (
        "import asyncio, os, sys;"
        "sys.path.insert(0, os.environ['ONBOARD_DIR']);"
        "import server as S;"
        "asyncio.run(S.memory_init(S.ProjectInitInput(description='board-lock probe')))"
    )
    proc = subprocess.run([sys.executable, "-c", code], env=_env(tmp_path),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-1200:]


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _seed_memories(tmp_path, entries):
    _write_json(_board(tmp_path) / "memories.json", {"entries": entries})


def _seed_agents(tmp_path, agents):
    _write_json(_board(tmp_path) / "agents.json", agents)


def _seed_tickets(tmp_path, tickets):
    _write_json(_board(tmp_path) / "tickets" / "_index.json", {"tickets": tickets})


def _memories(tmp_path):
    return json.loads((_board(tmp_path) / "memories.json").read_text())["entries"]


def _archive(tmp_path):
    path = _board(tmp_path) / "archive.json"
    return json.loads(path.read_text())["entries"] if path.exists() else []


def _tickets(tmp_path):
    return json.loads((_board(tmp_path) / "tickets" / "_index.json").read_text())["tickets"]


def _agents(tmp_path):
    return json.loads((_board(tmp_path) / "agents.json").read_text())


def _titles(entries):
    return [e["title"] for e in entries]


def _old_entry(i, day_offset=90):
    return {
        "id": f"old-{i}", "agent_name": "seeded", "memory_type": "progress",
        "title": f"old entry {i}", "content": "stale payload " * 5,
        "tags": [], "related_files": [], "related_tickets": [],
        "priority": 0, "pinned": False,
        "created_at": "2026-01-01T00:00:00",
        "timestamp": time.time() - day_offset * 86400,
    }


def spawn(tmp_path, plans, timeout=180):
    """Run every plan concurrently; honour rendezvous gates; collect JSON output."""
    (tmp_path / "signals").mkdir(parents=True, exist_ok=True)
    env = _env(tmp_path)
    procs = [
        subprocess.Popen([sys.executable, "-c", WORKER, json.dumps(plan)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for plan in plans
    ]
    gated = [(p, plan) for p, plan in zip(procs, plans) if plan.get("rendezvous")]
    for _, plan in gated:
        assert _wait_file(tmp_path / "signals" / ("ready-" + plan["agent_name"])), \
            f"{plan['agent_name']} never reached the gate (import error?)"
    for _ in gated:
        (tmp_path / "signals" / "go").write_text("")

    results = []
    for proc in procs:
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            raise AssertionError(f"worker hung (lock deadlock?): {err[-1000:]}")
        assert proc.returncode == 0, f"worker rc={proc.returncode}: {err[-1500:]}"
        results.append(json.loads(out.strip().splitlines()[-1]))
    return results


def _writes(n, prefix):
    return [{"op": "write", "title": f"{prefix}-{i}"} for i in range(n)]


# ── concurrent mutation pairs ─────────────────────────────────────────────

def test_concurrent_write_and_checkpoint_lose_nothing(tmp_path):
    """write read-modify-writes memories.json; checkpoint does too.

    Unlocked, the tmp+rename swap is atomic but the read-modify-write is not,
    so one of the two writers overwrites the other's entry.
    """
    _init_board(tmp_path)
    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a", "rendezvous": True, "steps": _writes(15, "A-progress")},
        {"agent_name": "probe-b", "rendezvous": True,
         "steps": [{"op": "checkpoint", "summary": f"cp-{i}"} for i in range(15)]},
    ])
    assert all("Saved" in r for r in a["writes"]), a["writes"]
    assert all("Checkpoint" in r for r in b["checkpoints"]), b["checkpoints"]

    entries = _memories(tmp_path)
    titles = _titles(entries)
    missing = [f"A-progress-{i}" for i in range(15) if f"A-progress-{i}" not in titles]
    assert missing == [], f"lost A's writes: {missing}"
    checkpoints = [e for e in entries if e["memory_type"] == "checkpoint"]
    assert len(checkpoints) == 15, f"lost checkpoints: {len(checkpoints)}/15"


def test_write_and_unpin_both_persist(tmp_path):
    """The unpin is a read-modify-write of the same file as the write."""
    _init_board(tmp_path)
    _seed_memories(tmp_path, [{
        "id": "m-pin", "agent_name": "seeded", "memory_type": "warning",
        "title": "pinned thing", "content": "must stay pinned until unpinned",
        "tags": [], "related_files": [], "priority": 3, "pinned": True,
        "pinned_summary": "pinned.", "created_at": "2026-01-01T00:00:00",
        "timestamp": time.time(),
    }])
    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a", "rendezvous": True, "steps": _writes(10, "A-progress")},
        {"agent_name": "probe-b", "rendezvous": True,
         "steps": [{"op": "unpin", "memory_id": "m-pin"}]},
    ])
    assert all("Saved" in r for r in a["writes"]), a["writes"]
    assert "Unpinned" in b["unpin"], b["unpin"]

    by_id = {e["id"]: e for e in _memories(tmp_path)}
    assert by_id["m-pin"]["pinned"] is False, "the unpin was lost"
    assert by_id["m-pin"]["unpinned_by"] == "probe-b"
    titles = _titles(by_id.values())
    missing = [f"A-progress-{i}" for i in range(10) if f"A-progress-{i}" not in titles]
    assert missing == [], f"lost A's writes: {missing}"


def test_write_and_handoff_both_persist(tmp_path):
    """Handoff writes memories.json AND agents.json; the write shares the first."""
    _init_board(tmp_path)
    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a", "rendezvous": True, "steps": _writes(10, "A-progress")},
        {"agent_name": "probe-b", "rendezvous": True,
         "steps": [{"op": "handoff", "summary": "leaving"}]},
    ])
    assert all("Saved" in r for r in a["writes"]), a["writes"]
    assert "Handoff" in b["handoff"], b["handoff"]

    titles = _titles(_memories(tmp_path))
    missing = [f"A-progress-{i}" for i in range(10) if f"A-progress-{i}" not in titles]
    assert missing == [], f"lost A's writes: {missing}"
    statuses = {ag["agent_name"]: ag["status"] for ag in _agents(tmp_path).values()}
    assert statuses.get("probe-b") == "handed_off", statuses


def test_write_survives_a_concurrent_compact(tmp_path):
    """Compaction rewrites memories.json wholesale (hot only) plus archive.json."""
    _init_board(tmp_path)
    _seed_memories(tmp_path, [_old_entry(i) for i in range(60)])
    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a", "rendezvous": True, "steps": _writes(5, "A-progress")},
        {"agent_name": "probe-b", "rendezvous": True, "steps": [{"op": "compact"}]},
    ])
    assert all("Saved" in r for r in a["writes"]), a["writes"]
    assert "Compaction complete" in b["compact"], b["compact"]

    mem, archive = _memories(tmp_path), _archive(tmp_path)
    titles = _titles(mem)
    missing = [f"A-progress-{i}" for i in range(5) if f"A-progress-{i}" not in titles]
    assert missing == [], f"compaction dropped the fresh writes: {missing}"
    archived_ids = {e["id"] for e in archive}
    lost = [f"old-{i}" for i in range(60) if f"old-{i}" not in archived_ids]
    assert lost == [], f"cold entries vanished: {lost}"
    assert len(mem) + len(archive) == 65, (len(mem), len(archive))


def test_state_updates_to_different_keys_keep_both(tmp_path):
    _init_board(tmp_path)
    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a", "rendezvous": True,
         "steps": [{"op": "state", "key": "key-a", "value": "va"}]},
        {"agent_name": "probe-b", "rendezvous": True,
         "steps": [{"op": "state", "key": "key-b", "value": "vb"}]},
    ])
    assert "key-a" in a["state"][0], a["state"]
    assert "key-b" in b["state"][0], b["state"]
    state = json.loads((_board(tmp_path) / "state.json").read_text())
    assert state["key-a"]["value"] == "va" and state["key-b"]["value"] == "vb", state


def test_park_heartbeat_and_sweep_all_preserve_agents(tmp_path):
    """agents.json is RMW'd by join, heartbeat and sweep at once.

    A parked listener heartbeats (under the lock) while a peer joins, sweeps a
    stale agent to KIA and writes a memory. Unlocked, the heartbeat is the
    write that vanishes — and a listener with a lost heartbeat is what the
    sweep then kills. The parked agent's last_activity must advance *during the
    park*, which only the heartbeat does.
    """
    _init_board(tmp_path)
    stale = time.time() - 3600
    _seed_agents(tmp_path, {"ghost": {
        "agent_name": "ghost", "agent_platform": "probe", "status": "active",
        "last_activity": stale, "memories_written": 0,
    }})

    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a", "rendezvous": True,
         "steps": [{"op": "snapshot_agents"}, {"op": "park", "timeout_s": 4}]},
        {"agent_name": "probe-b", "rendezvous": True,
         "steps": [{"op": "status"}, {"op": "write", "title": "B-progress"}]},
    ], timeout=90)

    assert "Nothing in" in a["park"], a["park"]
    assert "probe-b" in b["status"], b["status"]

    by_name = {ag["agent_name"]: ag for ag in _agents(tmp_path).values()}
    assert set(by_name) == {"ghost", "probe-a", "probe-b"}, list(by_name)
    assert by_name["ghost"]["status"] == "kia", "the sweep never ran"
    assert by_name["probe-a"]["status"] == "active", "the parked agent was swept"
    assert by_name["probe-a"]["last_activity"] > a["agents_before"]["probe-a"], \
        "the heartbeat write was lost"
    assert "B-progress" in _titles(_memories(tmp_path))


# ── read tools must not hold the lock while rendering ─────────────────────

def test_onboard_render_does_not_block_a_writer(tmp_path):
    """The join is locked; the render is not.

    A deliberate render delay is injected into the rendering half only. If the
    lock were held there, the peer's create would wait for the whole render.
    """
    _init_board(tmp_path)
    render_s = 3.0
    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a", "slow_render_s": render_s,
         "steps": [{"op": "onboard"}]},
        {"agent_name": "probe-b",
         "steps": [{"op": "wait_signal", "name": "rendering"},
                   {"op": "create_timed", "title": "not-blocked"}]},
    ], timeout=90)

    assert a["onboard"].startswith("<on_board_protocol>"), a["onboard"][:200]
    assert b["waited-rendering"] is True, "the render signal never fired"
    assert "Ticket created" in b["create"], b["create"]
    assert b["create_elapsed"] < render_s / 2, (
        f"writer waited {b['create_elapsed']}s behind a {render_s}s render — "
        "the render is holding the lock")


def test_parked_wait_does_not_block_a_writer(tmp_path):
    """A park may last minutes; it must hold no lock while it sleeps.

    The peer creates a ticket addressed to the parked agent and the park must
    wake on it — impossible had the create been blocked for the whole park.
    """
    _init_board(tmp_path)
    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a",
         "steps": [{"op": "park", "timeout_s": 1},
                   {"op": "signal", "name": "parked"},
                   {"op": "park", "timeout_s": 8}]},
        {"agent_name": "probe-b",
         "steps": [{"op": "wait_signal", "name": "parked"},
                   {"op": "create_timed", "title": "wake-probe",
                    "assigned_to": "probe-a"}]},
    ], timeout=90)

    assert b["waited-parked"] is True, "the park signal never fired"
    assert b["create_elapsed"] < 3.0, (
        f"create waited {b['create_elapsed']}s while a peer was parked — "
        "the park is holding the lock")
    assert "wake-probe" in a["park"], a["park"][:300]
    assert "Nothing in" not in a["park"]


def test_expired_claim_viewer_does_not_clobber_a_concurrent_create(tmp_path):
    """The auto-transition saves the index; the create appends to it.

    The old code auto-transitioned on the index list it read BEFORE rendering
    the briefing, then saved that stale list — erasing anything created in
    between. Both processes start together here.
    """
    _init_board(tmp_path)
    now = time.time()
    _seed_tickets(tmp_path, [{
        "id": "TK-exp", "title": "expired claim", "description": "d",
        "target_url": "local", "scope": "READ-ONLY", "required_fields": ["r"],
        "priority": "medium", "status": "claimed", "created_by": "owner",
        "assigned_to": None, "claimed_by": "probe-z",
        "claimed_at": now - 400, "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00", "timestamp": now,
    }])

    a, b = spawn(tmp_path, [
        {"agent_name": "probe-a", "rendezvous": True,
         "steps": [{"op": "list"}, {"op": "briefing"}]},
        {"agent_name": "probe-b", "rendezvous": True,
         "steps": [{"op": "create_claim_submit", "title": "fresh work"}]},
    ], timeout=120)

    assert "TK-exp" in a["list"], a["list"][:300]
    assert "TK-exp" in a["briefing"], a["briefing"][:300]
    assert all("cannot" not in r for r in b["create_claim_submit"]), b["create_claim_submit"]

    by_id = {t["id"]: t for t in _tickets(tmp_path)}
    assert len(by_id) == 2, f"a ticket was lost under concurrency: {list(by_id)}"
    # the expired claim advanced with its records intact
    assert by_id["TK-exp"]["status"] == "in_progress", by_id["TK-exp"]["status"]
    assert by_id["TK-exp"]["claimed_by"] == "probe-z"
    assert by_id["TK-exp"]["claimed_at"] == pytest.approx(now - 400, abs=1)
    # the concurrent create+submit survived the viewer's index save
    fresh = [t for t in by_id.values() if t["title"] == "fresh work"]
    assert len(fresh) == 1, list(by_id)
    assert fresh[0]["status"] == "submitted", fresh[0]["status"]
    assert fresh[0]["submitted_by"] == "probe-b"
    assert (_board(tmp_path) / "tickets" / "review" / f"{fresh[0]['id']}-submit.md").exists()


# ── the lock is not reentrant: no nesting ────────────────────────────────

def test_mutating_tools_do_not_deadlock_in_sequence(tmp_path):
    """Every mutator takes and releases the lock; none may nest it.

    flock on a fresh fd blocks on itself, and a nested acquisition hangs the
    board instead of raising. Running the mutating tools back to back in one
    process is the cheap proof that none of them nests.
    """
    _init_board(tmp_path)
    results = spawn(tmp_path, [{
        "agent_name": "probe-a",
        "steps": [
            {"op": "write", "title": "w1"},
            {"op": "checkpoint", "summary": "cp"},
            {"op": "state", "key": "k", "value": "v"},
            {"op": "handoff", "summary": "bye"},
            {"op": "onboard"},
            {"op": "list"},
            {"op": "status"},
            {"op": "briefing"},
            {"op": "compact"},
        ],
    }], timeout=60)[0]
    assert "Saved" in results["writes"][0]
    assert "Checkpoint" in results["checkpoints"][0]
    assert "k" in results["state"][0]
    assert "Handoff" in results["handoff"]
