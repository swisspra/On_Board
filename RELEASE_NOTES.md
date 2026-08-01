# v4.0.3 — hot memory stops evicting the newest thing on the board

Patch release. Two fixes to the hot/cold tiering, both found by watching the
board discard entries it had just been told to keep.

- **The overflow ranking put priority ahead of recency.** `_split_hot_cold`
  works out `is_recent` for every entry, then throws that decision away: when
  more entries survive than `AGENT_MEM_MAX_HOT` allows, it re-sorted by
  `(priority, timestamp)` and truncated. Priority dominates, so a brand-new
  unpinned `priority: 0` entry sorted below every week-old `priority: 1`
  handoff and lost its slot.

  That is why compaction ate the digest written for it.
  `memory_prepare_compaction` asks the agent to summarise the cold set with
  `memory_write(memory_type='context')`; the digest lands unpinned at priority
  0, overflow drops it into COLD, and the `memory_compact` it was written for
  archives it with the entries it summarised. Two agents hit this
  independently. Nothing was lost — `memory_search_archive` still finds them —
  but the next agent reads hot first, so a digest in the archive is a digest
  nobody reads.

  Overflow now ranks `(pinned, in-hot-window, priority, timestamp)`. On a live
  53-entry board the demoted set went from *[oldest handoff, second-newest
  entry]* to the three oldest handoffs.

- **Handoffs reserved hot slots forever.** Both writers hardcoded
  `priority: 3, pinned: True`, so the live board held 33 handoffs — 17 pinned —
  against 50 slots. But `pinned` on a handoff never meant "show me": every
  handoff surface selects by `memory_type` and recency, and both pinned lists
  exclude handoffs outright. It only ever meant "do not compact me".

  `memory_handoff` still pins, but demotes the author's earlier handoffs first,
  so the board keeps one per agent. The auto-handoff from
  `memory_submit_ticket` is now `priority: 1` and unpinned: it is a routing
  notice that expires when the review lands, and 21 of those 33 handoffs were
  auto-generated.

- **Two new offline test files**, `test_hot_cold_split_offline.py` (6) and
  `test_handoff_pinning_offline.py` (6). The first was negative-controlled:
  replayed against v4.0.2's `server.py`, three of its six tests fail.

Upgrading is a drop-in: no schema change, no migration, no config change. The
handoff change is forward-only — handoffs already pinned on your board stay
pinned until their author hands off again, or you clear them with
`memory_unpin`.
