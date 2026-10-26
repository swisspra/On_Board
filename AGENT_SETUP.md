# On Board Agent Setup Guide

Use this file when a user asks an agent to help install or explain On Board. It
is a pointer to the canonical setup, not a second setup recipe: install the skill
and let it configure the project. Do not improvise an alternative path.

## Canonical setup (skill-first)

Prerequisites, stated separately so nothing is hidden:

- **Node.js 22.20 or later** to run `npx skills`.
- **Python 3.11 or later** for the skill's `scripts/setup.py` helper; where the
  machine's `python3` is older, run the helper once with
  `uv run --no-project --python 3.12 scripts/setup.py …`.
- **Python 3.10 or later**, plus `uv` or `pipx`, for the `onboard-memory-mcp`
  runtime (reused if already installed).

1. Install the skill into the target project:

   ```bash
   npx skills add 'swisspra/On_Board#feat/skill-first-install' --skill onboard
   ```

   This is the v4.2.0 preview source. After it merges into `main`, use
   `npx skills add swisspra/On_Board --skill onboard`. `npx` installs the skill
   through the skills CLI, not a separate On Board npm package or the Python
   runtime. PyPI currently provides 4.1.1; preserve a working installation and
   do not claim the preview's native resources until a 4.2+ runtime is verified.

2. Reload the agent so it discovers the `/onboard` skill (reopen the window or
   start a new session).
3. Run the skill with this prompt:

   ```text
   Using /onboard, set up On Board for this project. Keep existing memory and other MCP servers unchanged.
   ```

4. Trust and restart the MCP client so it loads the new `agent-memory` server.

The skill reuses one shared `onboard-memory-mcp` runtime: it resolves an existing
executable first and installs the shared runtime only when none is present
(reuse, not a per-project install), then configures exactly one project (the one
you run it in) for exactly one chosen client. It writes only that project's own
MCP config: a project `.mcp.json` (Claude Code), `.cursor/mcp.json` (Cursor), or
the trusted project `.codex/config.toml`. It never edits global Claude, Cursor, Codex, Windsurf, VS Code, or
Antigravity config files -- global client configuration requires separate,
explicit user consent.

## Canonical references

Read these instead of inventing a flow:

- `skills/onboard/SKILL.md` -- the skill entry point.
- `skills/onboard/references/install.md` -- install/config reference: 
  prerequisites, client selection, the `scripts/setup.py` helper, and its
  operational JSON statuses `configured`, `unchanged`, `needs_configuration`,
  `conflict`, and `error`.
- `skills/onboard/references/protocol.md` -- the board protocol agents follow.
- `docs/SETUP.md` -- manual, package-manager, and clone/script paths.

## Setup is not memory initialization

- Nothing writes, moves, or migrates `.agent-mem/`. Existing memory is preserved
  exactly as it was.
- Existing MCP servers, instructions, and hooks in the project config are
  preserved; the helper merges rather than replaces.
- If the project already has `.agent-mem/`, do not bootstrap it just because
  setup ran again.

## After setup

Setup ends when the client is trusted/restarted and the `agent-memory` tools are
visible in a live session — that is **Ready**. Setup never initializes or joins a
board: no `memory_init`, `memory_bootstrap`, or `memory_onboard` call and no
`memory_doctor` health check is part of installation.

Initializing or joining happens only for a **separate, explicit request to start
work**, and only at that point:

- Existing project with `.agent-mem/` already present: join with
  `memory_onboard(...)`; never bootstrap it again.
- New or empty project: `memory_bootstrap(...)` for an existing repo, or
  `memory_init(...)` for a blank one, then `memory_onboard(...)`.

`memory_doctor()` is a board diagnostic for odd behavior, not a setup gate.

Use a specific `agent_role` when onboarding: `main`, `lead`, `planner`,
`worker`, `tester`, `reviewer`, `reporter`, `subagent`, `utility`. Use `main`,
`lead`, or `reviewer` only for agents that should coordinate or resolve stuck
tickets.

## Source-install safety boundary

Only when the user works from a clone of the On Board source:

- `bash setup-project.sh /path/to/project` and `bash doctor.sh /path/to/project`
  are the supported source commands; `doctor.sh` is read-only.
- Never run `setup-project.sh` with the On Board checkout itself as the target
  project. Verify source hygiene with `bash doctor.sh --self` instead.
- Linked-project helpers (`--list-linked`, `--refresh-linked`) only manage
  projects already registered in `<On_Board>/.onboard/linked-projects.json`,
  which is local machine state and gitignored -- do not commit it.
- `setup-project.sh` fingerprints core memory files before and after setup and
  writes `<project>/.onboard/migration-report.json`; it fails if they changed.
  It never initializes memory content, and it never writes, moves, or deletes
  `.agent-mem/`.

## If something fails

Follow `doctor.sh`'s `Next:` section rather than blindly rerunning setup: the
script intentionally does not overwrite custom files, so existing MCP configs and
hook files may need manual cleanup first. Do not use end-turn/`Stop` hooks to
write memory; write memory intentionally with `memory_write`, `memory_checkpoint`,
`memory_handoff`, and the ticket tools.
