"""Live end-to-end for memory_wait_for_event against a scratch .agent-mem/.

Real files, real asyncio, real On Board tools — only the timeouts are shrunk
so the run takes seconds instead of minutes.

Run: python3 test_a2a_live.py
"""

import asyncio
import os
import shutil
import sys
import tempfile

SCRATCH = tempfile.mkdtemp(prefix="onboard-a2a-live-")
os.environ["AGENT_PROJECT_DIR"] = SCRATCH

import server as S          # noqa: E402  (must follow the env var)

SUP = "desk-a"              # supervisor / ticket creator
WRK = "desk-b"              # worker / listener


async def join(name, role):
    await S.memory_agent_join(S.AgentJoinInput(
        agent_name=name, agent_platform="claude-desktop", agent_role=role))


async def make_ticket(by, title, assigned_to=None, delay=0.0):
    if delay:
        await asyncio.sleep(delay)
    return await S.memory_create_ticket(S.CreateTicketInput(
        agent_name=by, title=title, description="scratch test ticket",
        target_url="http://localhost/none", scope="READ-ONLY",
        required_fields=["console-log"], assigned_to=assigned_to))


async def wait_as(name, timeout_s=8, **kw):
    return await S.memory_wait_for_event(
        S.WaitForEventInput(agent_name=name, timeout_s=timeout_s, **kw))


async def main():
    ok, fail = [], []

    def check(label, cond, detail=""):
        (ok if cond else fail).append(label)
        print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ""))

    await S.memory_init(S.ProjectInitInput(description="a2a scratch"))
    await join(SUP, "lead")
    await join(WRK, "worker")
    print(f"scratch: {SCRATCH}\n")

    # 1. worker parks, supervisor files a ticket 3s later -> worker wakes
    print("1) wake on a peer's ticket mid-wait")
    res, _ = await asyncio.gather(
        wait_as(WRK, timeout_s=20),
        make_ticket(SUP, "please run the smoke test", assigned_to=WRK, delay=3.0),
    )
    check("worker woke", "event(s) after" in res, res[:90])
    check("saw the ticket", "please run the smoke test" in res, res[:90])
    check("did not time out", "Nothing in" not in res)

    # 2. two tickets land while nobody listens -> next call drains instantly
    print("\n2) backlog drains without blocking")
    await make_ticket(SUP, "backlog one", assigned_to=WRK)
    await make_ticket(SUP, "backlog two", assigned_to=WRK)
    t0 = asyncio.get_event_loop().time()
    res = await wait_as(WRK, timeout_s=20)
    elapsed = asyncio.get_event_loop().time() - t0
    check("returned immediately", elapsed < 1.0, f"{elapsed:.2f}s")
    check("drained both", "backlog one" in res and "backlog two" in res, res[:120])
    check("flagged as backlog", "backlog drained" in res, res[:90])

    # 3. loop guard: an agent must not wake on its own ticket
    print("\n3) loop guard")
    # assigned to SUP itself: the loop guard must drop it for SUP, and
    # only_mine must drop it for WRK. Leaving it unassigned would be the open
    # queue, which SHOULD wake WRK — a different (correct) behaviour.
    await make_ticket(SUP, "supervisor talking to itself", assigned_to=SUP)
    res = await wait_as(SUP, timeout_s=5)
    check("supervisor stayed asleep", "Nothing in" in res, res[:90])

    # 4. cursor persisted, and a re-arm on a quiet board reports idle
    print("\n4) cursor + idle re-arm")
    # HIGH-1: cursor is one file per agent — a single shared watch.json would
    # be RMW'd by two server processes and its .tmp path collides on save.
    ws, ww = S._watch_p(SUP), S._watch_p(WRK)
    check("per-agent cursor files exist", ws.exists() and ww.exists(),
          f"{ws.name}={ws.exists()} {ww.name}={ww.exists()}")
    watch = S._load_watch(WRK)
    check("cursor is reduced", watch and all(
        set(v) <= {"status", "assigned_to", "rejection_count"}
        for v in watch.get("tickets", {}).values()), "unreduced fields stored")
    res = await wait_as(WRK, timeout_s=5)
    check("idle on a quiet board", "Nothing in" in res, res[:90])

    # 5. role gate: the worker may not sign off on its own work
    print("\n5) role gate — completed != success")
    await make_ticket(SUP, "needs independent review", assigned_to=WRK)
    tid = [t["id"] for t in S._load_ticket_index()
           if t["title"] == "needs independent review"][0]
    await S.memory_claim_ticket(S.ClaimTicketInput(agent_name=WRK, ticket_id=tid))
    res = await S.memory_submit_ticket(S.SubmitTicketInput(
        agent_name=WRK, ticket_id=tid, summary="work done", stay_active=True))
    check("worker can submit", "cannot submit" not in res, res[:110])
    still = [a for a in S._load_agt().values()
             if a.get("agent_name") == WRK and a.get("status") == "active"]
    check("stay_active keeps the listener on board", bool(still),
          "submit auto-handed-off the worker")

    res = await S.memory_review_ticket(S.ReviewTicketInput(
        agent_name=WRK, ticket_id=tid, verdict="approve",
        review_notes="lgtm, reviewed by me"))
    check("worker BLOCKED from reviewing own work", "cannot review" in res, res[:140])
    check("denial names the owner to ask", SUP in res, res[:200])

    res = await S.memory_review_ticket(S.ReviewTicketInput(
        agent_name=SUP, ticket_id=tid, verdict="approve", review_notes="checked"))
    check("owner can review", "cannot review" not in res, res[:140])
    t = [x for x in S._load_ticket_index() if x["id"] == tid][0]
    check("ticket closed", t["status"] == "closed", t["status"])
    check("audit records the basis", t.get("review_permission") == "owner",
          str(t.get("review_permission")))

    # 6. reject -> retry -> approve, verdicts carried, nothing stale
    print("\n6) reject/retry cycle — MED-1 + MED-2")
    await make_ticket(SUP, "will be rejected once", assigned_to=WRK)
    tid = [t["id"] for t in S._load_ticket_index()
           if t["title"] == "will be rejected once"][0]
    await S.memory_claim_ticket(S.ClaimTicketInput(agent_name=WRK, ticket_id=tid))
    await S.memory_submit_ticket(S.SubmitTicketInput(
        agent_name=WRK, ticket_id=tid, summary="attempt 1", stay_active=True))
    await wait_as(WRK, timeout_s=1)          # advance wk cursor past own submit
    await S.memory_review_ticket(S.ReviewTicketInput(
        agent_name=SUP, ticket_id=tid, verdict="reject",
        review_notes="wrong block", fix_instructions="use lines 1-5"))
    res = await wait_as(WRK, timeout_s=5)
    check("worker wakes on reject with reason", "REJECTED" in res and "use lines 1-5" in res, res[:200])
    res_sup = await wait_as(SUP, timeout_s=2)
    check("rejecting owner does NOT wake on own reject", "Nothing in" in res_sup, res_sup[:120])

    await S.memory_claim_ticket(S.ClaimTicketInput(agent_name=WRK, ticket_id=tid))
    await S.memory_submit_ticket(S.SubmitTicketInput(
        agent_name=WRK, ticket_id=tid, summary="attempt 2", stay_active=True))
    await wait_as(WRK, timeout_s=1)
    await S.memory_review_ticket(S.ReviewTicketInput(
        agent_name=SUP, ticket_id=tid, verdict="approve", review_notes="good now"))
    res = await wait_as(WRK, timeout_s=5)
    check("worker wakes on the approve", "closed" in res, res[:160])
    check("approve is not flagged REJECTED", "REJECTED" not in res, res[:160])
    check("no stale Fix from the failed round", "use lines 1-5" not in res, res[:200])

    print(f"\n{len(ok)}/{len(ok) + len(fail)} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    sys.exit(code)
