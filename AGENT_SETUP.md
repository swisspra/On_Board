# On Board Agent Setup Guide

Use this file when a user asks an agent to help install or explain On Board.

## What This Is

On Board is a shared memory MCP server for multi-agent project work.

Install On Board once in one central folder. Each project points to that same
On Board folder, but gets its own memory through `AGENT_PROJECT_DIR`.

Project memory lives in:

```text
<project>/.agent-mem/
```

Local generated setup files live in:

```text
<project>/.onboard/
```

## Safe Setup Flow

Ask the user for the target project path, then run:

```bash
cd /path/to/On_Board
bash setup-project.sh /path/to/project
bash doctor.sh /path/to/project
```

`setup-project.sh`:

- Runs `uv sync --inexact` for the central On Board checkout
- Creates or updates project rules and session-start hooks
- Generates MCP config at `<project>/.onboard/mcp.generated.json`
- Generates agent setup control at `<project>/.onboard/AGENT_CONTROL.md`
- Generates a dashboard launcher at `<project>/.onboard/run-dashboard.sh`
- Registers the project in `<On_Board>/.onboard/linked-projects.json`
- Does not initialize memory content

`doctor.sh`:

- Read-only
- Checks the central runtime
- Checks generated MCP config paths
- Checks project rules and hooks
- Reports the next step

Linked project helpers:

```bash
bash setup-project.sh --list-linked
bash doctor.sh --list-linked
bash update.sh --list-linked
```

To refresh all registered projects after updating On Board:

```bash
bash update.sh --refresh-linked
```

This preserves each project's last registered hook mode. Do not override hook
mode for all projects unless the user explicitly asks.

The linked-project registry is local and gitignored. Do not commit it.

## MCP Client Step

Tell the user to use this generated config as the source for their MCP client:

```text
<project>/.onboard/mcp.generated.json
```

Some clients can use the JSON directly. Some clients require merging it into a
client-specific settings file or adding it through a CLI.

Do not silently edit global Claude, Cursor, Codex, Windsurf, VS Code, or
Antigravity config files unless the user explicitly asks for that.

If the user asks how to inspect or change On Board setup later, point their
agent to:

```text
<project>/.onboard/AGENT_CONTROL.md
```

## Manual Setup Alternative

If the user does not want to run the setup script:

```bash
cd /path/to/On_Board
uv sync --inexact
```

Then ask them to add this MCP server manually:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "/path/to/On_Board/.venv/bin/python",
      "args": ["/path/to/On_Board/server.py"],
      "env": {
        "AGENT_PROJECT_DIR": "/path/to/project"
      }
    }
  }
}
```

## First Agent Step

After the MCP client restarts and On Board tools are visible, tell the agent to
run:

```text
memory_bootstrap(...)
memory_onboard(...)
```

Use `memory_init(...)` instead of `memory_bootstrap(...)` only for a new or
empty project.

Use a specific `agent_role` when onboarding:

```text
main, lead, planner, worker, tester, reviewer, reporter, subagent, utility
```

Use `main`, `lead`, or `reviewer` only for agents that should coordinate or
resolve stuck tickets.

## Dashboard

After project memory exists, the user can run:

```bash
bash /path/to/project/.onboard/run-dashboard.sh
```

The launcher points back to the central On Board checkout, so projects do not
need their own dashboard copy.

## Important Runtime Rule

Use `uv sync --inexact` for install/update. `--inexact` avoids pruning already
installed dev/test extras from `.venv`. Use the pinned Python inside `.venv` for
MCP runtime:

```text
/path/to/On_Board/.venv/bin/python /path/to/On_Board/server.py
```

Do not use `uvx` or `uv run` as the default daily MCP startup command when the
user has many local MCP servers. It can be slow enough to trigger client startup
timeouts.

## Important Hook Rule

Do not use turn-scoped `Stop` / end-turn hooks to write memory or mark agents
inactive. Current Claude Code and Codex `Stop` hooks run every turn, so writing
memory there creates noise and marking agents KIA forces repeated onboarding.

Use session-start hooks only for lightweight context. Agents should write memory
intentionally with `memory_write`, `memory_checkpoint`, `memory_handoff`, and the
ticket tools.

## If Something Fails

If `doctor.sh` fails, rerun:

```bash
bash /path/to/On_Board/setup-project.sh /path/to/project
bash /path/to/On_Board/doctor.sh /path/to/project
```

If the MCP client still cannot see tools, check that its config uses:

```text
command = /path/to/On_Board/.venv/bin/python
args    = /path/to/On_Board/server.py
env     = AGENT_PROJECT_DIR=/path/to/project
```

Then restart the client.
