#!/bin/bash
# ─────────────────────────────────────────────────────────
# Claude Code Hook: Stop / SessionEnd (legacy no-op)
#
# Stop is a per-turn event in current Claude Code. Older On Board versions
# wrote checkpoints and marked active agents KIA here, which forced agents to
# re-onboard after every turn. Keep this script safe for existing installs.
# ─────────────────────────────────────────────────────────

exit 0
