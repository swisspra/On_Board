# 🧠 On Board — Cross-Platform Agent Shared Memory MCP

**One project. One memory. Every platform.** When agents die, context survives.

## The Problem

Multiple AI agents (Claude, Cursor, Codex, Claude Code, AntiGravity) work on the same project. When one dies (quota, crash), the next starts from zero. Decisions, discoveries, and context are lost.

## The Solution

A shared `.agent-mem/` directory inside your project that ALL agents read/write via MCP.

```
your-project/
├── .agent-mem/              ← Runtime memory (gitignored)
│   ├── memories.json        ← Entries stamped with agent_name
│   ├── agents.json          ← Agent history (who, when, KIA?)
│   ├── state.json           ← Shared key-value store
│   ├── project.json         ← Project metadata
│   ├── archive.json         ← Compacted old entries
│   ├── digests.json         ← Compressed long-term memory
│   ├── checkpoints/         ← Periodic snapshots
│   └── tickets/             ← Cross-agent ticketing system
└── CLAUDE.md / .cursorrules ← Agent rules
```

## What's New in v3.0.0

- **Smarter KIA detection** — agents are now tracked with heartbeats and auto-marked KIA after 30min idle
- **Better agent status** — more accurate active/offline tracking
- **Dashboard improvements** — agents grouped by name, platform colors, orphan ticket warnings
- **Naming convention** — agents get a naming tip on join for better traceability

See [CHANGELOG.md](CHANGELOG.md) for details.

---

## Quick Start

### 1. Clone & setup

```bash
git clone https://github.com/swisspra/agent_mem_MCP.git
cd agent_mem_MCP
python3 -m venv venv
./venv/bin/pip install httpx "mcp[cli]" pydantic
```

### 2. Note your full Python path

```bash
# Example: /Users/yourname/tools/agent-memory-mcp/venv/bin/python
```

### 3. Configure your platform

<details>
<summary><b>Claude Desktop</b></summary>

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "/full/path/to/venv/bin/python",
      "args": ["/full/path/to/server.py"],
      "env": { "AGENT_PROJECT_DIR": "/full/path/to/your/project" }
    }
  }
}
```
</details>

<details>
<summary><b>Cursor</b></summary>

Add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "/full/path/to/venv/bin/python",
      "args": ["/full/path/to/server.py"],
      "env": { "AGENT_PROJECT_DIR": "${workspaceFolder}" }
    }
  }
}
```
</details>

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add agent-memory -- /full/path/to/venv/bin/python /full/path/to/server.py
```
</details>

<details>
<summary><b>Codex (OpenAI)</b></summary>

```bash
codex mcp add agent-memory \
  --env AGENT_PROJECT_DIR="/full/path/to/your/project" \
  -- /full/path/to/venv/bin/python /full/path/to/server.py
```
</details>

<details>
<summary><b>AntiGravity (Gemini)</b></summary>

Use the MCP settings UI:
- **Command**: `/full/path/to/venv/bin/python`
- **Arguments**: `/full/path/to/server.py`
- **Environment**: `AGENT_PROJECT_DIR` = `/full/path/to/your/project`
</details>

---

## Usage

### New project
```
memory_init(description="My project", tech_stack="React/Node")
memory_agent_join(agent_name="claude-opus4.7-21apr26a", agent_platform="claude")
```

### Existing project (first time)
```
memory_bootstrap(agent_name="claude-onboard", description="My project", tech_stack="React/Node")
```

### Every subsequent agent
```
memory_get_briefing()                    ← read full context
memory_agent_join(agent_name="...", agent_platform="...")
... work ...
memory_write(agent_name="...", memory_type="progress", title="...", content="...")
memory_checkpoint(agent_name="...", summary="...")
memory_handoff(agent_name="...", summary="...", next_steps=["..."])
```

### Agent Naming Convention

Use: `{platform}-{model}-{date}{suffix}`
- ✅ `claude-opus4.7-21apr26a`
- ✅ `cursor-sonnet-ble-18apr26a`
- ❌ `Antigravity` (too vague)
- ❌ `claude-desktop-Opus4.6` (uppercase, includes "desktop")

---

## Tools (23 total)

| Category | Tool | Purpose |
|----------|------|---------|
| **Setup** | `memory_init` | Initialize `.agent-mem/` |
| | `memory_bootstrap` | Auto-scan existing project |
| **Agent** | `memory_agent_join` | Register (KIAs same-platform only) |
| | `memory_handoff` | Formal handoff to next agent |
| **Write** | `memory_write` | Write memory (stamped with name) |
| **Read** | `memory_read` | Read with filters |
| | `memory_search` | Full-text search |
| **State** | `memory_checkpoint` | Full state snapshot |
| | `memory_pin` | Pin/unpin critical entries |
| | `memory_update_state` | Shared key-value store |
| **Context** | `memory_get_briefing` | Full project briefing |
| | `memory_status` | Quick dashboard |
| | `memory_context_dirs` | List external ref dirs |
| | `memory_context_read` | Read from external dirs |
| **Tokens** | `memory_compact` | Compress old → save 70%+ |
| | `memory_prepare_compaction` | Preview cold entries |
| | `memory_token_usage` | Token breakdown report |
| | `memory_search_archive` | Search compacted entries |
| **Tickets** | `memory_create_ticket` | Request help from another agent |
| | `memory_claim_ticket` | Pick up a ticket |
| | `memory_submit_ticket` | Submit work for review |
| | `memory_review_ticket` | Approve or reject |
| | `memory_list_tickets` | List tickets |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PROJECT_DIR` | cwd | Project root path |
| `AGENT_MEM_CONTEXT_DIRS` | — | Colon-separated external info dirs |
| `AGENT_MEM_HOT_HOURS` | 24 | Hours to keep full detail |
| `AGENT_MEM_MAX_HOT` | 50 | Max hot entries |
| `AGENT_MEM_IDLE_KIA_MIN` | 30 | Minutes before idle agent auto-KIA |

## Updating

```bash
bash update.sh
```

Pulls latest, reinstalls deps, auto-deploys to detected copies. Restart your agents after.

## Tips

- **MANDATORY RULE**: Auto-save memory after EVERY code change
- If applying to an existing project, tell your first agent to read the codebase, then compact for others

## License

MIT
