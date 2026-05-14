# On Board — Agent Shared Memory SKILL.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Drop this file into any project that uses On Board MCP.
# Every AI agent (Claude, Cursor, Codex, Gemini, etc.) will read it
# automatically via their native instruction file system.
#
# Supported placements:
#   .cursor/skills/agent-memory/SKILL.md   ← Cursor
#   .claude/skills/agent-memory/SKILL.md   ← Claude Code / Cowork
#   AGENTS.md (append content)              ← Codex
#   .cursorrules (append content)           ← Cursor fallback
#   System prompt (paste content)           ← AntiGravity / any agent

## GET ON BOARD — YOU HAVE ACCESS TO AGENT SHARED MEMORY

This project uses On Board (`.agent-mem/`) for multi-agent coordination.
You are NOT the first agent. Others have worked here before you.
Their decisions, discoveries, warnings, and progress are saved in memory.

**If you skip reading memory, you WILL redo work that's already done.**
**If you skip writing memory, the next agent WILL redo YOUR work.**

---

## GET ON BOARD — MANDATORY PROTOCOL

<on_board_protocol>
  <required_first_call>memory_onboard</required_first_call>
  <agent_identity>Use a stable agent_name. Do not include dates, model names, or session ids.</agent_identity>
  <write_policy>Write after meaningful actions only.</write_policy>
  <ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>
  <handoff_policy>Always handoff before leaving.</handoff_policy>
</on_board_protocol>

### Step 1: ONBOARD (before doing ANYTHING)
```
memory_onboard(
  agent_name="<your-stable-name>",
  agent_platform="<claude|cursor|codex|antigravity|other>",
  agent_role="<main|reviewer|utility|planner>",
  mode="normal"
)
```
This registers you, reads the briefing, shows open tickets, and checks data health.
The briefing contains:
- What the project is about
- What previous agents did
- What decisions were made and WHY
- What's broken / blocked
- What tickets are waiting for you

Use `mode="brief"` for fast catchup, `mode="deep"` when context is unclear,
and `mode="handoff-only"` when you only need the latest transfer state.
For a specific ticket, pass `ticket_id="TK-xxx"`. For setup issues, run `memory_doctor()`.

Fallback if `memory_onboard` is not available:
```
memory_get_briefing(mode="normal")
memory_agent_join(
  agent_name="<your-stable-name>",
  agent_platform="<claude|cursor|codex|antigravity|other>",
  agent_role="<main|reviewer|utility|planner>"
)
```

Rules for agent_name:
- Use a STABLE name: `cursor-coder`, `claude-reviewer`, `codex-main`
- Do NOT put dates, model names, or session IDs in your name
- Keep the SAME name across sessions

### Step 2: CHECK TICKETS
```
memory_list_tickets()
```
Someone may have created a ticket for you. Claim it if relevant.

### Step 3: WORK (write after significant action)
After each significant code change, decision, discovery, blocker, or warning:
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
Do NOT batch important context. Write immediately after each significant action.
If you die mid-task, these writes are ALL the next agent has.
Use `memory_links(ticket_id="TK-xxx")` when you need to see how memories, tickets, files, agents, and tags connect.

### Step 4: CHECKPOINT (every 10-15 minutes)
```
memory_checkpoint(
  agent_name="<your-name>",
  summary="What I've done so far",
  remaining_tasks=["task1", "task2"],
  blockers=["blocker1"]
)
```

### Step 5: HANDOFF (before you finish)
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
ALWAYS handoff, even if you think you'll return. You might not.

---

## TICKETING (when you need help)

### Create a ticket for another agent
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

### Claim and work on a ticket
```
memory_claim_ticket(agent_name="<your-name>", ticket_id="TK-xxx")
# ... do the work ...
memory_submit_ticket(
  agent_name="<your-name>",
  ticket_id="TK-xxx",
  summary="What I did",
  files_changed=["file1.css"]
)
```
Submitting auto-handoffs you. The reviewer will pick it up.

### Review submitted work
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

When memory gets large, compress it:
```
memory_prepare_compaction()
```
Read the output, write your own summary, then archive:
```
memory_write(memory_type="context", title="Digest: <agent> (<period>)", content="your non-blank summary")
memory_compact(strategy="agent")
```
Fallback if you cannot write digests safely: `memory_compact(strategy="regex")`.

---

## MEMORY TYPES REFERENCE

| Type | When to use |
|------|-------------|
| `decision` | You chose X over Y — explain WHY |
| `progress` | You completed something |
| `blocker` | Something is stuck |
| `context` | Background info, digests, architecture notes |
| `todo` | Task that needs doing |
| `file_change` | Created, modified, or deleted a file |
| `discovery` | Learned something important about the codebase |
| `warning` | Gotcha — something that will trip up the next agent |
| `checkpoint` | Full state snapshot (auto via memory_checkpoint) |
| `handoff` | Formal handoff (auto via memory_handoff) |

---

## CONSEQUENCES

- ⛔ `memory_write` will BLOCK you if you haven't called `memory_onboard` or `memory_agent_join`
- ⛔ `memory_checkpoint` and `memory_handoff` will BLOCK you if you haven't joined
- ⛔ ticket mutation tools (`memory_claim_ticket`, `memory_submit_ticket`, `memory_review_ticket`, cancel/terminate) will BLOCK you if you haven't joined
- 💀 If you die without writing, the next agent starts from zero
- 🔄 If you skip the briefing, you'll redo work that's already done
- 📛 Your agent_name is stamped on every entry — you are accountable
