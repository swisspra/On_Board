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


def test_memory_onboard_registers_agent_and_returns_session_context(tmp_path):
    server = load_server(tmp_path)
    seed_project(server)
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

    assert "On Board Session" in output
    assert "codex-main" in output
    assert "Ticket Focus" in output
    assert "TK-abc" in output
    assert "Open Tickets" in output
    assert "Data Health" in output
    assert "<on_board_protocol>" in output
    assert "<required_first_call>memory_onboard</required_first_call>" in output
    assert "<ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>" in output
    assert "preferred one-call session entrypoint" not in output
    assert any(a["agent_name"] == "codex-main" and a["status"] == "active" for a in agents.values())


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
