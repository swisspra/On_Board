# v3.7.1 — Safer Setup, Compact Onboarding, MCP SDK Security

This release collects the major On Board changes after v3.5.2 into one current
GitHub Release, plus a security dependency update for the MCP Python SDK.

## Highlights

- Safer central-install workflow: one On Board checkout can serve multiple projects with separate project memory.
- Linked-project registry: `setup-project.sh`, `doctor.sh`, and `update.sh` can list or refresh known linked projects.
- Safer project refresh: `update.sh --refresh-linked` preserves registered hook mode and backs up overwritten generated files.
- Runtime launcher update: generated MCP config now uses `python3 onboard_server.py`, which normally runs `.venv/bin/python server.py` and only rebuilds `.venv` if missing.
- Compact onboarding: `memory_onboard` now returns current working context instead of full briefing and full ticket detail.
- Better agent routing: onboarding points agents to `memory_get_briefing`, `memory_list_tickets`, `memory_read`, `memory_search`, `memory_links`, `memory_doctor`, `memory_status`, and `memory_token_usage` for details.
- Critical memory cleanup: `memory_write(priority=3)` auto-pins important entries with a compact `pinned_summary` while preserving raw content.
- System-generated handoffs, checkpoints, ticket submit handoffs, and rejection warnings now also get `pinned_summary`.
- Hook behavior is safer by default: startup hooks return a small read-only briefing; legacy stop/end-turn hooks no longer write memory.
- Agent roles and ticket controls were expanded for parallel main, worker, tester, reviewer, and sub-agent flows.
- Removed the rarely used `memory_pin` public tool. Use `memory_write(priority=3, pinned_summary=...)` for critical memory.
- Public MCP tool surface is now 28 tools.
- Updated locked `mcp` dependency from `1.27.1` to `1.28.1`, covering the open high-severity Dependabot alerts for the MCP Python SDK lockfile entry.

## Notes

- This release is compatible with existing `.agent-mem` project memory.
- Existing linked projects can use `bash update.sh --refresh-linked` to update the central checkout and refresh generated project files in one run.
- Restart MCP clients after updating so they reload generated config and hooks.

## Upgrade

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

`--refresh-linked` also performs the normal update first. It preserves each
project's registered hook mode. Restart your MCP clients after updating.

If you are upgrading from v3.5.2 or older, refresh project setup after the
central update so generated `.onboard/` config, rules, hooks, and dashboard
launchers are current:

```bash
bash setup-project.sh /path/to/your/project
bash doctor.sh /path/to/your/project
```
