# On Board - Cross-Platform Agent Shared Memory MCP

One project, one shared memory, every agent platform.

On Board stores project context in `.agent-mem/` so Claude, Cursor, Codex, Claude Code, AntiGravity, and other MCP clients can continue work without losing decisions, warnings, tickets, or handoffs.

## Quick Start

```bash
git clone https://github.com/swisspra/agent_mem_MCP.git
cd agent_mem_MCP
python3 -m venv venv
./venv/bin/pip install httpx "mcp[cli]" pydantic
```

Use the full Python path from that venv when configuring clients:

```bash
/full/path/to/agent_mem_MCP/venv/bin/python
```

## MCP Client Setup

### Claude Desktop

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

### Cursor

Add to your project `.cursor/mcp.json`:

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

### Claude Code

```bash
claude mcp add agent-memory -- /full/path/to/venv/bin/python /full/path/to/server.py
```

### Codex

```bash
codex mcp add agent-memory \
  --env AGENT_PROJECT_DIR="/full/path/to/your/project" \
  -- /full/path/to/venv/bin/python /full/path/to/server.py
```

To use Codex hooks, enable the experimental hook feature in `~/.codex/config.toml`:

```toml
[features]
codex_hooks = true
```

### AntiGravity

Use the MCP settings UI:

- Command: `/full/path/to/venv/bin/python`
- Arguments: `/full/path/to/server.py`
- Environment: `AGENT_PROJECT_DIR=/full/path/to/your/project`

## Project Installer

Run this from the target project root:

```bash
bash /path/to/agent_mem_MCP/setup-project.sh
```

It installs project-local helper files:

```text
your-project/
├── .agent-mem/                         Runtime memory, gitignored
├── .agent-mem-hooks/                   Cursor and Claude Code hook scripts
├── .codex/hooks.json                   Codex hook config
├── .codex/hooks/                       Codex hook scripts
├── .cursor/hooks.json                  Cursor hook config
├── .claude/settings.json               Claude Code hook config
├── .agent/rules/on-board-agent-memory.md  AntiGravity workspace rule
├── AGENTS.md                           Codex rules
├── CLAUDE.md                           Claude Code rules
└── .cursorrules                        Cursor rules
```

If an existing config file is present, the installer leaves it alone and prints the template path to merge manually.

After installing, run `memory_doctor` from your MCP client to check project-local hooks, rules, runtime memory, and ignored paths.

## Agent Workflow

First time in a new project:

```text
memory_init(description="My project", tech_stack="React/Node")
memory_agent_join(agent_name="claude-main", agent_platform="claude")
```

First time in an existing project:

```text
memory_bootstrap(agent_name="claude-onboard", description="My project", tech_stack="React/Node")
```

Every later agent:

```text
memory_get_briefing(mode="normal")
memory_agent_join(agent_name="codex-main", agent_platform="codex")
memory_list_tickets()
memory_write(...)
memory_checkpoint(...)
memory_handoff(...)
```

Briefing modes:

- `brief` - fast catchup with the latest handoff and highest-signal memory
- `normal` - default onboarding
- `deep` - broader project history when context is unclear
- `handoff-only` - fastest transfer check

Use stable agent names such as `claude-main`, `cursor-coder`, or `codex-main`. Keep the same name across sessions; do not put dates, model names, or session IDs in `agent_name`.

## Ticket Workflow

Use tickets when work needs to move between agents:

- `memory_create_ticket` - request help or assign work
- `memory_claim_ticket` - pick up assigned or open work
- `memory_submit_ticket` - submit completed work for review
- `memory_review_ticket` - approve or reject submitted work
- `memory_cancel_ticket` - cancel a ticket you created
- `memory_terminate_ticket` - force-close a ticket you created
- `memory_list_tickets` - inspect open, claimed, submitted, and closed tickets

## Tools

On Board currently exposes 27 MCP tools.

Core:
`memory_init`, `memory_bootstrap`, `memory_agent_join`, `memory_get_briefing`, `memory_status`, `memory_doctor`, `memory_handoff`

Memory:
`memory_write`, `memory_read`, `memory_search`, `memory_search_vector`, `memory_pin`

State and context:
`memory_checkpoint`, `memory_update_state`, `memory_context_dirs`, `memory_context_read`

Compaction:
`memory_prepare_compaction`, `memory_compact`, `memory_token_usage`, `memory_search_archive`

Recommended compaction flow: run `memory_token_usage`, review old entries with `memory_prepare_compaction`, then run `memory_compact(use_llm=false)` when the preview looks safe.

Tickets:
`memory_create_ticket`, `memory_claim_ticket`, `memory_submit_ticket`, `memory_review_ticket`, `memory_cancel_ticket`, `memory_terminate_ticket`, `memory_list_tickets`

## Runtime Data

`.agent-mem/` contains project memory:

```text
.agent-mem/
├── project.json
├── agents.json
├── memories.json
├── state.json
├── archive.json
├── digests.json
├── checkpoints/
└── tickets/
```

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENT_PROJECT_DIR` | cwd | Project root path |
| `AGENT_MEM_CONTEXT_DIRS` | empty | Colon-separated external context directories |
| `AGENT_MEM_HOT_HOURS` | 24 | Hours to keep full-detail hot memory |
| `AGENT_MEM_MAX_HOT` | 50 | Max hot memory entries |
| `AGENT_MEM_IDLE_KIA_MIN` | 30 | Minutes before idle active agents are marked KIA |
| `AGENT_MEM_VECTOR_BACKEND` | none | Optional vector-style search backend: `none` or `local` |

## Updating

```bash
bash update.sh
```

Restart clients after updating MCP server config or hook/rule files.

## License

MIT
