# On Board Tools

On Board exposes 29 MCP tools. Most work starts with `memory_onboard`.

## Agent lifecycle

### `memory_onboard`

Primary entry point for every agent session. Joins the project and returns the briefing in one call.

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

Ticket control uses roles. `main`, `lead`, and `reviewer` can cancel or
terminate stuck tickets when the original creator is gone. Other roles can
still cancel their own tickets, and a claimed agent can cancel its claimed work.
- `task_focus`: short description of the current task
- `mode`: `brief`, `normal`, `deep`, or `handoff-only`

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

After handoff, rejoin with `memory_onboard` before calling more write/ticket tools.

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

### `memory_pin`

Pin or unpin an important memory so it stays visible in briefings.

## Ticket queue

Tickets are the cross-agent workflow layer. They live as files under `.agent-mem/tickets/`.

Basic lifecycle:

```text
open -> claimed -> in_progress -> submitted -> reviewing -> closed
```

Rejected tickets reopen with fix instructions instead of dying.

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

### `memory_claim_ticket`

Claim a ticket before doing the work. Use this so other agents do not duplicate the same task.

### `memory_submit_ticket`

Submit completed work for review.

Include summary, changed files, and reviewer notes.

After submit, rejoin with `memory_onboard` before doing more ticket work.

### `memory_review_ticket`

Approve or reject a submitted ticket.

Use `verdict="approve"` when evidence is good.

Use `verdict="reject"` with concrete `fix_instructions` when work needs another pass.

After review, rejoin with `memory_onboard` before doing more ticket work.

### `memory_list_tickets`

List open tickets by default. Can filter by status or assignee, and can include closed/rejected tickets.

### `memory_cancel_ticket`

Cancel a ticket that should no longer be done.

### `memory_terminate_ticket`

Force-terminate a ticket. This is destructive and should be rare.

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
