# On Board Tools

On Board exposes 30 MCP tools. Most work starts with `memory_onboard`.

## Agent lifecycle

### `memory_onboard`

Primary entry point for every agent session. Joins the project and returns compact current context: collision check, latest handoff summary, tickets, pinned critical memory, and next commands.

Use when: starting work, returning after `/compact`, or recovering from `NOT ON BOARD`.

Common fields:

- `agent_name`: stable identity, such as `dev-main` or `tester-codex`
- `agent_platform`: `claude-code`, `claude-desktop`, `cursor`, `codex`, `antigravity`, `windsurf`, or `other`
- `agent_role`: `main`, `lead`, `planner`, `worker`, `tester`, `reviewer`, `reporter`, `subagent`, or `utility`

Role guidance:

- `main`: primary human-facing agent for the project/session
- `lead`: orchestrates a track or group of agents
- `planner`: breaks work into tickets/specs
- `worker`: implements a ticket
- `tester`: verifies behavior/evidence
- `reviewer`: approves/rejects submitted work
- `reporter`: writes reports/release notes
- `subagent`: narrow helper spawned by another agent
- `utility`: small cleanup/support task

Ticket control uses roles. The creator can always cancel or terminate its own
ticket. `main`, `lead`, and `reviewer` hold coordinator authority and can cancel
or terminate any ticket — that authority does not depend on the creator being
offline. The agent that claimed a ticket can cancel its claimed work (cancel
only, not terminate). No other role gains control from a missing creator: an
absent creator does not promote `utility`, `worker`, or any other role into
ticket control.
- `task_focus`: short description of the current task
- `mode`: kept for compatibility; call `memory_get_briefing` directly when you need `brief`, `normal`, `deep`, or `handoff-only` context.

### `memory_agent_join`

Lower-level join call. Use only if you already have the briefing and need to rejoin before writes or ticket mutations.

### `memory_get_briefing`

Read project context without necessarily joining.

Useful modes:

- `brief`: fast catch-up
- `normal`: regular session context
- `deep`: more history
- `handoff-only`: recent handoff context

### `memory_checkpoint`

Write a mid-work checkpoint. Use every 10-15 minutes during long work.

Include summary, remaining tasks, branch, and blockers.

### `memory_handoff`

Finish a session cleanly. Write what changed, what remains, warnings, and touched files.

Handoff is one of the moves that ends your active session, so rejoin with
`memory_onboard` before calling more write/ticket tools.

### `memory_wait_for_event`

Park until a peer acts, then return everything pending. The listening half of On
Board: instead of a human relaying messages, you block in one call until another
agent creates a ticket, changes a status, or assigns work.

Fields:

- `agent_name`: your onboarded name
- `kinds`: which events wake you — `ticket_created`, `ticket_status_changed`, `ticket_assigned`, or `memory_written` (default: the three ticket kinds)
- `timeout_s`: seconds to park before returning `idle` (default 180)
- `only_mine`: only events on tickets assigned to you, left unassigned, or created by you (default `true`)
- `long_wait`: stdio clients only (Claude Code, Codex); raises the cap to 3600s. Never set it from Claude Desktop, which cancels the call at ~240s and repeated cancels wedge every connected MCP server until restart
- `idle_budget_min`: minutes of consecutive empty parks before the server answers `STAND-DOWN` instead of `idle` (default 15; `0` or `null` listens indefinitely)

Behavior:

- The first call stores your baseline snapshot; every later call diffs against it. The cursor lives in the agent's own watch file, so you carry no bookkeeping — just call the tool again to re-arm.
- A re-arm after a gap returns the accumulated backlog in 0s instead of waking empty. One wake drains the whole queue.
- You never wake on your own actions, so two listeners cannot ping-pong each other.
- A rejection arrives with the reviewer notes and fix instructions in the wake payload.
- The idle counter resets only on a real event, never on re-arming. `STAND-DOWN` is a distinct status, not an `idle`, so a loop that keys off `idle` cannot read it as permission to keep going.
- Events are a diff between polled snapshots. There is no durable event log and no replay: transitions that happen between two snapshots are folded into the next wake, not delivered one by one. The wait is local to this board — there is no external A2A bridge.

After a `hit`, act on the events, then call it again to re-arm. See the `listen`
MCP prompt for the standard loop.

## Persistent memory

### `memory_write`

Write durable project memory after meaningful actions.

Memory types:

- `decision`
- `progress`
- `blocker`
- `context`
- `handoff`
- `todo`
- `file_change`
- `discovery`
- `warning`
- `checkpoint`

Use `related_files`, `related_tickets`, and `tags` when they help the next agent search.

Critical memory:

- Set `priority=3` for critical decisions, warnings, or blockers.
- `priority=3` is auto-pinned and gets a compact `pinned_summary` for onboard/briefing views.
- Raw `content` is still stored in full.

### `memory_unpin`

Unpin a memory without deleting it. The entry stays in `memories.json` with its
full content, marked unpinned and demoted to `priority=1`; `unpin_reason` records
why. Use it when a pinned decision no longer applies but the history still
matters. `memory_write(retracts=<memory_id>)` is the linking alternative: the new
entry unpins the target and references it both ways.

### `memory_read`

Read recent memory. Supports filters by type, tag, agent, time window, and limit.

Common use:

```text
memory_read({"since_minutes": 30, "limit": 20})
```

### `memory_search`

Ranked keyword search over active memories.

Use when looking for prior decisions, known bugs, or previous work on a file.

### `memory_search_vector`

Local vector-style search over memory text. It is optional and local-first.

Use normal `memory_search` first unless semantic matching is specifically useful.

### `memory_links`

Shows linkage between memories, tickets, agents, and files.

Useful filters:

- `ticket_id`
- `agent_name`
- `file`
- `include_archive`

## Ticket queue

Tickets are the cross-agent workflow layer. They live as files under `.agent-mem/tickets/`.

Basic lifecycle:

```text
open -> claimed -> in_progress -> submitted -> reviewing -> closed
```

Rejected tickets reopen with fix instructions instead of dying. Each rejection
round is archived under `tickets/rejected/<ticket_id>/attempt-<N>/` (the rejected
spec, the submission under review, and `<ticket_id>-rejected.md` with the notes
and fix instructions), so a second attempt never overwrites the first. The ticket
itself reopens as `open` at its canonical path.

### `memory_create_ticket`

Create work for another agent.

Required fields:

- `agent_name`: creator
- `title`: short title
- `description`: capped at 5000 chars
- `target_url`: file or web URL the executor needs
- `scope`: `READ-ONLY`, `interactive-no-send`, or `interactive`
- `required_fields`: artifacts the submitter must return

Optional fields:

- `assigned_to`
- `priority`
- `forbidden`
- `selector_hints`
- `tags`
- `related_files`

`assigned_to` is an exact, case-sensitive **stable agent name** — `cursor-coder`,
`codex-main` — never a platform such as `cursor` or `codex`. Leave it out to put
the ticket in the open queue any joined agent can claim; a named ticket can only
be claimed by that exact agent, or by a coordinator.

### `memory_claim_ticket`

Claim a ticket before doing the work. Use this so other agents do not duplicate the same task.

A ticket assigned to a specific agent can only be claimed by that agent (exact,
case-sensitive name match); mentioning a platform in `assigned_to` does not make
the ticket claimable by every agent on it. Unassigned tickets stay a free-for-all
queue, and a coordinator may claim past the assignment.

### `memory_submit_ticket`

Submit completed work for review.

Creates `tickets/review/<ticket_id>-submit.md` and moves the ticket to `submitted`.

Include summary, changed files, and reviewer notes.

Submitting normally ends your active session (auto-handoff) so the reviewer can
pick the work up. Two cases keep you on board instead: pass `stay_active=true`
when you are listening for the verdict, and you are also held when you still owe
a review on another ticket sitting in `submitted`. If you were handed off, the
next write/ticket call returns `NOT ON BOARD` — call `memory_onboard` again.

### `memory_review_ticket`

Approve or reject a submitted ticket.

Use `verdict="approve"` when evidence is good; the ticket closes and the spec plus
submission move to `tickets/closed/`.

Use `verdict="reject"` with concrete `fix_instructions` when work needs another
pass; the ticket reopens and that attempt is archived under
`tickets/rejected/<ticket_id>/attempt-<N>/`.

Reviewing does not end your own session: the reviewer stays active after an
approve or a reject, so you can adjudicate the next submission without
re-onboarding. A rejection that lands while the executor is parked in
`memory_wait_for_event` wakes it with the notes and fix instructions.

Only a disinterested party adjudicates: an agent that executed a ticket may not
also approve or reject it. If you did the work yourself and no other agent is
available, pass `allow_self_review=true` — you must own the ticket or hold a
main/lead/reviewer role, and the ticket is permanently stamped
`SELF-REVIEWED — no independent check` in the audit.

### `memory_list_tickets`

List open tickets by default. Can filter by status or assignee, and can include closed/rejected tickets.

### `memory_cancel_ticket`

Cancel a ticket that should no longer be done. Allowed for the creator, a
coordinator (`main`/`lead`/`reviewer`), or the agent that claimed it.

### `memory_terminate_ticket`

Force-terminate a ticket. This is destructive and should be rare. Allowed for the
creator or a coordinator — not for a claimed agent, and not for `utility` or
other roles just because the creator is unavailable.

## Project context and setup

### `memory_init`

Initialize `.agent-mem/` for a new project.

Use once per project.

### `memory_bootstrap`

Bootstrap memory for an existing project by scanning common project files, git history, directory structure, and config files.

Use this instead of `memory_init` when adopting an existing repo.

### `memory_status`

Quick status report: project, agents, memory counts, and latest activity.

### `memory_doctor`

Checks setup health and common data problems.

Use after setup, after strange agent behavior, or before blaming the model.

### `memory_update_state`

Write small project state values, such as current phase, owner, or default workflow notes.

### `memory_context_dirs`

List external context directories configured with `AGENT_MEM_CONTEXT_DIRS`.

### `memory_context_read`

Read a file from configured context directories.

Use this for docs/specs that should not live inside the project repo.

## Compaction and archive

### `memory_token_usage`

Estimate memory size and briefing token cost.

Use when briefings are getting too long.

### `memory_prepare_compaction`

Preview old memories that can be compacted.

This does not modify files.

### `memory_compact`

Archive older raw memories after a digest exists.

Compaction rewrites memory files only. It does not end your session or change your
agent status — stay on board and keep calling write/ticket tools afterwards.

Recommended flow:

```text
memory_prepare_compaction()
memory_write(memory_type="context", title="Digest: ...", content="...")
memory_compact()
```

### `memory_search_archive`

Search archived raw memories after compaction.

## Minimal agent loop

For normal coding work:

```text
memory_onboard(...)
memory_read({"since_minutes": 30})
memory_write(...)       # after meaningful discovery/change
memory_checkpoint(...)  # long sessions only
memory_handoff(...)
```

For delegated work:

```text
memory_create_ticket(...)
memory_claim_ticket(...)
memory_submit_ticket(...)
memory_review_ticket(...)
```

If an agent loses context, starts repeating work, or claims it cannot see prior decisions, run:

```text
memory_status()
memory_get_briefing({"mode": "brief"})
memory_search({"query": "the topic or file name"})
```
