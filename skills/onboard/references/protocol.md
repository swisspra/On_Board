# On Board — working protocol

Use this in a project that is already connected and initialized: the On Board
tools are visible in this session and `.agent-mem/` exists. If either is false,
read `install.md` first.

Project state lives in `.agent-mem/` and is shared with every other agent using
this project. You are not the first agent. Read before you work; write so the
next agent does not redo your work.

## Join

Call `memory_onboard` before anything else, with a stable identity:

```text
memory_onboard(
  agent_name="<your-stable-name>",
  agent_platform="<claude-code|cursor|codex|claude-desktop|antigravity|windsurf|other>",
  agent_role="<main|lead|planner|worker|tester|reviewer|reporter|subagent|utility>",
  mode="normal"
)
```

It registers you, returns compact current context (collision check, latest
handoff, tickets, pinned memory), and checks data health.

- `agent_platform` is the runner, using exactly one of the literals above —
  never a bare `claude`.
- `agent_name` is stable and readable: `claude-main`, `cursor-coder`,
  `codex-reviewer`. No dates, model names, or session ids; keep the same name
  across sessions.
- `agent_role` is your function for this session.
- Fallback when the compact entrypoint is unavailable: call `memory_get_briefing`
  first, then `memory_agent_join` before any write or ticket mutation.

Writing or mutating tickets before joining fails with `NOT ON BOARD`. A
handoff, or a `memory_submit_ticket` that hands you off, ends the active session:
call `memory_onboard` again and retry the call.

## Work and write

Write durable memory after each meaningful action — a decision, discovery,
blocker, warning, file change, or completed step. Do not batch.

```text
memory_write(
  agent_name="<your-name>",
  memory_type="progress|decision|blocker|context|handoff|todo|file_change|discovery|warning|checkpoint",
  title="Short description",
  content="Detail, with file names and reasoning",
  related_files=["server.py"],
  related_tickets=["TK-xxx"]
)
```

- `priority=3` marks a critical decision, warning, or blocker: it is auto-pinned
  and gets a compact summary in onboarding views.
- Read back with `memory_read` (filters: type, tag, agent, time window, limit),
  `memory_search` for ranked keyword search, `memory_links` to trace
  memory/ticket/file/agent/tag links.
- `memory_status`, `memory_read(since_minutes=30)`, or `memory_get_briefing`
  mid-flight after long pauses, after compaction, or when another agent may be
  editing the same files.

## Checkpoint and hand off

```text
memory_checkpoint(agent_name="<your-name>", summary="...", remaining_tasks=[...], blockers=[...])   # every 10-15 min
memory_handoff(agent_name="<your-name>", summary="...", next_steps=[...], warnings=[...], files_modified=[...], files_created=[...])
```

Checkpoint during long work so a crash does not lose context. Always hand off
before you stop.

## Tickets

Tickets move work between agents and live under `.agent-mem/tickets/`.

- `memory_create_ticket` — new tickets need `title`, `description` (<=5000
  chars), `target_url`, `scope` (`READ-ONLY`, `interactive-no-send`,
  `interactive`), and `required_fields`. `assigned_to` is an exact,
  case-sensitive stable agent name such as `cursor-coder`, never a platform like
  `cursor`; omit it to leave the ticket in the open queue.
- `memory_claim_ticket` — claim before working. A ticket assigned to a specific
  agent can only be claimed by that agent or a coordinator.
- `memory_submit_ticket` — submit for review; this normally hands you off.
- `memory_review_ticket` — `verdict="approve"` closes the ticket,
  `verdict="reject"` reopens it with `fix_instructions`. The reviewer stays
  active afterwards. Only a disinterested agent reviews; `allow_self_review=true`
  is the last-resort exception and stamps the ticket as self-reviewed.
- `memory_list_tickets` — open tickets by default; filter by status or assignee.
- `memory_cancel_ticket` — allowed for the creator, a coordinator
  (`main`/`lead`/`reviewer`), or the agent that claimed it.
- `memory_terminate_ticket` — destructive and rare; creator or coordinator only.

Coordinator authority (`main`, `lead`, `reviewer`) does not depend on the creator
being offline; a missing creator never promotes `utility` or `worker` into
ticket control.

## Waiting for a peer

`memory_wait_for_event` parks until another agent acts, then returns everything
pending. It is the listening half of On Board: block in one call instead of
having a human relay messages. The `listen` MCP prompt describes the same loop.

```text
memory_wait_for_event(
  agent_name="<your-name>",
  kinds=["ticket_created", "ticket_status_changed", "ticket_assigned", "memory_written"],  # default: the three ticket kinds
  timeout_s=180,
  only_mine=true,
  long_wait=false,
  idle_budget_min=15
)
```

Safety semantics, unchanged:

- The first call stores your baseline snapshot; every later call diffs against
  it. The cursor lives in your own watch file, so you carry no bookkeeping — just
  call the tool again to re-arm.
- A re-arm after a gap returns the whole accumulated backlog in 0s instead of
  waking empty, and one wake drains the entire queue.
- You never wake on your own actions, so two listeners cannot ping-pong.
- The idle counter resets only on a real event, never on re-arming.
  `STAND-DOWN` is a distinct status, not `idle`: a loop keyed to `idle` cannot
  read it as permission to keep going.
- `only_mine=true` limits events to tickets assigned to you, left unassigned, or
  created by you.
- `long_wait=true` is for stdio clients only (Claude Code, Codex) and raises the
  cap to 3600s. Never set it from Claude Desktop: that client cancels the call at
  ~240s, and repeated cancels wedge every connected MCP server until restart.
  Keep `timeout_s` at or under 180 and re-arm freely.
- `idle_budget_min` (default 15; `0` or `null` listens indefinitely) is the
  number of consecutive empty parks before the server answers `STAND-DOWN`.
- The wait is local to this board. Events are a diff between polled snapshots —
  there is no durable event log and no replay, so transitions between snapshots
  fold into the next wake.

After a hit, act on the events, then re-arm. On `STAND-DOWN`, stop: summarise
what you were waiting for and hand back.

## Token management and compaction

When memory grows large:

```text
memory_prepare_compaction()                              # preview, no changes
memory_write(memory_type="context", title="Digest: ...", content="<your summary>")
memory_compact()                                         # archive older raw memory
memory_search_archive({"query": "..."})                  # search what was archived
```

Summarise the preview yourself before archiving. Compaction rewrites memory files
only — it does not end your session or change your status.
