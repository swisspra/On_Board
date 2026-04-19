# Agent Shared Memory — SKILL.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Drop this file into any project that uses the Agent Memory MCP.
# Every AI agent (Claude, Cursor, Codex, Gemini, etc.) will read it
# automatically via their native instruction file system.
#
# Supported placements:
#   .cursor/skills/agent-memory/SKILL.md   ← Cursor
#   .claude/skills/agent-memory/SKILL.md   ← Claude Code / Cowork
#   AGENTS.md (append content)              ← Codex
#   .cursorrules (append content)           ← Cursor fallback
#   System prompt (paste content)           ← AntiGravity / any agent

## YOU HAVE ACCESS TO AGENT SHARED MEMORY

This project uses a shared `.agent-mem/` directory for multi-agent coordination.
You are NOT the first agent. Others have worked here before you.
Their decisions, discoveries, warnings, and progress are saved in memory.

**If you skip reading memory, you WILL redo work that's already done.**
**If you skip writing memory, the next agent WILL redo YOUR work.**

---

## MANDATORY PROTOCOL — EXECUTE IN ORDER

### Step 1: READ (before doing ANYTHING)
```
memory_get_briefing()
```
Read the full project context. This contains:
- What the project is about
- What previous agents did
- What decisions were made and WHY
- What's broken / blocked
- What tickets are waiting for you

### Step 2: JOIN (register yourself)
```
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

### Step 3: CHECK TICKETS
```
memory_list_tickets()
```
Someone may have created a ticket for you. Claim it if relevant.

### Step 4: WORK (write after EVERY action)
After EVERY code change, decision, or discovery:
```
memory_write(
  agent_name="<your-name>",
  memory_type="progress|decision|file_change|discovery|warning|blocker",
  title="Short description",
  content="Detailed description with file names and reasoning"
)
```
Do NOT batch writes. Write immediately after each action.
If you die mid-task, these writes are ALL the next agent has.

### Step 5: CHECKPOINT (every 10-15 minutes)
```
memory_checkpoint(
  agent_name="<your-name>",
  summary="What I've done so far",
  remaining_tasks=["task1", "task2"],
  blockers=["blocker1"]
)
```

### Step 6: HANDOFF (before you finish)
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
memory_write(memory_type="context", title="Digest: ...", content="your summary")
memory_compact(use_llm=False)
```
You ARE an LLM — summarize yourself instead of paying for another API call.

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

- ⛔ `memory_write` will BLOCK you if you haven't called `memory_agent_join`
- ⛔ `memory_checkpoint` will BLOCK you if you haven't joined
- ⛔ `memory_handoff` will BLOCK you if you haven't joined
- 💀 If you die without writing, the next agent starts from zero
- 🔄 If you skip the briefing, you'll redo work that's already done
- 📛 Your agent_name is stamped on every entry — you are accountable
