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
    watch = S._load_watch()
    check("watch.json has both agents", SUP in watch and WRK in watch, str(list(watch)))
    check("cursor is reduced", all(
        set(v) <= {"status", "assigned_to"}
        for v in watch[WRK].get("tickets", {}).values()), "unreduced fields stored")
    res = await wait_as(WRK, timeout_s=5)
    check("idle on a quiet board", "Nothing in" in res, res[:90])

    print(f"\n{len(ok)}/{len(ok) + len(fail)} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    sys.exit(code)
