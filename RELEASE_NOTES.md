# v3.5.1 — uv Setup Templates

Small patch release for running On Board from a source checkout with `uv`.

## Highlights

- Added `uv sync` / `uv run --directory` install docs.
- Added `configs/uv-mcp.json` as a generic MCP config template for clients that can launch through `uv`.
- Added `uv.lock` for reproducible source-checkout installs.
- Documented testing through `uv sync --extra test` and `uv run python -m pytest tests -q`.
- Kept `uvx` out of the template for now; `uvx` should wait until On Board has a package entrypoint/console script.

## Upgrade

```bash
bash update.sh
# Restart Claude Desktop / Cursor / Codex / Claude Code
```

## Notes

This release does not change the MCP workflow behavior from v3.5.0. It only adds a cleaner checkout-based install/configuration path.
