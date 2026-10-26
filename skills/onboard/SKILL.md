---
name: onboard
description: Use when installing, configuring, updating, or diagnosing On Board for a project, or starting work in a project already using On Board shared memory.
---

# On Board

On Board is a shared multi-agent memory server. It keeps project state under
`.agent-mem/` and is reached over MCP under the server key `agent-memory`.

## Choose the matching path

**Install, configure, repair, update, or diagnose On Board → read `references/install.md`.**

It runs in order: pick the project and the MCP client, reuse or install the
`onboard-memory-mcp` runtime, write only the selected client's project config,
then report honest status (configured, or still waiting for restart/trust).

Installation is not memory initialization. Do not call `memory_onboard`,
`memory_bootstrap`, or `memory_init` as a setup step or a health check, and do
not create or migrate `.agent-mem/` while installing. Offer to start the project
afterwards — starting is a separate, explicit request.

**Already connected and initialized, doing project work → read `references/protocol.md`.**

It carries the session protocol: join, read the briefing, write after meaningful
actions, checkpoint, and hand off before you stop. If the project has no
`.agent-mem/` yet, or the On Board tools are not visible in this session, go back
to `references/install.md`.

## Primary commands

Install or refresh this skill for a project. Project scope by default; the skills
CLI manages client links and update tracking. For this v4.2.0 preview:

```bash
npx skills add 'swisspra/On_Board#feat/skill-first-install' --skill onboard
```

After these changes merge into `main`, the normal command is:

```bash
npx skills add swisspra/On_Board --skill onboard
```

On `main`, update the skill itself with the command below. For a preview refresh,
rerun its branch-pinned install command. Neither operation upgrades the runtime:

```bash
npx skills update -p onboard
```
