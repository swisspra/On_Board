# Security Policy

## Supported Versions

The On Board project maintains several release channels. Only the latest versions in supported channels receive security updates. Older or experimental builds do not.


| Version   | Supported          | Details                |
| ----------| -------------------| -----------------------|
| `main`    | :white_check_mark: | Main.                  |
| `v3.5.x`  | :white_check_mark: | Latest stable release  |
| `< v3.2.x`| :warning:          | Previous minor releases|
| `nightly` | :x:                | Experimental           |
| `< v3.0`  | :x:                | EOD                    |

## Reporting a Vulnerability

If you discover a potential vulnerability in On Board—such as cross‑agent data leakage, unauthorized access to .agent‑mem/, prompt injection vectors, or issues in agent onboarding—please report it privately. Avoid creating public GitHub issues to prevent accidental disclosure.

* How to report: Use GitHub’s Security Advisories (preferred, if enabled) or email the maintainer (@swisspra) with the subject line “On Board Security Report”.
* Include: A description of the issue, steps to reproduce, the version/branch affected (main, tagged release, or nightly), the environment details, potential impact, and any suggested mitigations.
* Response targets: We aim to acknowledge valid reports within 72 hours and to provide a status update within seven days. Fix timelines depend on severity and complexity.

## Security Model Notes

On Board is a local‑first, multi‑agent shared memory server. Keep these principles in mind:

* Trusted environment: Agents connected to the same project are assumed trusted unless isolated by external mechanisms.
* Sensitive directories: .agent‑mem/ and related memory folders may contain tickets, context, and hand‑offs; keep them private.
* Context exposure: The AGENT_MEM_CONTEXT_DIRS configuration can expose external documentation or filesystem content to agents. Remove it if the project memory should remain self‑contained.
* Hooks & scripts: Hooks installed in editors or agent clients run with user permissions; review them before enabling.

Users should restrict access to shared development environments, keep project memory directories private, and audit agent‑generated actions.

## Out of Scope

The following are not considered security issues unless they lead to privilege escalation or sensitive data exposure:

* Prompt quality issues or hallucinations without a reproducible boundary failure.
* Social engineering attempts.
* Misuse by a fully trusted local user.
* Vulnerabilities in third‑party MCP client implementations.
