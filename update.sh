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
REGISTRY_FILE="${ONBOARD_REGISTRY_FILE:-$SCRIPT_DIR/.onboard/linked-projects.json}"
TARGET=""
REFRESH_LINKED=0
LIST_LINKED=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --refresh-linked)
            REFRESH_LINKED=1
            shift
            ;;
        --list-linked)
            LIST_LINKED=1
            shift
            ;;
        --help|-h)
            echo "Usage: bash update.sh [deployed-copy-path]"
            echo "       bash update.sh --list-linked"
            echo "       bash update.sh --refresh-linked"
            exit 0
            ;;
        --*)
            echo "❌ Unknown option: $1"
            echo "Usage: bash update.sh [deployed-copy-path]"
            echo "       bash update.sh --list-linked"
            echo "       bash update.sh --refresh-linked"
            exit 1
            ;;
        *)
            if [ -n "$TARGET" ]; then
                echo "❌ Only one deployed-copy path is supported"
                exit 1
            fi
            TARGET="$1"
            shift
            ;;
    esac
done

list_linked_projects() {
    python3 - "$REGISTRY_FILE" <<'PY'
import json
import sys
from pathlib import Path

registry = Path(sys.argv[1])
if not registry.exists():
    raise SystemExit(0)

try:
    data = json.loads(registry.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

for project in data.get("projects", []):
    path = project.get("path")
    if path:
        print(path)
PY
}

list_linked_project_records() {
    python3 - "$REGISTRY_FILE" <<'PY'
import json
import sys
from pathlib import Path

registry = Path(sys.argv[1])
if not registry.exists():
    raise SystemExit(0)

try:
    data = json.loads(registry.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

for project in data.get("projects", []):
    path = project.get("path")
    hook_mode = project.get("hook_mode") or "safe"
    if path:
        print(f"{path}\t{hook_mode}")
PY
}

show_linked_projects() {
    LINKED="$(list_linked_projects)"
    echo "Linked projects:"
    if [ -n "$LINKED" ]; then
        printf '%s\n' "$LINKED" | sed 's/^/  /'
    else
        echo "  (none)"
    fi
}

refresh_linked_projects() {
    LINKED="$(list_linked_project_records)"
    if [ -z "$LINKED" ]; then
        echo "No linked projects registered yet."
        return 0
    fi
    while IFS=$'\t' read -r linked_project linked_hook_mode; do
        [ -n "$linked_project" ] || continue
        linked_hook_mode="${linked_hook_mode:-safe}"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Refreshing linked project: $linked_project"
        bash "$SCRIPT_DIR/setup-project.sh" "$linked_project" --hooks "$linked_hook_mode"
        bash "$SCRIPT_DIR/doctor.sh" "$linked_project"
    done <<< "$LINKED"
}

echo "🧠 On Board — Update"
echo ""

if [ "$LIST_LINKED" -eq 1 ]; then
    show_linked_projects
    exit 0
fi

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
    if uv sync --inexact -q 2>/dev/null; then
        TOOLS=$(.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from server import mcp
print(len(mcp._tool_manager._tools))
" 2>/dev/null || echo "?")
        echo "   ✅ uv synced without pruning extras ($TOOLS tools)"
        SYNCED=1
    else
        echo "   ⚠️ uv sync failed"
    fi
    echo ""
fi

if [ "$SYNCED" -eq 0 ] && [ -d ".venv" ]; then
    echo "📦 Checking existing .venv..."
    TOOLS=$(.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from server import mcp
print(len(mcp._tool_manager._tools))
" 2>/dev/null || echo "?")
    echo "   ⚠️ uv unavailable; keeping existing .venv ($TOOLS tools)"
    echo ""
fi

# ── Step 3: Show version ──
VERSION=$(grep -o 'version = "[^"]*"' pyproject.toml | head -1 | cut -d'"' -f2)
echo "📋 Version: v$VERSION"
echo ""

# ── Step 4: Deploy to other locations (optional) ──

is_onboard_target() {
    local dest="$1"
    [ -d "$dest" ] || return 1
    if [ -f "$dest/pyproject.toml" ] && grep -qE 'name = "(onboard-memory-mcp|swisspra-on_board)"' "$dest/pyproject.toml"; then
        return 0
    fi
    if [ -f "$dest/server.py" ] && grep -q "onboard_memory_mcp" "$dest/server.py" && grep -q "On Board" "$dest/server.py"; then
        return 0
    fi
    if [ -f "$dest/SKILL.md" ] && grep -q "On Board" "$dest/SKILL.md" && grep -q "agent-memory" "$dest/SKILL.md"; then
        return 0
    fi
    return 1
}

copy_file_if_present() {
    local src="$1"
    local dest="$2"
    [ -f "$src" ] || return 0
    mkdir -p "$(dirname "$dest")"
    if [ -f "$dest" ]; then
        local rel="${dest#$DEST/}"
        mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
        cp "$dest" "$BACKUP_DIR/$rel"
    fi
    cp "$src" "$dest"
}

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
    if name != 'agent-memory':
        continue
    for a in srv.get('args', []):
        if 'server.py' in a:
            dest = os.path.dirname(a)
            if os.path.realpath(dest) != src:
                pyproject = os.path.join(dest, 'pyproject.toml')
                marker = os.path.join(dest, 'server.py')
                ok = False
                if os.path.isfile(pyproject):
                    text = open(pyproject, encoding='utf-8').read()
                    ok = 'name = "onboard-memory-mcp"' in text or 'name = "swisspra-on_board"' in text
                if not ok and os.path.isfile(marker):
                    text = open(marker, encoding='utf-8', errors='replace').read(2000)
                    ok = 'On Board' in text and 'onboard_memory_mcp' in text
                if ok:
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
    echo ""
    show_linked_projects
    echo ""
    if [ "$REFRESH_LINKED" -eq 1 ]; then
        refresh_linked_projects
    else
        echo "Refresh known projects when needed:"
        echo "  bash \"$SCRIPT_DIR/update.sh\" --refresh-linked"
        echo "  bash \"$SCRIPT_DIR/setup-project.sh\" --all-linked"
        echo "  bash \"$SCRIPT_DIR/doctor.sh\" --all-linked"
    fi
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

    if [ "$(cd "$DEST" && pwd)" = "$SCRIPT_DIR" ]; then
        echo "   ✅ This is the source checkout — no copy needed"
        continue
    fi

    if ! is_onboard_target "$DEST"; then
        echo "   ❌ Not an On Board checkout — skipping to avoid overwriting unrelated files"
        echo "      Expected pyproject.toml name=onboard-memory-mcp or On Board markers in server.py/SKILL.md"
        continue
    fi

    BACKUP_DIR="$DEST/.onboard-update-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR/hooks" "$BACKUP_DIR/configs" "$BACKUP_DIR/templates" "$BACKUP_DIR/docs"

    copy_file_if_present "$SCRIPT_DIR/server.py" "$DEST/server.py"
    copy_file_if_present "$SCRIPT_DIR/pyproject.toml" "$DEST/pyproject.toml"
    copy_file_if_present "$SCRIPT_DIR/uv.lock" "$DEST/uv.lock"
    copy_file_if_present "$SCRIPT_DIR/dashboard_live.py" "$DEST/dashboard_live.py"
    copy_file_if_present "$SCRIPT_DIR/SKILL.md" "$DEST/SKILL.md"
    copy_file_if_present "$SCRIPT_DIR/AGENT_SETUP.md" "$DEST/AGENT_SETUP.md"
    copy_file_if_present "$SCRIPT_DIR/setup-project.sh" "$DEST/setup-project.sh"
    chmod +x "$DEST/setup-project.sh" 2>/dev/null || true
    copy_file_if_present "$SCRIPT_DIR/doctor.sh" "$DEST/doctor.sh"
    chmod +x "$DEST/doctor.sh" 2>/dev/null || true
    copy_file_if_present "$SCRIPT_DIR/README.md" "$DEST/README.md"
    copy_file_if_present "$SCRIPT_DIR/RELEASE_NOTES.md" "$DEST/RELEASE_NOTES.md"
    copy_file_if_present "$SCRIPT_DIR/CHANGELOG.md" "$DEST/CHANGELOG.md"

    if [ -d "$SCRIPT_DIR/hooks" ]; then
        mkdir -p "$DEST/hooks"
        copy_file_if_present "$SCRIPT_DIR/hooks/claude-code-session-start.sh" "$DEST/hooks/claude-code-session-start.sh"
        copy_file_if_present "$SCRIPT_DIR/hooks/codex-session-start.sh" "$DEST/hooks/codex-session-start.sh"
        copy_file_if_present "$SCRIPT_DIR/hooks/cursor-session-start.sh" "$DEST/hooks/cursor-session-start.sh"
        copy_file_if_present "$SCRIPT_DIR/hooks/onboard-mini-brief.py" "$DEST/hooks/onboard-mini-brief.py"
        [ -f "$DEST/hooks/claude-code-stop.sh" ] && cp "$DEST/hooks/claude-code-stop.sh" "$BACKUP_DIR/hooks/claude-code-stop.sh"
        [ -f "$DEST/hooks/codex-stop.sh" ] && cp "$DEST/hooks/codex-stop.sh" "$BACKUP_DIR/hooks/codex-stop.sh"
        [ -f "$DEST/hooks/cursor-session-end.sh" ] && cp "$DEST/hooks/cursor-session-end.sh" "$BACKUP_DIR/hooks/cursor-session-end.sh"
        rm -f "$DEST/hooks/claude-code-stop.sh" "$DEST/hooks/codex-stop.sh" "$DEST/hooks/cursor-session-end.sh" 2>/dev/null || true
        chmod +x "$DEST/hooks/"*.sh "$DEST/hooks/"*.py 2>/dev/null || true
    fi
    if [ -d "$SCRIPT_DIR/configs" ]; then
        mkdir -p "$DEST/configs"
        for src in "$SCRIPT_DIR/configs/"*; do
            [ -f "$src" ] && copy_file_if_present "$src" "$DEST/configs/$(basename "$src")"
        done
    fi
    if [ -d "$SCRIPT_DIR/templates" ]; then
        mkdir -p "$DEST/templates"
        for src in "$SCRIPT_DIR/templates/"*; do
            [ -f "$src" ] && copy_file_if_present "$src" "$DEST/templates/$(basename "$src")"
        done
    fi
    if [ -d "$SCRIPT_DIR/docs" ]; then
        mkdir -p "$DEST/docs"
        copy_file_if_present "$SCRIPT_DIR/docs/SETUP.md" "$DEST/docs/SETUP.md"
        copy_file_if_present "$SCRIPT_DIR/docs/TOOLS.md" "$DEST/docs/TOOLS.md"
        copy_file_if_present "$SCRIPT_DIR/docs/A2A.md" "$DEST/docs/A2A.md"
    fi

    DEPLOY_SYNCED=0
    if command -v uv >/dev/null 2>&1; then
        if (cd "$DEST" && uv sync --inexact -q) 2>/dev/null; then
            DEPLOY_SYNCED=1
        fi
    fi

    TOOLS="?"
    if [ "$DEPLOY_SYNCED" -eq 1 ]; then
        TOOLS=$(cd "$DEST" && .venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from server import mcp; print(len(mcp._tool_manager._tools))
" 2>/dev/null || echo "?")
    elif [ -f "$DEST/.venv/bin/python" ]; then
        TOOLS=$("$DEST/.venv/bin/python" -c "
import sys; sys.path.insert(0, '$DEST')
from server import mcp; print(len(mcp._tool_manager._tools))
" 2>/dev/null || echo "?")
    fi

    echo "   ✅ Updated ($TOOLS tools)"
    echo "   ↩ Backup: $BACKUP_DIR"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Updated On Board code. Next, refresh generated project config for each project:"
show_linked_projects
if [ "$REFRESH_LINKED" -eq 1 ]; then
    refresh_linked_projects
else
    echo ""
    echo "Refresh known projects when needed:"
    echo "  bash \"$SCRIPT_DIR/update.sh\" --refresh-linked"
    echo "  bash \"$SCRIPT_DIR/setup-project.sh\" --all-linked"
    echo "  bash \"$SCRIPT_DIR/doctor.sh\" --all-linked"
fi
echo ""
echo "Then restart Claude Desktop / Cursor / Codex to pick up changes."
