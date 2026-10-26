# v4.1.0 — MCP SDK 2, safer runtime, and Memory footprint

This release brings the official MCP Python SDK 2.3.0 migration, patched runtime
dependencies, complete installed-package payloads, and the board/dashboard
repairs together. The public surface remains thirty tools and two prompts over
stdio, with Python 3.10 or later. Existing board data needs no schema migration.

## Runtime and security

- Use the official `MCPServer` API and SDK2 models. Setup, doctor, and update
  scripts discover tools through the public SDK API instead of private registry
  internals. SDK1 is no longer supported by this release.
- Require patched AnyIO, PyJWT, and cryptography versions. The lock selects MCP
  2.3.0, AnyIO 4.15.1, PyJWT 2.15.1, and cryptography 50.0.2. SDK2 no longer
  brings certifi into the runtime dependency graph.
- Checkpoint filenames no longer use raw agent names as path components. An
  external checkpoint-directory symlink is rejected before checkpoint memory or
  heartbeat writes. Existing checkpoint files are retained.
- The dashboard HTTP server binds to loopback and refuses file, directory, and
  index symlinks that escape the selected canonical memory directory, for both
  GET and HEAD. Port zero reports the actual bound port.
- Memory identifiers use cryptographic randomness without changing their
  twelve-character lowercase hexadecimal format.

## Board correctness and deployment

- Serialize shared board read-modify-write paths, heartbeats, and idle sweeps
  under the board lock. Onboarding rendering and event-wait sleeps do not hold
  that lock. Cross-process serialization still relies on POSIX `fcntl`; the
  existing Windows multi-instance limitation is unchanged.
- Match assignments against exact, case-sensitive stable agent names. Preserve
  coordinator authority and the self-review gate.
- Keep each rejected submission under its own immutable attempt directory.
  Event waits detect a rejection-counter increase even when a fast cycle returns
  the ticket to the same status, and await asynchronous heartbeat callbacks.
- Build wheels from the source archive and ship only the seven runtime/icon
  payload paths plus package metadata. Local boards, environments, tests, caches,
  and scratch files stay outside published distributions.
- Deploy all runtime sidecars and the icon, preserve backups, and fail clearly
  when the destination cannot import the copied runtime. Paths containing
  apostrophes remain supported.

## Dashboard

- **Memory footprint** replaces the active Quota saved view. It shows live,
  digest, and archive text estimates, largest live entries, pinned content, and
  recorded compaction comparisons. These are storage estimates, not billing,
  provider quota, time gained, or measured session savings.
- The previous design remains accessible through **View obsoleted design** with
  an explicit **Obsoleted** warning and a return button.
- All eleven ticket states are represented consistently, inactive claimers are
  flagged through review, and terminated work is separate from cancellations.
  Token estimates match the server's per-field Unicode-code-point calculation.

## Release checks

CI treats test warnings as errors, audits the hashed locked runtime dependency
set without ignoring advisories, validates archives, and exercises a fresh
wheel-only installation outside the checkout. GitHub Actions use immutable
commits and scoped permissions. CodeQL covers Python and Actions; the dashboard
JavaScript test harness uses an HTML parser rather than tag-filtering regexes.

## Upgrade

Upgrade through your existing installation channel (`uv tool upgrade
onboard-memory-mcp`, `pipx upgrade onboard-memory-mcp`, or Homebrew after its tap
update). Source-checkout users can use the existing update workflow. No board
schema migration, linked-project refresh, or data deletion runs automatically
as part of this release.
