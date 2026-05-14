---
name: memory-digest-thrift
description: Apply thrift-style compression when writing memory digests for memory_compact workflow. Triggers when agent prepares to compact old memories. Saves ~70% tokens vs default regex digests.
version: 0.1.0
trigger: memory_prepare_compaction called, memory_compact(strategy="agent"), user says "compact memory"
applies_to: memory_write(memory_type='context') digest entries
---

# MEMORY DIGEST THRIFT

When user (or you) is about to compact memory via On Board MCP, write digests in compressed thrift style instead of letting server regex do it.

## WORKFLOW

1. Call `memory_prepare_compaction()` → see cold entries grouped by agent
2. **For each agent group**, write a digest with `memory_write(memory_type='context', ...)`:
   - Title: `Digest: <agent_name> (<period>)`
   - Content: non-blank thrift-compressed summary (rules below)
3. Call `memory_compact(strategy='agent')` → archives originals, keeps your digest

## DIGEST FORMAT RULES

### Structure
```
<topic-1>: <fact/decision>. files: x,y. by <agent>.
<topic-2>: <status>. blocker: <reason>. by <agent>.
warning: <gotcha>. by <agent>.
```

### Apply
- **Drop:** articles (a/an/the), filler (just/really), pleasantries, hedging
- **Fragments OK:** "Auth: JWT chosen, stateless API" not "We decided to use JWT because..."
- **Arrows for causality:** `X → Y` not "X led to Y"
- **Preserve verbatim:** filenames, function names, error strings, version numbers, agent_name
- **Always include:** `agent_name` attribution per fact (audit trail)

### Target sizes
- Per agent-session digest: **30-50 tokens** (vs ~150 tk regex output)
- Per fact line: **5-15 tokens**
- One session = one digest entry (not split per fact)

## EXAMPLES

### Bad (verbose, ~150 tk)
```
The previous agent worked on the authentication system over the course of
several days. They made the decision to use JWT tokens instead of session
cookies because of the stateless nature of the API. They created the
auth/jwt.py file and modified middleware/auth.py. There was also a blocker
related to refresh token rotation that needs follow-up.
```

### Good (thrift, ~40 tk)
```
Auth: JWT over sessions (stateless API). Files: auth/jwt.py (new), middleware/auth.py.
Blocker: refresh token rotation TBD. By alice.
```

### Multi-topic digest (thrift, ~60 tk)
```
Auth: JWT impl, files auth/jwt.py + middleware/auth.py. By alice.
DB: migration 0023 reserved for users table v2. By alice.
Warning: rate-limit on /login still 100/min — not raised. By alice.
Progress: 8 commits on auth branch, all passing CI.
```

## CONTENT PRIORITIES

Keep (with attribution):
- Decisions (why X over Y)
- Warnings, blockers
- File changes (path + nature)
- Discoveries about codebase
- Migration numbers / version reservations

Drop or collapse:
- Multiple progress entries → "N commits on X" one-liner
- Routine checkpoints
- Reading-only actions
- Redundant context restating

## WHY NOT strategy='regex'

Regex fallback is deterministic but loses nuance. You are already the summarizer: write the digest yourself in thrift style. Server's `strategy='agent'` mode skips its own summary generation and trusts your context entry.

## SAFETY

- Don't drop agent_name attribution (accountability)
- Don't compress error strings, file paths, function signatures
- If unsure about a decision's importance → keep it (verbose is recoverable, lost info is not)
- Pin critical context entries: `priority=2` or higher in memory_write
