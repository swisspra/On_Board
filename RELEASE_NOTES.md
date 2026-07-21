# v3.7.1 — MCP SDK Security Update

This patch updates the locked MCP Python SDK dependency used by On Board.
It keeps the v3.7.0 compact onboarding behavior unchanged.

## Highlights

- Updated locked `mcp` dependency from `1.27.1` to `1.28.1`.
- Covers the open high-severity Dependabot alerts for the MCP Python SDK lockfile entry.
- No On Board behavior changes from v3.7.0.
- No On Board tool, setup, memory, hook, or dashboard behavior changed.

## Upgrade

```bash
bash update.sh
bash update.sh --refresh-linked
```

`--refresh-linked` preserves each project's registered hook mode. Restart your
MCP clients after updating.
