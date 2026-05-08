# v3.5.0 — Onboard Protocol

This release tightens the daily multi-agent workflow around a single entrypoint: `memory_onboard`.

## Highlights

- `memory_onboard` joins the agent session, returns the briefing, shows open tickets, and reports data-health warnings in one call.
- XML protocol tags are now emitted by onboarding, generated rules, and start hooks so agents can identify the required workflow more reliably.
- Ticket-focused briefing and `memory_links` connect tickets, memories, related files, agents, and tags.
- Memory writes can now include `related_tickets`, and exact recent duplicate writes are skipped.
- Ticket mutations now require an onboarded/joined agent before claim, submit, review, cancel, or terminate.
- The live dashboard includes a Links/Data Health view for ticket-memory linkage and integrity warnings.
- `memory_doctor` now checks duplicate active identities, orphaned claimed tickets, invalid active ticket schemas, and duplicate memory IDs.
- pytest coverage now guards server workflows, docs/protocol drift, XML protocol hints, and dashboard linkage.

## Upgrade

```bash
bash update.sh
# Restart Claude Desktop / Cursor / Codex / Claude Code
```

## Notes

`AGENT_PROJECT_DIR` remains the project anchor for `.agent-mem/`; it keeps On Board memory project-local and does not replace dedicated filesystem or desktop-command MCP servers.
