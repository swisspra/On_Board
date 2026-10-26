# v4.1.1 — Refreshed dependency locks and accurate install guidance

This maintenance release refreshes the source checkout's locked runtime/test
environment and corrects the installation guidance shipped in package metadata.
The MCP SDK remains 2.3.0, with thirty tools, two prompts, and Python 3.10+.
Runtime APIs and public dependency requirements are unchanged.

## Dependency refresh

- Upgrade 22 locked packages to current compatible stable releases, including
  Pydantic 2.14.1, pydantic-core 2.50.1, Uvicorn 0.54.0, pytest 9.1.1,
  cffi 2.1.1, Typer 0.27.3, and updated validation/CLI dependencies.
- Keep explicit Python 3.10 resolver branches where newer upstream versions
  require Python 3.11 or later. The supported Python minimum is not raised.
- Retain current MCP/mcp-types 2.3.0, AnyIO 4.15.1, PyJWT 2.15.1, and
  cryptography 50.0.2. No advisory ignores or security-policy bypasses are added.

## Installation guidance

- Do not promise compiler-free installs independently of Python and architecture;
  dependency wheel availability varies by platform.
- Homebrew bottle builds target ARM macOS and x86_64 Linux. Upstream Rust,
  OpenSSL 3, and Python 3.12 dependency bottles are currently unavailable for
  Intel macOS, so Homebrew is not a compiler-free fallback there.
- The platform-independent PyPI package remains available. Source builds may
  require a C/Rust toolchain when a dependency has no matching wheel.

## Verification and upgrade

The upgraded graph passed the full 184-test warning-strict suite on Python 3.10
and 3.13, native scratch-board A2A checks (33/33 each), and multiprocess checks
preserving every one of 36 writes on each interpreter. Complete third-party
runtime/test advisory audits cover 42 installed packages on 3.10 and 40 on 3.13,
with zero known vulnerabilities. Release builds also check archives and exercise
fresh wheel-only installs outside the checkout.

Upgrade through your existing installation channel. Source-checkout users pick
up the new lock through the existing update workflow. This release does not
rewrite 4.1.0, migrate board data, refresh linked projects, or change global
configuration automatically.
