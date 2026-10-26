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
source_tools() {
    .venv/bin/python - "$SCRIPT_DIR" <<'PY' 2>/dev/null
import asyncio
import sys

sys.path.insert(0, sys.argv[1])

from server import mcp

print(len(asyncio.run(mcp.list_tools())))
PY
}

SYNCED=0
if command -v uv >/dev/null 2>&1; then
    echo "📦 Syncing uv environment..."
    if uv sync --inexact -q 2>/dev/null; then
        if TOOLS=$(source_tools); then
            echo "   ✅ uv synced without pruning extras ($TOOLS tools)"
        else
            echo "   ⚠️ uv synced, but the local server failed to import"
        fi
        SYNCED=1
    else
        echo "   ⚠️ uv sync failed"
    fi
    echo ""
fi

if [ "$SYNCED" -eq 0 ] && [ -d ".venv" ]; then
    echo "📦 Checking existing .venv..."
    if TOOLS=$(source_tools); then
        echo "   ⚠️ uv unavailable; keeping existing .venv ($TOOLS tools)"
    else
        echo "   ⚠️ uv unavailable and the existing .venv cannot import the server"
    fi
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
        python3 - "$CONFIG" "$SCRIPT_DIR" > "$TMPFILE" 2>/dev/null <<'PY'
import json, os, sys
with open(sys.argv[1]) as f:
    cfg = json.load(f)
src = os.path.realpath(sys.argv[2])
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
                    with open(pyproject, encoding='utf-8') as source:
                        text = source.read()
                    ok = 'name = "onboard-memory-mcp"' in text or 'name = "swisspra-on_board"' in text
                if not ok and os.path.isfile(marker):
                    with open(marker, encoding='utf-8', errors='replace') as source:
                        text = source.read(2000)
                    ok = 'On Board' in text and 'onboard_memory_mcp' in text
                if ok:
                    print(dest)
PY
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

# ── Mandatory deployment payload ──
# Every deployed copy needs these to import and render; check them before the
# first destination file is overwritten so a broken source cannot half-deploy.
MANDATORY_FILES=(
    "server.py"
    "a2a_wait.py"
    "ticket_roles.py"
    "thrift_compress.py"
    "docs/assets/on-board-icon.png"
)

MISSING_MANDATORY=()
for rel in "${MANDATORY_FILES[@]}"; do
    [ -f "$SCRIPT_DIR/$rel" ] || MISSING_MANDATORY+=("$rel")
done

if [ ${#MISSING_MANDATORY[@]} -gt 0 ]; then
    echo "❌ Cannot deploy: mandatory file(s) missing from $SCRIPT_DIR"
    printf '   - %s\n' "${MISSING_MANDATORY[@]}"
    echo "   No destination was modified. Restore the missing file(s) and rerun."
    exit 1
fi

echo "🚀 Deploying to ${#TARGETS[@]} location(s)..."
echo ""

DEPLOY_FAILED=0

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
    copy_file_if_present "$SCRIPT_DIR/a2a_wait.py" "$DEST/a2a_wait.py"
    copy_file_if_present "$SCRIPT_DIR/ticket_roles.py" "$DEST/ticket_roles.py"
    copy_file_if_present "$SCRIPT_DIR/thrift_compress.py" "$DEST/thrift_compress.py"
    copy_file_if_present "$SCRIPT_DIR/pyproject.toml" "$DEST/pyproject.toml"
    copy_file_if_present "$SCRIPT_DIR/uv.lock" "$DEST/uv.lock"
    copy_file_if_present "$SCRIPT_DIR/dashboard_live.py" "$DEST/dashboard_live.py"
    copy_file_if_present "$SCRIPT_DIR/SKILL.md" "$DEST/SKILL.md"
    copy_file_if_present "$SCRIPT_DIR/AGENT_SETUP.md" "$DEST/AGENT_SETUP.md"
    copy_file_if_present "$SCRIPT_DIR/setup-project.sh" "$DEST/setup-project.sh"
    chmod +x "$DEST/setup-project.sh" 2>/dev/null || true
    copy_file_if_present "$SCRIPT_DIR/doctor.sh" "$DEST/doctor.sh"
    chmod +x "$DEST/doctor.sh" 2>/dev/null || true
    copy_file_if_present "$SCRIPT_DIR/onboard-server.sh" "$DEST/onboard-server.sh"
    chmod +x "$DEST/onboard-server.sh" 2>/dev/null || true
    copy_file_if_present "$SCRIPT_DIR/onboard_server.py" "$DEST/onboard_server.py"
    chmod +x "$DEST/onboard_server.py" 2>/dev/null || true
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
        copy_file_if_present "$SCRIPT_DIR/docs/assets/on-board-icon.png" "$DEST/docs/assets/on-board-icon.png"
    fi

    if command -v uv >/dev/null 2>&1; then
        (cd "$DEST" && uv sync --inexact -q) 2>/dev/null || true
    fi

    DEST_PYTHON=""
    for candidate in "$DEST/.venv/bin/python" "$DEST/.venv/Scripts/python.exe"; do
        if [ -x "$candidate" ]; then
            DEST_PYTHON="$candidate"
            break
        fi
    done

    if [ -z "$DEST_PYTHON" ]; then
        echo "   ⚠️ Source copied to $DEST, but runtime unavailable there — no usable Python in $DEST/.venv"
        echo "      uv sync did not provide one (uv missing or sync failed); nothing was installed globally."
        echo "      Finish it there with: cd \"$DEST\" && uv sync --inexact"
        echo "   ↩ Backup: $BACKUP_DIR"
        DEPLOY_FAILED=1
        continue
    fi

    if ! TOOLS=$(cd "$DEST" && "$DEST_PYTHON" - "$DEST" <<'PY' 2>&1
import asyncio
import sys

sys.path.insert(0, sys.argv[1])

from server import mcp

print(len(asyncio.run(mcp.list_tools())))
PY
); then
        echo "   ❌ Source copied to $DEST, but the server there failed to import:"
        printf '%s\n' "$TOOLS" | sed 's/^/      /'
        echo "   ↩ Backup: $BACKUP_DIR"
        DEPLOY_FAILED=1
        continue
    fi

    echo "   ✅ Updated ($TOOLS tools)"
    echo "   ↩ Backup: $BACKUP_DIR"
done

if [ "$DEPLOY_FAILED" -ne 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ Update finished with deployment errors — see the failed location(s) above."
    echo "   Files were copied, but at least one copy is not usable yet."
    exit 1
fi

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
