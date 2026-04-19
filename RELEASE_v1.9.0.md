## 🧠 The Discipline Update: Taming the Wild Agents

Your agents are powerful. But some of them are **feral**. They skip briefings. They spam 200 progress entries. They forget to handoff. They crash and leave nothing behind.

**v1.9.0 fixes this.** Not by hoping agents behave — by *making them*.

---

### 🚨 Agent Discipline System

**The Problem**: Dumb agents (looking at you, certain Gemini and GPT instances) skip the memory protocol. They jump straight to coding without reading context. They never checkpoint. When they die, the next agent starts from zero.

**The Fix**: The MCP now **blocks** undisciplined agents.

- **Join Enforcement**: `memory_write`, `memory_checkpoint`, `memory_handoff`, and `memory_create_ticket` now **reject calls** from agents that haven't registered with `memory_agent_join`. No more ghost writes.
- **SKILL.md — The Universal Hook**: Not every platform supports MCP lifecycle hooks. But **every platform reads instruction files**. `SKILL.md` is a single file that forces any agent — Claude, Cursor, Codex, Gemini, *anything* — to follow the protocol. Drop it in `.claude/skills/`, `.cursorrules`, `AGENTS.md`, or paste it in a system prompt. It works everywhere.
- **Stronger Briefing Protocol**: The briefing output now includes explicit `⛔ YOU CANNOT WRITE ANYTHING UNTIL YOU JOIN` warnings. Even the laziest agent can't miss it.

---

### 🛡️ Anti-Spam Briefing (Type-Cap)

**The Problem**: One rogue agent writes 100 "progress: still thinking..." entries. The next agent's briefing gets flooded. Context window wasted. Performance tanks.

**The Fix**: **Briefing Type-Cap** — each memory type has a maximum number of entries loaded into briefings:

| Type | Cap | Why |
|------|-----|-----|
| `handoff`, `decision`, `warning`, `blocker` | **Unlimited** | High-signal — always relevant |
| `discovery`, `todo` | **10** | Usually valuable |
| `file_change`, `context` | **8** | Recent changes matter |
| `checkpoint` | **1** | Only the latest |
| **`progress`** | **5** | 🎯 **Spam-prone — capped hard** |

Real-world test on a live project: **13% token reduction** with normal usage. With a spammy agent writing 100+ progress entries: **90%+ reduction**.

The MCP doesn't judge quality. It doesn't decide what's "good" or "bad." It just limits by type and keeps the most recent. **Provable, predictable, no AI judgment needed.**

---

### 📊 Dashboard

```bash
python3 dashboard.py --open
# or
AGENT_PROJECT_DIR=/path/to/project python3 dashboard.py
```

A live HTML dashboard generated from your `.agent-mem/` data. Dark theme. Five views:
- **Overview** — KPIs, type breakdown, recent activity, agent roster
- **Timeline** — Every memory entry, chronological, searchable
- **Agents** — Full roster with status, role, platform, write count
- **Tickets** — Open/closed/rejected with priority and assignment
- **Tokens** — Hot memory, digests, archive, briefing cost estimate

No server needed. No dependencies. Just Python reading JSON and outputting HTML.

---

### 🔧 Agent-Driven Compaction

**The Problem** (spotted by Opus 4.7): `memory_compact` with `use_llm=True` spawns an external API call. But the agent calling it **is already an LLM**. You're paying twice for the same work.

**The Fix**:
- `use_llm` now defaults to `False` — rule-based compression works fine for 95% of cases
- New tool: **`memory_prepare_compaction()`** — shows cold entries grouped by agent session. The calling agent reads them, writes its own digest, then runs `memory_compact`. Agent-driven. Zero extra API cost. Better quality because the agent understands the project context.

---

### 🔌 Cross-Platform Compatibility

- **`extra="ignore"`** on all 18 input models — Codex and AntiGravity no longer crash when they send unknown fields like `role`, `project`, or `session`
- **`agent_platform`** now defaults to `"unknown"` — forgetting to send it won't error
- **`agent_role`** field added: `main`, `reviewer`, `utility`, `planner` — shows in briefings and agent roster

---

### 📦 What's New Since v1.7.0

| Feature | Tools |
|---------|-------|
| Join enforcement | All write tools now require `memory_agent_join` first |
| SKILL.md | Universal instruction file for ALL platforms |
| Type-cap briefing | Anti-spam on progress/checkpoint entries |
| Dashboard | `dashboard.py` generates live HTML |
| Agent-driven compaction | `memory_prepare_compaction` (tool #23) |
| Agent roles | `agent_role` field in `memory_agent_join` |
| Codex/AntiGravity compat | `extra="ignore"` × 18 models |
| LLM double-charge fix | `use_llm` default flipped to `False` |

**23 tools. 6 platforms. 1 memory.**

---

### 💡 One File to Rule Them All

```
your-project/.claude/skills/agent-memory/SKILL.md   ← Claude Code reads this
your-project/.cursorrules                             ← Cursor reads this
your-project/AGENTS.md                                ← Codex reads this
AntiGravity system prompt                             ← paste SKILL.md content
```

Every platform has a way to inject instructions. SKILL.md is written once, works everywhere. The agent doesn't need to support MCP hooks. It just needs to read a file.

**That's the insight: hooks are platform-specific. Instruction files are universal.**

---

*One Project. One Memory. Every Platform. Every Agent Follows Orders.*
**Get On Board.** ⚡
