# Greetings Agents!
# Welcome On Board — Agent Shared Memory Protocol

Project uses `.agent-mem/` for multi-agent coordination across platforms.
Get On Board before any work.

<on_board_protocol>
  <required_first_call>memory_onboard</required_first_call>
  <agent_identity>Use stable agent_name. No dates, model names, or session ids.</agent_identity>
  <write_policy>Write after meaningful actions only.</write_policy>
  <ticket_policy>Ticket mutations require onboarded session.</ticket_policy>
  <handoff_policy>Always handoff before leaving.</handoff_policy>
</on_board_protocol>

## Start Here

1. `memory_onboard` w/ stable agent_name, agent_platform, agent_role, optional task_focus → joins the session and returns the briefing in one call.
2. `memory_write` after significant code changes, decisions, discoveries, blockers, warnings.
3. `memory_checkpoint` every 10-15 min during long work.
4. `memory_handoff` before finishing.

Fallback: `memory_agent_join` for join-only. If `memory_onboard` unavailable → `memory_get_briefing` first, then `memory_agent_join`.

## Setup Control

On Board setup is managed by generated project files, not by hand-editing hook
configs. If the user asks to inspect or change On Board setup, read:

```text
.onboard/AGENT_CONTROL.md
```

Use the commands in that file for `doctor.sh`, MCP config, dashboard, and hook
mode changes.

## Ticket Flow

Tickets move work between agents:

- `memory_create_ticket` — request help / assign work
- Ticket description is capped at 5000 chars; keep concise, link to memories/files
- New tickets need: `target_url`, `scope`, `required_fields`
- Valid scope: `READ-ONLY`, `interactive-no-send`, `interactive`
- `memory_claim_ticket` — pick up assigned work
- `memory_submit_ticket` — submit for review
- `memory_review_ticket` — approve or reject w/ fix instructions

## Naming

- `agent_platform` = runner only. Values: `claude-code`, `claude-desktop`, `cursor`, `codex`, `antigravity`, `windsurf`, `other`. Never bare `claude`.
- `agent_name` = stable, readable. Keep role stable across sessions. No dates / session IDs.
- `agent_role` = function. Use one of:
  - `main`: primary human-facing agent for the project/session
  - `lead`: orchestrates a track or group of agents
  - `planner`: breaks work into tickets/specs
  - `worker`: implements a ticket
  - `tester`: verifies behavior/evidence
  - `reviewer`: approves/rejects submitted work
  - `reporter`: writes reports/release notes
  - `subagent`: narrow helper spawned by another agent
  - `utility`: small cleanup/support task
- `task_focus` = one sentence on current work. Shows in agent registry for coordination.

## Operating Rules

1. **Re-join after every off-board action.** `memory_handoff`, `memory_submit_ticket`, `memory_review_ticket`, compaction → end active session. Next write/ticket mutation may fail w/ `NOT ON BOARD` → call `memory_onboard` again, retry.
2. **Check mid-flight, not only at start.** Use `memory_status`, `memory_read since_minutes=30`, or `memory_get_briefing` after long pauses, after compaction, before commits on shared paths, when user mentions parallel agent.
3. **Write as you go, not batched.** After each commit, ticket claim, decision, discovery, blocker, warning → write next-agent context.
4. **`memory_checkpoint` every 10-15 min during long work.** Include status, files touched, blockers, remaining tasks.
5. **Commit carefully in shared working trees.** Commit incrementally. Before commit: `git status`. Before push: skim recent commits. Unfamiliar uncommitted edits → don't include/revert without context.
6. **Search memory before claiming prior research doesn't exist.**

Skip these → next agent has no context, redoes your work.
Your agent_name stamps every entry → write updates others can rely on.
