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

## Option 1: Agent setup

Use this if you already have an agent available.

Ask the agent to read:

```text
/full/path/to/On_Board/AGENT_SETUP.md
```

The agent-facing guide explains what On Board is, what commands are safe to
run, and where human confirmation is still needed.

## Option 2: Script setup

Use this for the normal setup path.

```bash
git clone https://github.com/swisspra/On_Board.git
cd On_Board
bash setup-project.sh /full/path/to/your/project
bash doctor.sh /full/path/to/your/project
```

This does six things:

- Installs/updates the central On Board `.venv` with `uv sync --inexact`
- Adds project rules and hooks for supported agents
- Generates a local MCP config at `/full/path/to/your/project/.onboard/mcp.generated.json`
- Generates an agent setup control guide at `/full/path/to/your/project/.onboard/AGENT_CONTROL.md`
- Generates a dashboard launcher at `/full/path/to/your/project/.onboard/run-dashboard.sh`
- Registers the project in the central `.onboard/linked-projects.json`

`doctor.sh` is read-only. It checks the generated config, rules, hooks, and
runtime path before you open the MCP client.

The linked-project registry is local machine state and is gitignored. It lets
On Board remember which projects point at this central checkout without scanning
your filesystem.

Maintainers can check the public source checkout itself with:

```bash
bash doctor.sh --self
```

That command verifies source hygiene only. Do not target the On Board checkout
with `setup-project.sh`; run setup against the project that should use On Board.

## Add the generated MCP config to your client

Open:

```text
/full/path/to/your/project/.onboard/mcp.generated.json
```

If you customize your own copy, keep it at:

```text
/full/path/to/your/project/.onboard/mcp.json
```

Some clients accept this JSON directly. Others require you to merge it into
their own MCP settings file or add it through a CLI.

The config will look like this, with real paths filled in:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "/full/path/to/On_Board/.venv/bin/python",
      "args": [
        "/full/path/to/On_Board/server.py"
      ],
      "env": {
        "AGENT_PROJECT_DIR": "/full/path/to/your/project",
        "AGENT_MEM_CONTEXT_DIRS": "/path/to/docs:/path/to/specs"
      }
    }
  }
}
```

This is the recommended local setup: install/update with `uv sync --inexact`,
run with the pinned Python inside `.venv`. `--inexact` keeps any already
installed development extras, such as pytest, instead of pruning the environment
back to runtime-only dependencies. Avoid using `uv run` or `uvx` as the daily
MCP startup command when your client loads many MCP servers; they can add enough
startup work to hit client timeouts.

`AGENT_PROJECT_DIR` is required. It tells On Board which project owns the `.agent-mem/` memory folder.

`AGENT_MEM_CONTEXT_DIRS` is optional. Add it when agents should read extra docs or specs outside the project with `memory_context_dirs` and `memory_context_read`.

The generic template is available in `configs/local-venv-mcp.json`.

For development or quick debugging, `configs/uv-run-mcp.json` keeps the older
`uv run --directory` style. Do not use it as the default local MCP startup
command if your client loads many MCP servers.

The setup script also adds local agent rules and hook files for supported clients:

- `CLAUDE.md` for Claude Code
- `AGENTS.md` for Codex
- `.cursorrules` for Cursor
- `.agent/rules/on-board-agent-memory.md` for AntiGravity
- session-start hook config/scripts for Claude Code, Cursor, and Codex where supported

On Board no longer installs end-turn `Stop` hooks. Current agent clients can
run `Stop` hooks after every turn; writing memory there creates noise and can
make agents re-onboard too often. If you used an older setup, remove old
On Board `Stop` / `stop` hook entries from the project hook config.

Runtime memory stays in `.agent-mem/` and should remain gitignored.

If the project already has `.agent-mem/`, `setup-project.sh` treats it as an
existing-memory migration. It does not write, move, or delete memory files. It
fingerprints core memory files before and after setup, then writes proof to:

```text
/full/path/to/your/project/.onboard/migration-report.json
```

If those core files change during setup, the script fails.

For existing-memory projects, do not bootstrap again unless you intentionally
want to re-seed project metadata. After setup, use:

```text
memory_onboard()
memory_doctor()
```

If an agent needs to inspect or change On Board setup later, point it to:

```text
/full/path/to/your/project/.onboard/AGENT_CONTROL.md
```

To open the dashboard after memory is initialized:

```bash
bash /full/path/to/your/project/.onboard/run-dashboard.sh
```

## Check setup

Before the MCP client can see On Board tools, use:

```bash
bash /full/path/to/On_Board/doctor.sh /full/path/to/your/project
```

After the MCP client can see On Board tools, use:

```text
memory_doctor()
```

## Update an existing install

Update the central On Board checkout first:

```bash
cd /full/path/to/On_Board
bash update.sh
```

`update.sh` shows linked projects it knows about. It does not refresh project
files by default.

To list linked projects:

```bash
bash setup-project.sh --list-linked
bash doctor.sh --list-linked
bash update.sh --list-linked
```

To refresh every linked project after an update:

```bash
bash update.sh --refresh-linked
```

This preserves each project's last registered hook mode.

Equivalent manual commands:

```bash
bash setup-project.sh --all-linked
bash doctor.sh --all-linked
```

`setup-project.sh --all-linked` also preserves each project's registered hook
mode. Add `--hooks safe` or `--hooks off` only when you intentionally want to
override every linked project.

To refresh one project:

```bash
bash /full/path/to/On_Board/setup-project.sh /full/path/to/your/project
bash /full/path/to/On_Board/doctor.sh /full/path/to/your/project
```

This regenerates `.onboard/` config, startup hooks, and rules. It does not
delete `.agent-mem/` project memory.

## Option 3: Advanced manual setup

Use this if you do not want to run `setup-project.sh`.

Install On Board once:

```bash
git clone https://github.com/swisspra/On_Board.git
cd On_Board
uv sync --inexact
```

Add this MCP server to your client, replacing both paths:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "/full/path/to/On_Board/.venv/bin/python",
      "args": ["/full/path/to/On_Board/server.py"],
      "env": {
        "AGENT_PROJECT_DIR": "/full/path/to/your/project"
      }
    }
  }
}
```

Then add project rules/hooks yourself, or run only the project preparation step:

```bash
bash /full/path/to/On_Board/setup-project.sh /full/path/to/your/project
```

The rule is simple: install On Board once, point each project at the same
On Board folder, and let `AGENT_PROJECT_DIR` choose the project memory.

## Initialize project memory

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

## Start every agent session with onboard

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
