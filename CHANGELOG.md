# Changelog

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
