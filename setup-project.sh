#!/bin/bash
# ─────────────────────────────────────────────────────────
# On Board — Project Setup Script
# Run this in your project root to set up hooks for all platforms
# Usage: bash /path/to/agent-memory-mcp/setup-project.sh
# ─────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${1:-$(pwd)}"

echo "🧠 On Board — Project Setup"
echo "Project: $PROJECT_DIR"
echo ""

# ── 1. Create hook directories in project ──
HOOKS_DIR="$PROJECT_DIR/.agent-mem-hooks"
mkdir -p "$HOOKS_DIR"

cp "$SCRIPT_DIR/hooks/cursor-session-start.sh" "$HOOKS_DIR/"
cp "$SCRIPT_DIR/hooks/cursor-session-end.sh" "$HOOKS_DIR/"
cp "$SCRIPT_DIR/hooks/claude-code-session-start.sh" "$HOOKS_DIR/"
cp "$SCRIPT_DIR/hooks/claude-code-stop.sh" "$HOOKS_DIR/"

chmod +x "$HOOKS_DIR"/*.sh

echo "✅ Hooks copied to .agent-mem-hooks/"

CODEX_DIR="$PROJECT_DIR/.codex"
CODEX_HOOKS_DIR="$CODEX_DIR/hooks"
mkdir -p "$CODEX_HOOKS_DIR"

cp "$SCRIPT_DIR/hooks/codex-session-start.sh" "$CODEX_HOOKS_DIR/"
cp "$SCRIPT_DIR/hooks/codex-stop.sh" "$CODEX_HOOKS_DIR/"

chmod +x "$CODEX_HOOKS_DIR"/*.sh

echo "✅ Codex hooks copied to .codex/hooks/"

# ── 1b. Copy SKILL.md to Claude Code skills ──
SKILL_DIR="$PROJECT_DIR/.claude/skills/agent-memory"
mkdir -p "$SKILL_DIR"
if [ -f "$SCRIPT_DIR/SKILL.md" ]; then
    cp "$SCRIPT_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
    echo "✅ SKILL.md copied to .claude/skills/agent-memory/"
fi

# ── 2. Set up Cursor hooks ──
CURSOR_DIR="$PROJECT_DIR/.cursor"
mkdir -p "$CURSOR_DIR"

if [ -f "$CURSOR_DIR/hooks.json" ]; then
    echo "⚠️  .cursor/hooks.json exists — please merge manually:"
    echo "    See: $SCRIPT_DIR/configs/cursor-hooks.json"
else
    cp "$SCRIPT_DIR/configs/cursor-hooks.json" "$CURSOR_DIR/hooks.json"
    echo "✅ Cursor hooks configured at .cursor/hooks.json"
fi

# ── 3. Set up Claude Code hooks ──
CLAUDE_DIR="$PROJECT_DIR/.claude"
mkdir -p "$CLAUDE_DIR"

if [ -f "$CLAUDE_DIR/settings.json" ]; then
    echo "⚠️  .claude/settings.json exists — please merge hooks manually:"
    echo "    See: $SCRIPT_DIR/configs/claude-code-settings.json"
else
    cp "$SCRIPT_DIR/configs/claude-code-settings.json" "$CLAUDE_DIR/settings.json"
    echo "✅ Claude Code hooks configured at .claude/settings.json"
fi

# ── 3b. Set up Codex hooks ──
if [ -f "$CODEX_DIR/hooks.json" ]; then
    echo "⚠️  .codex/hooks.json exists — please merge hooks manually:"
    echo "    See: $SCRIPT_DIR/configs/codex-hooks.json"
else
    cp "$SCRIPT_DIR/configs/codex-hooks.json" "$CODEX_DIR/hooks.json"
    echo "✅ Codex hooks configured at .codex/hooks.json"
fi

# ── 4. Update .gitignore ──
GITIGNORE="$PROJECT_DIR/.gitignore"
if [ -f "$GITIGNORE" ]; then
    if ! grep -q ".agent-mem/" "$GITIGNORE"; then
        echo "" >> "$GITIGNORE"
        echo "# Agent shared memory (runtime data)" >> "$GITIGNORE"
        echo ".agent-mem/" >> "$GITIGNORE"
        echo "✅ Added .agent-mem/ to .gitignore"
    fi
else
    echo ".agent-mem/" > "$GITIGNORE"
    echo "✅ Created .gitignore with .agent-mem/"
fi

# ── 5. Create CLAUDE.md / .cursorrules / AGENTS.md reminder ──
RULES_NOTE="
# On Board — Agent Shared Memory Protocol

This project uses .agent-mem/ for multi-agent coordination.
Get On Board before starting ANY work:
1. Call memory_get_briefing to read full context
2. Call memory_agent_join with your unique agent_name
3. Call memory_write after EVERY significant action
4. Call memory_checkpoint every 10-15 minutes
5. Call memory_handoff before you finish

When coordinating work between agents:
- Use memory_create_ticket to request help and assign it to a specific agent or platform when needed
- Use memory_claim_ticket to pick up work that was assigned to you
- Use memory_submit_ticket when your implementation is ready for review
- Use memory_review_ticket to approve work or send it back with concrete fix instructions

If you skip these steps, the next agent will have no context and will redo your work.
Your agent_name is stamped on every entry, so write updates another agent can rely on.
"

if [ ! -f "$PROJECT_DIR/CLAUDE.md" ]; then
    echo "$RULES_NOTE" > "$PROJECT_DIR/CLAUDE.md"
    echo "✅ Created CLAUDE.md with agent memory protocol"
fi

if [ ! -f "$PROJECT_DIR/.cursorrules" ]; then
    echo "$RULES_NOTE" > "$PROJECT_DIR/.cursorrules"
    echo "✅ Created .cursorrules with agent memory protocol"
fi

if [ -f "$PROJECT_DIR/AGENTS.md" ]; then
    echo "⚠️  AGENTS.md exists — please merge Codex instructions manually"
else
    echo "$RULES_NOTE" > "$PROJECT_DIR/AGENTS.md"
    echo "✅ Created AGENTS.md with agent memory protocol"
fi

ANTIGRAVITY_RULES_DIR="$PROJECT_DIR/.agent/rules"
ANTIGRAVITY_RULE_FILE="$ANTIGRAVITY_RULES_DIR/on-board-agent-memory.md"
mkdir -p "$ANTIGRAVITY_RULES_DIR"

if [ -f "$ANTIGRAVITY_RULE_FILE" ]; then
    echo "⚠️  .agent/rules/on-board-agent-memory.md exists — please merge AntiGravity rules manually"
else
    echo "$RULES_NOTE" > "$ANTIGRAVITY_RULE_FILE"
    echo "✅ Created .agent/rules/on-board-agent-memory.md for AntiGravity"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Structure created:"
echo "  $PROJECT_DIR/"
echo "  ├── .agent-mem-hooks/       ← Hook scripts (commit this)"
echo "  │   ├── cursor-session-start.sh"
echo "  │   ├── cursor-session-end.sh"
echo "  │   ├── claude-code-session-start.sh"
echo "  │   └── claude-code-stop.sh"
echo "  ├── .codex/hooks.json       ← Codex hook config"
echo "  ├── .codex/hooks/           ← Codex hook scripts"
echo "  │   ├── codex-session-start.sh"
echo "  │   └── codex-stop.sh"
echo "  ├── .cursor/hooks.json      ← Cursor hook config"
echo "  ├── .claude/settings.json   ← Claude Code hook config"
echo "  ├── .cursorrules            ← Rules for Cursor agents"
echo "  ├── CLAUDE.md               ← Rules for Claude Code agents"
echo "  ├── AGENTS.md               ← Rules for Codex agents"
echo "  ├── .agent/rules/           ← Rules for AntiGravity"
echo "  │   └── on-board-agent-memory.md"
echo "  └── .agent-mem/             ← Runtime memory (gitignored)"
echo ""
echo "Next: Add the MCP server to each agent platform:"
echo "  Cursor:     .cursor/mcp.json"
echo "  Claude Code: claude mcp add agent-memory -- python /path/to/server.py"
echo "  Codex:      enable codex_hooks in ~/.codex/config.toml and add agent-memory MCP"
echo "  AntiGravity: add agent-memory MCP and keep .agent/rules/on-board-agent-memory.md in the workspace"
echo ""
