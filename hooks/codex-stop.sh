#!/bin/bash
# ─────────────────────────────────────────────────────────
# Codex Hook: Stop (legacy no-op)
#
# Stop is turn-scoped in current Codex hooks. Older On Board versions wrote a
# checkpoint and marked active agents KIA here, which forced re-onboarding after
# every turn. Keep this script safe for existing installs.
# ─────────────────────────────────────────────────────────

printf '{"continue": true}\n'

exit 0
