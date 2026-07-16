#!/bin/bash
# ─────────────────────────────────────────────────────────
# Cursor Hook: sessionStart
# Injects a small read-only On Board startup hint.
# ─────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Read stdin (Cursor sends session info as JSON)
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null || echo "unknown")
PROJECT_DIR=$(printf '%s' "$INPUT" | python3 -c "
import json, os, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
for key in ('workspaceFolder', 'workspace_folder', 'workspaceRoot', 'workspace_root', 'project_dir', 'cwd'):
    value = data.get(key)
    if isinstance(value, str) and value:
        print(value)
        break
else:
    roots = data.get('workspaceFolders') or data.get('workspace_folders') or []
    if isinstance(roots, list) and roots:
        first = roots[0]
        if isinstance(first, str):
            print(first)
        elif isinstance(first, dict):
            print(first.get('path') or first.get('uri') or '')
" 2>/dev/null)
PROJECT_DIR="${CURSOR_PROJECT_DIR:-${PROJECT_DIR:-$(pwd)}}"
AGENT_MEM_DIR="$PROJECT_DIR/.agent-mem"

AGENT_MEM_DIR="$AGENT_MEM_DIR" SCRIPT_DIR="$SCRIPT_DIR" SESSION_ID="$SESSION_ID" PROJECT_DIR="$PROJECT_DIR" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

script = Path(os.environ["SCRIPT_DIR"]) / "onboard-mini-brief.py"
text = subprocess.check_output(["python3", str(script)], env=os.environ, text=True)
print(json.dumps({
    "additional_context": text,
    "env": {
        "AGENT_PROJECT_DIR": os.environ.get("PROJECT_DIR", os.environ.get("CURSOR_PROJECT_DIR", ".")),
        "AGENT_SESSION_ID": os.environ.get("SESSION_ID", "unknown"),
    },
}))
PY
