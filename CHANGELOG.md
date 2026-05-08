# Changelog

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
