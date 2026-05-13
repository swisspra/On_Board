# Greetings Agents!
# Welcome On Board — Agent Shared Memory Protocol

This project uses `.agent-mem/` for multi-agent coordination across platforms.
Get On Board before starting any work.

<on_board_protocol>
  <required_first_call>memory_onboard</required_first_call>
  <agent_identity>Use a stable agent_name. Do not include dates, model names, or session ids.</agent_identity>
  <write_policy>Write after meaningful actions only.</write_policy>
  <ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>
  <handoff_policy>Always handoff before leaving.</handoff_policy>
</on_board_protocol>

## Start Here

1. Call `memory_onboard` with your stable agent_name, agent_platform, agent_role, and optional task_focus. This is the primary entrypoint: it joins the session and returns the briefing in one call.
2. Call `memory_write` after significant code changes, decisions, discoveries, blockers, or warnings.
3. Call `memory_checkpoint` every 10-15 minutes during long work.
4. Call `memory_handoff` before you finish.

`memory_agent_join` still exists as a fallback when you only need to join without re-reading context. If `memory_onboard` is not available, call `memory_get_briefing` first, then `memory_agent_join`.

## Ticket Flow

Use tickets when work needs to move between agents:

- `memory_create_ticket` requests help and assigns work to a specific agent/platform or leaves it open.
- Ticket descriptions are capped at 5000 characters; keep them concise and link to memory entries or files for long context.
- New tickets should include `target_url`, `scope`, and `required_fields` so the executor knows where to work, what is allowed, and what must be returned.
- Valid scope values are `READ-ONLY`, `interactive-no-send`, and `interactive`.
- `memory_claim_ticket` picks up work assigned to you.
- `memory_submit_ticket` submits your work for review.
- `memory_review_ticket` approves work or rejects it with concrete fix instructions.

## Naming

- `agent_platform` is the runner only. Use values like `claude-code`, `claude-desktop`, `cursor`, `codex`, `antigravity`, `windsurf`, or `other`. Do not use bare `claude`.
- `agent_name` should be stable and readable. Keep the role stable across sessions. Do not use dates or session IDs.
- `agent_role` should describe your function, for example `main`, `planner`, `tester`, `reviewer`, or `utility`.
- `task_focus` should be one short sentence about the work you are about to do. It appears in the agent registry so parallel agents can coordinate.

## Operating Rules

1. Re-join after every off-board action. `memory_handoff`, `memory_submit_ticket`, `memory_review_ticket`, and compaction can end your active session. The next write or ticket mutation may fail with `NOT ON BOARD`; call `memory_onboard` again, then retry.
2. Check memory mid-flight, not only at session start. Use `memory_status`, `memory_read since_minutes=30`, or `memory_get_briefing` after long pauses, after compaction, before commits on shared code paths, or when the user mentions another agent may be working.
3. Write memory updates as you go, not as a batch at the end. After each meaningful commit, ticket claim, design decision, discovery, blocker, or warning, write the next-agent context.
4. Call `memory_checkpoint` every 10-15 minutes during long work. Include current status, files touched, blockers, and remaining tasks.
5. Commit carefully in shared working trees. Commit incrementally. Before committing, check `git status`; before pushing, skim recent commits. If you see unfamiliar uncommitted edits, do not include or revert them without understanding who made them.
6. Search memory before claiming prior research or decisions do not exist.

If you skip these steps, the next agent will have no context and will redo your work.
Your agent_name is stamped on every entry, so write updates another agent can rely on.
