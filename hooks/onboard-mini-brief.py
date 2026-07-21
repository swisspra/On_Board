#!/usr/bin/env python3
"""Build a tiny read-only On Board startup hint for agent hooks."""

import json
import os
import time
from pathlib import Path


def env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


MAX_CHARS = env_int("ONBOARD_HOOK_MAX_CHARS", 1800, 1)
PINNED_LIMIT = env_int("ONBOARD_HOOK_PINNED_LIMIT", 3, 0)
AGENTS_LIMIT = env_int("ONBOARD_HOOK_AGENTS_LIMIT", 5, 0)
HANDOFF_CHARS = env_int("ONBOARD_HOOK_HANDOFF_CHARS", 500, 0)
PINNED_TOTAL_CHARS = env_int("ONBOARD_HOOK_PINNED_CHARS", 700, 0)


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def entries_from(value) -> list:
    if isinstance(value, dict):
        return as_list(value.get("entries"))
    if isinstance(value, list):
        return value
    return []


def tickets_from(value) -> list:
    if isinstance(value, dict):
        return as_list(value.get("tickets"))
    if isinstance(value, list):
        return value
    return []


def truncate(text: object, limit: int) -> str:
    value = str(text or "").strip().replace("\r", "")
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    suffix = " ...[truncated]"
    if limit <= len(suffix):
        return suffix[:limit]
    return value[: max(0, limit - len(suffix))].rstrip() + suffix


def agent_ts(agent: dict) -> float:
    if not isinstance(agent, dict):
        return 0.0
    for key in ("last_activity", "timestamp"):
        value = agent.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    return 0.0


def memory_ts(memory: dict) -> float:
    if not isinstance(memory, dict):
        return 0.0
    value = memory.get("timestamp")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def protocol_lines() -> list[str]:
    return [
        "<on_board_protocol>",
        "  <required_first_call>memory_onboard</required_first_call>",
        "  <write_policy>Write memory only for meaningful progress. Do not write memory every turn.</write_policy>",
        "  <handoff_policy>Use memory_handoff only when actually handing off or ending work.</handoff_policy>",
        "</on_board_protocol>",
    ]


def build_no_memory() -> str:
    lines = [
        "⚠️ On Board memory not initialized.",
        "This project is configured for shared agent memory, but `.agent-mem/` does not exist yet.",
        "",
        *protocol_lines(),
        "",
        "Next: call `memory_bootstrap` for an existing project, or `memory_init` for a new/empty project. Then call `memory_onboard`.",
    ]
    return fit("\n".join(lines))


def fit(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    suffix = "\n...[startup hint truncated; call memory_onboard for compact current context]"
    if MAX_CHARS <= len(suffix):
        return suffix[:MAX_CHARS]
    return text[: max(0, MAX_CHARS - len(suffix))].rstrip() + suffix


def build_brief(mem_dir: Path) -> str:
    project = as_dict(load_json(mem_dir / "project.json", {}))
    agents = as_dict(load_json(mem_dir / "agents.json", {}))
    memories = entries_from(load_json(mem_dir / "memories.json", {}))
    tickets = tickets_from(load_json(mem_dir / "tickets" / "_index.json", {}))

    lines = ["🧠 On Board detected."]
    desc = project.get("description")
    tech = project.get("tech_stack")
    if desc or tech:
        project_line = f"Project: {desc or 'unknown'}"
        if tech:
            project_line += f" | Tech: {tech}"
        lines.append(truncate(project_line, 220))

    pinned = [
        m
        for m in memories
        if isinstance(m, dict) and m.get("pinned") and m.get("memory_type") != "handoff"
    ]
    pinned.sort(key=lambda m: (safe_int(m.get("priority", 0)), memory_ts(m)), reverse=True)
    if pinned:
        lines.append("\n📌 Pinned")
        used = 0
        for memory in pinned[:PINNED_LIMIT]:
            snippet = truncate(memory.get("content", ""), 180)
            row = f"- [{str(memory.get('memory_type', '?')).upper()}] {memory.get('title', '')}"
            if snippet:
                row += f": {snippet}"
            row = truncate(row, max(80, PINNED_TOTAL_CHARS - used))
            used += len(row)
            lines.append(row)
            if used >= PINNED_TOTAL_CHARS:
                break

    handoffs = [m for m in memories if isinstance(m, dict) and m.get("memory_type") == "handoff"]
    if handoffs:
        handoff = max(handoffs, key=memory_ts)
        lines.append(f"\n🤝 Last handoff from `{handoff.get('agent_name', '?')}`")
        lines.append(truncate(handoff.get("content", ""), HANDOFF_CHARS))

    if agents:
        lines.append(f"\n👥 Recent agents (last {AGENTS_LIMIT})")
        recent = sorted((a for a in agents.values() if isinstance(a, dict)), key=agent_ts, reverse=True)[:AGENTS_LIMIT]
        for agent in recent:
            lines.append(
                f"- {agent.get('agent_name', '?')} "
                f"({agent.get('agent_platform', '?')}) — {agent.get('status', '?')}"
            )

    open_tickets = [
        t for t in tickets
        if isinstance(t, dict) and t.get("status") not in ("closed", "canceled", "terminated")
    ]
    lines.append(
        f"\nCounts: {len(memories)} memories, {len(agents)} agents, {len(open_tickets)} open tickets."
    )
    lines.extend(["", *protocol_lines()])
    lines.append("Next: call `memory_onboard` for compact current context.")

    return fit("\n".join(lines))


def main() -> None:
    mem_dir = Path(os.environ.get("AGENT_MEM_DIR", ".agent-mem"))
    if not mem_dir.is_dir():
        print(build_no_memory())
    else:
        print(build_brief(mem_dir))


if __name__ == "__main__":
    main()
