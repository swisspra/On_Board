#!/bin/bash
# ─────────────────────────────────────────────────────────
# On Board MCP runtime launcher.
#
# MCP clients should point here instead of directly at .venv/bin/python.
# Normal startup still uses the local venv. If the venv is missing after a
# clone/update/cleanup, rebuild it once and then exec server.py.
# ─────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$PY" ]; then
    if ! command -v uv >/dev/null 2>&1; then
        echo "On Board runtime is missing and uv is not installed." >&2
        echo "Install uv, then run: cd \"$SCRIPT_DIR\" && uv sync --inexact" >&2
        exit 127
    fi
    cd "$SCRIPT_DIR"
    uv sync --inexact >&2
fi

exec "$PY" "$SCRIPT_DIR/server.py" "$@"
