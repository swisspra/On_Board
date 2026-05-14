#!/bin/bash
# ─────────────────────────────────────────────────────────
# On Board — Update to latest version
#
# For repo owner:  bash update.sh           ← git pull + reinstall + deploy
# For git users:   bash update.sh           ← git pull + reinstall
# Manual target:   bash update.sh /path/to  ← copy to specific location
# ─────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🧠 On Board — Update"
echo ""

# ── Step 1: Git pull (if this is a git repo) ──
if [ -d ".git" ]; then
    echo "📥 Pulling latest from git..."
    git pull --ff-only 2>/dev/null && echo "   ✅ Up to date" || echo "   ⚠️ Git pull failed — using local files"
    echo ""
fi

# ── Step 2: Sync local environment ──
SYNCED=0
if command -v uv >/dev/null 2>&1; then
    echo "📦 Syncing uv environment..."
    if uv sync -q 2>/dev/null; then
        TOOLS=$(uv run python -c "
import sys; sys.path.insert(0, '.')
from server import mcp
print(len(mcp._tool_manager._tools))
" 2>/dev/null || echo "?")
        echo "   ✅ uv synced ($TOOLS tools)"
        SYNCED=1
    else
        echo "   ⚠️ uv sync failed"
    fi
    echo ""
fi

if [ "$SYNCED" -eq 0 ] && [ -d "venv" ]; then
    echo "📦 Updating local venv..."
    ./venv/bin/pip install -q "mcp[cli]" pydantic 2>/dev/null
    TOOLS=$(./venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from server import mcp
print(len(mcp._tool_manager._tools))
" 2>/dev/null || echo "?")
    echo "   ✅ venv updated ($TOOLS tools)"
    echo ""
fi

# ── Step 3: Show version ──
VERSION=$(grep -o 'version = "[^"]*"' pyproject.toml | head -1 | cut -d'"' -f2)
echo "📋 Version: v$VERSION"
echo ""

# ── Step 4: Deploy to other locations (optional) ──
TARGET="${1:-}"

# If manual target specified
if [ -n "$TARGET" ]; then
    TARGETS=("$TARGET")
else
    # Auto-detect deployed copies from Claude Desktop config
    CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    TARGETS=()

    if [ -f "$CONFIG" ]; then
        TMPFILE=$(mktemp)
        python3 -c "
import json, os
with open('''$CONFIG''') as f:
    cfg = json.load(f)
src = os.path.realpath('$SCRIPT_DIR')
for name, srv in cfg.get('mcpServers', {}).items():
    for a in srv.get('args', []):
        if 'server.py' in a and 'Mem_MCP' in a:
            dest = os.path.dirname(a)
            if os.path.realpath(dest) != src:
                print(dest)
" > "$TMPFILE" 2>/dev/null
        while IFS= read -r line; do
            [ -n "$line" ] && TARGETS+=("$line")
        done < "$TMPFILE"
        rm -f "$TMPFILE"
    fi
fi

if [ ${#TARGETS[@]} -eq 0 ]; then
    echo "✅ Done! No deployed copies to update."
    echo ""
    echo "If this IS your deployed copy, you're all set — just restart your agents."
    echo "If you have separate deployed copies, run: bash update.sh /path/to/copy"
    exit 0
fi

echo "🚀 Deploying to ${#TARGETS[@]} location(s)..."
echo ""

for DEST in "${TARGETS[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎯 $DEST"

    if [ ! -d "$DEST" ]; then
        echo "   ❌ Not found — skipping"
        continue
    fi

    cp "$SCRIPT_DIR/server.py" "$DEST/server.py"
    cp "$SCRIPT_DIR/pyproject.toml" "$DEST/pyproject.toml"
    [ -f "$SCRIPT_DIR/uv.lock" ] && cp "$SCRIPT_DIR/uv.lock" "$DEST/uv.lock"
    [ -f "$SCRIPT_DIR/dashboard_live.py" ] && cp "$SCRIPT_DIR/dashboard_live.py" "$DEST/dashboard_live.py"
    [ -f "$SCRIPT_DIR/SKILL.md" ] && cp "$SCRIPT_DIR/SKILL.md" "$DEST/SKILL.md"

    [ -d "$SCRIPT_DIR/hooks" ] && mkdir -p "$DEST/hooks" && cp "$SCRIPT_DIR/hooks/"*.sh "$DEST/hooks/" 2>/dev/null && chmod +x "$DEST/hooks/"*.sh 2>/dev/null
    [ -d "$SCRIPT_DIR/configs" ] && mkdir -p "$DEST/configs" && cp "$SCRIPT_DIR/configs/"* "$DEST/configs/" 2>/dev/null

    DEPLOY_SYNCED=0
    if command -v uv >/dev/null 2>&1; then
        if (cd "$DEST" && uv sync -q) 2>/dev/null; then
            DEPLOY_SYNCED=1
        fi
    fi

    if [ "$DEPLOY_SYNCED" -eq 0 ] && [ -f "$DEST/venv/bin/pip" ]; then
        "$DEST/venv/bin/pip" install -q "mcp[cli]" pydantic 2>/dev/null
    fi

    TOOLS="?"
    if [ "$DEPLOY_SYNCED" -eq 1 ]; then
        TOOLS=$(cd "$DEST" && uv run python -c "
import sys; sys.path.insert(0, '.')
from server import mcp; print(len(mcp._tool_manager._tools))
" 2>/dev/null || echo "?")
    elif [ -f "$DEST/venv/bin/python" ]; then
        TOOLS=$("$DEST/venv/bin/python" -c "
import sys; sys.path.insert(0, '$DEST')
from server import mcp; print(len(mcp._tool_manager._tools))
" 2>/dev/null || echo "?")
    fi

    echo "   ✅ Updated ($TOOLS tools)"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Restart Claude Desktop / Cursor / Codex to pick up changes."
