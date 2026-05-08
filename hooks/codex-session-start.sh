#!/bin/bash
# ─────────────────────────────────────────────────────────
# Codex Hook: SessionStart
# Injects shared-memory context into Codex on startup/resume
# ─────────────────────────────────────────────────────────

INPUT=$(cat)
PROJECT_DIR=$(printf '%s' "$INPUT" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('cwd') or '.')" 2>/dev/null || pwd)
SESSION_ID=$(printf '%s' "$INPUT" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('session_id','unknown'))" 2>/dev/null || echo "unknown")
AGENT_MEM_DIR="$PROJECT_DIR/.agent-mem"

AGENT_MEM_DIR="$AGENT_MEM_DIR" SESSION_ID="$SESSION_ID" python3 - <<'PY'
import json
import os
from pathlib import Path

mem_dir = Path(os.environ["AGENT_MEM_DIR"])
session_id = os.environ.get("SESSION_ID", "unknown")


def emit_context(text: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": text,
                }
            }
        )
    )


ON_BOARD_PROTOCOL = "\n".join(
    [
        "<on_board_protocol>",
        "  <required_first_call>memory_onboard</required_first_call>",
        "  <agent_identity>Use a stable agent_name. Do not include dates, model names, or session ids.</agent_identity>",
        "  <write_policy>Write after meaningful actions only.</write_policy>",
        "  <ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>",
        "  <handoff_policy>Always handoff before leaving.</handoff_policy>",
        "</on_board_protocol>",
    ]
)


if not mem_dir.is_dir():
    emit_context(
        "⚠️ NO AGENT MEMORY FOUND at .agent-mem/\n\n"
        "This project uses shared agent memory for multi-agent coordination.\n"
        f"{ON_BOARD_PROTOCOL}\n\n"
        "Before doing anything else, run memory_init, then memory_onboard.\n"
        f"Current Codex session: {session_id}"
    )
    raise SystemExit(0)

lines = ["🧠 AGENT SHARED MEMORY ACTIVE"]

project_file = mem_dir / "project.json"
if project_file.exists():
    with project_file.open() as f:
        project = json.load(f)
    lines.append(
        f"Project: {project.get('description', '')} | Tech: {project.get('tech_stack', '')}"
    )

agents_file = mem_dir / "agents.json"
if agents_file.exists():
    with agents_file.open() as f:
        agents = json.load(f)
    if agents:
        lines.append(f"\n👥 {len(agents)} previous agent(s):")
        for agent in agents.values():
            emoji = {
                "active": "🟢",
                "kia": "💀",
                "completed": "✅",
                "handed_off": "🤝",
            }.get(agent.get("status", ""), "❓")
            lines.append(
                f"  {emoji} {agent.get('agent_name', '?')} "
                f"({agent.get('agent_platform', '?')}) — {agent.get('status', '?')}"
            )

memories_file = mem_dir / "memories.json"
if memories_file.exists():
    with memories_file.open() as f:
        entries = json.load(f).get("entries", [])
    handoffs = [entry for entry in entries if entry.get("memory_type") == "handoff"]
    if handoffs:
        handoff = handoffs[-1]
        lines.append(f"\n🤝 LAST HANDOFF from {handoff['agent_name']}:")
        lines.append(handoff.get("content", "")[:800])
    lines.append(f"\n📚 {len(entries)} total memories")

lines.append("\n" + ON_BOARD_PROTOCOL)
lines.append(
    "\n⚡ PROTOCOL: memory_onboard → work → "
    "memory_write → memory_checkpoint → memory_handoff"
)

emit_context("\n".join(lines))
PY

exit 0
