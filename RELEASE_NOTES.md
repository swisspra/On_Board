# v4.2.0 — Skill-first setup and native MCP context

Install the `onboard` skill in the target project:

```bash
npx skills add swisspra/On_Board --skill onboard
```

`npx` runs the skills CLI from npm; On Board's skill is distributed from Git.
No separate On Board npm package is required.

Reload the agent, then ask:

```text
Using /onboard, set up On Board for this project. Keep existing memory and other MCP servers unchanged.
```

## One project, one selected client, one shared runtime

The skill reuses a working runtime or provisions one through an existing
supported package manager. It merges the selected project's Claude Code,
Cursor, or Codex entry, preserving other servers and existing memory. Client
trust/restart is distinct from installing the skill; configuration alone is not
proof of a live connection. Starting work and initializing memory require a
separate explicit request.

The skills CLI requires Node.js 22.20+. The native-configuration helper requires
Python 3.11+, or a one-time Python 3.12 invocation through uv. The MCP runtime
remains Python 3.10+ on the existing MCP 2.3 dependency line.

## Native read surfaces

- `onboard://project` — bounded project description and tech-stack previews.
- `onboard://tickets` — whole-board counts and at most 50 open ticket summaries.
- `onboard://memory/summary` — memory/type/pin counts and at most 10 entry summaries.

All return JSON without initializing a board or returning raw memory bodies.
Static catalogs are privately cacheable for 60 seconds; all resource reads have
private zero-TTL hints.

Subscription-capable clients receive coalesced invalidation hints when shared
files change. They re-listen and refetch after reconnecting; there is no replay
or model-wake guarantee. Existing `memory_wait_for_event`, its persisted snapshot
cursor, role checks, idle budgets, and heartbeat locking are unchanged. No MCP
App or external A2A bridge is introduced.

## Distribution and upgrades

Wheels and sdists contain both native runtime modules, not the Git-distributed
skill or private project state. Source updates preserve the canonical skill
layout needed to set up another project and reject skill-only update targets.
The `--version` command reports installed package identity and exits before
starting stdio service.

Update the skill with `npx skills update -p onboard`. Runtime upgrades remain
separate and manager-matched. Preserve a working 4.1.1/source setup unless its
replacement is explicitly requested. Native resources require a verified 4.2+
runtime; a skill-only update does not add them to an older runtime.

Source installations can select the
[4.2.0 release tag](https://github.com/swisspra/On_Board/tree/v4.2.0);
see the [source runtime guide](https://github.com/swisspra/On_Board/blob/main/docs/SETUP.md#runtime-from-source-optional).
Do not replace a working shared runtime merely because the skill was updated.

## Safety and verification boundaries

The setup helper refuses tracked/conflicting configuration and indeterminate
Git tracking or ignore queries before writing. Existing unrelated servers,
Codex model/provider settings, and memory remain untouched.

Installed-wheel verification exercises real stdio in modern and legacy modes,
read-only uninitialized resources, an external-process atomic write followed by
subscription/refetch, reconnect/current-state refetch, package identity, and
ordinary EOF shutdown. These checks use synthetic projects, not a real board.
Native UI trust/restart and model wake-up remain host-dependent; configuration
alone is not Ready. No new Windows multi-writer guarantee is made.
