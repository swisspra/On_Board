"""Cross-process stress: N real processes hammer one board simultaneously.

Proves the two audit fixes at the process level, where the unit suites can't:
  HIGH-2  board lock -> zero lost tickets when creates/claims collide
  HIGH-1  per-agent cursors survive concurrent listeners without corruption

Run: python3 test_a2a_multiprocess.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
SCRATCH = Path(tempfile.mkdtemp(prefix="onboard-mp-"))
N_PROCS = 3
N_TICKETS = 12          # per process -> 36 total

WORKER = r"""
import asyncio, os, sys, time
sys.path.insert(0, os.environ["ONBOARD_DIR"])
import server as S

NAME = sys.argv[1]
N = int(sys.argv[2])
START_AT = float(sys.argv[3])

async def main():
    await S.memory_agent_join(S.AgentJoinInput(
        agent_name=NAME, agent_platform="stress", agent_role="worker"))
    # barrier: all processes fire in the same instant
    time.sleep(max(0.0, START_AT - time.time()))
    made = 0
    for i in range(N):
        r = await S.memory_create_ticket(S.CreateTicketInput(
            agent_name=NAME, title=f"{NAME}-t{i}", description="stress",
            target_url="http://x", scope="READ-ONLY",
            required_fields=["log"]))
        made += 1
        # interleave claims of whatever is open, to mix mutation types
        if i % 3 == 0:
            for t in S._load_ticket_index():
                if t["status"] == "open" and not t.get("assigned_to"):
                    await S.memory_claim_ticket(S.ClaimTicketInput(
                        agent_name=NAME, ticket_id=t["id"]))
                    break
    # one wait to exercise the per-agent cursor path concurrently
    await S.memory_wait_for_event(S.WaitForEventInput(agent_name=NAME, timeout_s=1))
    print(f"{NAME} made={made}")

asyncio.run(main())
"""


def main() -> int:
    env = dict(os.environ,
               AGENT_PROJECT_DIR=str(SCRATCH),
               ONBOARD_DIR=str(HERE))
    # init once
    subprocess.run([sys.executable, "-c",
        "import asyncio,os,sys; sys.path.insert(0,os.environ['ONBOARD_DIR']);"
        "import server as S;"
        "asyncio.run(S.memory_init(S.ProjectInitInput(description='mp stress')))"],
        env=env, check=True, capture_output=True)

    start_at = time.time() + 1.5
    procs = [subprocess.Popen(
                [sys.executable, "-c", WORKER, f"agent{i}", str(N_TICKETS), str(start_at)],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for i in range(N_PROCS)]
    for p in procs:
        out, err = p.communicate(timeout=120)
        print(" ", out.strip() or err.strip()[:200])
        if p.returncode != 0:
            print("WORKER FAILED:", err[:800])
            return 1

    idx = json.load(open(SCRATCH / ".agent-mem" / "tickets" / "_index.json"))
    tickets = idx["tickets"] if isinstance(idx, dict) else idx
    expected = N_PROCS * N_TICKETS
    ids = [t["id"] for t in tickets]

    ok = True
    def check(label, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ""))

    check(f"no lost tickets under contention ({expected} expected)",
          len(tickets) == expected, f"got {len(tickets)}")
    check("no duplicate ids", len(ids) == len(set(ids)))
    per_agent = {f"agent{i}": sum(1 for t in tickets if t["created_by"] == f"agent{i}")
                 for i in range(N_PROCS)}
    check("every process kept all its writes",
          all(v == N_TICKETS for v in per_agent.values()), str(per_agent))
    # HIGH-1: every listener got its own intact cursor file
    cursors = sorted((SCRATCH / ".agent-mem").glob("watch-*.json"))
    check(f"per-agent cursor files ({N_PROCS} expected)", len(cursors) == N_PROCS,
          str([c.name for c in cursors]))
    parse_ok = True
    for c in cursors:
        try:
            json.load(open(c))
        except Exception:
            parse_ok = False
    check("all cursors parse (no tmp-collision corruption)", parse_ok)

    print(f"\n{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        import shutil
        shutil.rmtree(SCRATCH, ignore_errors=True)
    sys.exit(code)
