# Greetings Agents!
# Welcome On Board — Agent Shared Memory Protocol

This project uses `.agent-mem/` for multi-agent coordination across platforms.

<on_board_protocol>
  <required_first_call>memory_onboard</required_first_call>
  <agent_identity>Use a stable agent_name. Do not include dates, model names, or session ids.</agent_identity>
  <write_policy>Write after meaningful actions only.</write_policy>
  <ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>
  <handoff_policy>Always handoff before leaving.</handoff_policy>
</on_board_protocol>

Get On Board before starting any work:

1. Call `memory_onboard` with your stable agent_name, agent_platform, agent_role, and optional task_focus.
2. Call `memory_write` after significant code changes, decisions, discoveries, blockers, or warnings.
3. Call `memory_checkpoint` every 10-15 minutes during long work.
4. Call `memory_handoff` before you finish.

If `memory_onboard` is not available, call `memory_get_briefing` first, then `memory_agent_join`.

## Ticket Flow

Use tickets when work needs to move between agents:

- `memory_create_ticket` requests help and assigns work to a specific agent/platform or leaves it open.
- `memory_claim_ticket` picks up work assigned to you.
- `memory_submit_ticket` submits your work for review.
- `memory_review_ticket` approves work or rejects it with concrete fix instructions.

Ticket creation should stay concise. Put long context in memory entries or files and link to them from the ticket.

## Naming

- `agent_platform` is the runner, for example `claude-code`, `claude-desktop`, `cursor`, `codex`, `antigravity`, `windsurf`, or `other`.
- `agent_name` should be stable and readable. Do not use dates or session IDs.
- `agent_role` should describe your function, for example `main`, `planner`, `tester`, `reviewer`, or `utility`.
- `task_focus` should be one short sentence about the work you are about to do.

## Operating Rules

1. Re-join after every off-board action. `memory_handoff`, `memory_submit_ticket`, `memory_review_ticket`, and compaction can end your active session; call `memory_onboard` again before the next write or ticket mutation.
2. Check memory mid-flight, not only at session start, when another agent may have worked in parallel or after a long pause.
3. Write memory updates as you go, not as a batch at the end.
4. Commit carefully in shared working trees. If you see unfamiliar uncommitted edits, do not include or revert them without understanding who made them.
5. Search memory before claiming prior research or decisions do not exist.

If you skip these steps, the next agent will have no context and will redo your work.
Your agent_name is stamped on every entry, so write updates another agent can rely on.
