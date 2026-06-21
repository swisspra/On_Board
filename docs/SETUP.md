# On Board Setup

This guide sets up On Board for one target project.

## Requirements

- Python 3.10+
- `uv`
- Git
- An MCP client such as Claude Desktop, Claude Code, Cursor, Codex, or AntiGravity

Install `uv` if needed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 1. Install On Board

```bash
git clone https://github.com/swisspra/On_Board.git
cd On_Board
uv sync
```

You can sanity-check the server with:

```bash
uv run python server.py
```

Stop it after it starts. Your MCP client will normally start it for you.

## 2. Add the MCP server to your client

Use this template and replace both paths:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/full/path/to/On_Board",
        "python",
        "server.py"
      ],
      "env": {
        "AGENT_PROJECT_DIR": "/full/path/to/your/project",
        "AGENT_MEM_CONTEXT_DIRS": "/path/to/docs:/path/to/specs"
      }
    }
  }
}
```

`AGENT_PROJECT_DIR` is required. It tells On Board which project owns the `.agent-mem/` memory folder.

`AGENT_MEM_CONTEXT_DIRS` is optional. Use it when agents should read extra docs or specs outside the project with `memory_context_dirs` and `memory_context_read`.

The same JSON is available in `configs/uv-mcp.json`.

## 3. Add project rules and hooks

From your target project root:

```bash
bash /full/path/to/On_Board/setup-project.sh
```

Or pass the target project explicitly:

```bash
bash /full/path/to/On_Board/setup-project.sh /full/path/to/your/project
```

The script adds local agent rules and hook files for supported clients:

- `CLAUDE.md` for Claude Code
- `AGENTS.md` for Codex
- `.cursorrules` for Cursor
- `.agent/rules/on-board-agent-memory.md` for AntiGravity
- hook config/scripts for Claude Code, Cursor, and Codex where supported

Runtime memory stays in `.agent-mem/` and should remain gitignored.

## 4. Initialize project memory

For a new project:

```text
memory_init({
  "description": "What this project is",
  "tech_stack": "Python / Node / etc."
})
```

For an existing project, use bootstrap instead:

```text
memory_bootstrap({
  "agent_name": "main-codex",
  "description": "What this project is",
  "current_task": "What agents should work on next"
})
```

`memory_bootstrap` scans common project files, recent git history, and structure, then seeds initial memory.

## 5. Start every agent session with onboard

In each MCP-aware agent chat:

```text
memory_onboard({
  "agent_name": "dev-main",
  "agent_platform": "codex",
  "agent_role": "main",
  "task_focus": "Short note about the current task"
})
```

Use a stable `agent_name`. Do not put dates or session IDs in it.

Valid `agent_platform` values include:

- `claude-code`
- `claude-desktop`
- `cursor`
- `codex`
- `antigravity`
- `windsurf`
- `other`

## Normal workflow

After onboarding:

```text
memory_write(...)       # after meaningful actions
memory_checkpoint(...)  # every 10-15 minutes on long work
memory_handoff(...)     # before ending the session
```

For cross-agent work:

```text
memory_create_ticket(...)
memory_claim_ticket(...)
memory_submit_ticket(...)
memory_review_ticket(...)
```

If a memory tool says `NOT ON BOARD`, call `memory_onboard` again and retry. Handoff, submit, review, and compaction flows may intentionally end the active session.

## Quick health check

Use:

```text
memory_status()
memory_doctor()
memory_get_briefing({"mode": "brief"})
```

If setup is correct, agents should see project memory, active agents, recent notes, and open tickets.
