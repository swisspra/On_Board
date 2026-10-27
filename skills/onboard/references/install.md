# On Board — install and configure

Use this when the user asked to install, configure, repair, update, or diagnose
On Board. It is not the working protocol; for day-to-day work in a project that
is already connected, read `protocol.md`.

The helper below is `scripts/setup.py`, a sibling of this file's `references/`
directory. Substitute its real path where the examples say `scripts/setup.py`.
It requires Python 3.11+ and writes native project files only; when the machine's
`python3` is older, run it with
`uv run --no-project --python 3.12 scripts/setup.py …` (that is running the
one-time helper, not the daily MCP command).

## Skill and runtime distribution

Install or refresh the skill in the selected project with
`npx skills add swisspra/On_Board --skill onboard`.

The skills CLI runs through npm, but On Board's skill comes from Git and its
Python runtime remains a separate install. Native resources require a verified
4.2+ runtime; skill installation alone does not add them to an older runtime.
Preserve a working 4.1.1/source binding. Never select an unreleased source
runtime or replace a working runtime without an explicit user request.

## Ground rules

- Inspect and change setup with file-based checks, not by calling MCP tools.
- Never run an installer with `sudo`, never edit shell profiles
  (`.zshrc`, `.bashrc`, `%USERPROFILE%` setup), and never pipe an unreviewed
  network script into a shell.
- Do not create or migrate `.agent-mem/`. Installation and memory
  initialization are separate steps.

## 1. Determine the workspace and the chosen client

- Project: the actual user workspace. Confirm it or default to the current
  working directory; never guess a different project.
- Client (host): the client the user wants configured. Project-scoped clients
  the helper can write are `claude-code` (`.mcp.json`), `cursor`
  (`.cursor/mcp.json`), and `codex` (`.codex/config.toml`). Claude Desktop and
  global-only clients are handled in step 7.

## 2. Inspect the existing setup (no MCP calls)

```bash
python3 scripts/setup.py --project <ABS> --client <client> --check
```

The command prints one JSON object and does not modify anything:

- `configured` — an `agent-memory` entry already matches; nothing to write.
- `unchanged` — a repeat run; nothing to write.
- `needs_configuration` — no `agent-memory` entry yet; add one in step 4.
- `conflict` — an existing `agent-memory` entry or client file cannot be safely
  reused; repair needs consent (step 6).
- `error` — the helper could not proceed: unsupported Python (<3.11), an I/O
  failure, or a `--command` that is missing or not an absolute path.

Exit codes: `0` for `configured`/`unchanged`, `2` for
`needs_configuration`/`conflict`, `1` for `error`.

## 3. Reuse a working runtime, or install the shared runtime

- First check the configuration shape, without executing anything it points at.
  An existing executable or wired source checkout is a runtime candidate, not
  proof of a live connection. Preserve a known-working binding and skip
  installing; use the trust/restart and tool-visibility checks in step 8.
  Do not run commands taken from the project config as a probe.
- Keep a known-working existing source or legacy binding in place. Do not require
  a packaged executable or a `--version` response to accept it: an old 4.1.1 may
  print no version, which is legacy/unknown capability, not a reason to
  reinstall.
- Otherwise install the shared runtime with the package manager already on the
  machine:
  - `uv` present: `uv tool install --python 3.12 onboard-memory-mcp`
  - `uv` absent but `pipx` present: `pipx install onboard-memory-mcp`
- Homebrew (`brew install swisspra/tap/onboard-memory`) and a source checkout
  (`git clone` + `uv sync`) are explicit alternatives to offer, never automatic
  guesses.
- If no supported installer or a Python 3.10+ interpreter exists, name the exact
  missing prerequisite and ask before installing it. Do not install compilers or
  switch package managers on your own.

## 4. Resolve the executable, then write config

Resolve the absolute path of the installed executable — `command -v
onboard-memory-mcp`, `shutil.which("onboard-memory-mcp")`, or `where
onboard-memory-mcp` on Windows — and pass it explicitly. Never rely on a PATH
lookup at MCP launch, and never configure `uvx` or `uv run` as the daily MCP
command (`uv` is only for the one-time install).

```bash
python3 scripts/setup.py --project <ABS> --client <client> --command <ABS>
```

Run the modifying form only when `--check` in step 2 reported
`needs_configuration`. If it reported `configured` or `unchanged`, keep the
binding exactly as it is and proceed to the trust/restart status in step 8;
do not run the modifying form as confirmation, especially for source launchers.
The helper touches only the selected client's On Board entry and, in the same
project, the selected generated config and On Board runtime ignores
(`.agent-mem/`, `.onboard/`) in `.gitignore`. Unrelated servers, settings, and
existing ignore lines are preserved.

## 5. If provisioning failed

If the runtime could not be installed or resolved, stop before writing config and
report the exact failure. Do not install compilers, switch package managers, or
silently replace a working shared runtime.

## 6. Repair a conflicting or tracked entry (needs consent)

The helper refuses to write and reports `conflict` when:

- an `agent-memory` entry exists but differs (another project, another command,
  unusable fields, or an unresolved `${…}` variable reference in
  `AGENT_PROJECT_DIR`, reported as "confirm it manually");
- the client file is a symlink or is not a regular file;
- the client file is not valid JSON/TOML;
- the client file is tracked by Git — machine-specific paths need explicit
  consent — or Git cannot determine its tracking or effective ignore status;
- the file changed while the helper was reading it.

There is no force flag, and the helper never rewrites a tracked file or a global
config. Ask the user before changing anything, and do not work around a refusal
by editing a global file. After consent: show the minimal proposed change, edit
only the On Board `agent-memory` entry in that project file with your normal
editing tool, preserve unrelated servers, settings, comments, and Git tracking,
then rerun `--check`.

## 7. Claude Desktop, global-only clients, and Codex

- Claude Desktop has no project-scoped MCP config. It reads the global config
  (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS,
  `%APPDATA%\Claude\claude_desktop_config.json` on Windows,
  `~/.config/Claude/claude_desktop_config.json` on Linux). Generate the entry for
  the user to review, and treat writing that global file as a separate, explicit
  consent step. Do not pretend a project scope exists.
- Codex reads the trusted project file `.codex/config.toml`. Have the helper write
  that file; do not run `codex mcp add` with an assumed scope flag.

## 8. Status vocabulary and the version probe

Report status honestly, in these terms:

- `runtime available` — the executable resolved.
- `project configured` — the selected client file has a matching On Board entry.
- `waiting for trust/restart` — the entry is written but the client has not been
  restarted or the project has not been trusted yet.
- `ready` — the On Board tools are actually visible in a live session.

Never report connected only because config was written. Optionally probe the
runtime with `onboard-memory-mcp --version`, stdin closed (`< /dev/null`) and a
bounded timeout (5s). An older runtime may print no version: that is
legacy/unknown capability, not permission to initialize a board.

Preserve a working 4.1.1 runtime. Native resources (`onboard://…`) exist only on
a verified 4.2+ runtime; do not advertise them for 4.1.1. Upgrade only On Board,
and ask before replacing an existing shared runtime.

## 9. Skill updates versus runtime upgrades

They are separate operations:

- Skill: `npx skills update -p onboard`.
- Runtime: a manager-matched `uv tool upgrade onboard-memory-mcp`,
  `pipx upgrade onboard-memory-mcp`, or an explicitly selected Homebrew/source
  update.

Updating the skill does not upgrade every linked project's runtime; linked
projects keep working until they are refreshed.

## 10. Finish: offer to start, separately

After setup, offer to start the project. Only an explicit start request enters
the existing initialization/briefing workflow in `protocol.md`. If `.agent-mem/`
already exists, never bootstrap it again — just join. Otherwise the first work
session initializes memory once (`memory_init`, or `memory_bootstrap` when
adopting an existing repo), then joins with `memory_onboard`.
