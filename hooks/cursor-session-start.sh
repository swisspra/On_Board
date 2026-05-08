#!/bin/bash
# ─────────────────────────────────────────────────────────
# Cursor Hook: sessionStart
# Forces the agent to read .agent-mem/ before doing anything
# ─────────────────────────────────────────────────────────

AGENT_MEM_DIR="${CURSOR_PROJECT_DIR:-.}/.agent-mem"

# Read stdin (Cursor sends session info as JSON)
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null || echo "unknown")

# Check if .agent-mem exists
if [ ! -d "$AGENT_MEM_DIR" ]; then
    # Return context telling agent to initialize
    cat <<EOF
{
  "additional_context": "⚠️ NO AGENT MEMORY FOUND at .agent-mem/\n\nThis project uses shared agent memory for multi-agent coordination.\n\n<on_board_protocol>\n  <required_first_call>memory_onboard</required_first_call>\n  <agent_identity>Use a stable agent_name. Do not include dates, model names, or session ids.</agent_identity>\n  <write_policy>Write after meaningful actions only.</write_policy>\n  <ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>\n  <handoff_policy>Always handoff before leaving.</handoff_policy>\n</on_board_protocol>\n\nBEFORE doing anything else, run: memory_init\nThen: memory_onboard with your stable agent_name and platform\n\nYou are likely taking over from a previous agent that may have died (KIA)."
}
EOF
    exit 0
fi

# Build briefing context from files
BRIEFING=""

# Project info
if [ -f "$AGENT_MEM_DIR/project.json" ]; then
    PROJ=$(cat "$AGENT_MEM_DIR/project.json")
    DESC=$(echo "$PROJ" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description',''))" 2>/dev/null)
    TECH=$(echo "$PROJ" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tech_stack',''))" 2>/dev/null)
    BRIEFING="$BRIEFING\n📋 PROJECT: $DESC | Tech: $TECH"
fi

# Agent history
if [ -f "$AGENT_MEM_DIR/agents.json" ]; then
    AGENTS=$(python3 -c "
import json
with open('$AGENT_MEM_DIR/agents.json') as f:
    agents = json.load(f)
for aid, a in agents.items():
    status = a.get('status','?')
    emoji = {'active':'🟢','kia':'💀','completed':'✅','handed_off':'🤝'}.get(status,'❓')
    print(f\"  {emoji} {a.get('agent_name','?')} ({a.get('agent_platform','?')}) — {status} — {a.get('memories_written',0)} writes\")
" 2>/dev/null)
    if [ -n "$AGENTS" ]; then
        BRIEFING="$BRIEFING\n\n👥 PREVIOUS AGENTS:\n$AGENTS"
    fi
fi

# Last handoff
if [ -f "$AGENT_MEM_DIR/memories.json" ]; then
    HANDOFF=$(python3 -c "
import json
with open('$AGENT_MEM_DIR/memories.json') as f:
    entries = json.load(f).get('entries',[])
handoffs = [e for e in entries if e.get('memory_type')=='handoff']
if handoffs:
    h = handoffs[-1]
    print(f\"🤝 LAST HANDOFF from {h['agent_name']}:\")
    print(h.get('content','')[:1000])
" 2>/dev/null)
    if [ -n "$HANDOFF" ]; then
        BRIEFING="$BRIEFING\n\n$HANDOFF"
    fi
fi

# Memory count
if [ -f "$AGENT_MEM_DIR/memories.json" ]; then
    COUNT=$(python3 -c "
import json
with open('$AGENT_MEM_DIR/memories.json') as f:
    entries = json.load(f).get('entries',[])
print(f'{len(entries)} total memories')
" 2>/dev/null)
    BRIEFING="$BRIEFING\n\n📚 $COUNT"
fi

# Output context for Cursor to inject
cat <<EOF
{
  "additional_context": "🧠 AGENT SHARED MEMORY ACTIVE\n$BRIEFING\n\n<on_board_protocol>\n  <required_first_call>memory_onboard</required_first_call>\n  <agent_identity>Use a stable agent_name. Do not include dates, model names, or session ids.</agent_identity>\n  <write_policy>Write after meaningful actions only.</write_policy>\n  <ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>\n  <handoff_policy>Always handoff before leaving.</handoff_policy>\n</on_board_protocol>\n\n⚡ MANDATORY PROTOCOL:\n1. Call memory_onboard with your stable agent_name and platform NOW\n2. Call memory_write after significant actions\n3. Call memory_checkpoint every 10-15 min\n4. Call memory_handoff before finishing\n5. Your agent_name is stamped on everything — you are accountable!",
  "env": {
    "AGENT_PROJECT_DIR": "${CURSOR_PROJECT_DIR:-.}",
    "AGENT_SESSION_ID": "$SESSION_ID"
  }
}
EOF
