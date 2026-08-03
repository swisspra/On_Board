import asyncio
import importlib.util
import os
import time
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_server(tmp_path, vector_backend="none"):
    os.environ["AGENT_PROJECT_DIR"] = str(tmp_path)
    os.environ["AGENT_MEM_VECTOR_BACKEND"] = vector_backend
    module_name = f"server_under_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._ensure()
    return module


def seed_project(server):
    now = time.time()
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_agt({
        "a1": {
            "agent_name": "codex-main",
            "agent_platform": "codex",
            "status": "active",
            "memories_written": 3,
            "last_activity": now,
        }
    })
    server._save_mem([
        {
            "id": "m1",
            "agent_name": "codex-main",
            "memory_type": "decision",
            "title": "Ticket TK-abc implementation decision",
            "content": "Use server.py for the ticket-scoped briefing implementation.",
            "tags": ["ticket", "briefing"],
            "related_files": ["server.py"],
            "priority": 2,
            "pinned": False,
            "created_at": "2026-05-08T12:00:00",
            "timestamp": now,
        },
        {
            "id": "m2",
            "agent_name": "codex-main",
            "memory_type": "handoff",
            "title": "Handoff from codex-main",
            "content": "Next agent should inspect TK-abc.",
            "tags": ["handoff"],
            "related_files": [],
            "priority": 3,
            "pinned": True,
            "created_at": "2026-05-08T12:05:00",
            "timestamp": now,
        },
    ])


def test_ticket_scoped_briefing_shows_ticket_details_and_related_memory(tmp_path):
    server = load_server(tmp_path)
    seed_project(server)
    server._tickets_dir()
    server._save_ticket_index([
        {
            "id": "TK-abc",
            "title": "Implement ticket scoped briefing",
            "description": "Briefing should focus on one ticket and related memory.",
            "target_url": "file://server.py",
            "scope": "READ-ONLY",
            "required_fields": ["related-memory", "next-step"],
            "forbidden": ["change unrelated tools"],
            "selector_hints": [],
            "priority": "high",
            "status": "open",
            "created_by": "codex-main",
            "assigned_to": "codex",
            "claimed_by": None,
            "tags": ["briefing"],
            "related_files": ["server.py"],
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": time.time(),
        }
    ])

    output = asyncio.run(server.memory_get_briefing(server.BriefingInput(mode="brief", ticket_id="TK-abc")))

    assert "Ticket Focus" in output
    assert "TK-abc" in output
    assert "Required Fields" in output
    assert "related-memory" in output
    assert "Related Memories" in output
    assert "Ticket TK-abc implementation decision" in output


def test_briefing_and_status_limit_agent_history_to_latest_ten(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    now = time.time()
    server._save_agt({
        f"a{i:02d}": {
            "agent_name": f"agent-{i:02d}",
            "agent_platform": "codex",
            "status": "kia",
            "memories_written": i,
            "last_activity": now + i,
        }
        for i in range(12)
    })
    server._save_mem([])

    briefing = asyncio.run(server.memory_get_briefing(server.BriefingInput(mode="brief", token_budget=8000)))
    status = asyncio.run(server.memory_status())

    assert "Agent History (latest 10 of 12)" in briefing
    assert briefing.count("**agent-") == 10
    assert "agent-11" in briefing
    assert "agent-02" in briefing
    assert "agent-01" not in briefing
    assert "agent-00" not in briefing

    assert "Agents (latest 10 of 12)" in status
    assert status.count("**agent-") == 10
    assert "agent-11" in status
    assert "agent-02" in status
    assert "agent-01" not in status
    assert "agent-00" not in status


def test_briefing_hides_type_header_when_all_entries_are_pinned(tmp_path):
    server = load_server(tmp_path)
    seed_project(server)
    mem = server._load_mem()
    for m in mem:
        if m["memory_type"] == "decision":
            m["pinned"] = True
    server._save_mem(mem)

    briefing = asyncio.run(server.memory_get_briefing(server.BriefingInput(mode="brief", token_budget=8000)))

    assert "## 📌 Pinned" in briefing
    assert "## 🏛️ Decision" not in briefing


def test_memory_onboard_registers_agent_and_returns_session_context(tmp_path):
    server = load_server(tmp_path)
    seed_project(server)
    mem = server._load_mem()
    mem.append({
        "id": "m3",
        "agent_name": "codex-main",
        "memory_type": "warning",
        "title": "Critical deploy warning",
        "content": "Do not replace production bindings with placeholder values.",
        "pinned_summary": "Production bindings must stay real; placeholders break deploys.",
        "tags": ["deploy"],
        "related_files": [],
        "priority": 3,
        "pinned": True,
        "created_at": "2026-05-08T12:06:00",
        "timestamp": time.time(),
    })
    server._save_mem(mem)
    server._tickets_dir()
    server._save_ticket_index([
        {
            "id": "TK-abc",
            "title": "Implement session onboarding",
            "description": "New agents should enter through one On Board call.",
            "target_url": "file://server.py",
            "scope": "READ-ONLY",
            "required_fields": ["briefing", "agent-registration"],
            "priority": "high",
            "status": "open",
            "created_by": "codex-main",
            "assigned_to": "codex",
            "claimed_by": None,
            "tags": ["onboard"],
            "related_files": ["server.py"],
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": time.time(),
        }
    ])

    output = asyncio.run(server.memory_onboard(server.OnboardInput(
        agent_name="codex-main",
        agent_platform="codex",
        agent_role="main",
        task_focus="Implement session onboarding",
        mode="brief",
        ticket_id="TK-abc",
    )))
    agents = server._load_agt()

    assert "# On Board: `codex-main`" in output
    assert "codex-main" in output
    assert "Active Agents / Collision Check" in output
    assert "Current Status" in output
    assert "Pending/assigned for you" in output
    assert "TK-abc" in output
    assert "Open Tickets" in output
    assert "Pinned Critical Memory" in output
    assert "Production bindings must stay real" in output
    assert "Data Health" in output
    assert "Where Details Live" in output
    assert "memory_get_briefing" in output
    assert "## Briefing" not in output
    assert "Ticket Focus" not in output
    assert "Required Fields" not in output
    assert "Long-term Memory" not in output
    assert "<on_board_protocol>" in output
    assert "<required_first_call>memory_onboard</required_first_call>" in output
    assert "<ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>" in output
    assert any(a["agent_name"] == "codex-main" and a["status"] == "active" for a in agents.values())


def test_update_state_defaults_to_single_active_agent(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "state project", "tech_stack": "python"})
    server._save_mem([])

    asyncio.run(server.memory_onboard(server.OnboardInput(
        agent_name="claude-opus-main",
        agent_platform="claude",
        mode="brief",
        include_tickets=False,
        include_health=False,
    )))

    output = asyncio.run(server.memory_update_state(server.UpdateStateInput(
        key="mcp_tool_test",
        value="ok",
    )))
    state = server._load_sta()

    assert "(by `claude-opus-main`)" in output
    assert state["mcp_tool_test"]["updated_by"] == "claude-opus-main"


def test_update_state_requires_agent_name_when_multiple_agents_are_active(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "state project", "tech_stack": "python"})
    server._save_agt({
        "a1": {"agent_name": "codex-worker-a", "agent_platform": "codex", "status": "active", "last_activity": time.time()},
        "a2": {"agent_name": "codex-worker-b", "agent_platform": "codex", "status": "active", "last_activity": time.time()},
    })

    output = asyncio.run(server.memory_update_state(server.UpdateStateInput(
        key="mcp_tool_test",
        value="ok",
    )))

    assert "agent_name is required because multiple active agents are on board" in output
    assert "mcp_tool_test" not in server._load_sta()


def test_same_platform_workers_can_stay_active_together(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "parallel project", "tech_stack": "python"})
    server._save_mem([])

    for name in ("codex-worker-a", "codex-worker-b", "codex-worker-c"):
        asyncio.run(server.memory_onboard(server.OnboardInput(
            agent_name=name,
            agent_platform="codex",
            agent_role="worker",
            mode="brief",
            include_tickets=False,
            include_health=False,
        )))

    agents = server._load_agt()
    active = [a for a in agents.values() if a.get("status") == "active"]

    assert len(active) == 3
    assert {a["agent_name"] for a in active} == {"codex-worker-a", "codex-worker-b", "codex-worker-c"}
    assert all(a["agent_platform"] == "codex" for a in active)
    assert all(a["agent_role"] == "worker" for a in active)


def test_onboard_accepts_legacy_role_aliases(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "legacy role project", "tech_stack": "python"})
    server._save_mem([])

    asyncio.run(server.memory_onboard(server.OnboardInput(
        agent_name="cursor-dev",
        agent_platform="cursor",
        agent_role="dev",
        mode="brief",
        include_tickets=False,
        include_health=False,
    )))
    asyncio.run(server.memory_onboard(server.OnboardInput(
        agent_name="weird-agent",
        agent_platform="other",
        agent_role="custom-old-role",
        mode="brief",
        include_tickets=False,
        include_health=False,
    )))
    agents = {a["agent_name"]: a for a in server._load_agt().values()}

    assert agents["cursor-dev"]["agent_role"] == "worker"
    assert agents["weird-agent"]["agent_role"] == "utility"


def test_ticket_mutations_require_onboarded_agent(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    now = time.time()
    server._tickets_dir()
    server._save_ticket_index([
        {
            "id": "TK-open",
            "title": "Open ticket",
            "description": "Should not be claimable before onboarding.",
            "target_url": "local",
            "scope": "READ-ONLY",
            "required_fields": ["result"],
            "priority": "medium",
            "status": "open",
            "created_by": "ghost",
            "assigned_to": None,
            "claimed_by": None,
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": now,
        },
        {
            "id": "TK-claimed",
            "title": "Claimed ticket",
            "description": "Should not be submittable before onboarding.",
            "target_url": "local",
            "scope": "READ-ONLY",
            "required_fields": ["result"],
            "priority": "medium",
            "status": "claimed",
            "created_by": "ghost",
            "assigned_to": None,
            "claimed_by": "ghost",
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": now,
        },
        {
            "id": "TK-submitted",
            "title": "Submitted ticket",
            "description": "Should not be reviewable before onboarding.",
            "target_url": "local",
            "scope": "READ-ONLY",
            "required_fields": ["result"],
            "priority": "medium",
            "status": "submitted",
            "created_by": "ghost",
            "assigned_to": None,
            "claimed_by": "ghost",
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": now,
        },
    ])

    claim = asyncio.run(server.memory_claim_ticket(server.ClaimTicketInput(agent_name="ghost", ticket_id="TK-open")))
    submit = asyncio.run(server.memory_submit_ticket(server.SubmitTicketInput(
        agent_name="ghost",
        ticket_id="TK-claimed",
        summary="done",
        files_changed=["server.py"],
    )))
    review = asyncio.run(server.memory_review_ticket(server.ReviewTicketInput(
        agent_name="ghost",
        ticket_id="TK-submitted",
        verdict="approve",
        review_notes="looks fine",
    )))
    cancel = asyncio.run(server.memory_cancel_ticket(agent_name="ghost", ticket_id="TK-open"))
    terminate = asyncio.run(server.memory_terminate_ticket(agent_name="ghost", ticket_id="TK-open"))

    for output in (claim, submit, review, cancel, terminate):
        assert "NOT ON BOARD" in output


def test_ticket_control_uses_agent_roles_for_stuck_work(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_mem([])
    server._tickets_dir()
    now = time.time()
    server._save_agt({
        "creator": {
            "agent_name": "old-planner",
            "agent_platform": "claude-code",
            "agent_role": "planner",
            "status": "kia",
            "last_activity": now - 9999,
        },
        "lead": {
            "agent_name": "codex-lead",
            "agent_platform": "codex",
            "agent_role": "lead",
            "status": "active",
            "last_activity": now,
        },
        "utility": {
            "agent_name": "codex-helper",
            "agent_platform": "codex",
            "agent_role": "utility",
            "status": "active",
            "last_activity": now,
        },
    })
    server._save_ticket_index([
        {
            "id": "TK-stuck",
            "title": "Stuck ticket",
            "description": "Creator is gone.",
            "target_url": "local",
            "scope": "READ-ONLY",
            "required_fields": ["result"],
            "priority": "medium",
            "status": "open",
            "created_by": "old-planner",
            "assigned_to": None,
            "claimed_by": None,
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": now,
        },
        {
            "id": "TK-danger",
            "title": "Danger ticket",
            "description": "Only coordinator should terminate.",
            "target_url": "local",
            "scope": "READ-ONLY",
            "required_fields": ["result"],
            "priority": "medium",
            "status": "open",
            "created_by": "old-planner",
            "assigned_to": None,
            "claimed_by": None,
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": now,
        },
    ])

    denied = asyncio.run(server.memory_terminate_ticket(
        agent_name="codex-helper",
        ticket_id="TK-danger",
        reason="not needed",
    ))
    cancel_denied = asyncio.run(server.memory_cancel_ticket(
        agent_name="codex-helper",
        ticket_id="TK-stuck",
        reason="not mine",
    ))
    canceled = asyncio.run(server.memory_cancel_ticket(
        agent_name="codex-lead",
        ticket_id="TK-stuck",
        reason="creator KIA and scope obsolete",
    ))
    terminated = asyncio.run(server.memory_terminate_ticket(
        agent_name="codex-lead",
        ticket_id="TK-danger",
        reason="unsafe duplicate",
    ))
    tickets = {ticket["id"]: ticket for ticket in server._load_ticket_index()}

    assert "cannot terminate" in denied
    assert "cannot cancel" in cancel_denied
    assert "lead role" in canceled
    assert tickets["TK-stuck"]["status"] == "canceled"
    assert tickets["TK-stuck"]["canceled_by"] == "codex-lead"
    assert "lead role" in terminated
    assert tickets["TK-danger"]["status"] == "terminated"
    assert tickets["TK-danger"]["terminated_by"] == "codex-lead"

    # Both terminal states leave the open queue, the way approval already did.
    # Cancel and terminate used to rewrite the md in tickets/ and never move it,
    # so the directory documented as the open queue kept dead tickets and the
    # next agent's `ls` disagreed with the index.
    tdir = server._tickets_dir()
    for ticket_id in ("TK-stuck", "TK-danger"):
        assert not (tdir / f"{ticket_id}.md").exists()
        assert (tdir / "closed" / f"{ticket_id}.md").exists()
    assert "tickets/closed/TK-stuck.md" in canceled
    assert "tickets/closed/TK-danger.md" in terminated


def test_memory_doctor_reports_duplicate_agents_and_orphaned_tickets(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    now = time.time()
    server._save_agt({
        "a1": {"agent_name": "codex-main", "agent_platform": "codex", "status": "active", "last_activity": now},
        "a2": {"agent_name": "codex-main", "agent_platform": "codex", "status": "active", "last_activity": now},
    })
    server._tickets_dir()
    server._save_ticket_index([
        {
            "id": "TK-orphan",
            "title": "Orphaned claimed ticket",
            "status": "claimed",
            "priority": "medium",
            "created_by": "codex-main",
            "assigned_to": None,
            "claimed_by": "ghost-agent",
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": now,
        }
    ])

    output = asyncio.run(server.memory_doctor())

    assert "Data Integrity" in output
    assert "duplicate active agent identity" in output
    assert "orphaned ticket" in output
    assert "TK-orphan" in output


def test_vector_search_default_disabled_and_local_backend_returns_hits(tmp_path):
    server = load_server(tmp_path)
    seed_project(server)

    disabled = asyncio.run(server.memory_search_vector(server.VectorSearchInput(query="briefing")))
    local = asyncio.run(server.memory_search_vector(server.VectorSearchInput(query="briefing", backend="local")))

    assert "Vector search is disabled" in disabled
    assert "Ticket TK-abc implementation decision" in local
    assert "similarity" in local


def test_memory_write_skips_exact_recent_duplicate_and_preserves_ticket_links(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_agt({
        "a1": {
            "agent_name": "codex-main",
            "agent_platform": "codex",
            "status": "active",
            "memories_written": 0,
            "last_activity": time.time(),
        }
    })

    payload = server.MemoryWriteInput(
        agent_name="codex-main",
        memory_type="decision",
        title="TK-abc linkage decision",
        content="Tie memory entries back to tickets and files.",
        tags=["linkage"],
        related_files=["server.py"],
        related_tickets=["TK-abc"],
        priority=2,
    )

    first = asyncio.run(server.memory_write(payload))
    second = asyncio.run(server.memory_write(payload))
    memories = server._load_mem()

    assert "Saved" in first
    assert "Duplicate skipped" in second
    assert len(memories) == 1
    assert memories[0]["related_tickets"] == ["TK-abc"]


def test_priority_three_memory_auto_pins_with_compact_summary_and_raw_content(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_agt({
        "a1": {
            "agent_name": "codex-main",
            "agent_platform": "codex",
            "status": "active",
            "memories_written": 0,
            "last_activity": time.time(),
        }
    })
    raw_content = ("Critical rule. " + ("Keep the raw details intact. " * 40)).strip()

    output = asyncio.run(server.memory_write(server.MemoryWriteInput(
        agent_name="codex-main",
        memory_type="warning",
        title="Critical pinned warning",
        content=raw_content,
        priority=3,
    )))
    memory = server._load_mem()[0]
    briefing = asyncio.run(server.memory_get_briefing(server.BriefingInput(mode="brief", token_budget=8000)))

    assert memory["pinned"] is True
    assert memory["content"] == raw_content
    assert memory["pinned_summary"].startswith("Critical rule.")
    assert len(memory["pinned_summary"]) <= server.PINNED_SUMMARY_MAX_CHARS
    assert "Pinned summary" in output
    assert memory["pinned_summary"] in briefing


def test_memory_write_retracts_and_links_without_deleting_target(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_agt({"a1": {"agent_name": "codex-main", "status": "active", "last_activity": time.time()}})

    original = asyncio.run(server.memory_write(server.MemoryWriteInput(
        agent_name="codex-main", memory_type="warning", title="False pinned diagnosis",
        content="This diagnosis is no longer correct.", priority=3,
        pinned_summary="Wrong diagnosis; must be retracted.")))
    target_id = server._load_mem()[0]["id"]
    result = asyncio.run(server.memory_write(server.MemoryWriteInput(
        agent_name="codex-main", memory_type="discovery", title="Correction",
        content="The previous diagnosis was incorrect.", retracts=target_id)))

    memories = server._load_mem()
    target = next(m for m in memories if m["id"] == target_id)
    correction = next(m for m in memories if m["title"] == "Correction")
    assert "Saved" in original and "Retracted" in result
    assert len(memories) == 2
    assert target["pinned"] is False
    assert target["priority"] == 1
    assert "pinned_summary" not in target
    assert target["title"] == "[RETRACTED] False pinned diagnosis"
    assert target["retracted_by"] == correction["id"]
    assert correction["retracts"] == target_id
    # Retraction is a demotion, so it must leave the same audit trail as an
    # explicit unpin. Without this the board can say WHAT superseded an entry
    # but not who demoted it or when, and only for retractions -- an asymmetry
    # that is invisible until someone audits the one case that lacks it.
    assert target["unpinned_by"] == "codex-main"
    assert target["unpinned_at"]
    assert correction["id"] in target["unpin_reason"]


def test_legacy_rejection_warning_is_left_pinned(tmp_path):
    """Demotion is forward-only: no 'auto-rejection' tag, no demotion.

    A pre-tag rejection warning is indistinguishable from a human's warning
    about the same ticket, and demoting a human's warning would be worse than
    leaving a stale one pinned. memory_unpin is the remedy, not a wider match.
    """
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_agt({"a1": {"agent_name": "codex-main", "status": "active",
                             "last_activity": time.time()}})

    asyncio.run(server.memory_write(server.MemoryWriteInput(
        agent_name="codex-main", memory_type="warning",
        title="❌ Rejected TK-000000000000: legacy shape",
        content="Written before the auto-rejection tag existed.", priority=3,
        tags=["ticket", "rejected"])))

    mem = server._load_mem()
    assert server._demote_rejection_warnings(
        mem, "TK-000000000000", "closed", "codex-main") is False
    assert mem[0]["pinned"] is True
    assert not mem[0]["title"].startswith("[RESOLVED")


def test_memory_unpin_missing_id_is_non_mutating(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_agt({"a1": {"agent_name": "codex-main", "status": "active", "last_activity": time.time()}})
    server._save_mem([{"id": "m1", "title": "Pinned", "content": "keep", "pinned": True, "priority": 3}])
    before = server._load_mem()
    result = asyncio.run(server.memory_unpin(server.MemoryUnpinInput(agent_name="codex-main", memory_id="missing")))
    assert "not found" in result
    assert server._load_mem() == before


def test_memory_write_retract_missing_id_fails_without_mutation(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_agt({"a1": {"agent_name": "codex-main", "status": "active", "last_activity": time.time()}})
    before = server._load_mem()
    result = asyncio.run(server.memory_write(server.MemoryWriteInput(
        agent_name="codex-main", memory_type="discovery", title="Unlinked correction",
        content="Must not be written.", retracts="missing")))
    assert "target not found" in result
    assert server._load_mem() == before


def test_auto_pinned_system_memories_get_compact_summary(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    now = time.time()
    server._save_agt({
        "worker": {
            "agent_name": "codex-worker",
            "agent_platform": "codex",
            "status": "active",
            "memories_written": 0,
            "last_activity": now,
        },
        "reviewer": {
            "agent_name": "codex-reviewer",
            "agent_platform": "codex",
            "agent_role": "reviewer",
            "status": "active",
            "memories_written": 0,
            "last_activity": now,
        },
    })
    server._tickets_dir()
    server._save_ticket_index([
        {
            "id": "TK-submit",
            "title": "Submit ticket",
            "description": "Submit should write auto-handoff memory.",
            "target_url": "local",
            "scope": "READ-ONLY",
            "required_fields": ["result"],
            "priority": "medium",
            "status": "claimed",
            "created_by": "planner",
            "assigned_to": None,
            "claimed_by": "codex-worker",
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": now,
        },
        {
            "id": "TK-review",
            "title": "Review ticket",
            "description": "Reject should write pinned warning memory.",
            "target_url": "local",
            "scope": "READ-ONLY",
            "required_fields": ["result"],
            "priority": "medium",
            "status": "submitted",
            "created_by": "planner",
            "assigned_to": None,
            "claimed_by": "codex-worker",
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": now,
        },
    ])

    asyncio.run(server.memory_handoff(server.HandoffInput(
        agent_name="codex-worker",
        summary="handoff summary",
        next_steps=["continue"],
    )))
    server._save_agt({
        **server._load_agt(),
        "worker-2": {
            "agent_name": "codex-worker",
            "agent_platform": "codex",
            "status": "active",
            "memories_written": 0,
            "last_activity": now,
        },
    })
    asyncio.run(server.memory_submit_ticket(server.SubmitTicketInput(
        agent_name="codex-worker",
        ticket_id="TK-submit",
        summary="submitted work",
    )))
    asyncio.run(server.memory_review_ticket(server.ReviewTicketInput(
        agent_name="codex-reviewer",
        ticket_id="TK-review",
        verdict="reject",
        review_notes="not enough evidence",
        fix_instructions="add proof",
    )))

    mem = server._load_mem()
    pinned = [m for m in mem if m.get("pinned")]

    # Three auto-pinned writes happen above, but only the rejection warning
    # stays pinned: the auto-handoff from memory_submit_ticket is a routing
    # notice and is written unpinned, and writing it supersedes codex-worker's
    # earlier hand-written handoff. Handoffs are surfaced by recency, never by
    # `pinned`, so this costs no visibility and frees two hot slots.
    assert [m["memory_type"] for m in pinned] == ["warning"]
    assert all(m.get("pinned_summary") for m in pinned)
    assert all(len(m["pinned_summary"]) <= server.PINNED_SUMMARY_MAX_CHARS for m in pinned)

    handoffs = [m for m in mem if m["memory_type"] == "handoff"]
    assert len(handoffs) == 2
    assert handoffs[0]["unpin_reason"] == "superseded by a newer handoff"
    assert handoffs[1]["pinned"] is False


def test_memory_links_shows_ticket_file_and_agent_linkage(tmp_path):
    server = load_server(tmp_path)
    seed_project(server)
    server._tickets_dir()
    server._save_ticket_index([
        {
            "id": "TK-abc",
            "title": "Implement linkage view",
            "description": "Show memory links.",
            "target_url": "file://server.py",
            "scope": "READ-ONLY",
            "required_fields": ["link-map"],
            "priority": "high",
            "status": "open",
            "created_by": "codex-main",
            "assigned_to": "codex",
            "claimed_by": None,
            "tags": ["briefing"],
            "related_files": ["server.py"],
            "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00",
            "timestamp": time.time(),
        }
    ])
    memories = server._load_mem()
    memories[0]["related_tickets"] = ["TK-abc"]
    server._save_mem(memories)

    output = asyncio.run(server.memory_links(server.MemoryLinksInput(ticket_id="TK-abc")))

    assert "Memory Linkage" in output
    assert "TK-abc" in output
    assert "Ticket TK-abc implementation decision" in output
    assert "server.py" in output
    assert "codex-main" in output


def test_reviewer_stays_active_after_approve_and_reject(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    server._save_mem([])
    now = time.time()
    server._save_agt({
        "reviewer": {
            "agent_name": "codex-reviewer",
            "agent_platform": "codex",
            "agent_role": "reviewer",
            "status": "active",
            "memories_written": 0,
            "last_activity": now,
        },
    })
    server._tickets_dir()

    def _ticket(tid):
        return {
            "id": tid, "title": tid, "description": "d", "target_url": "local",
            "scope": "READ-ONLY", "required_fields": ["result"], "priority": "medium",
            "status": "submitted", "created_by": "planner", "assigned_to": None,
            "claimed_by": "codex-worker", "created_at": "2026-05-08T12:01:00",
            "updated_at": "2026-05-08T12:01:00", "timestamp": now,
        }

    server._save_ticket_index([_ticket("TK-ok"), _ticket("TK-no")])

    approve = asyncio.run(server.memory_review_ticket(server.ReviewTicketInput(
        agent_name="codex-reviewer", ticket_id="TK-ok",
        verdict="approve", review_notes="looks fine",
    )))
    assert "Approved" in approve
    assert "still on board" in approve
    # reviewer must NOT be auto-handed-off after approving
    assert server._load_agt()["reviewer"]["status"] == "active"

    reject = asyncio.run(server.memory_review_ticket(server.ReviewTicketInput(
        agent_name="codex-reviewer", ticket_id="TK-no",
        verdict="reject", review_notes="nope", fix_instructions="redo",
    )))
    assert "Rejected" in reject
    assert "still on board" in reject
    assert server._load_agt()["reviewer"]["status"] == "active"


def test_rejection_warning_demotes_on_approve_but_manual_warning_survives(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "test project", "tech_stack": "python"})
    now = time.time()
    server._save_agt({"reviewer": {
        "agent_name": "codex-reviewer", "agent_platform": "codex",
        "agent_role": "reviewer", "status": "active", "last_activity": now,
    }})
    server._tickets_dir()
    ticket = {
        "id": "TK-resolve", "title": "Resolve warning", "description": "d",
        "target_url": "local", "scope": "READ-ONLY", "required_fields": ["result"],
        "priority": "medium", "status": "submitted", "created_by": "planner",
        "assigned_to": None, "claimed_by": "worker", "created_at": "2026-05-08T12:01:00",
        "updated_at": "2026-05-08T12:01:00", "timestamp": now,
    }
    server._save_ticket_index([ticket])
    server._save_mem([{
        "id": "manual", "agent_name": "codex-main", "memory_type": "warning",
        "title": "Manual warning about TK-resolve", "content": "Keep this warning.",
        "tags": ["ticket", "warning"], "related_tickets": ["TK-resolve"],
        "priority": 3, "pinned": True, "pinned_summary": "Manual warning.",
    }])

    reject = asyncio.run(server.memory_review_ticket(server.ReviewTicketInput(
        agent_name="codex-reviewer", ticket_id="TK-resolve", verdict="reject",
        review_notes="needs evidence", fix_instructions="add proof")))
    assert "Rejected" in reject
    rejected_warning = next(m for m in server._load_mem() if "Rejected TK-resolve" in m["title"])
    assert rejected_warning["pinned"] is True
    assert rejected_warning["related_tickets"] == ["TK-resolve"]
    assert "auto-rejection" in rejected_warning["tags"]

    reopened = server._load_ticket_index()[0]
    reopened["status"] = "submitted"
    server._save_ticket_index([reopened])
    approve = asyncio.run(server.memory_review_ticket(server.ReviewTicketInput(
        agent_name="codex-reviewer", ticket_id="TK-resolve", verdict="approve",
        review_notes="evidence added")))
    assert "Approved" in approve

    memories = server._load_mem()
    rejected_warning = next(m for m in memories if "Rejected TK-resolve" in m["title"])
    manual = next(m for m in memories if m["id"] == "manual")
    assert rejected_warning["pinned"] is False
    assert rejected_warning["priority"] == 1
    assert rejected_warning["title"].startswith("[RESOLVED:closed] ")
    assert rejected_warning["title"].count("[RESOLVED:closed]") == 1
    assert manual["pinned"] is True

    server._demote_rejection_warnings(memories, "TK-resolve", "closed", "codex-reviewer")
    assert next(m for m in memories if "Rejected TK-resolve" in m["title"])["title"].count("[RESOLVED:closed]") == 1
# --- issue #13 polish -----------------------------------------------------

def test_ticket_md_status_is_the_wire_value_not_an_enum_repr(tmp_path):
    """f-string on a str-mixin Enum yields 'TicketStatus.X' on Python 3.11+."""
    server = load_server(tmp_path)
    path = tmp_path / "t.md"
    server._write_ticket_md(path, {"id": "TK-1", "title": "t",
                                   "status": server.TicketStatus.SUBMITTED})
    body = path.read_text()
    assert "**Status**: submitted" in body
    assert "TicketStatus" not in body


def test_closed_ticket_md_is_rewritten_with_its_final_status(tmp_path):
    """The .md was written at submit and never again, so closed read 'submitted'.

    _index.json is the source of truth, but a human diagnosing a problem reads
    the .md — a stale one sends them down the wrong path, which is exactly how
    a reviewer once concluded a rejection had been silently reverted.
    """
    server = load_server(tmp_path)
    server._save_prj({"description": "p", "tech_stack": "python"})
    server._save_agt({"a1": {"agent_name": "lead", "status": "active",
                             "last_activity": time.time()},
                      "a2": {"agent_name": "worker", "status": "active",
                             "last_activity": time.time()}})
    server._save_ticket_index([{
        "id": "TK-done", "title": "probe", "description": "d",
        "target_url": "local", "scope": "READ-ONLY", "required_fields": ["r"],
        "priority": "medium", "status": "submitted", "created_by": "lead",
        "assigned_to": "worker", "claimed_by": "worker",
        "created_at": "2026-05-08T12:00:00", "updated_at": "2026-05-08T12:00:00",
        "timestamp": time.time(),
    }])
    server._write_ticket_md(server._tickets_dir() / "TK-done.md",
                            server._load_ticket_index()[0])

    asyncio.run(server.memory_review_ticket(server.ReviewTicketInput(
        agent_name="lead", ticket_id="TK-done", verdict="approve",
        review_notes="ok")))

    body = (server._tickets_dir() / "closed" / "TK-done.md").read_text()
    assert "**Status**: closed" in body
    assert "submitted" not in body.split("**Priority**")[0]


def test_submit_keeps_an_agent_that_owes_a_review_on_board(tmp_path):
    """Auto-handoff must not strand a submission the leaver was due to review.

    Observed live: codex submitted its own ticket, auto-handed off, and its
    peer's submission then sat unreviewed with nobody on board to adjudicate.
    """
    server = load_server(tmp_path)
    server._save_prj({"description": "p", "tech_stack": "python"})
    server._save_agt({"a1": {"agent_name": "lead", "status": "active",
                             "last_activity": time.time()}})
    now = time.time()
    common = {"description": "d", "target_url": "local", "scope": "READ-ONLY",
              "required_fields": ["r"], "priority": "medium",
              "created_at": "2026-05-08T12:00:00",
              "updated_at": "2026-05-08T12:00:00", "timestamp": now}
    server._save_ticket_index([
        # lead's own work, about to be submitted
        dict(common, id="TK-mine", title="mine", status="claimed",
             created_by="lead", assigned_to="lead", claimed_by="lead"),
        # a peer's submission that lead owns and therefore owes a verdict on
        dict(common, id="TK-peer", title="peer", status="submitted",
             created_by="lead", assigned_to="peer", claimed_by="peer"),
    ])

    out = asyncio.run(server.memory_submit_ticket(server.SubmitTicketInput(
        agent_name="lead", ticket_id="TK-mine", summary="done")))

    assert "owe a review" in out and "TK-peer" in out
    statuses = [a["status"] for a in server._load_agt().values()
                if a["agent_name"] == "lead"]
    assert statuses == ["active"], statuses


def test_submit_still_hands_off_when_nothing_is_owed(tmp_path):
    """The guard must be narrow: no owed review, original behaviour stands."""
    server = load_server(tmp_path)
    server._save_prj({"description": "p", "tech_stack": "python"})
    server._save_agt({"a1": {"agent_name": "solo", "status": "active",
                             "last_activity": time.time()}})
    server._save_ticket_index([{
        "id": "TK-only", "title": "only", "description": "d",
        "target_url": "local", "scope": "READ-ONLY", "required_fields": ["r"],
        "priority": "medium", "status": "claimed", "created_by": "boss",
        "assigned_to": "solo", "claimed_by": "solo",
        "created_at": "2026-05-08T12:00:00", "updated_at": "2026-05-08T12:00:00",
        "timestamp": time.time(),
    }])

    out = asyncio.run(server.memory_submit_ticket(server.SubmitTicketInput(
        agent_name="solo", ticket_id="TK-only", summary="done")))

    assert "off board" in out
    assert [a["status"] for a in server._load_agt().values()] == ["handed_off"]


def test_server_icons_declared_only_when_the_asset_exists(tmp_path):
    """No placeholder branding is invented when the icon file is absent."""
    server = load_server(tmp_path)
    missing = tmp_path / "nope.png"
    real = tmp_path / "icon.png"
    real.write_bytes(b"\x89PNG\r\n\x1a\nfake-but-nonempty")

    original = server._ICON_PATH
    try:
        server._ICON_PATH = missing
        assert server._server_icons() is None
        server._ICON_PATH = real
        icons = server._server_icons()
        assert icons and icons[0].src.startswith("data:image/png;base64,")
        assert icons[0].mimeType == "image/png"
    finally:
        server._ICON_PATH = original


def _seed_claim_fixtures(server):
    """One directed ticket and one open-queue ticket, both claimable."""
    now = time.time()
    server._tickets_dir()
    server._save_ticket_index([
        {
            "id": "TK-directed", "title": "Addressed to one agent",
            "description": "assigned_to must be honoured.", "target_url": "local",
            "scope": "READ-ONLY", "required_fields": ["result"], "priority": "medium",
            "status": "open", "created_by": "owner", "assigned_to": "codex",
            "claimed_by": None, "created_at": "2026-08-01T09:00:00",
            "updated_at": "2026-08-01T09:00:00", "timestamp": now,
        },
        {
            "id": "TK-queue", "title": "Open to anyone",
            "description": "No assignee means the open queue.", "target_url": "local",
            "scope": "READ-ONLY", "required_fields": ["result"], "priority": "medium",
            "status": "open", "created_by": "owner", "assigned_to": None,
            "claimed_by": None, "created_at": "2026-08-01T09:00:00",
            "updated_at": "2026-08-01T09:00:00", "timestamp": now,
        },
    ])


def _join(server, name, role):
    asyncio.run(server.memory_onboard(server.OnboardInput(
        agent_name=name, agent_platform="codex", agent_role=role,
        mode="brief", include_tickets=False, include_health=False)))


def test_assigned_ticket_cannot_be_claimed_by_another_agent(tmp_path):
    """The hole this closes: claiming was the only lifecycle move with no gate.

    Seen in practice: tickets addressed to one agent were claimed by a
    differently-named agent that had spawned for the occasion, because
    ticket_roles.may_claim forbade it but had no caller anywhere in the server.
    """
    server = load_server(tmp_path)
    server._save_prj({"description": "claim gate", "tech_stack": "python"})
    server._save_mem([])
    _seed_claim_fixtures(server)
    _join(server, "codex-sub-spawned", "worker")

    out = asyncio.run(server.memory_claim_ticket(server.ClaimTicketInput(
        agent_name="codex-sub-spawned", ticket_id="TK-directed")))

    assert "cannot claim" in out
    assert "codex" in out
    ticket = {t["id"]: t for t in server._load_ticket_index()}["TK-directed"]
    assert ticket["status"] == "open", "a refused claim must not move the ticket"
    assert ticket["claimed_by"] is None


def test_assignee_and_coordinator_may_claim_and_the_basis_is_recorded(tmp_path):
    server = load_server(tmp_path)
    server._save_prj({"description": "claim gate", "tech_stack": "python"})
    server._save_mem([])
    _seed_claim_fixtures(server)
    _join(server, "codex", "worker")
    _join(server, "lead-agent", "lead")

    assert "Claimed" in asyncio.run(server.memory_claim_ticket(
        server.ClaimTicketInput(agent_name="codex", ticket_id="TK-directed")))
    tickets = {t["id"]: t for t in server._load_ticket_index()}
    assert tickets["TK-directed"]["claimed_by"] == "codex"
    # claim_permission was None on every ticket ever written before this gate.
    assert tickets["TK-directed"]["claim_permission"]

    # A coordinator may take work addressed to someone else; that is the
    # documented escape hatch in may_claim, not an accident.
    _seed_claim_fixtures(server)
    assert "Claimed" in asyncio.run(server.memory_claim_ticket(
        server.ClaimTicketInput(agent_name="lead-agent", ticket_id="TK-directed")))


def test_open_queue_stays_a_free_for_all(tmp_path):
    """Racing for unassigned work is a feature and must survive the gate."""
    server = load_server(tmp_path)
    server._save_prj({"description": "claim gate", "tech_stack": "python"})
    server._save_mem([])
    _seed_claim_fixtures(server)
    _join(server, "stranger", "worker")

    out = asyncio.run(server.memory_claim_ticket(server.ClaimTicketInput(
        agent_name="stranger", ticket_id="TK-queue")))

    assert "Claimed" in out
    assert {t["id"]: t for t in server._load_ticket_index()}["TK-queue"]["claimed_by"] == "stranger"


def test_gate_does_not_intercept_the_reclaim_heartbeat(tmp_path):
    """Calling claim again on your own claimed ticket still advances it."""
    server = load_server(tmp_path)
    server._save_prj({"description": "claim gate", "tech_stack": "python"})
    server._save_mem([])
    _seed_claim_fixtures(server)
    _join(server, "codex", "worker")

    asyncio.run(server.memory_claim_ticket(server.ClaimTicketInput(
        agent_name="codex", ticket_id="TK-directed")))
    again = asyncio.run(server.memory_claim_ticket(server.ClaimTicketInput(
        agent_name="codex", ticket_id="TK-directed")))

    assert "in_progress" in again
    assert {t["id"]: t for t in server._load_ticket_index()}["TK-directed"]["status"] == "in_progress"
