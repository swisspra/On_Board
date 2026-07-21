# Changelog

## v3.7.1 — Safer Setup, Compact Onboarding, MCP SDK Security (2026-07-21)

**Current GitHub Release collecting all major changes after v3.5.2, plus a security patch for the open Dependabot MCP Python SDK alerts.**

### Changed
- GitHub Release notes now include the v3.6.0 safer setup/update workflow and v3.7.0 compact onboarding changes.
- Updated locked `mcp` dependency from `1.27.1` to `1.28.1`.
- No On Board behavior changes from v3.7.0.

### Removed
- Removed the old root `index.html` GitHub Pages landing page.

### Upgrade
Update this On Board checkout only:

```bash
bash update.sh
bash doctor.sh --self
```

Update this checkout and refresh every registered linked project:

```bash
bash update.sh --refresh-linked
bash doctor.sh --all-linked
```

`--refresh-linked` also performs the normal update first and preserves each
project's registered hook mode.

If upgrading from v3.5.2 or older, rerun `setup-project.sh /path/to/your/project`
and `doctor.sh /path/to/your/project` for projects that are not in the linked
project registry.

Restart your MCP clients after updating.

---

## v3.7.0 — Compact Onboarding (2026-07-21)

**Agent startup is now shorter, with full context moved back to explicit tools.**

### Changed
- `memory_onboard` now returns compact current context instead of embedding full `memory_get_briefing` and full `memory_list_tickets` output.
- Onboard output now points agents to the right detail tools: `memory_get_briefing`, `memory_list_tickets`, `memory_read`, `memory_search`, `memory_links`, `memory_doctor`, `memory_status`, and `memory_token_usage`.
- `memory_write(priority=3)` now auto-pins critical memory and stores a compact `pinned_summary` while preserving raw `content`.
- System-generated pinned entries, including handoffs, checkpoints, ticket submit handoffs, and rejection warnings, now get `pinned_summary`.
- Startup hook and agent-rule wording now describe compact current context instead of full briefing.

### Removed
- Removed the rarely used `memory_pin` public tool. Use `memory_write(priority=3, pinned_summary=...)` for critical pinned memory.
- Public tool count is now 28.

### Upgrade
```bash
bash update.sh
bash update.sh --refresh-linked
```

Restart your MCP clients after updating.

---

## v3.6.0 — Safer Setup And Updates (2026-07-16)

**One central On Board checkout can now safely serve and refresh multiple linked projects.**

### Added
- Local linked-project registry at `.onboard/linked-projects.json`
- `setup-project.sh --list-linked` and `setup-project.sh --all-linked`
- `doctor.sh --list-linked` and `doctor.sh --all-linked`
- `update.sh --list-linked` and `update.sh --refresh-linked`
- `AGENT_SETUP.md` as an agent-facing setup guide
- `doctor.sh` as a read-only setup checker

### Changed
- `setup-project.sh` now generates `.onboard/` project config, `AGENT_CONTROL.md`, and a project dashboard launcher
- `update.sh` now skips unrelated folders, backs up overwritten files, and requires an explicit refresh for linked projects
- Linked project refresh preserves each project's registered hook mode
- Default MCP runtime now uses `python3 onboard_server.py`, which normally runs `.venv/bin/python server.py` and rebuilds `.venv` only if missing
- Startup hooks now return a small read-only briefing; legacy stop/end-turn hooks no longer write memory
- Agent roles and ticket controls were expanded for parallel worker/tester/reviewer flows

### Upgrade
```bash
bash update.sh
bash update.sh --refresh-linked
```

Restart your MCP clients after updating.

---

## v3.5.2 — Context Dir Template (2026-05-09)

**Small template fix for projects that use external reference directories.**

### Changed
- Added `AGENT_MEM_CONTEXT_DIRS` to the `uv run --directory` MCP config template
- Clarified that context directories are optional and exposed through `memory_context_dirs` / `memory_context_read`

---

## v3.5.1 — uv Setup Templates (2026-05-09)

**A small install-path release for running On Board from a source checkout with `uv`.**

### Added
- `uv sync` / `uv run --directory` install and MCP configuration docs for source checkouts
- Generic `configs/uv-mcp.json` template for MCP clients that can launch through `uv`
- `uv.lock` for reproducible local `uv sync` installs

---

## v3.5.0 — Onboard Protocol (2026-05-09)

**A tighter agent workflow release: one-call onboarding, XML protocol hints, ticket-linked memory, data-health checks, and dashboard linkage.**

### Added
- `memory_onboard` as the primary one-call agent entrypoint: join session, read briefing, inspect tickets, and surface data-health warnings
- XML protocol tags in onboarding output, generated rules, and start hooks to improve agent instruction-following
- `memory_get_briefing(ticket_id=...)` for ticket-scoped onboarding with ticket details and related memories
- `memory_links` for viewing ticket, memory, file, agent, and tag linkage
- `memory_doctor` data-integrity warnings for duplicate active agent identities, orphaned claimed tickets, invalid ticket schemas, and duplicate memory IDs
- pytest workflow harness for docs/protocol drift, ticket-focused briefing, doctor integrity checks, and vector-style search

### Changed
- `SKILL.md` now matches the significant-action memory protocol and current ticket schema
- Ticket mutation tools now require an onboarded/joined agent before claim, submit, review, cancel, or terminate
- `memory_write` now accepts `related_tickets` and skips exact recent duplicates
- Live dashboard now includes a Links/Data Health tab

---

## v3.2.0 — Workflow UX (2026-05-08)

**Improved the daily agent workflow: cleaner briefing modes, setup diagnosis, ranked search, and opt-in local vector-style search.**

### Added
- `memory_get_briefing(mode=...)` with `brief`, `normal`, `deep`, and `handoff-only`
- `memory_doctor` for read-only checks of hooks, rules, runtime memory, and ignored paths
- `memory_search_vector` with opt-in local backend (`AGENT_MEM_VECTOR_BACKEND=local`)

### Changed
- `memory_search` and archive search now rank by relevance, priority, pinned state, and recency
- Compaction output now gives a clearer review-first workflow
- `.agent-mem/*.json` remains the source of truth; vector-style search is a cache/search aid only

### Upgrade
```bash
bash update.sh
# Restart Claude Desktop / Cursor / Codex
```

---

## v3.1.1 — Agent Rejoin Dedup (2026-04-24)

**Fix: `memory_agent_join` no longer creates duplicate entries when the same agent rejoins.**

### Changed
- `memory_agent_join` — same name + same platform → update existing active entry instead of KIA + create new
  - `agent_role` and `task_focus` refreshed on rejoin
  - `joined_at` preserved (session continuity)
  - Response shows `🔄 Rejoined` instead of `🟢 On Board`
- `_mark_prev_kia` — removed `rejoin_same_identity` KIA case; same-identity rejoins now handled by update logic

### Why
Agents joining multiple times per session (crash/restart/reconnect) accumulated duplicate entries in `agents.json` under the same name. Dashboard and briefing showed the same agent multiple times. Reported by claude-opus4.7-web-20apr26 after multiple same-session joins.

### Upgrade
```bash
bash update.sh
# Restart Claude Desktop / Cursor / Codex
```
Existing `agents.json` works as-is — no migration needed.

---

## v3.1.0 — Ticket Schema Enforcement (2026-04-24)

**Tightened `memory_create_ticket` to force structured ticket specs — prevents missing-deliverable rejections.**

### Changed
- `memory_create_ticket` — 3 new required fields: `target_url`, `scope`, `required_fields`
  - `target_url` (str) — URL the executor navigates to; MCP rejects if missing
  - `scope` (enum) — must be `READ-ONLY`, `interactive-no-send`, or `interactive`; MCP rejects invalid values
  - `required_fields` (list, min 1 item) — deliverables executor MUST capture; MCP rejects empty list
- `memory_create_ticket` — 2 new optional fields: `forbidden` (default `[]`), `selector_hints` (default `[]`)
- All 5 new fields stored in ticket data and `.md` file for Jonhny to relay to subagents verbatim

### Why
Simulation (2026-04-21) showed 28.6% rejection rate from Opus tickets missing `required_fields` in ticket bodies. Fixing this at the MCP layer means bad tickets are rejected at creation time, not after a subagent wastes a full run.

### Upgrade
```bash
bash update.sh
# Restart Claude Desktop / Cursor / Codex
```
Existing tickets are unaffected — new fields only apply to newly created tickets.

---

## v3.0.0 — Reliability & Dashboard (2026-04-21)

**Improved agent lifecycle tracking and dashboard UX.**

### Added
- **Heartbeat tracking** — `last_activity` updated on every tool call (10 tools)
- **Idle auto-KIA** — agents idle >30min auto-marked KIA with debounced sweep
- **Idle warnings** — briefing shows warnings for agents approaching KIA threshold
- **Naming validation** — warns on bad agent names (too short, uppercase, same as platform)
- **Dashboard: agent grouping** — groups records by `agent_name`, shows session count
- **Dashboard: platform colors** — Claude=blue, Cursor=violet, Codex=gold, AntiGravity=green
- **Dashboard: orphan ticket detection** — flags tickets whose claimer went offline
- **Dashboard: idle indicators** — active agents idle >15min show warning in roster
- `AGENT_MEM_IDLE_KIA_MIN` env var (default: 30 minutes)
- `--poll-sec` dashboard flag alias

### Changed
- Smarter KIA logic — more precise replacement tracking
- Dashboard default poll interval: 3s → 5s
- Agent join output: shows last 5 recent agents instead of full history
- Version: 1.9.3 → 3.0.0

### Upgrade
```bash
bash update.sh
# Restart Claude Desktop / Cursor / Codex
```
No data migration needed — existing `agents.json` works as-is.

---

## v1.9.3 — Stable (2026-04-15)

- 23 MCP tools
- Tiered memory (hot/warm/cold)
- File-based ticketing system
- Live dashboard with quota tracking
- Bootstrap for existing projects
