#!/bin/bash
# ─────────────────────────────────────────────────────────
# On Board — Launch Live Dashboard
# Generate + serve + open browser in one command.
#
# Usage:
#   bash run-dashboard.sh                        ← serves current project (AGENT_PROJECT_DIR or cwd)
#   bash run-dashboard.sh /path/to/project       ← specify project
#   bash run-dashboard.sh --port 9000            ← custom port
#   bash run-dashboard.sh --stop                 ← stop any running dashboard server
# ─────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8765}"

# Parse --stop flag early
for arg in "$@"; do
    if [ "$arg" = "--stop" ]; then
        PIDS=$(lsof -ti:"$PORT" 2>/dev/null || true)
        if [ -n "$PIDS" ]; then
            echo "🛑 Stopping dashboard server on port $PORT (PIDs: $PIDS)"
            echo "$PIDS" | xargs kill 2>/dev/null || true
            echo "✅ Stopped"
        else
            echo "ℹ️  No server running on port $PORT"
        fi
        exit 0
    fi
done

# Parse --port N
POSITIONAL=()
while [ $# -gt 0 ]; do
    case "$1" in
        --port)
            PORT="$2"
            shift 2
            ;;
        --port=*)
            PORT="${1#--port=}"
            shift
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

# Project path: arg → env → cwd
PROJECT_DIR="${POSITIONAL[0]:-${AGENT_PROJECT_DIR:-$(pwd)}}"

# Kill any existing server on this port so we start clean
EXISTING=$(lsof -ti:"$PORT" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    echo "♻️  Port $PORT busy — stopping old server (PIDs: $EXISTING)"
    echo "$EXISTING" | xargs kill 2>/dev/null || true
    sleep 0.5
fi

echo "🧠 On Board — Live Dashboard"
echo "   Project: $PROJECT_DIR"
echo "   Port   : $PORT"
echo ""

exec python3 "$SCRIPT_DIR/dashboard_live.py" "$PROJECT_DIR" --port "$PORT" --open
