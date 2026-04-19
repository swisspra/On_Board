#!/bin/bash
# ─────────────────────────────────────────────────────────
# Codex Hook: Stop
# Auto-save emergency checkpoint when a Codex turn stops
# ─────────────────────────────────────────────────────────

INPUT=$(cat)
PROJECT_DIR=$(printf '%s' "$INPUT" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('cwd') or '.')" 2>/dev/null || pwd)
TURN_ID=$(printf '%s' "$INPUT" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('turn_id',''))" 2>/dev/null || echo "")
STOP_HOOK_ACTIVE=$(printf '%s' "$INPUT" | python3 -c "import json,sys; data=json.load(sys.stdin); print('true' if data.get('stop_hook_active') else 'false')" 2>/dev/null || echo "false")
AGENT_MEM_DIR="$PROJECT_DIR/.agent-mem"

if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
    echo '{"continue": true}'
    exit 0
fi

AGENT_MEM_DIR="$AGENT_MEM_DIR" TURN_ID="$TURN_ID" python3 - <<'PY'
import json
import os
import time
from datetime import datetime
from pathlib import Path


def emit_ok() -> None:
    print(json.dumps({"continue": True}))


def local_now() -> str:
    return datetime.now().astimezone().isoformat()


mem_dir = Path(os.environ["AGENT_MEM_DIR"])
turn_id = os.environ.get("TURN_ID", "")

if not mem_dir.is_dir():
    emit_ok()
    raise SystemExit(0)

agents_file = mem_dir / "agents.json"
if not agents_file.exists():
    emit_ok()
    raise SystemExit(0)

with agents_file.open() as f:
    agents = json.load(f)

active_name = "unknown"
for agent in agents.values():
    if agent.get("status") == "active":
        active_name = agent.get("agent_name", "unknown")
        agent["status"] = "kia"
        agent["kia_at"] = local_now()
        agent["kia_reason"] = "codex_stop_hook"
        break

with agents_file.open("w") as f:
    json.dump(agents, f, indent=2)

memories_file = mem_dir / "memories.json"
if memories_file.exists():
    with memories_file.open() as f:
        memories = json.load(f)
else:
    memories = {"entries": []}

if memories.get("entries"):
    memories["entries"].append(
        {
            "id": f"codex-stop-{int(time.time())}",
            "agent_name": active_name,
            "memory_type": "checkpoint",
            "title": "⚡ Auto-checkpoint on Codex stop",
            "content": json.dumps(
                {
                    "reason": "codex_stop_hook",
                    "note": "Auto-saved by Codex Stop hook. Agent may not have had time to handoff.",
                    "turn_id": turn_id,
                    "timestamp": local_now(),
                }
            ),
            "tags": ["emergency", "auto-checkpoint", "codex"],
            "related_files": [],
            "priority": 2,
            "pinned": True,
            "created_at": local_now(),
            "timestamp": time.time(),
        }
    )
    with memories_file.open("w") as f:
        json.dump(memories, f, indent=2)

emit_ok()
PY

exit 0
