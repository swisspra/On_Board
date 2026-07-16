#!/bin/bash
# ─────────────────────────────────────────────────────────
# Codex Hook: SessionStart
# Injects a small read-only On Board startup hint into Codex.
# ─────────────────────────────────────────────────────────

INPUT=$(cat)
PROJECT_DIR=$(printf '%s' "$INPUT" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('cwd') or '.')" 2>/dev/null || pwd)
SESSION_ID=$(printf '%s' "$INPUT" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('session_id','unknown'))" 2>/dev/null || echo "unknown")
AGENT_MEM_DIR="$PROJECT_DIR/.agent-mem"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AGENT_MEM_DIR="$AGENT_MEM_DIR" SESSION_ID="$SESSION_ID" SCRIPT_DIR="$SCRIPT_DIR" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

script = Path(os.environ["SCRIPT_DIR"]) / "onboard-mini-brief.py"
text = subprocess.check_output(["python3", str(script)], env=os.environ, text=True)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
PY

exit 0
