# v3.7.0 — Compact Onboarding

This release makes agent startup shorter and clearer. Onboarding now joins the
project and shows only the current working context; deeper history stays in the
tools built for it.

## Highlights

- `memory_onboard` now returns compact current context instead of embedding full briefing and full ticket detail.
- Onboard output now includes collision check, recent KIA agents, latest handoff summary, ticket summary, pinned critical memory, data health, and where to load details.
- `memory_write(priority=3)` now auto-stores a compact `pinned_summary` while preserving raw memory content.
- System-generated pinned memories, including handoffs, checkpoints, ticket submit handoffs, and rejection warnings, also get `pinned_summary`.
- Removed the rarely used `memory_pin` public tool. Critical memory now flows through `memory_write(priority=3)`.
- Tool surface is now 28 MCP tools.

## Upgrade

```bash
bash update.sh
bash update.sh --refresh-linked
```

`--refresh-linked` preserves each project's registered hook mode. Restart your
MCP clients after updating.
