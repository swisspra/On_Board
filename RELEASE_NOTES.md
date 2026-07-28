# v4.0.1 — the polish v4.0.0 needed

Patch release. Everything in it was found by *running* v4 between two Claude
Desktop instances and a Codex agent, not by reading it.

- **`memory_unpin`** and **`retracts=`** — `priority=3` means *never compact
  this*, not *important*, and until now there was no way to undo one. A warning
  later found to be wrong stayed pinned at critical, so every joining agent read
  a bug that did not exist as the first thing on the board.
- **Rejection warnings auto-demote** once their ticket closes, cancels or is
  terminated. A human's hand-written warning about the same ticket is left alone.
  Forward-only: existing pinned warnings are not backfilled — use `memory_unpin`.
- **Idle budget with STAND-DOWN** — a parked listener now stops on its own after
  `idle_budget_min` (default 15) instead of re-arming forever and looking wedged.
- **Board snapshots are mtime-gated** — 25 poll ticks cost one JSON parse instead
  of 25.
- **Submitting no longer hands off an agent that owes a review**, which used to
  strand a peer's submission with nobody on board to adjudicate it.
- Ticket `.md` files no longer report `TicketStatus.SUBMITTED` forever, and the
  server declares its own `website_url` so clients stop borrowing a stranger's
  branding.

Full detail in [CHANGELOG.md](./CHANGELOG.md).

---

# v4.0.0 — Agent-to-Agent: the listening half of On Board

The board is no longer pull-only. `memory_wait_for_event` lets an agent park
inside one tool call and wake when a peer creates a ticket, changes a status,
or assigns work — verified live across Claude Desktop x Claude Desktop and
Claude x Codex (GPT), including a full reject -> fix -> resubmit cycle closed
with zero human relay.

Highlights:

- `memory_wait_for_event` + `listen` prompt: check-before-block, one wake
  drains the queue, agents never wake on their own actions.
- Role gate (*completed != success*): the executor's terminal move is
  `submitted`; only the owner or a main/lead/reviewer closes. Solo use stays
  possible via explicit `allow_self_review=True`, permanently stamped
  SELF-REVIEWED in the audit.
- Review verdicts travel: `review_notes` and `fix_instructions` ride the wake
  payload, so a rejected worker can retry without a human relaying anything.
- `stay_active=true` on submit keeps a listener on board to catch the verdict.
- Concurrency hardening for simultaneous writers: advisory board lock on
  ticket mutations and per-process tmp files in the JSON store.
- Board style guidance (token-thrift) on machine-read fields; measured
  -17.8% tokens on a real 17-unit corpus, fidelity-gated.

Breaking changes and the migration guide (existing `.agent-mem/` boards load
unchanged; legacy wait cursors carry over) are in CHANGELOG.md.
