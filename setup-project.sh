#!/bin/bash
# ─────────────────────────────────────────────────────────
# On Board — Project Setup Script
# Prepare one project to use this central On Board checkout.
# Usage: bash /path/to/On_Board/setup-project.sh /path/to/project
# ─────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_FILE="${ONBOARD_REGISTRY_FILE:-$SCRIPT_DIR/.onboard/linked-projects.json}"
if [ "${1:-}" != "" ] && [[ "${1:-}" != --* ]]; then
    PROJECT_DIR="$1"
    shift
else
    PROJECT_DIR="$(pwd)"
fi
HOOK_MODE="${ONBOARD_HOOK_MODE:-safe}"
HOOK_MODE_EXPLICIT=0
LIST_LINKED=0
ALL_LINKED=0

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
        --hooks)
            if [ "$#" -lt 2 ]; then
                echo "❌ --hooks requires one of: off, safe, guard, lifeline"
                exit 1
            fi
            HOOK_MODE="$2"
            HOOK_MODE_EXPLICIT=1
            shift 2
            ;;
        --hooks=*)
            HOOK_MODE="${1#--hooks=}"
            HOOK_MODE_EXPLICIT=1
            shift
            ;;
        --show-hooks)
            HOOK_MODE="__show__"
            shift
            ;;
        *)
            echo "❌ Unknown option: $1"
            echo "Usage: bash setup-project.sh /path/to/project [--hooks off|safe]"
            echo "       bash setup-project.sh --list-linked"
            echo "       bash setup-project.sh --all-linked [--hooks off|safe]"
            exit 1
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

case "$HOOK_MODE" in
    off|safe|__show__)
        ;;
    guard|lifeline)
        echo "❌ Hook mode '$HOOK_MODE' is planned but not implemented yet."
        echo "Use '--hooks safe' or '--hooks off' for now."
        exit 1
        ;;
    *)
        echo "❌ Unknown hook mode: $HOOK_MODE"
        echo "Available now: off, safe"
        echo "Planned: guard, lifeline"
        exit 1
        ;;
esac

if [ "$ALL_LINKED" -eq 1 ]; then
    LINKED="$(list_linked_project_records)"
    if [ -z "$LINKED" ]; then
        echo "No linked projects registered yet."
        exit 0
    fi
    while IFS=$'\t' read -r linked_project linked_hook_mode; do
        [ -n "$linked_project" ] || continue
        if [ "$HOOK_MODE_EXPLICIT" -eq 1 ]; then
            linked_hook_mode="$HOOK_MODE"
        else
            linked_hook_mode="${linked_hook_mode:-safe}"
        fi
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Refreshing linked project: $linked_project"
        bash "$SCRIPT_DIR/setup-project.sh" "$linked_project" --hooks "$linked_hook_mode"
    done <<< "$LINKED"
    exit 0
fi

if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Project directory not found: $PROJECT_DIR"
    exit 1
fi

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
MIGRATION_SNAPSHOT="$(mktemp)"
trap 'rm -f "$MIGRATION_SNAPSHOT"' EXIT

find_onboard_python() {
    if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
        printf "%s\n" "$SCRIPT_DIR/.venv/bin/python"
    elif [ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]; then
        printf "%s\n" "$SCRIPT_DIR/.venv/Scripts/python.exe"
    else
        printf "%s\n" "$SCRIPT_DIR/.venv/bin/python"
    fi
}

ONBOARD_PY="$(find_onboard_python)"
ONBOARD_SERVER="$SCRIPT_DIR/onboard-server.sh"
ONBOARD_PY_LAUNCHER="$SCRIPT_DIR/onboard_server.py"

python3 - "$PROJECT_DIR" "$MIGRATION_SNAPSHOT" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

project = Path(sys.argv[1])
out = Path(sys.argv[2])
mem = project / ".agent-mem"
core = [
    "project.json",
    "agents.json",
    "memories.json",
    "state.json",
    "tickets/_index.json",
]

def digest_file(path: Path):
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def snapshot():
    files = []
    total_bytes = 0
    if mem.exists():
        for root, dirs, names in os.walk(mem):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in names:
                path = Path(root) / name
                if not path.is_file():
                    continue
                rel = path.relative_to(mem).as_posix()
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                files.append(rel)
                total_bytes += size
    return {
        "exists": mem.exists(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "core_sha256": {item: digest_file(mem / item) for item in core},
    }

out.write_text(json.dumps(snapshot(), indent=2) + "\n", encoding="utf-8")
PY

echo "🧠 On Board — Project Setup"
echo "On Board: $SCRIPT_DIR"
echo "Project: $PROJECT_DIR"
if [ "$HOOK_MODE" != "__show__" ]; then
    echo "Hook mode: $HOOK_MODE"
fi
if [ -d "$PROJECT_DIR/.agent-mem" ]; then
    echo "Existing memory: detected — setup will not write or migrate .agent-mem/"
else
    echo "Existing memory: none yet"
fi
echo ""

if [ "$HOOK_MODE" = "__show__" ]; then
    SETTINGS_FILE="$PROJECT_DIR/.onboard/settings.json"
    CURRENT="unknown"
    if [ -f "$SETTINGS_FILE" ]; then
        CURRENT="$(python3 - "$SETTINGS_FILE" <<'PY' 2>/dev/null || echo unknown
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("hook_mode", "unknown"))
PY
)"
    fi
    echo "Current hook mode: $CURRENT"
    echo "Available now: off, safe"
    echo "Planned: guard, lifeline"
    echo "Change:"
    echo "  bash \"$SCRIPT_DIR/setup-project.sh\" \"$PROJECT_DIR\" --hooks safe"
    echo "  bash \"$SCRIPT_DIR/setup-project.sh\" \"$PROJECT_DIR\" --hooks off"
    exit 0
fi

is_same_file() {
    local left="$1"
    local right="$2"
    [ -f "$left" ] && [ -f "$right" ] && cmp -s "$left" "$right"
}

# ── 1. Prepare the central On Board runtime ──
if command -v uv >/dev/null 2>&1; then
    echo "📦 Syncing On Board runtime..."
    UV_SYNC_LOG="$(mktemp)"
    if (cd "$SCRIPT_DIR" && uv sync --inexact -q >"$UV_SYNC_LOG" 2>&1); then
        ONBOARD_PY="$(find_onboard_python)"
        echo "✅ Runtime ready at $ONBOARD_PY"
    elif [ -x "$ONBOARD_PY" ]; then
        echo "⚠️  uv sync failed — using existing runtime at $ONBOARD_PY"
    else
        echo "❌ uv sync failed and no existing .venv was found."
        cat "$UV_SYNC_LOG"
        echo "Try:"
        echo "  cd \"$SCRIPT_DIR\" && uv sync --inexact"
        rm -f "$UV_SYNC_LOG"
        exit 1
    fi
    rm -f "$UV_SYNC_LOG"
elif [ ! -x "$ONBOARD_PY" ]; then
    echo "❌ uv is not installed and no existing .venv was found."
    echo "Install uv, then rerun:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  bash \"$SCRIPT_DIR/setup-project.sh\" \"$PROJECT_DIR\""
    exit 1
else
    echo "⚠️  uv not found — using existing .venv"
fi

if TOOLS=$(PYTHONPATH="$SCRIPT_DIR" "$ONBOARD_PY" -c "
from server import mcp
print(len(mcp._tool_manager._tools))
" 2>/dev/null); then
    echo "✅ On Board server import OK ($TOOLS tools)"
else
    echo "❌ On Board server import failed"
    echo "Try:"
    echo "  cd \"$SCRIPT_DIR\" && uv sync --inexact"
    exit 1
fi
echo ""

# ── 2. Create hook directories in project ──
HOOKS_DIR="$PROJECT_DIR/.agent-mem-hooks"
if [ "$HOOK_MODE" = "safe" ]; then
    mkdir -p "$HOOKS_DIR"

    cp "$SCRIPT_DIR/hooks/cursor-session-start.sh" "$HOOKS_DIR/"
    cp "$SCRIPT_DIR/hooks/claude-code-session-start.sh" "$HOOKS_DIR/"
    cp "$SCRIPT_DIR/hooks/onboard-mini-brief.py" "$HOOKS_DIR/"

    chmod +x "$HOOKS_DIR"/*.sh "$HOOKS_DIR"/*.py

    echo "✅ Hooks copied to .agent-mem-hooks/"
else
    mkdir -p "$HOOKS_DIR"
    rm -f "$HOOKS_DIR/cursor-session-start.sh" "$HOOKS_DIR/claude-code-session-start.sh" "$HOOKS_DIR/onboard-mini-brief.py"
    rm -f "$HOOKS_DIR/cursor-session-end.sh" "$HOOKS_DIR/claude-code-stop.sh"
    echo "✅ On Board project hooks disabled"
fi

CODEX_DIR="$PROJECT_DIR/.codex"
CODEX_HOOKS_DIR="$CODEX_DIR/hooks"
if [ "$HOOK_MODE" = "safe" ]; then
    mkdir -p "$CODEX_HOOKS_DIR"

    cp "$SCRIPT_DIR/hooks/codex-session-start.sh" "$CODEX_HOOKS_DIR/"
    cp "$SCRIPT_DIR/hooks/onboard-mini-brief.py" "$CODEX_HOOKS_DIR/"

    chmod +x "$CODEX_HOOKS_DIR"/*.sh "$CODEX_HOOKS_DIR"/*.py

    echo "✅ Codex hooks copied to .codex/hooks/"
else
    mkdir -p "$CODEX_HOOKS_DIR"
    rm -f "$CODEX_HOOKS_DIR/codex-session-start.sh" "$CODEX_HOOKS_DIR/onboard-mini-brief.py" "$CODEX_HOOKS_DIR/codex-stop.sh"
    echo "✅ On Board Codex hooks disabled"
fi

# ── 2b. Copy SKILL.md to Claude Code skills ──
SKILL_DIR="$PROJECT_DIR/.claude/skills/agent-memory"
mkdir -p "$SKILL_DIR"
if [ -f "$SCRIPT_DIR/SKILL.md" ]; then
    cp "$SCRIPT_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
    echo "✅ SKILL.md copied to .claude/skills/agent-memory/"
fi

# ── 3. Set up Cursor hooks ──
CURSOR_DIR="$PROJECT_DIR/.cursor"
mkdir -p "$CURSOR_DIR"

if [ -f "$CURSOR_DIR/hooks.json" ] && ! is_same_file "$CURSOR_DIR/hooks.json" "$SCRIPT_DIR/configs/cursor-hooks.json"; then
    echo "⚠️  .cursor/hooks.json exists — please merge manually:"
    echo "    See: $SCRIPT_DIR/configs/cursor-hooks.json"
    echo "    Remove old stop/end-turn hooks if present; On Board no longer writes memory from Stop hooks."
else
    if [ "$HOOK_MODE" = "safe" ]; then
        cp "$SCRIPT_DIR/configs/cursor-hooks.json" "$CURSOR_DIR/hooks.json"
        echo "✅ Cursor hooks configured at .cursor/hooks.json"
    else
        rm -f "$CURSOR_DIR/hooks.json"
        echo "✅ Cursor hooks disabled"
    fi
fi

# ── 4. Set up Claude Code hooks ──
CLAUDE_DIR="$PROJECT_DIR/.claude"
mkdir -p "$CLAUDE_DIR"

if [ -f "$CLAUDE_DIR/settings.json" ] && ! is_same_file "$CLAUDE_DIR/settings.json" "$SCRIPT_DIR/configs/claude-code-settings.json"; then
    echo "⚠️  .claude/settings.json exists — please merge hooks manually:"
    echo "    See: $SCRIPT_DIR/configs/claude-code-settings.json"
    echo "    Remove old Stop hooks if present; On Board no longer writes memory from Stop hooks."
else
    if [ "$HOOK_MODE" = "safe" ]; then
        cp "$SCRIPT_DIR/configs/claude-code-settings.json" "$CLAUDE_DIR/settings.json"
        echo "✅ Claude Code hooks configured at .claude/settings.json"
    else
        rm -f "$CLAUDE_DIR/settings.json"
        echo "✅ Claude Code hooks disabled"
    fi
fi

# ── 4b. Set up Codex hooks ──
if [ -f "$CODEX_DIR/hooks.json" ] && ! is_same_file "$CODEX_DIR/hooks.json" "$SCRIPT_DIR/configs/codex-hooks.json"; then
    echo "⚠️  .codex/hooks.json exists — please merge hooks manually:"
    echo "    See: $SCRIPT_DIR/configs/codex-hooks.json"
    echo "    Remove old Stop hooks if present; On Board no longer writes memory from Stop hooks."
else
    if [ "$HOOK_MODE" = "safe" ]; then
        cp "$SCRIPT_DIR/configs/codex-hooks.json" "$CODEX_DIR/hooks.json"
        echo "✅ Codex hooks configured at .codex/hooks.json"
    else
        rm -f "$CODEX_DIR/hooks.json"
        echo "✅ Codex hooks disabled"
    fi
fi

# ── 5. Update .gitignore ──
GITIGNORE="$PROJECT_DIR/.gitignore"
if [ -f "$GITIGNORE" ]; then
    if ! grep -qF ".agent-mem/" "$GITIGNORE"; then
        echo "" >> "$GITIGNORE"
        echo "# Agent shared memory (runtime data)" >> "$GITIGNORE"
        echo ".agent-mem/" >> "$GITIGNORE"
        echo "✅ Added .agent-mem/ to .gitignore"
    fi
    for ENTRY in \
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
        if ! grep -qF "$ENTRY" "$GITIGNORE"; then
            echo "$ENTRY" >> "$GITIGNORE"
            echo "✅ Added $ENTRY to .gitignore"
        fi
    done
else
    cat > "$GITIGNORE" <<'EOF'
.agent-mem/
.onboard/
.agent-mem-hooks/
.codex/
.cursor/
.claude/
.agent/
AGENTS.md
CLAUDE.md
.cursorrules
EOF
    echo "✅ Created .gitignore with On Board runtime files"
fi

# ── 6. Create CLAUDE.md / .cursorrules / AGENTS.md reminder ──
RULES_TEMPLATE="$SCRIPT_DIR/templates/agent-rules.md"
if [ -f "$RULES_TEMPLATE" ]; then
    RULES_NOTE="$(cat "$RULES_TEMPLATE")"
else
    RULES_NOTE="# On Board — Agent Shared Memory Protocol

This project uses .agent-mem/ for multi-agent coordination.

<on_board_protocol>
  <required_first_call>memory_onboard</required_first_call>
  <agent_identity>Use a stable agent_name. Do not include dates, model names, or session ids.</agent_identity>
  <write_policy>Write after meaningful actions only.</write_policy>
  <ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>
  <handoff_policy>Always handoff before leaving.</handoff_policy>
</on_board_protocol>

Get On Board before starting any work:
1. Call memory_onboard with your stable agent_name and platform
2. Call memory_write after every significant action
3. Call memory_checkpoint every 10-15 minutes
4. Call memory_handoff before you finish

If memory_onboard is not available, call memory_get_briefing first, then memory_agent_join.
"
fi

if [ ! -f "$PROJECT_DIR/CLAUDE.md" ]; then
    printf "%s\n" "$RULES_NOTE" > "$PROJECT_DIR/CLAUDE.md"
    echo "✅ Created CLAUDE.md with agent memory protocol"
fi

if [ ! -f "$PROJECT_DIR/.cursorrules" ]; then
    printf "%s\n" "$RULES_NOTE" > "$PROJECT_DIR/.cursorrules"
    echo "✅ Created .cursorrules with agent memory protocol"
fi

if [ -f "$PROJECT_DIR/AGENTS.md" ]; then
    echo "⚠️  AGENTS.md exists — please merge Codex instructions manually"
else
    printf "%s\n" "$RULES_NOTE" > "$PROJECT_DIR/AGENTS.md"
    echo "✅ Created AGENTS.md with agent memory protocol"
fi

ANTIGRAVITY_RULES_DIR="$PROJECT_DIR/.agent/rules"
ANTIGRAVITY_RULE_FILE="$ANTIGRAVITY_RULES_DIR/on-board-agent-memory.md"
mkdir -p "$ANTIGRAVITY_RULES_DIR"

if [ -f "$ANTIGRAVITY_RULE_FILE" ]; then
    echo "⚠️  .agent/rules/on-board-agent-memory.md exists — please merge AntiGravity rules manually"
else
    printf "%s\n" "$RULES_NOTE" > "$ANTIGRAVITY_RULE_FILE"
    echo "✅ Created .agent/rules/on-board-agent-memory.md for AntiGravity"
fi

# ── 7. Generate local MCP config with real paths ──
ONBOARD_DIR="$PROJECT_DIR/.onboard"
mkdir -p "$ONBOARD_DIR"

"$ONBOARD_PY" - "$SCRIPT_DIR" "$PROJECT_DIR" "$ONBOARD_DIR" "$ONBOARD_PY" "$ONBOARD_SERVER" "$ONBOARD_PY_LAUNCHER" "$HOOK_MODE" <<'PY'
import json
import shlex
import sys
from pathlib import Path

onboard = Path(sys.argv[1]).resolve()
project = Path(sys.argv[2]).resolve()
out_dir = Path(sys.argv[3]).resolve()
python = Path(sys.argv[4])
shell_launcher = Path(sys.argv[5])
python_launcher = Path(sys.argv[6])
hook_mode = sys.argv[7]

server = {
    "command": "python3",
    "args": [str(python_launcher)],
    "env": {
        "AGENT_PROJECT_DIR": str(project)
    }
}

config = {"mcpServers": {"agent-memory": server}}
payload = json.dumps(config, indent=2) + "\n"

(out_dir / "mcp.generated.json").write_text(payload, encoding="utf-8")

(out_dir / "settings.json").write_text(json.dumps({
    "hook_mode": hook_mode,
    "implemented_hook_modes": ["off", "safe"],
    "planned_hook_modes": ["guard", "lifeline"],
    "onboard_dir": str(onboard),
    "project_dir": str(project),
}, indent=2) + "\n", encoding="utf-8")

primary = out_dir / "mcp.json"
if not primary.exists():
    primary.write_text(payload, encoding="utf-8")
    primary_status = "created"
else:
    primary_status = "kept existing"

has_existing_memory = (project / ".agent-mem").exists()
if has_existing_memory:
    agent_next_step = "Call memory_onboard for this project, then memory_doctor."
    client_next_step = (
        "If your MCP client already works for this project, no client config change is required now. "
        "Use mcp.generated.json only when adding a new client or migrating old config."
    )
else:
    agent_next_step = "Call memory_bootstrap for this project, then memory_onboard."
    client_next_step = "Add mcp.generated.json to your MCP client, then restart it."

(out_dir / "README.md").write_text(f"""# On Board MCP config

This folder was generated by `setup-project.sh`.

Use `mcp.generated.json` as the fresh generated config.

`mcp.json` status: {primary_status}

If you customize `mcp.json`, rerunning setup will not overwrite it.

On Board is installed once at:

```text
{onboard}
```

Runtime launcher:

```text
python3 {python_launcher}
```

Cached runtime Python:

```text
{python}
```

This project memory is selected by:

```text
AGENT_PROJECT_DIR={project}
```

If this project already had `.agent-mem/`, setup verified the core memory files
before and after writing local setup files. The report is:

```text
{out_dir / "migration-report.json"}
```

Client config:

```text
{client_next_step}
```

Agent next step:

```text
{agent_next_step}
```

Do not commit this folder. It contains local machine paths.
""", encoding="utf-8")

(out_dir / "AGENT_CONTROL.md").write_text(f"""# On Board agent control

This file tells agents how to inspect or change the local On Board setup for
this project.

Do not hand-edit generated hook config unless the user explicitly asks. Prefer
rerunning the central setup script.

## Paths

On Board checkout:

```text
{onboard}
```

Project:

```text
{project}
```

Generated MCP config:

```text
{out_dir / "mcp.generated.json"}
```

Primary local MCP config, if customized:

```text
{out_dir / "mcp.json"}
```

	Dashboard launcher:

```text
	{out_dir / "run-dashboard.sh"}
	```

	## Client config

	{client_next_step}

	Use this generated config when needed:

	```text
	{out_dir / "mcp.generated.json"}
	```

	## Agent next step

	```text
	{agent_next_step}
	```

Migration report for existing `.agent-mem/`:

```text
{out_dir / "migration-report.json"}
```

## Inspect setup

```bash
bash {shlex.quote(str(onboard / "doctor.sh"))} {shlex.quote(str(project))}
```

## Linked projects known to this On Board checkout

```bash
bash {shlex.quote(str(onboard / "setup-project.sh"))} --list-linked
bash {shlex.quote(str(onboard / "doctor.sh"))} --list-linked
```

Refresh all linked projects after updating On Board:

```bash
bash {shlex.quote(str(onboard / "update.sh"))} --refresh-linked
```

## Regenerate project setup

```bash
bash {shlex.quote(str(onboard / "setup-project.sh"))} {shlex.quote(str(project))}
```

## Hook modes

Current hook mode: `{hook_mode}`

Supported modes now:

- `off`: no On Board hooks
- `safe`: startup mini brief only

Planned modes:

- `guard`: safe plus protocol guard hooks where the client supports them
- `lifeline`: guard plus emergency handoff hooks for compaction/session end

Change hook mode with:

```bash
bash {shlex.quote(str(onboard / "setup-project.sh"))} {shlex.quote(str(project))} --hooks safe
bash {shlex.quote(str(onboard / "setup-project.sh"))} {shlex.quote(str(project))} --hooks off
```

`guard` and `lifeline` are planned but not implemented yet.

## Rules for agents

- Ask the user before changing hook mode.
- Prefer `safe` unless the user asks for stronger automation.
- Use `guard` when the user wants protocol enforcement.
- Use `lifeline` only when the user accepts automatic emergency memory writes.
- Do not edit global Claude, Cursor, Codex, Windsurf, VS Code, or AntiGravity
  config files unless the user explicitly asks.
""", encoding="utf-8")

dashboard = out_dir / "run-dashboard.sh"
dashboard.write_text(f"""#!/bin/bash
# Launch On Board dashboard for this project.
exec bash {shlex.quote(str(onboard / 'run-dashboard.sh'))} {shlex.quote(str(project))} "$@"
""", encoding="utf-8")
dashboard.chmod(0o755)
PY

echo "✅ Generated MCP config at .onboard/mcp.generated.json"
echo "✅ Generated agent control guide at .onboard/AGENT_CONTROL.md"
echo "✅ Generated dashboard launcher at .onboard/run-dashboard.sh"
if [ -f "$PROJECT_DIR/.onboard/mcp.json" ]; then
    echo "ℹ️  Primary config available at .onboard/mcp.json"
fi

python3 - "$REGISTRY_FILE" "$PROJECT_DIR" "$SCRIPT_DIR" "$HOOK_MODE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

registry = Path(sys.argv[1])
project = Path(sys.argv[2]).resolve()
onboard = Path(sys.argv[3]).resolve()
hook_mode = sys.argv[4]
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

registry.parent.mkdir(parents=True, exist_ok=True)
try:
    data = json.loads(registry.read_text(encoding="utf-8")) if registry.exists() else {}
except Exception:
    data = {}

projects = data.get("projects", [])
projects = [item for item in projects if item.get("path") != str(project)]
projects.append({
    "path": str(project),
    "onboard_dir": str(onboard),
    "agent_mem_dir": str(project / ".agent-mem"),
    "mcp_generated_json": str(project / ".onboard" / "mcp.generated.json"),
    "dashboard": str(project / ".onboard" / "run-dashboard.sh"),
    "hook_mode": hook_mode,
    "last_setup_at": now,
})
projects.sort(key=lambda item: item.get("path", ""))
data = {
    "version": 1,
    "updated_at": now,
    "projects": projects,
}
registry.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
echo "✅ Registered linked project in .onboard/linked-projects.json"

python3 - "$PROJECT_DIR" "$MIGRATION_SNAPSHOT" "$PROJECT_DIR/.onboard/migration-report.json" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

project = Path(sys.argv[1])
before_path = Path(sys.argv[2])
report_path = Path(sys.argv[3])
mem = project / ".agent-mem"
core = [
    "project.json",
    "agents.json",
    "memories.json",
    "state.json",
    "tickets/_index.json",
]

def digest_file(path: Path):
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def snapshot():
    files = []
    total_bytes = 0
    if mem.exists():
        for root, dirs, names in os.walk(mem):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in names:
                path = Path(root) / name
                if not path.is_file():
                    continue
                rel = path.relative_to(mem).as_posix()
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                files.append(rel)
                total_bytes += size
    return {
        "exists": mem.exists(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "core_sha256": {item: digest_file(mem / item) for item in core},
    }

before = json.loads(before_path.read_text(encoding="utf-8"))
after = snapshot()
core_unchanged = before.get("core_sha256") == after.get("core_sha256")
report = {
    "version": 1,
    "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "project_dir": str(project),
    "existing_memory_detected": before.get("exists", False),
    "memory_policy": "setup-project.sh must not write, move, or delete .agent-mem/",
    "before": before,
    "after": after,
    "core_unchanged": core_unchanged,
}
report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

if before.get("exists") and not core_unchanged:
    print("❌ Existing .agent-mem core files changed during setup; inspect .onboard/migration-report.json")
    raise SystemExit(1)
PY
if [ -d "$PROJECT_DIR/.agent-mem" ]; then
    echo "✅ Existing .agent-mem verified unchanged"
    echo "✅ Wrote migration report at .onboard/migration-report.json"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Structure created:"
echo "  $PROJECT_DIR/"
echo "  ├── .agent-mem-hooks/       ← Agent hook scripts"
echo "  │   ├── cursor-session-start.sh"
echo "  │   ├── claude-code-session-start.sh"
echo "  │   ├── onboard-mini-brief.py"
echo "  │   └── ..."
echo "  ├── .codex/hooks.json       ← Codex hook config"
echo "  ├── .codex/hooks/           ← Codex hook scripts"
echo "  │   ├── codex-session-start.sh"
echo "  │   └── onboard-mini-brief.py"
echo "  ├── .cursor/hooks.json      ← Cursor hook config"
echo "  ├── .claude/settings.json   ← Claude Code hook config"
echo "  ├── .cursorrules            ← Rules for Cursor agents"
echo "  ├── CLAUDE.md               ← Rules for Claude Code agents"
echo "  ├── AGENTS.md               ← Rules for Codex agents"
echo "  ├── .agent/rules/           ← Rules for AntiGravity"
echo "  │   └── on-board-agent-memory.md"
echo "  ├── .onboard/mcp.generated.json ← Fresh generated MCP config (do not commit)"
echo "  ├── .onboard/mcp.json       ← Primary MCP config if not customized (do not commit)"
echo "  ├── .onboard/AGENT_CONTROL.md ← Agent setup control guide (do not commit)"
echo "  ├── .onboard/run-dashboard.sh ← Project dashboard launcher (do not commit)"
echo "  ├── .onboard/migration-report.json ← Existing-memory migration proof (do not commit)"
echo "  └── .agent-mem/             ← Runtime memory after init (gitignored)"
echo ""
echo "Linked project registry:"
echo "  $REGISTRY_FILE"
echo "  (local only; gitignored)"
echo ""
echo "Next:"
if [ -d "$PROJECT_DIR/.agent-mem" ]; then
    echo "  1. Existing memory was detected and verified unchanged."
    echo "  2. If your MCP client already works for this project, no client config change is required now."
    echo "  3. Use this generated config only for a new client or old config migration:"
    echo "     $PROJECT_DIR/.onboard/mcp.generated.json"
    echo "  4. If you update a client config, restart that client."
    echo "  5. In the agent, run:"
    echo "     memory_onboard, then memory_doctor"
else
    echo "  1. Add this MCP config to your client:"
    echo "     $PROJECT_DIR/.onboard/mcp.generated.json"
    echo "  2. Restart Claude Desktop / Claude Code / Cursor / Codex / AntiGravity / Windsurf."
    echo "  3. Ask your agent:"
    echo "     Call memory_bootstrap for this project, then memory_onboard."
fi
echo ""
echo "Dashboard:"
echo "  bash \"$PROJECT_DIR/.onboard/run-dashboard.sh\""
echo ""
