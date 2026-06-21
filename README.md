# On Board

> **The shared brain for a multi-agent dev team.**
> Tickets, persistent memory, and a QA gate that catches what the coder
> agent misses. Vendor-neutral. Local-first. Open source.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-6ee7b7)]()
[![A2A interop](https://img.shields.io/badge/A2A-adapter%20on%20roadmap-8ea0c2)]()
[![MCP Badge](https://lobehub.com/badge/mcp/swisspra-on_board)](https://lobehub.com/mcp/swisspra-on_board)

---

## What this is

A self-hosted MCP server that turns Claude Desktop, Claude Code, Codex,
Cursor, and Antigravity into **one engineering team that actually
remembers**. Every agent — regardless of platform — joins the same
project memory, claims tickets from the same queue, and submits work to
the same review gate.

```
spec  →  build  →  test in a real browser  →  review  →
reject + fix instructions  →  retest  →  approve
```

This is the loop a human engineering team runs. On Board lets a team of
AI agents run it.

## Why this exists

I built this because

1. **Every new chat is amnesia.** I was re-explaining the codebase, the
   conventions, and "the bug we already fixed last Tuesday" to every new
   session.

2. **One model wrote the code and "reviewed" it.** There was no second
   pair of eyes. Bugs shipped because the same agent never caught its
   own mistakes.

3. **My Claude Desktop Pro quota was the bottleneck**, not the work. I had three
   Pro accounts sitting idle while one throttled.

On Board fixes all three:

- **Persistent memory** — `.agent-mem/` in the repo, gitignored. The next
  session reads a briefing and picks up cold.
- **Independent review gate** — a separate agent runs the UI in a real
  browser, captures screenshots, and submits PASS/FAIL with evidence.
  Rejected tickets come back with fix instructions, not death.
- **Multi-account orchestration** — when one Claude Pro seat throttles,
  the orchestrator routes the next ticket to another. The whole stack
  runs on seat plans, not pay-per-token APIs.

## Proof

A real production app — a small-business inventory + sales + production
batches + FIFO cost accounting system — was built using this loop.

```
107 tickets resolved · 232 agent handoffs · 212 submit ↔ review pairs
16 reject → fix → retest cycles · 100% bug-fix verify rate
11.5 active hours over 49.5 calendar hours
$60/month total stack cost · 0 lines of code typed by the human
```

The full case study with screenshots, cost breakdown, and a worked example
of a real ORM bug the QA loop caught (Drizzle correlated subquery → 25
active minutes from bug report to deployed fix) by requested.

## Who this is for

- **Solo devs** running parallel agents and losing context between sessions
- **Engineering managers** with a backlog of small internal tools that
  nobody has time to staff
- **Indie hackers / agency owners** delivering CRUD apps and ops tools
  for SMBs
- **A2A-curious teams** looking for a memory + accountability layer that
  speaks MCP today and A2A tomorrow

This is NOT for: autonomous AI advocates who want a "no-human-in-the-loop"
agent swarm. By design, On Board keeps a human in the loop — as the
**acceptance tester**, not the line-by-line code reviewer. The QA agent
is the per-merge gate; the human is the running-app gate. In the case
study, the human approved roughly 30% of merges directly (the critical
ones), spot-read ~10% of the source code, and ran end-to-end manual
acceptance testing of the whole app before declaring it production-ready.
Trust is earned per project.

---

## Quick start

```bash
git clone https://github.com/swisspra/On_Board.git
cd On_Board
uv sync
uv run python server.py
```

Add to your MCP client config:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "uv",
      "args": ["run", "--directory", "/full/path/to/On_Board", "python", "server.py"],
      "env": {
        "AGENT_PROJECT_DIR": "/full/path/to/your/project",
        "AGENT_MEM_CONTEXT_DIRS": "/path/to/docs:/path/to/specs"
      }
    }
  }
}
```

`AGENT_MEM_CONTEXT_DIRS` is optional. Remove it if you do not need external
reference folders; keep it when agents should browse shared docs/specs with
`memory_context_dirs` and `memory_context_read`.

In your first chat with any MCP-aware agent (Claude Desktop, Claude Code,
Cursor, Codex, Antigravity):

```
memory_onboard(
  agent_name="dev-main",
  agent_platform="claude-code",
  agent_role="main"
)
```

That's it. The agent now sees the project briefing, the open tickets, the
recent memory, and the protocol it should follow. Every subsequent action
is stamped with its identity.

Full client setup (Claude Desktop, Cursor, Codex, AntiGravity): see
[SETUP.md](.SETUP.md).

---

## The loop in one example

```
1. SPEC
   opus-testcase reads requirement → writes 5–20 acceptance tickets
   with explicit pre/post conditions.

2. BUILD
   dev-track-2 claims a ticket → implements in src/ → submits with
   file diff + test plan.

3. TEST
   Jonhny-tester picks up submission → runs UI in Chromium → captures
   screenshots → submits PASS or FAIL with evidence.

4. REVIEW
   desktop-opus4.7 (or the human) checks evidence → approves OR rejects
   with concrete fix instructions.

   If rejected → ticket reopens → dev-track-2 patches → Jonhny retests
   → loop closes.
```

When this loop runs cleanly, a single ticket goes from `open` to "shipped
to production" in 4–15 minutes of agent time. The human checks in at the
end, not in the middle.

---

## Tools (29 MCP tools, 5 buckets)

| Bucket | Tools |
|---|---|
| **Agent lifecycle** | `memory_onboard`, `memory_agent_join`, `memory_handoff`, `memory_checkpoint`, `memory_get_briefing` |
| **Ticket queue** | `memory_create_ticket`, `memory_claim_ticket`, `memory_submit_ticket`, `memory_review_ticket`, `memory_cancel_ticket`, `memory_terminate_ticket`, `memory_list_tickets` |
| **Persistent memory** | `memory_write`, `memory_read`, `memory_search`, `memory_search_vector`, `memory_links`, `memory_pin` |
| **Project context** | `memory_init`, `memory_bootstrap`, `memory_status`, `memory_doctor`, `memory_update_state`, `memory_context_dirs`, `memory_context_read` |
| **Compaction** | `memory_prepare_compaction`, `memory_compact`, `memory_token_usage`, `memory_search_archive` |

Full reference: [TOOLS.md](.TOOLS.md).

---

## What makes this different from other memory MCPs

Several memory MCP servers exist. I didn't know that when I started — I
built this for myself. But the difference matters:

| Most memory MCPs | On Board |
|---|---|
| Vector store of conversation history | Memory **AND** a ticket queue **AND** a review gate |
| Single-agent retrieval | Multi-agent identity, KIA detection, handoff protocol |
| No notion of work state | `open → claimed → submitted → reviewed → closed` lifecycle |
| No QA gate | Independent agent runs the UI, captures evidence, PASS/FAIL |
| One-vendor focus | Tested on 7+ platforms simultaneously |

The unique thing here is the **loop**, not the memory. Memory is the
substrate that makes the loop possible.

---

## Honest gaps

- **No fully autonomous mode.** A human is in the loop — as the acceptance
  tester. By design.
- **No cross-project memory yet.** Each `.agent-mem/` is per-repo.
  Federation is on the wishlist (see below) — no committed date.
- **No interactive operator web console** (claim/review/dispatch from a
  browser). There IS a live observability dashboard with agent grouping,
  platform colors, orphan ticket detection, and idle indicators (since v3.0).
  An interactive console is on the wishlist.
- **No public REST API.** It's all MCP. Other agents can join if they
  speak MCP. An A2A adapter is on the wishlist and would partially
  address this.

---

## A2A interop (wishlist, no date)

A2A adapter is on the wishlist (no committed date — see roadmap section
below). Mapping when shipped:

- A2A `context_id` ↔ On Board active session
- A2A `tenant` ↔ `AGENT_PROJECT_DIR`
- A2A `Task` ↔ derived read-only projection of an On Board ticket
- A2A `INPUT_REQUIRED` ↔ awaiting reviewer
- A2A `REJECTED` ↔ **never mapped** from On Board reviewer-reject (which
  is non-terminal and retry-friendly; A2A REJECTED is terminal)

On Board would expose A2A as an output format, not an input format. The
MCP session gate would remain the entry point.
for the full design discussion.

---

## Project structure (runtime data)

```
your-project/
├── .agent-mem/                runtime memory, gitignored
│   ├── project.json
│   ├── agents.json            agent registry (identity, status, KIA)
│   ├── memories.json
│   ├── state.json             project phase, owner, design defaults
│   ├── archive.json
│   ├── digests.json
│   ├── checkpoints/
│   └── tickets/
│       ├── _index.json
│       ├── TK-<id>.md         the spec
│       ├── TK-<id>-submit.md  dev submission
│       ├── TK-<id>-review.md  QA / reviewer verdict
│       └── closed/
```

Everything is plain text or JSON. You can `cat` your way through the
project's full history. No vector DB lock-in, no opaque embeddings — just
files an audit can read.

---

## What's already shipped (v3.5.2, 2026-05-09)

On Board has been iterating in production with weekly releases for the
last ~4 weeks. Highlights from the CHANGELOG:

- **v3.5.x** — One-call `memory_onboard`, XML protocol tags, `memory_links`,
  data-integrity `memory_doctor`, pytest workflow harness, `uv` install
- **v3.2** — Briefing modes (brief/normal/deep/handoff-only), opt-in local
  vector search, ranked memory_search
- **v3.1** — Ticket schema enforcement (`target_url`, `scope`,
  `required_fields`), agent rejoin dedup
- **v3.0** — Live dashboard (agent grouping, platform colors, orphan
  ticket detection, idle indicators), heartbeat tracking, idle auto-KIA
- **Always** — First-class on every platform with an MCP client (Claude
  Desktop, Claude Code, Cursor, Codex, AntiGravity)
- **Parallel agent dispatch** — three dev tracks + a separate QA squad
  run concurrently (see pitch deck Gantt). Practical ceiling is "how
  many AI clients can your machine run at once" — on M4 MacBook Pro
  that's a small number, not a protocol-side problem.
- **Role / ticket templates** — opus-testcase, dev-track-N, Jonhny-tester,
  desktop-opus, plus acceptance-test patterns and ticket schema. Working
  in the case study since v1. Not yet packaged for outside drop-in use,
  but the role names and ticket schema are documented enough that you
  can replicate with your own prompts. **Recommended for best result**.

Full CHANGELOG: [CHANGELOG.md](./CHANGELOG.md).

---

## License

Apache-2.0. Free to use, fork, modify, redistribute, build commercial
products on. No restrictions on use.

---
to start, the README mention of "Q3 templates" is the area that needs
the most early collaborators.
