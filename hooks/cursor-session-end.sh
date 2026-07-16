#!/bin/bash
# ─────────────────────────────────────────────────────────
# Cursor Hook: stop/session end (legacy no-op)
#
# Current agent clients often fire stop-style hooks per turn. Older On Board
# versions wrote checkpoints and sometimes marked active agents KIA here, which
# made agents re-onboard too often. Keep this script safe for existing installs.
# ─────────────────────────────────────────────────────────

exit 0
