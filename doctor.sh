#!/bin/bash
# ─────────────────────────────────────────────────────────
# On Board — Setup Doctor
# Read-only check for one project setup.
# Usage: bash /path/to/On_Board/doctor.sh /path/to/project
# ─────────────────────────────────────────────────────────

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_FILE="${ONBOARD_REGISTRY_FILE:-$SCRIPT_DIR/.onboard/linked-projects.json}"
PROJECT_DIR="$(pwd)"
LIST_LINKED=0
ALL_LINKED=0
SELF_CHECK=0

if [ "${1:-}" != "" ] && [[ "${1:-}" != --* ]]; then
    PROJECT_DIR="$1"
    shift
fi

while [ "$#" -gt 0 ]; do
    case "$1" in
        --list-linked)
            LIST_LINKED=1
            shift
            ;;
        --all-linked)
            ALL_LINKED=1
            shift
            ;;
        --self)
            SELF_CHECK=1
            shift
            ;;
        *)
            echo "❌ Unknown option: $1"
            echo "Usage: bash doctor.sh /path/to/project"
            echo "       bash doctor.sh --list-linked"
            echo "       bash doctor.sh --all-linked"
            echo "       bash doctor.sh --self"
            exit 1
            ;;
    esac
done

OK=0
WARN=0
FAIL=0
MANUAL_FAIL=0
SETUP_FAIL=0
MANUAL_ACTIONS=()

pass() {
    OK=$((OK + 1))
    echo "✅ $1"
}

warn() {
    WARN=$((WARN + 1))
    echo "⚠️  $1"
}

fail() {
    FAIL=$((FAIL + 1))
    SETUP_FAIL=$((SETUP_FAIL + 1))
    echo "❌ $1"
}

fail_manual() {
    FAIL=$((FAIL + 1))
    MANUAL_FAIL=$((MANUAL_FAIL + 1))
    echo "❌ $1"
}

add_manual_action() {
    MANUAL_ACTIONS+=("$1")
}

check_file() {
    local path="$1"
    local label="$2"
    if [ -f "$path" ]; then
        pass "$label"
    else
        fail "$label missing: $path"
    fi
}

check_executable() {
    local path="$1"
    local label="$2"
    if [ -x "$path" ]; then
        pass "$label"
    else
        fail "$label missing or not executable: $path"
    fi
}

check_optional_file() {
    local path="$1"
    local label="$2"
    if [ -f "$path" ]; then
        pass "$label"
    else
        warn "$label not found: $path"
    fi
}

self_check_path_absent() {
    local path="$1"
    local label="$2"
    if [ -e "$path" ]; then
        fail "$label should not exist in the public source repo: $path"
    else
        pass "$label absent"
    fi
}

self_check_tracked_absent() {
    local path="$1"
    local label="$2"
    if git -C "$SCRIPT_DIR" ls-files --deleted --error-unmatch "$path" >/dev/null 2>&1; then
        pass "$label scheduled for removal"
        return
    fi
    if git -C "$SCRIPT_DIR" ls-files --error-unmatch "$path" >/dev/null 2>&1; then
        fail "$label is still tracked: $path"
    else
        pass "$label not tracked"
    fi
}

find_onboard_python() {
    if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
        printf "%s\n" "$SCRIPT_DIR/.venv/bin/python"
    elif [ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]; then
        printf "%s\n" "$SCRIPT_DIR/.venv/Scripts/python.exe"
    else
        printf "%s\n" "$SCRIPT_DIR/.venv/bin/python"
    fi
}

find_onboard_launcher() {
    printf "%s\n" "$SCRIPT_DIR/onboard-server.sh"
}

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

if [ "$LIST_LINKED" -eq 1 ]; then
    echo "Linked On Board projects:"
    LINKED="$(list_linked_projects)"
    if [ -n "$LINKED" ]; then
        printf '%s\n' "$LINKED"
    else
        echo "  (none)"
    fi
    exit 0
fi

if [ "$SELF_CHECK" -eq 1 ]; then
    echo "🩺 On Board Source Doctor"
    echo "On Board: $SCRIPT_DIR"
    echo ""
    echo "Public Source Hygiene"
    for rel in \
        ".agent-mem" \
        ".agent-mem-hooks" \
        ".codex" \
        ".cursor" \
        ".claude" \
        ".agent" \
        "AGENTS.md" \
        "CLAUDE.md" \
        ".cursorrules"; do
        self_check_path_absent "$SCRIPT_DIR/$rel" "$rel"
    done
    for rel in \
        "hooks/claude-code-stop.sh" \
        "hooks/codex-stop.sh" \
        "hooks/cursor-session-end.sh"; do
        self_check_path_absent "$SCRIPT_DIR/$rel" "$rel"
        self_check_tracked_absent "$rel" "$rel"
    done
    echo ""
    echo "Local Runtime"
    if [ -d "$SCRIPT_DIR/.onboard" ]; then
        warn ".onboard exists; this is local linked-project registry data and must stay gitignored"
    else
        pass ".onboard absent"
    fi
    if [ -d "$SCRIPT_DIR/.venv" ]; then
        pass ".venv exists"
    else
        warn ".venv missing; run uv sync --inexact before local MCP use"
    fi

    echo ""
    echo "Summary: $OK passed, $WARN warnings, $FAIL failed"
    [ "$FAIL" -eq 0 ] || exit 1
    exit 0
fi

if [ "$ALL_LINKED" -eq 1 ]; then
    LINKED="$(list_linked_projects)"
    if [ -z "$LINKED" ]; then
        echo "No linked projects registered yet."
        exit 0
    fi
    RESULT=0
    while IFS= read -r linked_project; do
        [ -n "$linked_project" ] || continue
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Checking linked project: $linked_project"
        if ! bash "$SCRIPT_DIR/doctor.sh" "$linked_project"; then
            RESULT=1
        fi
    done <<< "$LINKED"
    exit "$RESULT"
fi

echo "🩺 On Board Doctor"
echo "On Board: $SCRIPT_DIR"

if [ ! -d "$PROJECT_DIR" ]; then
    fail "Project directory not found: $PROJECT_DIR"
    echo ""
    echo "Result: FAIL"
    exit 1
fi

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
ONBOARD_PY="$(find_onboard_python)"
ONBOARD_LAUNCHER="$(find_onboard_launcher)"

echo "Project: $PROJECT_DIR"
echo ""

echo "Runtime"
check_executable "$ONBOARD_PY" "On Board Python: $ONBOARD_PY"
check_executable "$ONBOARD_LAUNCHER" "On Board launcher: $ONBOARD_LAUNCHER"
check_file "$SCRIPT_DIR/server.py" "On Board server.py"

TOOLS=$(PYTHONPATH="$SCRIPT_DIR" "$ONBOARD_PY" -c "
from server import mcp
print(len(mcp._tool_manager._tools))
" 2>/dev/null)
if [ -n "$TOOLS" ]; then
    pass "Server import OK ($TOOLS tools)"
else
    fail "Server import failed"
fi

echo ""
echo "Existing Memory Migration"
if [ -d "$PROJECT_DIR/.agent-mem" ]; then
    pass ".agent-mem exists"
    if [ -f "$PROJECT_DIR/.onboard/migration-report.json" ]; then
        if MIGRATION_CHECK=$(python3 - "$PROJECT_DIR/.onboard/migration-report.json" <<'PY' 2>&1
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("existing_memory_detected") and not report.get("core_unchanged"):
    print("BAD: existing memory changed during setup")
    raise SystemExit(1)
print("OK")
PY
        ); then
            pass ".onboard/migration-report.json memory unchanged"
        else
            fail ".onboard/migration-report.json reports unsafe migration: $MIGRATION_CHECK"
        fi
    elif [ ! -f "$PROJECT_DIR/.onboard/mcp.generated.json" ]; then
        warn "Existing .agent-mem detected without new setup wrapper; run setup-project.sh to add local config without changing memory"
    else
        warn ".onboard/migration-report.json missing; rerun setup-project.sh to record migration proof"
    fi
else
    warn ".agent-mem does not exist yet. Ask your agent to call memory_bootstrap or memory_init."
fi

echo ""
echo "Generated MCP Config"
MCP_JSON="$PROJECT_DIR/.onboard/mcp.json"
GENERATED_MCP_JSON="$PROJECT_DIR/.onboard/mcp.generated.json"
SETTINGS_JSON="$PROJECT_DIR/.onboard/settings.json"
HOOK_MODE="safe"
check_file "$GENERATED_MCP_JSON" ".onboard/mcp.generated.json"
check_file "$PROJECT_DIR/.onboard/AGENT_CONTROL.md" ".onboard/AGENT_CONTROL.md"
check_executable "$PROJECT_DIR/.onboard/run-dashboard.sh" ".onboard/run-dashboard.sh"
if [ -d "$PROJECT_DIR/.agent-mem" ]; then
    check_file "$PROJECT_DIR/.onboard/migration-report.json" ".onboard/migration-report.json"
fi
if [ -f "$SETTINGS_JSON" ]; then
    HOOK_MODE="$(python3 - "$SETTINGS_JSON" <<'PY' 2>/dev/null || echo safe
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data.get("hook_mode") or "safe")
PY
)"
    pass ".onboard/settings.json hook_mode=$HOOK_MODE"
else
    warn ".onboard/settings.json not found; assuming hook_mode=safe"
fi
if [ -f "$MCP_JSON" ]; then
    pass ".onboard/mcp.json"
else
    warn ".onboard/mcp.json not found; use .onboard/mcp.generated.json as the fresh generated config"
    MCP_JSON="$GENERATED_MCP_JSON"
fi

if [ -f "$MCP_JSON" ] && [ -x "$ONBOARD_PY" ]; then
    if CONFIG_CHECK=$(PYTHONPATH="$SCRIPT_DIR" "$ONBOARD_PY" - "$MCP_JSON" "$SCRIPT_DIR" "$PROJECT_DIR" "$ONBOARD_PY" "$ONBOARD_LAUNCHER" <<'PY' 2>&1
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
onboard = Path(sys.argv[2])
project = Path(sys.argv[3])
python = Path(sys.argv[4])
launcher = Path(sys.argv[5])

cfg = json.loads(config_path.read_text(encoding="utf-8"))
srv = cfg["mcpServers"]["agent-memory"]

command = srv.get("command")
args = srv.get("args")
if command == str(launcher):
    command_ok = True
    args_ok = args in (None, [])
elif command == str(python):
    command_ok = True
    args_ok = args == [str(onboard / "server.py")]
else:
    command_ok = False
    args_ok = False

checks = [
    ("command", command_ok, command),
    ("args", args_ok, args),
    ("AGENT_PROJECT_DIR", srv.get("env", {}).get("AGENT_PROJECT_DIR") == str(project), srv.get("env", {}).get("AGENT_PROJECT_DIR")),
]

for name, ok, actual in checks:
    print(f"{name}=OK" if ok else f"{name}=BAD:{actual}")
PY
    ); then
        while IFS= read -r line; do
            case "$line" in
                *=OK) pass "MCP config $line" ;;
                AGENT_PROJECT_DIR=BAD:*)
                    fail_manual "MCP config $line"
                    add_manual_action "Fix AGENT_PROJECT_DIR in $MCP_JSON, or replace it with $GENERATED_MCP_JSON if this project should use the generated config."
                    ;;
                *=BAD:*)
                    fail_manual "MCP config $line"
                    add_manual_action "Review $MCP_JSON against $GENERATED_MCP_JSON. setup-project.sh will not overwrite an existing primary MCP config."
                    ;;
                *) [ -n "$line" ] && warn "MCP config check: $line" ;;
            esac
        done <<< "$CONFIG_CHECK"
    else
        fail "MCP config is invalid: $MCP_JSON"
        [ -n "$CONFIG_CHECK" ] && echo "$CONFIG_CHECK"
    fi
fi

echo ""
echo "Project Rules And Hooks"
check_file "$PROJECT_DIR/AGENTS.md" "Codex rules AGENTS.md"
check_file "$PROJECT_DIR/CLAUDE.md" "Claude rules CLAUDE.md"
check_file "$PROJECT_DIR/.cursorrules" "Cursor legacy rules .cursorrules"
check_file "$PROJECT_DIR/.agent/rules/on-board-agent-memory.md" "AntiGravity workspace rule"
if [ "$HOOK_MODE" = "off" ]; then
    warn "Hook mode is off; startup hook files are optional"
else
    check_file "$PROJECT_DIR/.cursor/hooks.json" "Cursor hooks config"
    check_file "$PROJECT_DIR/.claude/settings.json" "Claude Code hooks config"
    check_file "$PROJECT_DIR/.codex/hooks.json" "Codex hooks config"
fi
for hook_config in \
    "$PROJECT_DIR/.cursor/hooks.json" \
    "$PROJECT_DIR/.claude/settings.json" \
    "$PROJECT_DIR/.codex/hooks.json"; do
    if [ -f "$hook_config" ]; then
        if python3 - "$hook_config" <<'PY'
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

hooks = data.get("hooks", {})
if isinstance(hooks, dict) and any(key in hooks for key in ("Stop", "stop")):
    raise SystemExit(1)
raise SystemExit(0)
PY
        then
            :
        else
            fail_manual "Turn-scoped Stop hook is still configured: $hook_config"
            add_manual_action "Remove the Stop/stop hook block from $hook_config, or merge the current template from $SCRIPT_DIR/configs/."
        fi
    fi
done
if [ "$HOOK_MODE" != "off" ]; then
    check_executable "$PROJECT_DIR/.agent-mem-hooks/cursor-session-start.sh" "Cursor session-start hook"
    check_executable "$PROJECT_DIR/.agent-mem-hooks/claude-code-session-start.sh" "Claude Code session-start hook"
    check_executable "$PROJECT_DIR/.agent-mem-hooks/onboard-mini-brief.py" "Shared startup mini-brief helper"
    check_executable "$PROJECT_DIR/.codex/hooks/codex-session-start.sh" "Codex session-start hook"
    check_executable "$PROJECT_DIR/.codex/hooks/onboard-mini-brief.py" "Codex startup mini-brief helper"
fi
for legacy_stop in \
    "$PROJECT_DIR/.agent-mem-hooks/cursor-session-end.sh" \
    "$PROJECT_DIR/.agent-mem-hooks/claude-code-stop.sh" \
    "$PROJECT_DIR/.codex/hooks/codex-stop.sh"; do
    if [ -f "$legacy_stop" ]; then
        warn "Legacy On Board stop hook file remains: $legacy_stop"
    fi
done
check_optional_file "$PROJECT_DIR/.claude/skills/agent-memory/SKILL.md" "Claude Code agent-memory skill"

echo ""
echo "Git Ignore"
GITIGNORE="$PROJECT_DIR/.gitignore"
check_file "$GITIGNORE" ".gitignore"
if [ -f "$GITIGNORE" ]; then
    for entry in \
        ".agent-mem/" \
        ".onboard/" \
        ".agent-mem-hooks/" \
        ".codex/" \
        ".cursor/" \
        ".claude/" \
        ".agent/" \
        "AGENTS.md" \
        "CLAUDE.md" \
        ".cursorrules"; do
        if grep -qF "$entry" "$GITIGNORE"; then
            pass ".gitignore contains $entry"
        else
            fail ".gitignore missing $entry"
        fi
    done
fi

echo ""
echo "Summary: $OK passed, $WARN warnings, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Next:"
    if [ "$MANUAL_FAIL" -gt 0 ]; then
        echo "  Manual cleanup is required for existing custom files. Do not rerun setup-project.sh for these failures; it will not overwrite them."
        if [ "${#MANUAL_ACTIONS[@]}" -gt 0 ]; then
            for action in "${MANUAL_ACTIONS[@]}"; do
                echo "  - $action"
            done
        fi
        echo ""
        echo "  Agent-assisted fix:"
        echo "  Ask your agent to review this doctor output, fix only the listed On Board config/hook issues,"
        echo "  do not rerun setup-project.sh for these manual failures, do not change .agent-mem/, then rerun:"
    fi
    if [ "$SETUP_FAIL" -gt 0 ]; then
        echo "  After manual cleanup, rerun setup if generated files are still missing:"
        echo "  bash \"$SCRIPT_DIR/setup-project.sh\" \"$PROJECT_DIR\""
    fi
    echo "  bash \"$SCRIPT_DIR/doctor.sh\" \"$PROJECT_DIR\""
    exit 1
fi

echo ""
echo "Next:"
if [ ! -d "$PROJECT_DIR/.agent-mem" ]; then
    echo "  Add $PROJECT_DIR/.onboard/mcp.generated.json to your MCP client, restart it, then ask:"
    echo "  Call memory_bootstrap for this project, then memory_onboard."
else
    echo "  Setup looks usable. In the agent, run memory_doctor for runtime memory checks."
fi

if [ "$WARN" -gt 0 ]; then
    exit 0
fi

exit 0
