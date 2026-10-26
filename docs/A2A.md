# A2A design note

Last checked: 2026-07-16

This is a research note about the external A2A protocol (a2a-protocol.org).
Status update 2026-07-27: On Board v4.0.0 ships its own native agent-to-agent
wake loop (`memory_wait_for_event`) following exactly the shape recommended
below — On Board stays the coordination core. An external A2A-protocol
bridge remains unshipped roadmap.

## Three signals, three layers (native, no external bridge)

On Board's local agent-to-agent story is three distinct things. They are easy to
conflate, so keep them separate:

- **Resource invalidation** — MCP resource notifications. All three native
  resources are watched (`onboard://project` too, since `project.json` is
  mutable): while at least one listener is attached, a process-local watcher
  stats the shared board files every 2 s; when one changes, clients that support
  and honor resource subscriptions receive a coalesced `ResourceUpdated` hint.
  It means "re-read this resource." It is capability-dependent, carries no
  payload, has no durable log, and never wakes a model. Reads are never cached
  (private `ttlMs 0`); only the static response catalogs carry `ttlMs 60000`.
- **Cursor-backed (portable) A2A wait** — `memory_wait_for_event`. The wait keeps
  a persisted snapshot cursor in the agent's own watch file, so a re-arm after a
  gap returns the pending snapshot diff instead of waking empty. It is a diff
  between snapshots, not a lossless transition log: intermediate transitions
  coalesce and can be missed, and there is no event log or replay. Even so, the
  wait is what makes the board push-capable without a human relay.
- **Model wake-up** — the listening loop that actually resumes a parked agent
  when `memory_wait_for_event` returns. This is the only layer that continues
  agent work; resource notifications never wake a model, so native hints alone
  do not guarantee a host's model wakes.

MCP resources and their notifications are for cheap context refresh inside one
client. The cursor-backed wait is the coordination half. Neither is an external
A2A transport — that remains unshipped roadmap below.

## Current protocol read

A2A and MCP solve different parts of the same system. MCP connects an agent to
tools and resources. A2A is for communication between agents. The official A2A
docs describe them as complementary protocols, with many systems using A2A
between agents and MCP inside each agent.

For On Board, the useful shape is slightly different:

```text
agent -> MCP On Board tools -> project room / tickets / handoffs
optional A2A bridge -> external agent-to-agent transport
```

On Board should stay the coordination core. A2A can become a transport or bridge
later, but it should not replace onboarding, ticket ownership, or review state.

Sources:

- https://a2a-protocol.org/latest/topics/a2a-and-mcp/
- https://a2a-protocol.org/latest/whats-new-v1/

## Mapping direction

If an A2A bridge is added later, map On Board state outward:

| On Board | A2A v1.0 candidate |
|---|---|
| Project selected by `AGENT_PROJECT_DIR` | A2A context or application boundary |
| Onboarded agent session | Agent card metadata plus active conversation context |
| Ticket | A2A task projection |
| Ticket claim | Task assignment / working state |
| Submit for review | Task artifact plus status update |
| Reviewer asks for fixes | `TASK_STATE_INPUT_REQUIRED` or a new follow-up task |
| Approve and close | `TASK_STATE_COMPLETED` |
| Cancel | `TASK_STATE_CANCELED` |
| Force terminate | `TASK_STATE_FAILED` or `TASK_STATE_CANCELED`, depending on reason |

Do not map On Board reviewer rejection to `TASK_STATE_REJECTED` by default.
In A2A v1.0, `TASK_STATE_REJECTED` means the agent decided not to perform the
task and the state is terminal. In On Board, rejection normally means "fix this
and submit again." That is closer to input-required or reopened work.

## A2A v1.0 details that matter

- Task states now use prefixed enum names such as `TASK_STATE_COMPLETED`,
  `TASK_STATE_INPUT_REQUIRED`, and `TASK_STATE_REJECTED`.
- Agent cards changed in v1.0. Discovery should read `supportedInterfaces`
  and capability fields instead of older single-endpoint fields.
- Task listing uses cursor pagination.
- Error handling changed to `google.rpc.Status` style payloads.
- The v1.0 Part object is richer than plain text messages, so an eventual
  bridge should preserve artifacts and evidence instead of flattening every
  update into chat text.

## Recommended stance

Keep the first A2A experiment manual and local:

1. Agents still call `memory_onboard` first.
2. On Board exposes a simple room/ticket view.
3. A bridge can publish selected ticket events into A2A.
4. Human review remains in On Board until the workflow proves itself.

That keeps the current MCP workflow strong while leaving room for A2A transport
experiments.
