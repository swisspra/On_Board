# v3.5.2 — Context Dir Template

Small patch release for projects that use external context directories.

## Highlights

- Added `AGENT_MEM_CONTEXT_DIRS` to `configs/uv-mcp.json`.
- Updated the `uv run --directory` README example to include optional context directories.
- Clarified that agents can browse those context directories through `memory_context_dirs` and `memory_context_read`.

## Upgrade

```bash
bash update.sh
# Restart Claude Desktop / Cursor / Codex / Claude Code
```

## Notes

No MCP behavior changed. This release only fixes the checkout-based `uv` template/docs so existing runtime support for context directories is visible.
