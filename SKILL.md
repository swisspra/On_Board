# Greetings Agents!
# Welcome On Board — Agent Shared Memory SKILL.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Drop into any project that uses On Board MCP.
# Every AI agent (Claude, Cursor, Codex, Gemini, etc.) reads automatically
# via native instruction file system.
#
# Placements:
#   .cursor/skills/agent-memory/SKILL.md   ← Cursor
#   .claude/skills/agent-memory/SKILL.md   ← Claude Code / Cowork
#   AGENTS.md (append)                      ← Codex
#   .cursorrules (append)                   ← Cursor fallback
#   System prompt (paste)                   ← AntiGravity / any agent

## GET ON BOARD — YOU HAVE ACCESS TO AGENT SHARED MEMORY

Project uses On Board (`.agent-mem/`) for multi-agent coordination.
You are NOT the first agent. Others worked here before. Their decisions, discoveries, warnings, progress are in memory.

**Skip reading memory → redo done work.**
**Skip writing memory → next agent redoes YOUR work.**

---

## GET ON BOARD — MANDATORY PROTOCOL

<on_board_protocol>
  <required_first_call>memory_onboard</required_first_call>
  <agent_identity>Use stable agent_name. No dates, model names, or session ids.</agent_identity>
  <write_policy>Write after meaningful actions only.</write_policy>
  <ticket_policy>Ticket mutations require onboarded session.</ticket_policy>
  <handoff_policy>Always handoff before leaving.</handoff_policy>
</on_board_protocol>

### Step 1: ONBOARD (before ANYTHING)
```
memory_onboard(
  agent_name="<your-stable-name>",
  agent_platform="<claude|cursor|codex|antigravity|other>",
  agent_role="<main|reviewer|utility|planner>",
  mode="normal"
)
```
Registers you, reads briefing, shows tickets, checks data health.

Briefing contains:
- Project description
- Previous agents' work
- Decisions + WHY
- Broken / blocked items
- Tickets waiting for you

Modes: `brief` (fast catchup), `deep` (unclear context), `handoff-only` (latest transfer).
For specific ticket → `ticket_id="TK-xxx"`. Setup issues → `memory_doctor()`.

Fallback if `memory_onboard` unavailable:
```
memory_get_briefing(mode="normal")
memory_agent_join(
  agent_name="<your-stable-name>",
  agent_platform="<claude|cursor|codex|antigravity|other>",
  agent_role="<main|reviewer|utility|planner>"
)
```

agent_name rules:
- STABLE: `cursor-coder`, `claude-reviewer`, `codex-main`
- NO dates, model names, session IDs
- SAME name across sessions

### Step 2: CHECK TICKETS
```
memory_list_tickets()
```
Claim if relevant.

### Step 3: WORK (write after significant action)
After each code change, decision, discovery, blocker, warning:
```
memory_write(
  agent_name="<your-name>",
  memory_type="progress|decision|file_change|discovery|warning|blocker",
  title="Short description",
  content="Detailed description with file names and reasoning",
  related_files=["server.py"],
  related_tickets=["TK-xxx"]
)
```
Write immediately after action — don't batch.
Crash mid-task → only these writes survive.
Use `memory_links(ticket_id="TK-xxx")` to inspect memory/ticket/file/agent/tag links.

### Step 4: CHECKPOINT (every 10-15 min)
```
memory_checkpoint(
  agent_name="<your-name>",
  summary="What I've done so far",
  remaining_tasks=["task1", "task2"],
  blockers=["blocker1"]
)
```

### Step 5: HANDOFF (before finishing)
```
memory_handoff(
  agent_name="<your-name>",
  summary="What I accomplished",
  next_steps=["step1", "step2"],
  warnings=["warning1"],
  files_modified=["file1.py"],
  files_created=["file2.py"]
)
```
ALWAYS handoff, even if you'll return. You might not.

---

## TICKETING (when you need help)

### Create ticket for another agent
```
memory_create_ticket(
  agent_name="<your-name>",
  title="Fix CSS bug on WiFi page",
  description="Buttons overlap on mobile < 375px",
  target_url="http://localhost:3000/wifi",
  scope="interactive-no-send",
  required_fields=["screenshot", "files_changed", "verification"],
  priority="high",
  assigned_to="cursor"
)
```

### Claim + work
```
memory_claim_ticket(agent_name="<your-name>", ticket_id="TK-xxx")
# ... do work ...
memory_submit_ticket(
  agent_name="<your-name>",
  ticket_id="TK-xxx",
  summary="What I did",
  files_changed=["file1.css"]
)
```
Submit auto-handoffs you. Reviewer picks up.

### Review
```
memory_review_ticket(
  agent_name="<your-name>",
  ticket_id="TK-xxx",
  verdict="approve",
  review_notes="Looks good",
  fix_instructions="..."
)
```

---

## TOKEN MANAGEMENT

Large memory → compress:
```
memory_prepare_compaction()
```
Read output, write your summary, archive:
```
memory_write(memory_type="context", title="Digest: ...", content="your summary")
memory_compact()
```
Summarize the preview yourself before archiving old raw entries.

---

## MEMORY TYPES REFERENCE

| Type | When to use |
|------|-------------|
| `decision` | Chose X over Y — explain WHY |
| `progress` | Completed something |
| `blocker` | Stuck on something |
| `context` | Background, digests, architecture notes |
| `todo` | Task pending |
| `file_change` | Created/modified/deleted file |
| `discovery` | Important codebase finding |
| `warning` | Gotcha for next agent |
| `checkpoint` | Full state snapshot (auto via memory_checkpoint) |
| `handoff` | Formal handoff (auto via memory_handoff) |

---

## CONSEQUENCES

- ⛔ `memory_write` BLOCKED without `memory_onboard` / `memory_agent_join`
- ⛔ `memory_checkpoint` / `memory_handoff` BLOCKED without join
- ⛔ ticket mutation tools (`memory_claim_ticket`, `memory_submit_ticket`, `memory_review_ticket`, cancel/terminate) BLOCKED without join
- 💀 Die without writing → next agent starts from zero
- 🔄 Skip briefing → redo done work
- 📛 Your agent_name stamps every entry — you are accountable
