#!/bin/bash
# ─────────────────────────────────────────────────────────
# Claude Code Hook: SessionStart
# Injects a small read-only On Board startup hint.
# Works with Claude Code's hook system (settings.json)
# ─────────────────────────────────────────────────────────

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
AGENT_MEM_DIR="$PROJECT_DIR/.agent-mem"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Read stdin (Claude Code sends JSON)
cat >/dev/null

AGENT_MEM_DIR="$AGENT_MEM_DIR" python3 "$SCRIPT_DIR/onboard-mini-brief.py" 2>/dev/null

exit 0
