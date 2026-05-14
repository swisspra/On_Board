#!/usr/bin/env python3
"""
On Board — Cross-Platform Agent Shared Memory MCP Server

PROJECT-LOCAL shared memory for multi-agent sequential workflows.
Memory lives in .agent-mem/ inside the project directory — NOT global.

Design principles:
  - Agents run ONE AT A TIME (after previous agent KIA/done)
  - Every entry is stamped with agent_name + agent_platform for traceability
  - Agents are FORCED to read memory on session start via hooks
  - Agents are FORCED to checkpoint via hooks before session ends
  - If an agent dies (KIA), the next agent gets full context from .agent-mem/

Supports: Claude, Cursor, Codex, Claude Code, AntiGravity, any MCP client.
"""

import json, os, time, hashlib, math, re
from datetime import datetime
from typing import Optional, List, Literal
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# ── Config — PROJECT LOCAL ──────────────────────────────
PROJECT_ROOT = Path(os.environ.get(
    "AGENT_PROJECT_DIR",
    os.environ.get("CURSOR_PROJECT_DIR",
    os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
))
MEMORY_DIR = PROJECT_ROOT / ".agent-mem"

# ── Tiered Memory Config ────────────────────────────────
# HOT:  recent entries (full detail) — loaded in briefings
# WARM: older entries compressed into per-session digests
# COLD: raw archive on disk, never loaded unless searched
HOT_WINDOW_HOURS = int(os.environ.get("AGENT_MEM_HOT_HOURS", "24"))
MAX_HOT_ENTRIES = int(os.environ.get("AGENT_MEM_MAX_HOT", "50"))
VECTOR_BACKEND = os.environ.get("AGENT_MEM_VECTOR_BACKEND", "none").lower()

# ── Multi-Agent Concurrency Config ──────────────────────
# Idle detection: agents with no heartbeat for this long get auto-KIA'd
IDLE_KIA_MIN = int(os.environ.get("AGENT_MEM_IDLE_KIA_MIN", "30"))
IDLE_WARN_MIN = IDLE_KIA_MIN // 2  # warn at half the KIA threshold
AGENT_HISTORY_LIMIT = 10

# Briefing type caps — how many entries of each type to include in briefings.
# High-signal types get unlimited. Spam-prone types get capped hard.
BRIEFING_TYPE_CAP = {
    "handoff": 999,      # always all — critical for continuity
    "decision": 999,     # always all — architecture decisions matter
    "warning": 999,      # always all — safety
    "blocker": 999,      # always all — blockers need visibility
    "discovery": 10,     # usually valuable
    "todo": 10,          # actionable
    "file_change": 8,    # recent file changes
    "context": 8,        # background info / digests
    "checkpoint": 1,     # only latest
    "progress": 5,       # ← SPAM PRONE — cap hard, most recent only
}

# External info/reference folders — colon-separated paths
# e.g. "/Users/swiss/docs/specs:/Users/swiss/shared/reference"
CONTEXT_DIRS = [
    Path(p.strip()) for p in os.environ.get("AGENT_MEM_CONTEXT_DIRS", "").split(":")
    if p.strip()
]

def _agent_activity_ts(agent: dict) -> float:
    for key in ("last_activity", "timestamp"):
        value = agent.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    for key in ("joined_at", "handed_off_at", "completed_at", "kia_at"):
        value = agent.get(key)
        if value:
            try:
                return datetime.fromisoformat(str(value)).timestamp()
            except ValueError:
                pass
    return 0.0

def _recent_agent_items(agents: dict, limit: int = AGENT_HISTORY_LIMIT) -> list:
    return sorted(agents.items(), key=lambda item: _agent_activity_ts(item[1]), reverse=True)[:limit]

# ── MCP Server ──────────────────────────────────────────
mcp = FastMCP("onboard_memory_mcp")

# ── Enums ───────────────────────────────────────────────
class MemoryType(str, Enum):
    DECISION="decision"; PROGRESS="progress"; BLOCKER="blocker"
    CONTEXT="context"; HANDOFF="handoff"; TODO="todo"
    FILE_CHANGE="file_change"; DISCOVERY="discovery"
    WARNING="warning"; CHECKPOINT="checkpoint"

class AgentStatus(str, Enum):
    ACTIVE="active"; KIA="kia"; COMPLETED="completed"; HANDED_OFF="handed_off"

class ResponseFormat(str, Enum):
    MARKDOWN="markdown"; JSON="json"

class BriefingMode(str, Enum):
    BRIEF="brief"; NORMAL="normal"; DEEP="deep"; HANDOFF_ONLY="handoff-only"

class VectorBackend(str, Enum):
    NONE="none"; LOCAL="local"

# ── Storage ─────────────────────────────────────────────
class JsonMemoryStore:
    """Project-local JSON store. Keep all persistence behind this boundary."""

    def __init__(self, root: Path):
        self.root = root
        self.memory_dir = root / ".agent-mem"

    def ensure(self):
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        (self.memory_dir / "checkpoints").mkdir(exist_ok=True)
        gi = self.root / ".gitignore"
        marker = ".agent-mem/"
        if gi.exists():
            content = gi.read_text()
            if marker not in content:
                with open(gi, "a") as f:
                    f.write("\n# Agent shared memory — runtime data, do NOT commit\n.agent-mem/\n")
        else:
            with open(gi, "w") as f:
                f.write("# Agent shared memory — runtime data, do NOT commit\n.agent-mem/\n")

    def load(self, fp: Path):
        if fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save(self, fp: Path, data):
        self.ensure()
        fp.parent.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        tmp.rename(fp)

    def path(self, name: str) -> Path:
        return self.memory_dir / name

STORE = JsonMemoryStore(PROJECT_ROOT)

def _ensure():
    STORE.ensure()

def _load(fp):
    return STORE.load(fp)

def _save(fp, data):
    STORE.save(fp, data)

def _local_now() -> datetime:
    return datetime.now().astimezone()

def _now(): return _local_now().isoformat()
def _id(): return hashlib.md5(f"{time.time()}-{os.urandom(8).hex()}".encode()).hexdigest()[:12]

# Paths
def _mem_p(): return MEMORY_DIR / "memories.json"
def _agt_p(): return MEMORY_DIR / "agents.json"
def _sta_p(): return MEMORY_DIR / "state.json"
def _prj_p(): return MEMORY_DIR / "project.json"

def _load_mem(): return _load(_mem_p()).get("entries", [])
def _save_mem(e): _save(_mem_p(), {"entries": e})
def _load_agt(): return _load(_agt_p())
def _save_agt(a): _save(_agt_p(), a)
def _load_sta(): return _load(_sta_p())
def _save_sta(s): _save(_sta_p(), s)
def _load_prj(): return _load(_prj_p())
def _save_prj(p): _save(_prj_p(), p)

def _mark_prev_kia(exclude=None, platform=None, agent_name=None):
    """Platform-scoped KIA: only kills agents on the SAME platform.
    Agents from different platforms (claude, cursor, antigravity) coexist.
    Same name + same platform → handled by update logic in memory_agent_join, not KIA'd here."""
    agents = _load_agt(); changed = False
    for aid, info in agents.items():
        if aid == exclude or info.get("status") != AgentStatus.ACTIVE:
            continue
        # Same platform, different name → replaced (sequential per platform)
        if platform and info.get("agent_platform") == platform and info.get("agent_name") != agent_name:
            info["status"] = AgentStatus.KIA
            info["kia_at"] = _now()
            info["kia_reason"] = "replaced_same_platform"
            changed = True
        # Same name + same platform → skip (caller will update existing entry)
        # Different platform → LEAVE ALONE (multi-agent concurrency)
    if changed: _save_agt(agents)

def _touch_heartbeat(agent_name: str):
    """Update last_activity for all active records of this agent."""
    agents = _load_agt(); changed = False
    for a in agents.values():
        if a.get("agent_name") == agent_name and a.get("status") == AgentStatus.ACTIVE:
            a["last_activity"] = time.time()
            changed = True
    if changed: _save_agt(agents)

_last_sweep_ts = 0
_SWEEP_MIN_INTERVAL = 30  # debounce: max once per 30s

def _lazy_kia_sweep():
    """Auto-KIA agents idle longer than IDLE_KIA_MIN. Debounced."""
    global _last_sweep_ts
    if time.time() - _last_sweep_ts < _SWEEP_MIN_INTERVAL:
        return
    _last_sweep_ts = time.time()
    agents = _load_agt(); changed = False; now = time.time()
    for a in agents.values():
        if a.get("status") != AgentStatus.ACTIVE:
            continue
        idle_sec = now - a.get("last_activity", 0)
        if idle_sec > IDLE_KIA_MIN * 60:
            a["status"] = AgentStatus.KIA
            a["kia_at"] = _now()
            a["kia_reason"] = f"idle_{int(idle_sec // 60)}min"
            changed = True
    if changed: _save_agt(agents)

def _require_joined(agent_name: str) -> Optional[str]:
    """Check if agent has joined. Returns error message if not, None if OK."""
    agents = _load_agt()
    for a in agents.values():
        if a.get("agent_name") == agent_name and a.get("status") == AgentStatus.ACTIVE:
            return None
    return (
        f"⛔ NOT ON BOARD: Agent `{agent_name}` has not joined this project.\n\n"
        f"**Get On Board** — follow these steps IN ORDER:\n"
        f"1. `memory_onboard(agent_name='{agent_name}', agent_platform='...')` — join and read context\n"
        f"2. Then call the write/ticket/checkpoint tool again.\n\n"
        f"Bootstrap-only tools like `memory_get_briefing(mode='brief')` and `memory_doctor()` remain safe before onboarding."
    )

def _on_board_protocol_xml() -> str:
    return "\n".join([
        "<on_board_protocol>",
        "  <required_first_call>memory_onboard</required_first_call>",
        "  <agent_identity>Use a stable agent_name. Do not include dates, model names, or session ids.</agent_identity>",
        "  <write_policy>Write after meaningful actions only.</write_policy>",
        "  <ticket_policy>Ticket mutations require an onboarded agent session.</ticket_policy>",
        "  <handoff_policy>Always handoff before leaving.</handoff_policy>",
        "</on_board_protocol>",
    ])

# ── Tiered Memory Engine ────────────────────────────────
def _archive_p(): return MEMORY_DIR / "archive.json"
def _digests_p(): return MEMORY_DIR / "digests.json"

def _load_archive(): return _load(_archive_p()).get("entries", [])
def _save_archive(e): _save(_archive_p(), {"entries": e})
def _load_digests(): return _load(_digests_p()).get("digests", [])
def _save_digests(d): _save(_digests_p(), {"digests": d})

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4

def _count_mem_tokens(memories: list) -> int:
    """Estimate total tokens across all memory entries."""
    total = 0
    for m in memories:
        total += _estimate_tokens(m.get("title", ""))
        total += _estimate_tokens(m.get("content", ""))
    return total

def _rank_memory_hits(query: str, memories: list) -> list:
    """Rank memory hits by relevance, then recency.

    This intentionally stays local and deterministic. It improves keyword search
    without introducing a vector backend or changing the JSON source of truth.
    """
    q = query.lower().strip()
    terms = [t for t in q.split() if t]
    now = time.time()
    type_weight = {
        "blocker": 8,
        "warning": 7,
        "decision": 6,
        "handoff": 6,
        "checkpoint": 4,
        "todo": 4,
        "discovery": 3,
        "context": 2,
        "file_change": 2,
        "progress": 1,
    }
    ranked = []

    for m in memories:
        title = str(m.get("title", "")).lower()
        content = str(m.get("content", "")).lower()
        tags = " ".join(m.get("tags", [])).lower()
        agent = str(m.get("agent_name", "")).lower()
        files = " ".join(m.get("related_files", [])).lower()
        haystack = f"{title} {content} {tags} {agent} {files}"

        if q not in haystack and not any(t in haystack for t in terms):
            continue

        score = 0
        if q in title: score += 18
        if q in tags: score += 14
        if q in files: score += 12
        if q in agent: score += 8
        if q in content: score += 6

        for term in terms:
            if term in title: score += 5
            if term in tags: score += 4
            if term in files: score += 4
            if term in content: score += 1

        score += type_weight.get(m.get("memory_type", ""), 0)
        score += int(m.get("priority", 0)) * 3
        if m.get("pinned"):
            score += 8

        age_hours = (now - m.get("timestamp", 0)) / 3600 if m.get("timestamp") else 9999
        if age_hours <= 24:
            score += 4
        elif age_hours <= 24 * 7:
            score += 2

        ranked.append((score, m.get("timestamp", 0), m))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked

def _tokenize_for_vector(text: str) -> list:
    return re.findall(r"[a-z0-9_./-]+", text.lower())

def _local_vector(text: str) -> dict:
    vec = {}
    for token in _tokenize_for_vector(text):
        vec[token] = vec.get(token, 0) + 1
    return vec

def _cosine_similarity(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    dot = sum(weight * b.get(token, 0) for token, weight in a.items())
    norm_a = math.sqrt(sum(weight * weight for weight in a.values()))
    norm_b = math.sqrt(sum(weight * weight for weight in b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)

def _memory_search_text(m: dict) -> str:
    return " ".join([
        str(m.get("title", "")),
        str(m.get("content", "")),
        " ".join(m.get("tags", [])),
        str(m.get("agent_name", "")),
        " ".join(m.get("related_files", [])),
        " ".join(m.get("related_tickets", [])),
        str(m.get("memory_type", "")),
    ])

def _enum_value(value):
    return value.value if hasattr(value, "value") else value

def _same_memory_fingerprint(a: dict, params) -> bool:
    return (
        a.get("agent_name") == params.agent_name
        and str(_enum_value(a.get("memory_type"))) == str(_enum_value(params.memory_type))
        and str(a.get("title", "")).strip() == params.title.strip()
        and str(a.get("content", "")).strip() == params.content.strip()
        and sorted(a.get("tags", [])) == sorted(params.tags or [])
        and sorted(a.get("related_files", [])) == sorted(params.related_files or [])
        and sorted(a.get("related_tickets", [])) == sorted(params.related_tickets or [])
    )

def _recent_duplicate_memory(memories: list, params, within_seconds: int = 600) -> Optional[dict]:
    now = time.time()
    for memory in reversed(memories):
        if now - memory.get("timestamp", 0) > within_seconds:
            continue
        if _same_memory_fingerprint(memory, params):
            return memory
    return None

def _local_vector_search(query: str, memories: list) -> list:
    query_vec = _local_vector(query)
    ranked = []
    for m in memories:
        similarity = _cosine_similarity(query_vec, _local_vector(_memory_search_text(m)))
        if similarity <= 0:
            continue
        score = similarity
        score += int(m.get("priority", 0)) * 0.03
        if m.get("pinned"):
            score += 0.08
        ranked.append((score, m.get("timestamp", 0), m))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked

def _ticket_related_memories(ticket: dict, memories: list, limit: int = 8) -> list:
    ticket_id = str(ticket.get("id", "")).lower()
    title_terms = [t for t in _tokenize_for_vector(ticket.get("title", "")) if len(t) > 2]
    desc_terms = [t for t in _tokenize_for_vector(ticket.get("description", "")) if len(t) > 3]
    tags = [str(t).lower() for t in ticket.get("tags", [])]
    files = [str(f).lower() for f in ticket.get("related_files", [])]
    required = [str(f).lower() for f in ticket.get("required_fields", [])]
    ranked = []

    for m in memories:
        text = _memory_search_text(m).lower()
        score = 0
        if ticket_id and ticket_id in text:
            score += 50
        if ticket.get("id") in m.get("related_tickets", []):
            score += 80
        for filename in files:
            if filename and filename in text:
                score += 25
        for tag in tags:
            if tag and tag in text:
                score += 12
        for field in required:
            if field and field in text:
                score += 8
        score += sum(3 for term in title_terms if term in text)
        score += sum(1 for term in desc_terms if term in text)

        if score <= 0:
            continue
        score += int(m.get("priority", 0)) * 3
        if m.get("pinned"):
            score += 5
        ranked.append((score, m.get("timestamp", 0), m))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[:limit]

def _doctor_data_integrity(agents: dict, tickets: list, memories: list) -> list:
    warnings = []
    active_names = set()
    active_identities = {}

    for agent in agents.values():
        if agent.get("status") != AgentStatus.ACTIVE:
            continue
        name = agent.get("agent_name", "unknown")
        platform = agent.get("agent_platform", "unknown")
        active_names.add(name)
        active_identities.setdefault((name, platform), 0)
        active_identities[(name, platform)] += 1

    for (name, platform), count in active_identities.items():
        if count > 1:
            warnings.append(f"- ⚠️ duplicate active agent identity: `{name}` on `{platform}` ({count} records)")

    active_ticket_statuses = {
        TicketStatus.CLAIMED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.CREATING_REPORT,
        TicketStatus.SUBMITTED,
        TicketStatus.REVIEWING,
        TicketStatus.IN_REVIEW,
    }
    for ticket in tickets:
        status = ticket.get("status")
        claimed_by = ticket.get("claimed_by")
        if status in active_ticket_statuses and claimed_by and claimed_by not in active_names:
            warnings.append(f"- ⚠️ orphaned ticket: `{ticket.get('id', '?')}` claimed by inactive/missing `{claimed_by}`")

        missing = []
        for field in ("target_url", "scope", "required_fields"):
            if not ticket.get(field):
                missing.append(field)
        if missing and status not in (TicketStatus.CLOSED, TicketStatus.CANCELED, TicketStatus.TERMINATED):
            warnings.append(f"- ⚠️ invalid ticket schema: `{ticket.get('id', '?')}` missing {', '.join(missing)}")

    memory_ids = set()
    duplicate_memory_ids = set()
    for memory in memories:
        mid = memory.get("id")
        if not mid:
            continue
        if mid in memory_ids:
            duplicate_memory_ids.add(mid)
        memory_ids.add(mid)
    if duplicate_memory_ids:
        warnings.append(f"- ⚠️ duplicate memory IDs: {', '.join(sorted(duplicate_memory_ids))}")

    return warnings

def _doctor_file(path: Path, label: str, required: bool = True, executable: bool = False, json_file: bool = False) -> tuple:
    if not path.exists():
        display = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
        if required:
            return "missing", f"- ❌ {label}: missing `{display}`"
        return "optional-missing", f"- ⚪ {label}: not installed `{display}`"
    if executable and not os.access(path, os.X_OK):
        return "warn", f"- ⚠️ {label}: exists but is not executable `{path}`"
    if json_file:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as ex:
            return "fail", f"- ❌ {label}: invalid JSON `{path}` ({ex})"
    return "ok", f"- ✅ {label}: ok"

def _doctor_gitignore() -> tuple:
    gi = PROJECT_ROOT / ".gitignore"
    if not gi.exists():
        return "fail", "- ❌ .gitignore: missing"
    content = gi.read_text(encoding="utf-8", errors="replace")
    required = [".agent-mem/"]
    local_only = [".agent/", ".agent-mem-hooks/", ".claude/", ".codex/", ".cursor/", "AGENTS.md", "CLAUDE.md"]
    missing_required = [entry for entry in required if entry not in content]
    missing_local = [entry for entry in local_only if entry not in content]
    if missing_required:
        return "fail", f"- ❌ .gitignore: missing required runtime ignores: {', '.join(missing_required)}"
    if missing_local:
        return "warn", f"- ⚠️ .gitignore: runtime memory ignored; local helper ignores missing: {', '.join(missing_local)}"
    return "ok", "- ✅ .gitignore: runtime/local paths ignored"

def _rule_based_compress(entries: list, error: str = "") -> str:
    """Compress with deterministic regex-style rules — extract key facts, drop verbose content."""
    lines = []
    if error:
        lines.append(f"*[Compressed with regex fallback: {error[:80]}]*\n")

    by_type = {}
    for e in entries:
        by_type.setdefault(e["memory_type"], []).append(e)

    # Decisions — keep full
    if "decision" in by_type:
        lines.append("## Decisions")
        for d in by_type["decision"]:
            lines.append(f"- **{d['title']}** (`{d['agent_name']}`): {d['content'][:150]}")

    # Progress — compress to one line each
    if "progress" in by_type:
        lines.append("\n## Progress")
        for p in by_type["progress"]:
            lines.append(f"- {p['title']} (`{p['agent_name']}`)")

    # Warnings, blockers — keep
    for t in ("warning", "blocker"):
        if t in by_type:
            lines.append(f"\n## {t.title()}s")
            for w in by_type[t]:
                lines.append(f"- **{w['title']}** (`{w['agent_name']}`): {w['content'][:150]}")

    # File changes — keep
    if "file_change" in by_type:
        lines.append("\n## Files")
        for f in by_type["file_change"]:
            lines.append(f"- {f['title']} (`{f['agent_name']}`)")

    # Discoveries — keep title only
    if "discovery" in by_type:
        lines.append("\n## Discoveries")
        for d in by_type["discovery"]:
            lines.append(f"- {d['title']} (`{d['agent_name']}`)")

    # Everything else — count only
    other_types = set(by_type.keys()) - {"decision","progress","warning","blocker","file_change","discovery","handoff","checkpoint"}
    for t in other_types:
        lines.append(f"\n*{len(by_type[t])} {t} entries compressed*")

    return "\n".join(lines)

def _split_hot_cold(memories: list) -> tuple:
    """Split memories into hot (recent) and cold (old) based on time and count."""
    if len(memories) <= MAX_HOT_ENTRIES:
        return memories, []

    cutoff_time = time.time() - (HOT_WINDOW_HOURS * 3600)

    # Always keep: pinned, handoffs, latest checkpoint
    hot = []
    cold = []

    for m in memories:
        is_protected = (
            m.get("pinned") or
            m["memory_type"] == MemoryType.HANDOFF or
            m.get("priority", 0) >= 2
        )
        is_recent = m.get("timestamp", 0) >= cutoff_time

        if is_protected or is_recent:
            hot.append(m)
        else:
            cold.append(m)

    # If still too many hot, keep only the most recent MAX_HOT_ENTRIES
    if len(hot) > MAX_HOT_ENTRIES:
        # Sort by priority desc then timestamp desc
        hot.sort(key=lambda m: (m.get("priority", 0), m.get("timestamp", 0)), reverse=True)
        overflow = hot[MAX_HOT_ENTRIES:]
        hot = hot[:MAX_HOT_ENTRIES]
        cold = overflow + cold

    return hot, cold

# ── Input Models ────────────────────────────────────────
class ProjectInitInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    description: str = Field(..., description="What this project is about", min_length=1, max_length=1000)
    tech_stack: Optional[str] = Field(default=None, description="Tech stack summary")

class AgentJoinInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., description="Your stable identity — keep the SAME name across sessions. Example: 'claude-main', 'cursor-coder', 'codex-main'. Do NOT put dates or model names in here.", min_length=1, max_length=100)
    agent_platform: str = Field(default="unknown", description="Platform: claude, cursor, codex, claude-code, antigravity, windsurf, other", max_length=50)
    agent_role: str = Field(default="main", description="Role: main (default), reviewer, utility, planner", max_length=30)
    task_focus: Optional[str] = Field(default=None, description="What you'll work on this session", max_length=500)

class MemoryWriteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., description="Your agent name — same name you used in memory_onboard or memory_agent_join. Example: cursor-coder", min_length=1, max_length=100)
    memory_type: MemoryType = Field(..., description="One of: decision, progress, blocker, context, handoff, todo, file_change, discovery, warning, checkpoint")
    title: str = Field(..., description="Short one-line summary of what happened", min_length=1, max_length=200)
    content: str = Field(..., description="Detailed description — be specific, include file names and reasoning", min_length=1, max_length=10000)
    tags: Optional[List[str]] = Field(default_factory=list)
    related_files: Optional[List[str]] = Field(default_factory=list)
    related_tickets: Optional[List[str]] = Field(default_factory=list)
    priority: Optional[int] = Field(default=0, ge=0, le=3, description="0=normal 3=critical(auto-pin)")

class MemoryReadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    memory_type: Optional[MemoryType] = None
    tag: Optional[str] = None
    agent_name: Optional[str] = Field(default=None, description="Filter by who wrote it")
    since_minutes: Optional[int] = Field(default=None, ge=1)
    limit: Optional[int] = Field(default=50, ge=1, le=500)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class CheckpointInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., min_length=1, max_length=100)
    summary: str = Field(..., min_length=1, max_length=5000)
    remaining_tasks: Optional[List[str]] = Field(default_factory=list)
    active_branch: Optional[str] = None
    blockers: Optional[List[str]] = Field(default_factory=list)

class HandoffInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., min_length=1, max_length=100)
    summary: str = Field(..., min_length=1, max_length=5000)
    next_steps: List[str] = Field(..., min_length=1)
    warnings: Optional[List[str]] = Field(default_factory=list)
    files_modified: Optional[List[str]] = Field(default_factory=list)
    files_created: Optional[List[str]] = Field(default_factory=list)

class BriefingInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    mode: Optional[BriefingMode] = Field(default=BriefingMode.NORMAL, description="Briefing workflow mode: brief, normal, deep, or handoff-only")
    ticket_id: Optional[str] = Field(default=None, description="Focus briefing on one ticket ID")
    focus_area: Optional[str] = None
    include_full_history: Optional[bool] = False
    token_budget: Optional[int] = Field(default=None, description="Max tokens for briefing output. Overrides mode default.", ge=500, le=50000)
    suppress_protocol: Optional[bool] = Field(default=False, description="Hide the mandatory protocol footer when another tool already handles onboarding")

class OnboardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., description="Your stable identity — keep the SAME name across sessions. Example: 'claude-main', 'cursor-coder', 'codex-main'.", min_length=1, max_length=100)
    agent_platform: str = Field(default="unknown", description="Platform: claude, cursor, codex, claude-code, antigravity, windsurf, other", max_length=50)
    agent_role: str = Field(default="main", description="Role: main (default), reviewer, utility, planner", max_length=30)
    task_focus: Optional[str] = Field(default=None, description="What you'll work on this session", max_length=500)
    mode: Optional[BriefingMode] = Field(default=BriefingMode.NORMAL, description="Briefing workflow mode")
    ticket_id: Optional[str] = Field(default=None, description="Optional ticket ID to focus the briefing")
    focus_area: Optional[str] = Field(default=None, description="Optional topic/file/area to focus the briefing", max_length=500)
    token_budget: Optional[int] = Field(default=None, description="Max tokens for briefing output. Overrides mode default.", ge=500, le=50000)
    include_tickets: Optional[bool] = Field(default=True, description="Include open ticket queue after the briefing")
    include_health: Optional[bool] = Field(default=True, description="Include data-integrity warnings after the briefing")

class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    query: str = Field(..., min_length=1, max_length=200)
    limit: Optional[int] = Field(default=20, ge=1, le=100)

class VectorSearchInput(SearchInput):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    backend: Optional[VectorBackend] = Field(default=None, description="Override AGENT_MEM_VECTOR_BACKEND. Supported: none, local")

class MemoryLinksInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    ticket_id: Optional[str] = Field(default=None, description="Focus links on one ticket ID")
    agent_name: Optional[str] = Field(default=None, description="Focus links on one agent")
    file: Optional[str] = Field(default=None, description="Focus links on one related file")
    include_archive: Optional[bool] = Field(default=False, description="Include archived memories in link analysis")
    limit: Optional[int] = Field(default=20, ge=1, le=100)

class PinInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    memory_id: str = Field(..., min_length=1)
    pinned: bool = True

class UpdateStateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., max_length=5000)
    agent_name: Optional[str] = Field(default=None, max_length=100)

class CompactInput(BaseModel):
    """Compact old memories into digests to save tokens."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: Optional[str] = Field(default=None, description="Who is running the compaction", max_length=100)
    force: Optional[bool] = Field(default=False, description="Force compaction even if under threshold")
    strategy: Literal["agent", "regex"] = Field(default="agent", description="Compaction strategy: 'agent' (default, trust agent-written context digests; requires memory_write before this call — see memory-digest-thrift skill) or 'regex' (deterministic fallback summary generated by the server).")

class BootstrapInput(BaseModel):
    """Bootstrap memory for an existing project by scanning the codebase."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., description="Your agent name doing the bootstrap", min_length=1, max_length=100)
    description: str = Field(..., description="Project description", min_length=1, max_length=1000)
    tech_stack: Optional[str] = Field(default=None, description="Tech stack")
    scan_readme: Optional[bool] = Field(default=True, description="Read README.md/README for context")
    scan_git: Optional[bool] = Field(default=True, description="Scan recent git log for history")
    scan_structure: Optional[bool] = Field(default=True, description="Scan directory structure")
    scan_config: Optional[bool] = Field(default=True, description="Read package.json, pyproject.toml, etc. for tech stack")
    extra_context: Optional[str] = Field(default=None, description="Any additional context you want to seed", max_length=5000)
    current_task: Optional[str] = Field(default=None, description="What the project should work on next", max_length=1000)
    known_warnings: Optional[List[str]] = Field(default_factory=list, description="Gotchas you already know about")

# ── Tools ───────────────────────────────────────────────

@mcp.tool(name="memory_init", annotations={"title":"Initialize Project Memory","readOnlyHint":False,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_init(params: ProjectInitInput) -> str:
    """Initialize .agent-mem/ in the project root. Call once per project. Safe to re-call."""
    _ensure()
    prj = _load_prj()
    if prj:
        return f"Already initialized at `{MEMORY_DIR}`\n**Description**: {prj.get('description')}\nUse `memory_onboard` to join and catch up."
    prj = {"description": params.description, "tech_stack": params.tech_stack, "project_root": str(PROJECT_ROOT), "created_at": _now()}
    _save_prj(prj); _save_mem([]); _save_agt({}); _save_sta({})
    return f"✅ Initialized at `{MEMORY_DIR}`\n**Project**: {PROJECT_ROOT.name}\n**Description**: {params.description}\n**Tech**: {params.tech_stack or 'N/A'}\n\nNext: `memory_onboard`"

@mcp.tool(name="memory_agent_join", annotations={"title":"Register as Active Agent","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_agent_join(params: AgentJoinInput) -> str:
    """Register as the active agent. KIAs only agents on the SAME platform (multi-agent concurrency).
    Your agent_name is stamped on EVERY write for traceability."""
    prj = _load_prj()
    if not prj: return "Error: Not initialized. Call `memory_init` first."
    _lazy_kia_sweep()  # clean up idle agents before joining
    _mark_prev_kia(platform=params.agent_platform, agent_name=params.agent_name)
    agents = _load_agt()
    # Update existing active entry if same name+platform, otherwise create new
    existing_aid = next(
        (k for k, v in agents.items()
         if v.get("agent_name") == params.agent_name
         and v.get("agent_platform") == params.agent_platform
         and v.get("status") == AgentStatus.ACTIVE),
        None
    )
    rejoined = existing_aid is not None
    if rejoined:
        aid = existing_aid
        agents[aid]["agent_role"] = params.agent_role
        agents[aid]["task_focus"] = params.task_focus
        agents[aid]["last_activity"] = time.time()
    else:
        aid = f"{params.agent_platform}-{_id()}"
        agents[aid] = {"agent_name": params.agent_name, "agent_platform": params.agent_platform,
                       "agent_role": params.agent_role, "task_focus": params.task_focus, "status": AgentStatus.ACTIVE,
                       "joined_at": _now(), "last_activity": time.time(), "memories_written": 0}
    _save_agt(agents)
    status_line = "🔄 **Rejoined**" if rejoined else "🟢 **On Board**"
    lines = [f"{status_line}: `{params.agent_name}` ({params.agent_platform})", f"ID: `{aid}`", ""]
    # Naming warning
    if params.agent_name == params.agent_platform or len(params.agent_name) < 5 or params.agent_name[0].isupper():
        lines.append("⚠️ **Naming tip**: Use a stable lowercase role name like `claude-main`, `cursor-coder`, or `codex-reviewer`. Do not include dates, model names, or session IDs.\n")
    # Show currently active agents on OTHER platforms
    active_others = {k:v for k,v in agents.items() if k != aid and v.get("status") == AgentStatus.ACTIVE}
    if active_others:
        lines.append("🌐 **Co-active agents** (other platforms):")
        for k,v in active_others.items():
            lines.append(f"  🟢 `{v['agent_name']}` ({v['agent_platform']})")
        lines.append("")
    # Show recent agents (bounded for context)
    prev = sorted(
        [(k,v) for k,v in agents.items() if k != aid and v.get("status") != AgentStatus.ACTIVE],
        key=lambda x: x[1].get("last_activity", 0), reverse=True
    )[:AGENT_HISTORY_LIMIT]
    if prev:
        lines.append("📜 **Recent agents**:")
        for k,v in prev:
            e = {"active":"🟢","kia":"💀","completed":"✅","handed_off":"🤝"}.get(v.get("status",""),"❓")
            lines.append(f"  {e} `{v['agent_name']}` ({v['agent_platform']}) — {v['status']}")
        lines.append("")
    mem = _load_mem()
    ho = [m for m in mem if m["memory_type"] == MemoryType.HANDOFF]
    if ho: lines.append(f"🤝 Last handoff from `{ho[-1]['agent_name']}` — read the briefing!\n")
    # Show pending tickets for this agent
    tickets = _load_ticket_index()
    my_tickets = [t for t in tickets if t["status"] in (TicketStatus.OPEN, TicketStatus.REJECTED, TicketStatus.CLAIMED)
                  and (not t.get("assigned_to")
                       or params.agent_name.lower() in t["assigned_to"].lower()
                       or params.agent_platform.lower() in t["assigned_to"].lower())]
    if my_tickets:
        pri_emoji = {"low":"🟢","medium":"🟡","high":"🟠","critical":"🔴"}
        lines.append(f"🎫 **{len(my_tickets)} ticket(s) waiting for you!**")
        for t in my_tickets:
            pe = pri_emoji.get(t["priority"],"⚪")
            rej = f" ⚠️ rejected {t['rejection_count']}x" if t.get("rejection_count") else ""
            lines.append(f"  {pe} `{t['id']}` — {t['title']} (from `{t['created_by']}`){rej}")
        lines.append(f"Use `memory_list_tickets` for details, `memory_claim_ticket` to start.\n")
    lines += ["⚡ **Protocol**:", "1. `memory_get_briefing` — read context NOW if you did not call `memory_onboard`",
              "2. `memory_write` — after significant actions", "3. `memory_checkpoint` — every 10-15 min",
              "4. `memory_handoff` — before leaving", f"5. Always use agent_name=`{params.agent_name}`"]
    return "\n".join(lines)

@mcp.tool(name="memory_onboard", annotations={"title":"On Board Agent Session","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_onboard(params: OnboardInput) -> str:
    """One-call session entrypoint: register the agent, read briefing, inspect tickets, and surface data-health warnings."""
    if not _load_prj():
        return "No .agent-mem/ found. Run `memory_init`."

    join_output = await memory_agent_join(AgentJoinInput(
        agent_name=params.agent_name,
        agent_platform=params.agent_platform,
        agent_role=params.agent_role,
        task_focus=params.task_focus,
    ))
    briefing_output = await memory_get_briefing(BriefingInput(
        mode=params.mode,
        ticket_id=params.ticket_id,
        focus_area=params.focus_area,
        token_budget=params.token_budget,
        suppress_protocol=True,
    ))

    lines = [
        _on_board_protocol_xml(),
        "",
        f"# 🚢 On Board Session: `{params.agent_name}`",
        f"*Platform: `{params.agent_platform}` | Role: `{params.agent_role}`*",
    ]
    if params.task_focus:
        lines.append(f"*Focus: {params.task_focus}*")
    lines.extend(["", "## Agent Registration", join_output, "", "## Briefing", briefing_output])

    if params.include_tickets:
        tickets_output = await memory_list_tickets(ListTicketsInput(include_closed=False))
        lines.extend(["", "## Open Tickets", tickets_output])

    if params.include_health:
        warnings = _doctor_data_integrity(_load_agt(), _load_ticket_index(), _load_mem())
        lines.append("")
        lines.append("## Data Health")
        if warnings:
            lines.extend(warnings[:12])
            if len(warnings) > 12:
                lines.append(f"- ... {len(warnings) - 12} more warnings. Run `memory_doctor()` for full detail.")
        else:
            lines.append("- ✅ No data-integrity warnings.")

    lines.extend([
        "",
        "## Next",
        f"- Use `agent_name=\"{params.agent_name}\"` on every write, ticket mutation, checkpoint, and handoff.",
        "- Use `memory_write` after meaningful changes only.",
        "- Use `memory_handoff` before leaving the task.",
    ])
    return "\n".join(lines)

@mcp.tool(name="memory_write", annotations={"title":"Write Memory","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_write(params: MemoryWriteInput) -> str:
    """Write a memory entry stamped with your agent_name."""
    err = _require_joined(params.agent_name)
    if err: return err
    _touch_heartbeat(params.agent_name)
    mem = _load_mem()
    duplicate = _recent_duplicate_memory(mem, params)
    if duplicate:
        return (
            f"⚠️ Duplicate skipped: `{duplicate['id']}` by **{params.agent_name}**\n"
            f"Exact same memory was written recently. Link to the existing entry instead of adding noise.\n"
            f"**{duplicate['title']}**"
        )
    entry = {"id": _id(), "agent_name": params.agent_name, "memory_type": params.memory_type,
             "title": params.title, "content": params.content, "tags": params.tags or [],
             "related_files": params.related_files or [], "related_tickets": params.related_tickets or [],
             "priority": params.priority or 0,
             "pinned": (params.priority or 0) >= 3, "created_at": _now(), "timestamp": time.time()}
    mem.append(entry); _save_mem(mem)
    agents = _load_agt()
    for a in agents.values():
        if a.get("agent_name") == params.agent_name and a.get("status") == AgentStatus.ACTIVE:
            a["memories_written"] = a.get("memories_written",0) + 1; a["last_activity"] = time.time(); break
    _save_agt(agents)
    e = {"decision":"🏛️","progress":"✅","blocker":"🚫","context":"📖","handoff":"🤝","todo":"📝","file_change":"📁","discovery":"💡","warning":"⚠️","checkpoint":"💾"}.get(params.memory_type,"📌")
    links = []
    if entry["related_tickets"]:
        links.append("tickets: " + ", ".join(f"`{t}`" for t in entry["related_tickets"]))
    if entry["related_files"]:
        links.append("files: " + ", ".join(f"`{f}`" for f in entry["related_files"][:5]))
    link_line = "\n" + " | ".join(links) if links else ""
    return f"{e} Saved `{entry['id']}` by **{params.agent_name}** | {params.memory_type.value} | {'🔴'*(params.priority or 0) or '⚪'}\n**{params.title}**{link_line}"

@mcp.tool(name="memory_read", annotations={"title":"Read Memories","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_read(params: MemoryReadInput) -> str:
    """Read memories with filters. Filter by agent_name to trace who wrote what."""
    mem = _load_mem()
    if not mem: return "No memories yet."
    f = mem
    if params.memory_type: f = [m for m in f if m["memory_type"] == params.memory_type]
    if params.tag: f = [m for m in f if params.tag in m.get("tags",[])]
    if params.agent_name: f = [m for m in f if m.get("agent_name") == params.agent_name]
    if params.since_minutes: cut = time.time()-(params.since_minutes*60); f = [m for m in f if m.get("timestamp",0) >= cut]
    f.sort(key=lambda m: m.get("timestamp",0), reverse=True); f = f[:params.limit]
    if not f: return "No matches."
    if params.response_format == ResponseFormat.JSON: return json.dumps(f, indent=2)
    lines = [f"# 📚 {len(f)} entries\n"]
    for m in f:
        pin = "📌 " if m.get("pinned") else ""
        lines.append(f"### {pin}[{m['memory_type'].upper()}] {m['title']}")
        lines.append(f"*✍️ {m['agent_name']} | {m['created_at']}*\n{m['content']}")
        if m.get("tags"): lines.append(f"Tags: {', '.join(m['tags'])}")
        lines.append("---\n")
    return "\n".join(lines)

@mcp.tool(name="memory_search", annotations={"title":"Search Memories","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_search(params: SearchInput) -> str:
    """Search across all memories with local relevance ranking."""
    mem = _load_mem()
    ranked = _rank_memory_hits(params.query, mem)
    hits = ranked[:params.limit]
    if not hits: return f"No results for '{params.query}'."
    lines = [f"# 🔍 '{params.query}' — {len(hits)} results\n"]
    for score, _, m in hits:
        pin = "📌 " if m.get("pinned") else ""
        lines.append(f"### [{m['memory_type'].upper()}] {m['title']}")
        lines.append(f"*{pin}score {score} | ✍️ {m['agent_name']} | {m.get('created_at','')}*")
        lines.append(f"{m['content'][:300]}{'...' if len(m.get('content',''))>300 else ''}")
        if m.get("tags"):
            lines.append(f"Tags: {', '.join(m['tags'])}")
        if m.get("related_files"):
            lines.append(f"Files: {', '.join(m['related_files'][:5])}")
        lines.append("---\n")
    return "\n".join(lines)

@mcp.tool(name="memory_search_vector", annotations={"title":"Vector-style Search Memories","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_search_vector(params: VectorSearchInput) -> str:
    """Optional vector-style search. Disabled by default; JSON remains canonical."""
    backend = params.backend or VectorBackend(VECTOR_BACKEND if VECTOR_BACKEND in {b.value for b in VectorBackend} else "none")
    if backend == VectorBackend.NONE:
        return (
            "Vector search is disabled.\n\n"
            "Set `AGENT_MEM_VECTOR_BACKEND=local` or pass `backend='local'` to use the local vector-style backend. "
            "This does not send data outside the machine and does not replace `.agent-mem/*.json`."
        )

    mem = _load_mem()
    hits = _local_vector_search(params.query, mem)[:params.limit]
    if not hits:
        return f"No vector-style results for '{params.query}'."

    lines = [f"# 🧭 Vector-style Search: '{params.query}' — {len(hits)} results", f"*Backend: `{backend.value}`*\n"]
    for score, _, m in hits:
        pin = "📌 " if m.get("pinned") else ""
        lines.append(f"### [{m['memory_type'].upper()}] {m['title']}")
        lines.append(f"*{pin}similarity {score:.3f} | ✍️ {m['agent_name']} | {m.get('created_at','')}*")
        lines.append(f"{m['content'][:300]}{'...' if len(m.get('content',''))>300 else ''}")
        if m.get("tags"):
            lines.append(f"Tags: {', '.join(m['tags'])}")
        if m.get("related_files"):
            lines.append(f"Files: {', '.join(m['related_files'][:5])}")
        lines.append("---\n")
    return "\n".join(lines)

@mcp.tool(name="memory_links", annotations={"title":"View Memory Linkage","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_links(params: MemoryLinksInput) -> str:
    """Show ticket, file, agent, and tag relationships across memory entries."""
    memories = _load_mem()
    if params.include_archive:
        memories = memories + _load_archive()
    tickets = _load_ticket_index()

    if params.agent_name:
        memories = [m for m in memories if m.get("agent_name") == params.agent_name]
        tickets = [t for t in tickets if t.get("created_by") == params.agent_name or t.get("claimed_by") == params.agent_name]

    if params.file:
        needle = params.file.lower()
        memories = [m for m in memories if any(needle in str(f).lower() for f in m.get("related_files", []))]
        tickets = [t for t in tickets if any(needle in str(f).lower() for f in t.get("related_files", []))]

    focus_ticket = None
    if params.ticket_id:
        focus_ticket = next((t for t in tickets if t.get("id") == params.ticket_id), None)
        if not focus_ticket:
            return f"Ticket `{params.ticket_id}` not found."
        related = [m for _, _, m in _ticket_related_memories(focus_ticket, memories, limit=params.limit or 20)]
        memories = related
        tickets = [focus_ticket]

    file_counts = {}
    tag_counts = {}
    agent_counts = {}
    ticket_counts = {}

    for memory in memories:
        agent = memory.get("agent_name", "unknown")
        agent_counts[agent] = agent_counts.get(agent, 0) + 1
        for f in memory.get("related_files", []):
            file_counts[f] = file_counts.get(f, 0) + 1
        for tag in memory.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for ticket_id in memory.get("related_tickets", []):
            ticket_counts[ticket_id] = ticket_counts.get(ticket_id, 0) + 1

    lines = ["# 🕸️ Memory Linkage", ""]
    filters = []
    if params.ticket_id: filters.append(f"ticket `{params.ticket_id}`")
    if params.agent_name: filters.append(f"agent `{params.agent_name}`")
    if params.file: filters.append(f"file `{params.file}`")
    if filters:
        lines.append("*Focus: " + ", ".join(filters) + "*")
        lines.append("")

    if tickets:
        lines.append("## Tickets")
        for ticket in tickets[:params.limit]:
            related = _ticket_related_memories(ticket, memories, limit=5)
            lines.append(f"- `{ticket.get('id')}` **{ticket.get('title', 'Untitled')}** ({ticket.get('status', '?')}, {ticket.get('priority', '?')})")
            if ticket.get("related_files"):
                lines.append("  Files: " + ", ".join(f"`{f}`" for f in ticket["related_files"][:5]))
            if related:
                lines.append("  Related memories:")
                for score, _, memory in related:
                    lines.append(f"  - [{memory.get('memory_type', '?').upper()}] **{memory.get('title', '')}** (`{memory.get('agent_name', '?')}`, score {score})")
        lines.append("")

    if memories:
        lines.append("## Memories")
        for memory in sorted(memories, key=lambda m: m.get("timestamp", 0), reverse=True)[:params.limit]:
            bits = []
            if memory.get("related_tickets"):
                bits.append("tickets " + ", ".join(f"`{t}`" for t in memory["related_tickets"]))
            if memory.get("related_files"):
                bits.append("files " + ", ".join(f"`{f}`" for f in memory["related_files"][:3]))
            suffix = " — " + " | ".join(bits) if bits else ""
            lines.append(f"- [{memory.get('memory_type', '?').upper()}] **{memory.get('title', '')}** (`{memory.get('agent_name', '?')}`){suffix}")
        lines.append("")

    if file_counts:
        lines.append("## Files")
        for f, count in sorted(file_counts.items(), key=lambda x: (-x[1], x[0]))[:params.limit]:
            lines.append(f"- `{f}` — {count} memories")
        lines.append("")

    if agent_counts:
        lines.append("## Agents")
        for agent, count in sorted(agent_counts.items(), key=lambda x: (-x[1], x[0]))[:params.limit]:
            lines.append(f"- `{agent}` — {count} memories")
        lines.append("")

    if tag_counts:
        lines.append("## Tags")
        for tag, count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:params.limit]:
            lines.append(f"- `{tag}` — {count} memories")
        lines.append("")

    if ticket_counts and not params.ticket_id:
        lines.append("## Explicit Memory → Ticket Links")
        for ticket_id, count in sorted(ticket_counts.items(), key=lambda x: (-x[1], x[0]))[:params.limit]:
            lines.append(f"- `{ticket_id}` — {count} memories")
        lines.append("")

    if len(lines) <= 2:
        return "No memory links found."
    return "\n".join(lines).rstrip()

@mcp.tool(name="memory_checkpoint", annotations={"title":"Save Checkpoint","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_checkpoint(params: CheckpointInput) -> str:
    """Full state checkpoint. Do every 10-15 min or before risky ops. Saves both as memory entry AND standalone file."""
    err = _require_joined(params.agent_name)
    if err: return err
    _touch_heartbeat(params.agent_name)
    cpd = {"summary": params.summary, "remaining_tasks": params.remaining_tasks or [],
           "active_branch": params.active_branch, "blockers": params.blockers or [], "state": _load_sta()}
    mem = _load_mem()
    entry = {"id": _id(), "agent_name": params.agent_name, "memory_type": MemoryType.CHECKPOINT,
             "title": f"Checkpoint: {params.summary[:80]}", "content": json.dumps(cpd, indent=2, default=str),
             "tags": ["checkpoint"], "related_files": [], "priority": 2, "pinned": True,
             "created_at": _now(), "timestamp": time.time()}
    mem.append(entry); _save_mem(mem)
    ts = _local_now().strftime("%Y%m%d_%H%M%S")
    cp_file = MEMORY_DIR / "checkpoints" / f"cp_{params.agent_name}_{ts}.json"
    _save(cp_file, cpd)
    return f"💾 Checkpoint by `{params.agent_name}` — {len(params.remaining_tasks or [])} tasks left, {len(params.blockers or [])} blockers"

@mcp.tool(name="memory_handoff", annotations={"title":"Handoff to Next Agent","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_handoff(params: HandoffInput) -> str:
    """Formal handoff. ALWAYS call before leaving. Next agent sees this first."""
    err = _require_joined(params.agent_name)
    if err: return err
    _touch_heartbeat(params.agent_name)
    content = f"## Summary\n{params.summary}\n\n## Next Steps\n" + "\n".join(f"{i+1}. {s}" for i,s in enumerate(params.next_steps)) + "\n"
    if params.warnings: content += "\n## ⚠️ Warnings\n" + "\n".join(f"- {w}" for w in params.warnings) + "\n"
    if params.files_modified: content += "\n## Modified\n" + "\n".join(f"- `{f}`" for f in params.files_modified) + "\n"
    if params.files_created: content += "\n## Created\n" + "\n".join(f"- `{f}`" for f in params.files_created) + "\n"
    mem = _load_mem()
    entry = {"id": _id(), "agent_name": params.agent_name, "memory_type": MemoryType.HANDOFF,
             "title": f"Handoff from {params.agent_name}", "content": content,
             "tags": ["handoff"], "related_files": (params.files_modified or [])+(params.files_created or []),
             "priority": 3, "pinned": True, "created_at": _now(), "timestamp": time.time()}
    mem.append(entry); _save_mem(mem)
    agents = _load_agt()
    for a in agents.values():
        if a.get("agent_name") == params.agent_name and a.get("status") == AgentStatus.ACTIVE:
            a["status"] = AgentStatus.HANDED_OFF; a["handed_off_at"] = _now(); break
    _save_agt(agents)
    return f"🤝 Handoff from `{params.agent_name}` — {len(params.next_steps)} next steps, {len(params.warnings or [])} warnings"

@mcp.tool(name="memory_get_briefing", annotations={"title":"Get Full Briefing","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_get_briefing(params: BriefingInput) -> str:
    """CALL THIS FIRST. Token-aware briefing with workflow modes.

    Loads: hot memories (full detail) + warm digests (compressed history).
    Use mode='brief' for handoff-first catchup, 'normal' for default onboarding,
    'deep' for broad context, or 'handoff-only' for fast task transfer."""
    prj = _load_prj()
    if not prj: return "No .agent-mem/ found. Run `memory_init`."
    _lazy_kia_sweep()  # clean up idle agents before briefing
    mem = _load_mem(); agents = _load_agt(); state = _load_sta()
    digests = _load_digests()
    tickets = _load_ticket_index()
    focus_ticket = None
    if params.ticket_id:
        focus_ticket = next((t for t in tickets if t.get("id") == params.ticket_id), None)
        if not focus_ticket:
            return f"Ticket `{params.ticket_id}` not found. Use `memory_list_tickets` to inspect available tickets."
    mode = params.mode or BriefingMode.NORMAL
    mode_defaults = {
        BriefingMode.HANDOFF_ONLY: 1500,
        BriefingMode.BRIEF: 2500,
        BriefingMode.NORMAL: 4000,
        BriefingMode.DEEP: 8000,
    }
    budget = params.token_budget or mode_defaults.get(mode, 4000)
    type_caps = dict(BRIEFING_TYPE_CAP)
    if mode == BriefingMode.BRIEF:
        type_caps.update({"decision": 6, "warning": 6, "blocker": 6, "discovery": 4, "todo": 6, "file_change": 3, "context": 3, "progress": 2})
    elif mode == BriefingMode.DEEP:
        type_caps.update({"discovery": 20, "todo": 20, "file_change": 15, "context": 15, "progress": 10})
    elif mode == BriefingMode.HANDOFF_ONLY:
        type_caps = {}
    include_detail_sections = mode != BriefingMode.HANDOFF_ONLY
    include_digests = mode in (BriefingMode.NORMAL, BriefingMode.DEEP)
    include_state = mode in (BriefingMode.NORMAL, BriefingMode.DEEP)
    used = 0

    def _add(text):
        nonlocal used
        cost = _estimate_tokens(text)
        if used + cost > budget and used > 500:
            return False
        used += cost
        L.append(text)
        return True

    L = []
    _add(f"# 📋 ON BOARD: {PROJECT_ROOT.name}")
    _add(f"*Mode: `{mode.value}` | Budget: ~{budget:,} tokens*")
    _add(f"**Description**: {prj.get('description')}\n**Tech**: {prj.get('tech_stack','N/A')}\n**Memories**: {len(mem)} hot + {len(digests)} digests\n")

    # Agents — always show, but keep briefing output bounded.
    agent_items = _recent_agent_items(agents)
    agent_heading = "## 👥 Agent History"
    if len(agents) > AGENT_HISTORY_LIMIT:
        agent_heading += f" (latest {AGENT_HISTORY_LIMIT} of {len(agents)})"
    _add(agent_heading)
    for aid,a in agent_items:
        e = {"active":"🟢","kia":"💀","completed":"✅","handed_off":"🤝"}.get(a.get("status",""),"❓")
        role = a.get("agent_role", "main")
        role_tag = f" [{role}]" if role != "main" else ""
        _add(f"- {e} **{a['agent_name']}**{role_tag} ({a['agent_platform']}) — {a['status']} — {a.get('memories_written',0)} writes")
        # Idle warning for active agents
        if a.get("status") == AgentStatus.ACTIVE:
            idle_sec = time.time() - a.get("last_activity", 0)
            if idle_sec > IDLE_WARN_MIN * 60:
                _add(f"  ⚠️ idle {int(idle_sec // 60)}min — may auto-KIA at {IDLE_KIA_MIN}min")
    _add("")

    # Handoff — highest priority, always include
    ho = [m for m in mem if m["memory_type"]==MemoryType.HANDOFF]
    if ho:
        h = ho[-1]
        _add("## 🤝 LATEST HANDOFF — READ FIRST")
        # Handoffs get full content, but truncate if over budget
        handoff_content = h['content']
        if _estimate_tokens(handoff_content) > budget // 3:
            handoff_content = handoff_content[:budget] + "\n... (truncated for token budget)"
        _add(f"*From **{h['agent_name']}** at {h['created_at']}*\n{handoff_content}\n")

    if focus_ticket:
        _add("## 🎫 Ticket Focus")
        _add(
            f"`{focus_ticket.get('id')}` **{focus_ticket.get('title', 'Untitled')}** "
            f"({focus_ticket.get('status', '?')}, {focus_ticket.get('priority', '?')})"
        )
        _add(f"*Created by `{focus_ticket.get('created_by', '?')}` → assigned to `{focus_ticket.get('assigned_to') or 'any'}`*")
        if focus_ticket.get("description"):
            _add(focus_ticket["description"][:600])
        if focus_ticket.get("target_url") or focus_ticket.get("scope"):
            _add(f"**Scope**: `{focus_ticket.get('scope', 'n/a')}` | **Target**: `{focus_ticket.get('target_url', 'n/a')}`")
        if focus_ticket.get("required_fields"):
            _add("**Required Fields**: " + ", ".join(f"`{f}`" for f in focus_ticket["required_fields"]))
        if focus_ticket.get("forbidden"):
            _add("**Forbidden**: " + ", ".join(f"`{f}`" for f in focus_ticket["forbidden"]))
        if focus_ticket.get("related_files"):
            _add("**Related Files**: " + ", ".join(f"`{f}`" for f in focus_ticket["related_files"]))

        related = _ticket_related_memories(focus_ticket, mem + _load_archive(), limit=8)
        if related:
            _add("### Related Memories")
            for score, _, m in related:
                if not _add(f"- [{m['memory_type'].upper()}] **{m['title']}** (`{m['agent_name']}`, score {score})"):
                    break
        _add("")

    # Pinned — second priority
    pinned = [m for m in mem if m.get("pinned") and m["memory_type"]!=MemoryType.HANDOFF]
    if include_detail_sections and pinned:
        _add("## 📌 Pinned")
        for m in pinned[-8:]:
            max_content = min(300, (budget - used) // 4)
            c = m["content"][:max_content] + ("..." if len(m["content"]) > max_content else "")
            if not _add(f"- [{m['memory_type'].upper()}] **{m['title']}** (`{m['agent_name']}`): {c}"):
                break
        _add("")

    # Latest checkpoint
    cps = [m for m in mem if m["memory_type"]==MemoryType.CHECKPOINT]
    if mode != BriefingMode.HANDOFF_ONLY and cps:
        cp = cps[-1]
        _add("## 💾 Latest Checkpoint")
        try:
            d = json.loads(cp["content"])
            _add(f"*✍️ {cp['agent_name']}* — {d.get('summary','')}")
            if d.get("remaining_tasks"): _add("**Tasks**: " + " / ".join(d["remaining_tasks"][:8]))
            if d.get("blockers"): _add("**Blockers**: " + " / ".join(d["blockers"][:5]))
        except: _add(cp["content"][:300])
        _add("")

    # ── Type-capped sections (respects BRIEFING_TYPE_CAP) ──
    type_emoji = {"blocker":"🚫","decision":"🏛️","warning":"⚠️","todo":"📝",
                  "progress":"✅","file_change":"📁","discovery":"💡","context":"📖"}
    # Group by type, sorted newest first
    by_type = {}
    for m in mem:
        if m["memory_type"] not in (MemoryType.HANDOFF, MemoryType.CHECKPOINT):
            by_type.setdefault(m["memory_type"], []).append(m)

    # Show in priority order: blockers first, then decisions, warnings, etc.
    type_order = ["blocker","decision","warning","discovery","todo","file_change","progress","context"]
    for mtype in type_order:
        if not include_detail_sections:
            break
        entries = by_type.get(mtype, [])
        if not entries: continue
        cap = type_caps.get(mtype, 5)
        # Sort newest first, take top N
        entries_sorted = sorted(entries, key=lambda m: m.get("timestamp",0), reverse=True)
        capped = entries_sorted[:cap]
        skipped = len(entries) - len(capped)

        emoji = type_emoji.get(mtype, "📌")
        header = f"## {emoji} {mtype.replace('_',' ').title()}"
        if skipped > 0:
            header += f" ({len(capped)}/{len(entries)} — {skipped} older entries skipped)"
        _add(header)

        for m in capped:
            # Skip pinned entries (already shown in pinned section)
            if m.get("pinned"): continue
            c = m["content"][:120] + ("..." if len(m["content"]) > 120 else "")
            if not _add(f"- **{m['title']}** (`{m['agent_name']}`): {c}"): break
        _add("")

    # State — compact
    if include_state and state:
        _add("## 🔧 State")
        for k,v in state.items():
            if not k.startswith("_"):
                val = v.get("value",v) if isinstance(v,dict) else v
                who = v.get("updated_by","?") if isinstance(v,dict) else "?"
                if not _add(f"- **{k}**: {str(val)[:150]} (`{who}`)"): break
        _add("")

    # ── WARM MEMORY: Digests (compressed long-term) ──
    if include_digests and digests:
        _add("## 🗜️ Long-term Memory (compressed)")
        for dg in digests[-5:]:
            remaining = budget - used
            if remaining < 200: break
            max_summary = min(400, remaining // 2)
            summary_truncated = dg["summary"][:max_summary * 4]  # chars, not tokens
            if not _add(f"### Session: {dg['agent_name']} ({dg['period']})\n"
                       f"*{dg['entry_count']} entries → ~{dg['digest_tokens']} tokens | method: {dg['method']}*\n"
                       f"{summary_truncated}\n"): break
        _add("")

    # Focus area
    if params.focus_area:
        all_searchable = mem + _load_archive()
        fc = [m for _, _, m in _rank_memory_hits(params.focus_area, all_searchable)]
        if fc:
            _add(f"## 🎯 Focus: {params.focus_area}")
            for m in fc[:8]:
                if not _add(f"- [{m['memory_type'].upper()}] {m['title']} (`{m['agent_name']}`)"): break
            _add("")

    if params.include_full_history or mode == BriefingMode.DEEP:
        _add("## 📜 Full History")
        for m in mem:
            if not _add(f"[{m['memory_type'].upper()}] {m['title']} by `{m['agent_name']}`: {m['content'][:200]}\n---"): break

    _add("---")
    _add(f"*Briefing: ~{used:,} tokens used of {budget:,} budget*")

    # Context dirs hint
    if CONTEXT_DIRS:
        avail = [str(d.name) for d in CONTEXT_DIRS if d.exists()]
        if avail:
            _add(f"\n📂 **Reference dirs available**: {', '.join(avail)} — use `memory_context_dirs` to browse")

    # Tickets
    if _auto_transition_claimed(tickets):
        _save_ticket_index(tickets)
    open_tickets = [t for t in tickets if t["status"] in (
        TicketStatus.OPEN, TicketStatus.CLAIMED, TicketStatus.IN_PROGRESS,
        TicketStatus.CREATING_REPORT, TicketStatus.SUBMITTED, TicketStatus.REVIEWING,
        TicketStatus.IN_REVIEW)]
    if open_tickets:
        pri_emoji = {"low":"🟢","medium":"🟡","high":"🟠","critical":"🔴"}
        _add(f"## 🎫 Open Tickets ({len(open_tickets)})")
        for t in sorted(open_tickets, key=lambda x: {"critical":0,"high":1,"medium":2,"low":3}.get(x["priority"],9)):
            pe = pri_emoji.get(t["priority"],"⚪")
            assign = f"→ `{t['assigned_to']}`" if t.get("assigned_to") else "→ any"
            _add(f"- {pe} `{t['id']}` **{t['title']}** ({t['status']}) {assign} — from `{t['created_by']}`")
        _add("")

    if not params.suppress_protocol:
        L += ["## 🚨 GET ON BOARD — MANDATORY PROTOCOL",
              "**STEP 1**: `memory_onboard(agent_name='your-stable-name', agent_platform='your-platform')` — preferred one-call session entrypoint",
              "**Fallback**: if you already read this briefing, call `memory_agent_join` before any write/ticket mutation",
              "**STEP 2**: `memory_write` after significant code changes, decisions, discoveries, blockers, or warnings",
              "**STEP 3**: `memory_checkpoint` every 10-15 min — if you die, this is all the next agent has",
              "**STEP 4**: `memory_handoff` before you finish — the next agent depends on this",
              "**STEP 5**: `memory_list_tickets` — check if anyone needs your help",
              "⛔ If you skip steps, your work will be untracked and the next agent will redo everything."]
    return "\n".join(L)

@mcp.tool(name="memory_status", annotations={"title":"Status","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_status() -> str:
    """Quick status dashboard."""
    _lazy_kia_sweep()
    mem = _load_mem(); agents = _load_agt()
    tc = {}
    for m in mem: tc[m.get("memory_type","?")] = tc.get(m.get("memory_type","?"),0)+1
    agent_heading = "## Agents"
    if len(agents) > AGENT_HISTORY_LIMIT:
        agent_heading += f" (latest {AGENT_HISTORY_LIMIT} of {len(agents)})"
    L = [f"# 📊 {PROJECT_ROOT.name}", f"`{MEMORY_DIR}`", f"Total: {len(mem)} memories\n{agent_heading}"]
    for _,a in _recent_agent_items(agents):
        e = {"active":"🟢","kia":"💀","completed":"✅","handed_off":"🤝"}.get(a.get("status",""),"❓")
        L.append(f"- {e} **{a['agent_name']}** ({a['agent_platform']}) — {a.get('memories_written',0)} writes")
    L.append("\n## Types")
    for t,c in sorted(tc.items()): L.append(f"- {t}: {c}")
    if mem:
        l = mem[-1]; L.append(f"\n## Last: `{l['agent_name']}` [{l['memory_type']}] {l['title']}")
    return "\n".join(L)

@mcp.tool(name="memory_doctor", annotations={"title":"Doctor Project Setup","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_doctor() -> str:
    """Check project-local On Board setup without changing files."""
    checks = []
    required_files = [
        (MEMORY_DIR, ".agent-mem/ runtime directory", True, False, False),
        (PROJECT_ROOT / ".agent-mem-hooks" / "cursor-session-start.sh", "Cursor session-start hook", False, True, False),
        (PROJECT_ROOT / ".agent-mem-hooks" / "cursor-session-end.sh", "Cursor stop hook", False, True, False),
        (PROJECT_ROOT / ".agent-mem-hooks" / "claude-code-session-start.sh", "Claude Code session-start hook", False, True, False),
        (PROJECT_ROOT / ".agent-mem-hooks" / "claude-code-stop.sh", "Claude Code stop hook", False, True, False),
        (PROJECT_ROOT / ".cursor" / "hooks.json", "Cursor hooks config", False, False, True),
        (PROJECT_ROOT / ".claude" / "settings.json", "Claude Code settings", False, False, True),
        (PROJECT_ROOT / ".codex" / "hooks.json", "Codex hooks config", False, False, True),
        (PROJECT_ROOT / ".codex" / "hooks" / "codex-session-start.sh", "Codex session-start hook", False, True, False),
        (PROJECT_ROOT / ".codex" / "hooks" / "codex-stop.sh", "Codex stop hook", False, True, False),
        (PROJECT_ROOT / ".agent" / "rules" / "on-board-agent-memory.md", "AntiGravity workspace rule", False, False, False),
        (PROJECT_ROOT / "AGENTS.md", "Codex rules", False, False, False),
        (PROJECT_ROOT / "CLAUDE.md", "Claude Code rules", False, False, False),
        (PROJECT_ROOT / ".cursorrules", "Cursor rules", False, False, False),
    ]

    for args in required_files:
        checks.append(_doctor_file(*args))
    checks.append(_doctor_gitignore())

    prj = _load_prj()
    mem = _load_mem()
    agents = _load_agt()
    tickets = _load_ticket_index()
    digests = _load_digests()
    data_warnings = _doctor_data_integrity(agents, tickets, mem)

    failures = [line for status, line in checks if status in ("fail", "missing")]
    warnings = [line for status, line in checks if status in ("warn", "optional-missing")]
    ok = [line for status, line in checks if status == "ok"]

    status = "PASS" if not failures else "FAIL"
    if (warnings or data_warnings) and not failures:
        status = "PASS WITH WARNINGS"

    lines = [
        f"# 🩺 On Board Doctor: {status}",
        f"`{PROJECT_ROOT}`",
        "",
        "## Runtime",
        f"- Project initialized: {'yes' if prj else 'no'}",
        f"- Hot memories: {len(mem)}",
        f"- Digests: {len(digests)}",
        f"- Agents: {len(agents)}",
        f"- Tickets: {len(tickets)}",
        f"- Vector backend: `{VECTOR_BACKEND}`",
        "",
        "## Checks",
    ]
    lines.extend(ok)
    lines.extend(warnings)
    lines.extend(failures)

    if data_warnings:
        lines.append("")
        lines.append("## Data Integrity")
        lines.extend(data_warnings)

    lines.append("")
    lines.append("## Next Step")
    if failures:
        lines.append("Run `bash /path/to/agent_mem_MCP/setup-project.sh` from the target project root, then rerun `memory_doctor`.")
    elif warnings:
        lines.append("Setup is usable. Review warnings if this client/platform should be active in this project.")
    else:
        lines.append("Setup looks complete. Use `memory_get_briefing(mode='brief')` for a quick runtime check.")
    return "\n".join(lines)

@mcp.tool(name="memory_pin", annotations={"title":"Pin/Unpin","readOnlyHint":False,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_pin(params: PinInput) -> str:
    """Pin/unpin a memory."""
    mem = _load_mem()
    for m in mem:
        if m["id"] == params.memory_id:
            m["pinned"] = params.pinned; _save_mem(mem)
            return f"{'📌 Pinned' if params.pinned else '📍 Unpinned'}: {m['title']}"
    return f"ID '{params.memory_id}' not found."

@mcp.tool(name="memory_update_state", annotations={"title":"Update State","readOnlyHint":False,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_update_state(params: UpdateStateInput) -> str:
    """Update shared key-value state. Stamped with agent_name."""
    if params.agent_name:
        _touch_heartbeat(params.agent_name)
    s = _load_sta()
    s[params.key] = {"value": params.value, "updated_at": _now(), "updated_by": params.agent_name or "unknown"}
    _save_sta(s)
    return f"🔧 `{params.key}` = `{params.value[:100]}` (by `{params.agent_name or '?'}`)"

# ── Token-Saving Tools ──────────────────────────────────

@mcp.tool(name="memory_compact", annotations={"title":"Compact Old Memories","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":True})
async def memory_compact(params: CompactInput) -> str:
    """Compact old memories into compressed digests to save tokens.

    How it works:
    1. Splits memories into HOT (recent/pinned) and COLD (old)
    2. Groups cold entries by agent session
    3. Uses agent-written digests by default, or regex fallback if requested
    4. Archives raw cold entries to archive.json
    5. Keeps only hot entries in memories.json + digest references

    Strategies (via `strategy` param):
    - `agent` (default, recommended, saves ~70%): trust agent-written context digests.
      Requires one non-blank `memory_write(memory_type='context', title='Digest: <agent> ...')`
      BEFORE this call for every cold agent group. Apply the `memory-digest-thrift` skill.
    - `regex` (safe fallback): deterministic server-generated digest.

    Token savings: typically 60-80% reduction on old entries.

    Config via env vars:
    - AGENT_MEM_HOT_HOURS: hours to keep full detail (default: 24)
    - AGENT_MEM_MAX_HOT: max hot entries (default: 50)
    """
    mem = _load_mem()
    if not mem:
        return "Nothing to compact."

    hot, cold = _split_hot_cold(mem)

    if not cold and not params.force:
        return f"Nothing to compact. {len(hot)} entries, all recent/pinned. (Use force=true to override)"

    if not cold:
        return f"All {len(hot)} entries are protected (pinned/recent/high-priority). Nothing to compact."

    strategy = params.strategy

    matched_digest_entries = []
    duplicate_digest_count = 0

    # Agent-driven: require recent, non-blank context digest entries (one per cold agent group)
    if strategy == "agent":
        cold_agents = {m.get("agent_name", "unknown") for m in cold}
        cold_oldest_ts = min((m.get("timestamp", 0) for m in cold), default=0)
        digest_entries_by_agent = {}
        valid_digest_entries = []
        digest_counts_by_agent = {agent_name: 0 for agent_name in cold_agents}
        for m in mem:
            if m.get("memory_type") != MemoryType.CONTEXT:
                continue
            if m.get("timestamp", 0) <= cold_oldest_ts:
                continue
            content = m.get("content", "").strip()
            if len(content) < 40:
                continue
            title = m.get("title", "").lower()
            for agent_name in cold_agents:
                if title.startswith(f"digest: {agent_name}".lower()):
                    valid_digest_entries.append(m)
                    digest_counts_by_agent[agent_name] += 1
                    existing = digest_entries_by_agent.get(agent_name)
                    if not existing or m.get("timestamp", 0) > existing.get("timestamp", 0):
                        digest_entries_by_agent[agent_name] = m

        missing_agents = cold_agents - set(digest_entries_by_agent.keys())
        if missing_agents:
            return (
                "❌ Agent-driven compact requires one non-blank digest per cold agent group.\n\n"
                "Workflow:\n"
                "1. `memory_prepare_compaction()` — preview cold entries grouped by agent\n"
                "2. For each missing agent, `memory_write(memory_type='context', title='Digest: <agent> (<period>)', content='<thrift-compressed summary>')`\n"
                "3. Retry `memory_compact(strategy='agent')`\n\n"
                f"Missing/blank digests for: {', '.join(sorted(missing_agents))}\n"
                "Apply the `memory-digest-thrift` skill if available — saves ~70% tokens.\n"
                "Or fall back to: `memory_compact(strategy='regex')` for server-generated digests."
            )

        matched_digest_entries = valid_digest_entries
        duplicate_digest_count = sum(max(0, count - 1) for count in digest_counts_by_agent.values())
        matched_digest_ids = {m.get("id") for m in matched_digest_entries}
        cold = [m for m in cold if m.get("id") not in matched_digest_ids]
        hot_ids = {m.get("id") for m in hot}
        hot.extend(m for m in matched_digest_entries if m.get("id") not in hot_ids)

    # Token counts before
    tokens_before = _count_mem_tokens(mem)

    # Group cold entries by agent_name for per-session digests
    by_agent = {}
    for m in cold:
        agent = m.get("agent_name", "unknown")
        by_agent.setdefault(agent, []).append(m)

    # Archive raw cold entries
    archive = _load_archive()
    archive.extend(cold)
    _save_archive(archive)

    # Create digests
    digests = _load_digests()
    new_digest_titles = []

    for agent_name, entries in by_agent.items():
        if strategy == "agent":
            # Trust agent-written context digests. Skip auto-summary.
            continue
        summary = _rule_based_compress(entries)

        ts_range = ""
        timestamps = [e.get("created_at", "") for e in entries]
        if timestamps:
            ts_range = f"{timestamps[0][:10]} → {timestamps[-1][:10]}"

        digest = {
            "id": _id(),
            "agent_name": agent_name,
            "period": ts_range,
            "entry_count": len(entries),
            "original_tokens": _count_mem_tokens(entries),
            "digest_tokens": _estimate_tokens(summary),
            "summary": summary,
            "compressed_at": _now(),
            "method": strategy,
        }
        digests.append(digest)
        new_digest_titles.append(f"`{agent_name}` ({len(entries)} entries → ~{digest['digest_tokens']} tokens)")

    _save_digests(digests)

    # Replace memories.json with only hot entries
    _save_mem(hot)

    # Token counts after
    if strategy == "agent":
        # No new digests; existing context entries already in hot memory carry the summary
        tokens_after = _count_mem_tokens(hot)
        method_label = "agent-driven (trusted context digests)"
        digest_summary = "No auto-digests created — relied on existing context entries."
        if duplicate_digest_count:
            digest_summary += f"\nFound {duplicate_digest_count} duplicate digest entr{'y' if duplicate_digest_count == 1 else 'ies'}; kept all valid digest entries hot."
    else:
        tokens_after = _count_mem_tokens(hot) + sum(_estimate_tokens(d.get("summary", "")) for d in digests)
        method_label = "regex fallback"
        digest_summary = "**New digests**:\n" + "\n".join(f"- {t}" for t in new_digest_titles) if new_digest_titles else "No new digests."

    saved = tokens_before - tokens_after
    pct = (saved / tokens_before * 100) if tokens_before > 0 else 0

    return (
        f"🗜️ Compaction complete!\n\n"
        f"**Before**: {len(mem)} entries (~{tokens_before:,} tokens)\n"
        f"**After**: {len(hot)} hot + {len(digests)} digests (~{tokens_after:,} tokens)\n"
        f"**Saved**: ~{saved:,} tokens ({pct:.0f}% reduction)\n"
        f"**Archived**: {len(cold)} entries to archive.json\n\n"
        f"{digest_summary}\n\n"
        f"Method: {method_label}\n\n"
        f"Next: run `memory_get_briefing(mode='brief')` to verify the handoff still reads cleanly."
    )


@mcp.tool(name="memory_token_usage", annotations={"title":"Token Usage Report","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_token_usage() -> str:
    """Show token usage breakdown and recommend compaction if needed.

    Returns token estimates for: hot memories, digests, archive, briefing output.
    """
    mem = _load_mem()
    digests = _load_digests()
    archive = _load_archive()

    hot_tokens = _count_mem_tokens(mem)
    digest_tokens = sum(_estimate_tokens(d.get("summary", "")) for d in digests)
    archive_tokens = _count_mem_tokens(archive)

    # Estimate briefing output by workflow mode. These are rough upper bounds,
    # not billing-grade counts.
    briefing_est = min(hot_tokens + digest_tokens + 500, 4000)
    brief_est = min(hot_tokens + 500, 2500)
    deep_est = min(hot_tokens + digest_tokens + 1000, 8000)

    hot, cold = _split_hot_cold(mem)
    cold_tokens = _count_mem_tokens(cold)

    lines = [
        f"# 📊 Token Usage Report",
        f"",
        f"## Current Memory",
        f"- **Hot entries**: {len(mem)} (~{hot_tokens:,} tokens)",
        f"  - Recent/pinned: {len(hot)}",
        f"  - Compactable: {len(cold)} (~{cold_tokens:,} tokens)",
        f"- **Digests**: {len(digests)} (~{digest_tokens:,} tokens)",
        f"- **Archive**: {len(archive)} entries (~{archive_tokens:,} tokens, on disk only)",
        f"",
        f"## Briefing Cost",
        f"- `memory_get_briefing(mode='brief')`: ~{brief_est:,} tokens",
        f"- `memory_get_briefing(mode='normal')`: ~{briefing_est:,} tokens",
        f"- `memory_get_briefing(mode='deep')`: ~{deep_est:,} tokens",
        f"",
    ]

    if cold_tokens > 8000:
        potential_saving = int(cold_tokens * 0.7)  # ~70% savings typical
        lines.append(f"## Recommended Workflow")
        lines.append(f"1. Run `memory_prepare_compaction` to review {len(cold)} compactable entries.")
        lines.append(f"2. Write one non-blank thrift digest per agent group with `memory_write(memory_type='context', title='Digest: <agent> (<period>)', content='...')`.")
        lines.append(f"3. Run `memory_compact(strategy='agent')`, or `memory_compact(strategy='regex')` as fallback.")
        lines.append(f"4. Expected saving: ~{potential_saving:,} tokens.")
    elif cold_tokens > 2000:
        potential_saving = int(cold_tokens * 0.7)
        lines.append(f"## Recommended Workflow")
        lines.append(f"Memory is starting to grow. Run `memory_prepare_compaction` before your next handoff.")
        lines.append(f"Expected saving if compacted: ~{potential_saving:,} tokens.")
    else:
        lines.append("## Recommended Workflow")
        lines.append("No compaction needed. Use `memory_get_briefing(mode='brief')` for cheap catchup or `mode='normal'` for regular onboarding.")

    return "\n".join(lines)


@mcp.tool(name="memory_prepare_compaction", annotations={"title":"Prepare Compaction (Agent-Driven)","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_prepare_compaction() -> str:
    """Returns cold entries grouped by agent session — ready for YOU to summarize.

    Instead of using server-generated regex summaries, YOU can write better digests.
    Read the returned entries, write your own digest with memory_write(memory_type='context'),
    then run memory_compact(strategy='agent') to archive the originals.

    Workflow:
    1. Call memory_prepare_compaction() → get grouped cold entries
    2. Apply the memory-digest-thrift skill and summarize each agent group yourself
    3. Call memory_write(memory_type='context', title='Digest: <agent> (<period>)', content='your non-blank summary')
    4. Call memory_compact(strategy='agent') → archives cold entries, keeps your digest

    Returns:
        str: Cold entries grouped by agent, with token counts.
    """
    mem = _load_mem()
    hot, cold = _split_hot_cold(mem)

    if not cold:
        return f"Nothing to compact. All {len(hot)} entries are recent/pinned."

    # Group by agent
    by_agent = {}
    for m in cold:
        by_agent.setdefault(m.get("agent_name", "unknown"), []).append(m)

    lines = [
        f"# 🗜️ Compaction Preview",
        f"**{len(cold)} cold entries** (~{_count_mem_tokens(cold):,} tokens) ready to compress",
        f"**{len(hot)} hot entries** will be kept as-is",
        f"",
        f"This is a preview. No files are changed until `memory_compact` runs.",
        f"",
    ]

    for agent_name, entries in by_agent.items():
        tokens = _count_mem_tokens(entries)
        type_counts = {}
        for e in entries:
            type_counts[e.get("memory_type", "?")] = type_counts.get(e.get("memory_type", "?"), 0) + 1
        type_summary = ", ".join(f"{k}:{v}" for k, v in sorted(type_counts.items()))
        lines.append(f"## Agent: `{agent_name}` ({len(entries)} entries, ~{tokens:,} tokens)")
        lines.append(f"Types: {type_summary}")
        for e in entries[:5]:
            pri = "🔴" * e.get("priority", 0) if e.get("priority", 0) > 0 else ""
            lines.append(f"- {pri}[{e['memory_type'].upper()}] **{e['title']}**: {e['content'][:120]}...")
        if len(entries) > 5:
            lines.append(f"- ... {len(entries) - 5} more entries hidden from preview")
        lines.append("")

    lines.append("---")
    lines.append("## Recommended Workflow (agent-driven, saves ~70% tokens)")
    lines.append("1. Apply the `memory-digest-thrift` skill if available (compressed format: drop articles/filler, fragments OK, preserve agent_name attribution).")
    lines.append("2. For each agent group above, write a non-blank digest: `memory_write(memory_type='context', title='Digest: <agent> (<period>)', content='<thrift-compressed summary>')`.")
    lines.append("3. Run `memory_compact(strategy='agent')` — server skips its own summary generation and trusts your digests.")
    lines.append("")
    lines.append("Fallback: `memory_compact(strategy='regex')` for server-generated regex digests.")
    lines.append("Use `memory_search_archive(query='...')` later if you need the old raw details.")

    return "\n".join(lines)


@mcp.tool(name="memory_search_archive", annotations={"title":"Search Archive","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_search_archive(params: SearchInput) -> str:
    """Search the cold archive (compacted entries). Use when you need old details
    that were compressed out of the hot memory."""
    archive = _load_archive()
    if not archive:
        return "Archive is empty. No compacted entries yet."

    hits = _rank_memory_hits(params.query, archive)[:params.limit]

    if not hits:
        return f"No archived entries matching '{params.query}'."

    lines = [f"# 🗄️ Archive Search: '{params.query}' ({len(hits)} results)\n"]
    for score, _, m in hits:
        lines.append(f"### [{m['memory_type'].upper()}] {m['title']}")
        lines.append(f"*score {score} | ✍️ {m['agent_name']} | {m['created_at']}*")
        lines.append(f"{m['content'][:400]}{'...' if len(m.get('content',''))>400 else ''}\n---\n")
    return "\n".join(lines)

# ── Bootstrap for Existing Projects ─────────────────────

def _safe_read(path: Path, max_chars: int = 3000) -> str:
    """Read a file safely, truncating if too large."""
    try:
        if path.exists() and path.is_file() and path.stat().st_size < 500_000:
            text = path.read_text(encoding="utf-8", errors="replace")
            return text[:max_chars] + ("..." if len(text) > max_chars else "")
    except:
        pass
    return ""

def _scan_directory_structure(root: Path, max_depth: int = 3) -> str:
    """Scan directory tree, skip common noise."""
    skip = {".git", "node_modules", "__pycache__", ".next", ".nuxt", "dist",
            "build", ".agent-mem", ".agent-mem-hooks", "venv", ".venv", "env",
            ".env", ".idea", ".vscode", "coverage", ".cache", "target"}
    lines = []

    def _walk(p: Path, depth: int, prefix: str = ""):
        if depth > max_depth:
            return
        try:
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return

        dirs = [i for i in items if i.is_dir() and i.name not in skip and not i.name.startswith(".")]
        files = [i for i in items if i.is_file() and not i.name.startswith(".")]

        for f in files[:15]:  # Cap files per dir
            lines.append(f"{prefix}{f.name}")
        if len(files) > 15:
            lines.append(f"{prefix}... +{len(files)-15} more files")

        for d in dirs[:10]:
            lines.append(f"{prefix}{d.name}/")
            _walk(d, depth + 1, prefix + "  ")

    _walk(root, 0)
    return "\n".join(lines[:100])  # Cap total lines

def _scan_git_log(root: Path, n: int = 15) -> str:
    """Get recent git log."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{n}", "--no-decorate"],
            cwd=str(root), capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return ""

def _scan_git_branch(root: Path) -> str:
    """Get current branch."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(root), capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return ""

def _detect_tech_stack(root: Path) -> str:
    """Auto-detect tech stack from config files."""
    signals = []
    if (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text())
            deps = list((pkg.get("dependencies", {}) | pkg.get("devDependencies", {})).keys())
            frameworks = [d for d in deps if d in (
                "react", "vue", "svelte", "next", "nuxt", "angular", "express",
                "fastify", "hono", "astro", "remix", "solid-js", "tailwindcss",
                "typescript", "vite", "webpack", "prisma", "drizzle-orm"
            )]
            signals.append(f"Node.js ({', '.join(frameworks[:6])})" if frameworks else "Node.js")
        except: signals.append("Node.js")
    if (root / "pyproject.toml").exists(): signals.append("Python")
    if (root / "requirements.txt").exists(): signals.append("Python")
    if (root / "Cargo.toml").exists(): signals.append("Rust")
    if (root / "go.mod").exists(): signals.append("Go")
    if (root / "Gemfile").exists(): signals.append("Ruby")
    if (root / "docker-compose.yml").exists() or (root / "docker-compose.yaml").exists(): signals.append("Docker")
    if (root / "Dockerfile").exists(): signals.append("Docker")
    if (root / ".env").exists(): signals.append("env-file")
    if (root / "tsconfig.json").exists(): signals.append("TypeScript")
    return " / ".join(signals) if signals else "Unknown"

@mcp.tool(name="memory_bootstrap", annotations={"title":"Bootstrap Existing Project","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_bootstrap(params: BootstrapInput) -> str:
    """Bootstrap .agent-mem/ for an EXISTING project by auto-scanning the codebase.

    Reads: README, git log, directory structure, package configs.
    Seeds memory with: project context, tech stack, recent history, structure, warnings.

    Use this instead of memory_init when joining an existing project for the first time.
    After bootstrap, the next agent gets full context without you manually typing everything.

    Returns:
        str: Bootstrap summary with what was discovered and seeded.
    """
    _ensure()
    prj = _load_prj()
    if prj and _load_mem():
        return (f"⚠️ Project already has memory ({len(_load_mem())} entries).\n"
                f"Use `memory_get_briefing` instead. If you want to re-bootstrap, delete `.agent-mem/` first.")

    # Auto-detect tech if not provided
    tech = params.tech_stack or _detect_tech_stack(PROJECT_ROOT)

    # Init project
    prj = {"description": params.description, "tech_stack": tech,
            "project_root": str(PROJECT_ROOT), "created_at": _now(), "bootstrapped": True}
    _save_prj(prj)
    _save_agt({})
    _save_sta({})

    entries = []
    discoveries = []

    def _add_entry(mtype, title, content, tags=None, priority=0):
        entries.append({
            "id": _id(), "agent_name": params.agent_name, "memory_type": mtype,
            "title": title, "content": content, "tags": tags or [],
            "related_files": [], "priority": priority,
            "pinned": priority >= 3, "created_at": _now(), "timestamp": time.time()
        })

    # ── Scan README ──
    if params.scan_readme:
        for readme_name in ("README.md", "README.rst", "README.txt", "README"):
            readme_text = _safe_read(PROJECT_ROOT / readme_name, 2000)
            if readme_text:
                _add_entry(MemoryType.CONTEXT, f"Project README ({readme_name})",
                          readme_text, tags=["bootstrap", "readme"], priority=2)
                discoveries.append(f"📖 Read {readme_name} ({len(readme_text)} chars)")
                break

    # ── Scan directory structure ──
    if params.scan_structure:
        structure = _scan_directory_structure(PROJECT_ROOT)
        if structure:
            _add_entry(MemoryType.CONTEXT, "Codebase structure",
                      f"```\n{structure}\n```", tags=["bootstrap", "structure"], priority=1)
            discoveries.append(f"📁 Scanned directory ({structure.count(chr(10))+1} items)")

    # ── Scan git ──
    if params.scan_git:
        branch = _scan_git_branch(PROJECT_ROOT)
        log = _scan_git_log(PROJECT_ROOT, 20)
        if log:
            git_content = f"**Branch**: {branch or 'unknown'}\n\n**Recent commits**:\n```\n{log}\n```"
            _add_entry(MemoryType.CONTEXT, f"Git history (branch: {branch or '?'})",
                      git_content, tags=["bootstrap", "git"], priority=1)
            discoveries.append(f"🔀 Git: branch `{branch}`, {log.count(chr(10))+1} recent commits")
            if branch:
                _save_sta({"current_branch": {"value": branch, "updated_at": _now(), "updated_by": params.agent_name}})

    # ── Scan config files ──
    if params.scan_config:
        config_files = [
            ("package.json", ["dependencies", "scripts"]),
            ("pyproject.toml", None),
            ("Cargo.toml", None),
            ("tsconfig.json", None),
        ]
        for cfname, _ in config_files:
            cftext = _safe_read(PROJECT_ROOT / cfname, 1500)
            if cftext:
                _add_entry(MemoryType.CONTEXT, f"Config: {cfname}",
                          f"```\n{cftext}\n```", tags=["bootstrap", "config"])
                discoveries.append(f"⚙️ Read {cfname}")

    # ── Tech stack decision ──
    _add_entry(MemoryType.DECISION, f"Tech stack: {tech}",
              f"Detected/declared tech stack: {tech}\nProject root: {PROJECT_ROOT}",
              tags=["bootstrap", "tech"], priority=2)

    # ── Extra context ──
    if params.extra_context:
        _add_entry(MemoryType.CONTEXT, "Additional context (human-provided)",
                  params.extra_context, tags=["bootstrap", "human"], priority=2)
        discoveries.append("📝 Added human-provided context")

    # ── Known warnings ──
    for w in (params.known_warnings or []):
        _add_entry(MemoryType.WARNING, w, w, tags=["bootstrap", "human-warning"], priority=2)
        discoveries.append(f"⚠️ Warning: {w[:60]}")

    # ── Current task ──
    if params.current_task:
        _add_entry(MemoryType.TODO, params.current_task, params.current_task,
                  tags=["bootstrap", "active-task"], priority=2)
        discoveries.append(f"📝 TODO: {params.current_task[:60]}")

    # ── Bootstrap checkpoint ──
    _add_entry(MemoryType.CHECKPOINT, "Bootstrap checkpoint",
              json.dumps({
                  "summary": f"Bootstrapped from existing project. {len(entries)} entries seeded.",
                  "remaining_tasks": [params.current_task] if params.current_task else [],
                  "blockers": [],
                  "active_branch": _scan_git_branch(PROJECT_ROOT) if params.scan_git else None,
              }, indent=2),
              tags=["bootstrap", "checkpoint"], priority=2)

    _save_mem(entries)

    # Register the bootstrap agent
    aid = f"{params.agent_name.split('-')[0] if '-' in params.agent_name else 'bootstrap'}-{_id()}"
    agents = {aid: {
        "agent_name": params.agent_name, "agent_platform": "bootstrap",
        "task_focus": "Initial memory bootstrap", "status": AgentStatus.ACTIVE,
        "joined_at": _now(), "last_activity": time.time(), "memories_written": len(entries)
    }}
    _save_agt(agents)

    # Build response
    lines = [
        f"🚀 **Bootstrap complete!**\n",
        f"**Project**: {PROJECT_ROOT.name}",
        f"**Tech**: {tech}",
        f"**Memories seeded**: {len(entries)}",
        f"**Token cost**: ~{_count_mem_tokens(entries):,} tokens\n",
        f"## Discoveries",
    ]
    lines.extend(f"- {d}" for d in discoveries)
    lines.append(f"\n## What's in .agent-mem/ now")
    by_type = {}
    for e in entries:
        by_type.setdefault(e["memory_type"], []).append(e)
    for t, es in sorted(by_type.items()):
        lines.append(f"- {t}: {len(es)} entries")

    lines.append(f"\n## Next steps")
    lines.append(f"1. Review the seeded memories: `memory_read`")
    lines.append(f"2. Add any missing context: `memory_write(type='context', ...)`")
    lines.append(f"3. Add known decisions/warnings: `memory_write(type='decision|warning', ...)`")
    lines.append(f"4. Hand off: `memory_handoff` — then the next agent is fully onboarded")

    return "\n".join(lines)

# ── Context Dirs (external info folders) ────────────────

def _scan_context_dir(d: Path, max_files: int = 20) -> list:
    """List readable files in an external context dir."""
    if not d.exists() or not d.is_dir():
        return []
    files = []
    skip_ext = {".pyc", ".pyo", ".so", ".dylib", ".o", ".exe", ".dll",
                ".zip", ".tar", ".gz", ".jpg", ".png", ".gif", ".mp4"}
    try:
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.suffix.lower() not in skip_ext and not any(
                p.startswith(".") for p in f.relative_to(d).parts
            ):
                files.append(f)
                if len(files) >= max_files:
                    break
    except PermissionError:
        pass
    return files

class ContextDirReadInput(BaseModel):
    """Read a file from one of the configured context directories."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    filename: str = Field(..., description="Filename or relative path to read from context dirs", min_length=1, max_length=500)
    max_chars: Optional[int] = Field(default=3000, description="Max characters to return", ge=100, le=50000)

@mcp.tool(name="memory_context_dirs", annotations={"title":"List Context Directories","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_context_dirs() -> str:
    """List all configured external context/info directories and their files.

    Context dirs are set via AGENT_MEM_CONTEXT_DIRS env var (colon-separated paths).
    These folders contain reference docs, specs, shared info that agents should know about
    but live outside the project folder.

    Returns:
        str: List of context dirs and their contents.
    """
    if not CONTEXT_DIRS:
        return ("No context directories configured.\n\n"
                "Set `AGENT_MEM_CONTEXT_DIRS` in your MCP config env:\n"
                "```\n\"env\": {\n  \"AGENT_MEM_CONTEXT_DIRS\": \"/path/to/docs:/path/to/specs\"\n}\n```")

    lines = ["# 📂 External Context Directories\n"]
    for d in CONTEXT_DIRS:
        if not d.exists():
            lines.append(f"## ❌ `{d}` — not found")
            continue
        files = _scan_context_dir(d)
        lines.append(f"## 📁 `{d}`")
        lines.append(f"*{len(files)} readable files*\n")
        for f in files:
            rel = f.relative_to(d)
            size = f.stat().st_size
            size_str = f"{size:,} bytes" if size < 10000 else f"{size/1024:.1f} KB"
            lines.append(f"- `{rel}` ({size_str})")
        lines.append("")

    lines.append("Use `memory_context_read(filename='...')` to read any file.")
    return "\n".join(lines)

@mcp.tool(name="memory_context_read", annotations={"title":"Read from Context Dir","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_context_read(params: ContextDirReadInput) -> str:
    """Read a file from the external context directories.

    Searches all configured AGENT_MEM_CONTEXT_DIRS for the filename.
    Use memory_context_dirs to list available files first.

    Returns:
        str: File content (truncated to max_chars).
    """
    if not CONTEXT_DIRS:
        return "No context directories configured. Set AGENT_MEM_CONTEXT_DIRS."

    # Search all context dirs for the file
    for d in CONTEXT_DIRS:
        candidate = d / params.filename
        if candidate.exists() and candidate.is_file():
            content = _safe_read(candidate, params.max_chars)
            if content:
                return (f"📄 **{params.filename}** (from `{d}`)\n"
                        f"*{candidate.stat().st_size:,} bytes*\n\n"
                        f"```\n{content}\n```")
            return f"File exists but could not be read: `{candidate}`"

    # Try fuzzy: search by filename only
    target = Path(params.filename).name
    for d in CONTEXT_DIRS:
        for f in _scan_context_dir(d, 50):
            if f.name == target:
                content = _safe_read(f, params.max_chars)
                if content:
                    rel = f.relative_to(d)
                    return (f"📄 **{rel}** (from `{d}`)\n"
                            f"*{f.stat().st_size:,} bytes*\n\n"
                            f"```\n{content}\n```")

    return f"File `{params.filename}` not found in any context directory."


# ── Ticketing System (file-based) ────────────────────────
#
# Folder structure inside .agent-mem/:
#   tickets/
#   ├── TK-abc123.md              ← OPEN tickets (root = queue)
#   ├── review/                   ← Agent submitted work for review
#   │   └── TK-abc123-submit.md
#   ├── closed/                   ← Approved & done
#   │   ├── TK-abc123.md          ← Original ticket (moved here)
#   │   └── TK-abc123-submit.md   ← Submitted work (moved here)
#   └── rejected/                 ← Failed review
#       ├── TK-abc123.md          ← Original ticket (moved here)
#       ├── TK-abc123-submit.md   ← Submitted work (moved here)
#       └── TK-abc123-rejected.md ← Rejection note + how to fix

import shutil

def _tickets_dir() -> Path:
    d = MEMORY_DIR / "tickets"
    d.mkdir(parents=True, exist_ok=True)
    (d / "review").mkdir(exist_ok=True)
    (d / "closed").mkdir(exist_ok=True)
    (d / "rejected").mkdir(exist_ok=True)
    return d

def _ticket_index_p() -> Path:
    return MEMORY_DIR / "tickets" / "_index.json"

def _load_ticket_index() -> list:
    return _load(_ticket_index_p()).get("tickets", [])

def _save_ticket_index(tickets: list):
    _save(_ticket_index_p(), {"tickets": tickets})

def _auto_transition_claimed(idx: list) -> bool:
    """Auto-advance claimed tickets to in_progress after 2 minutes. Returns True if any changed."""
    changed = False
    threshold = 120  # 2 minutes
    for t in idx:
        if t.get("status") == TicketStatus.CLAIMED and t.get("claimed_at"):
            if time.time() - t["claimed_at"] >= threshold:
                t["status"] = TicketStatus.IN_PROGRESS
                t["updated_at"] = _now()
                changed = True
    return changed

def _write_ticket_md(filepath: Path, data: dict):
    """Write a ticket as a human-readable .md file."""
    lines = [f"# {data.get('title', 'Untitled')}"]
    lines.append(f"**ID**: `{data.get('id', '?')}`")
    lines.append(f"**Status**: {data.get('status', '?')}")
    lines.append(f"**Priority**: {data.get('priority', '?')}")
    lines.append(f"**Created by**: `{data.get('created_by', '?')}`")
    lines.append(f"**Created at**: {data.get('created_at', '?')}")
    if data.get("assigned_to"):
        lines.append(f"**Assigned to**: `{data['assigned_to']}`")
    if data.get("tags"):
        lines.append(f"**Tags**: {', '.join(data['tags'])}")
    if data.get("related_files"):
        lines.append(f"**Files**: {', '.join(data['related_files'])}")
    lines.append(f"\n---\n")
    lines.append(data.get("description", ""))
    filepath.write_text("\n".join(lines), encoding="utf-8")


class TicketPriority(str, Enum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"

class TicketStatus(str, Enum):
    OPEN = "open"; CLAIMED = "claimed"; IN_PROGRESS = "in_progress"
    CREATING_REPORT = "creating_report"; SUBMITTED = "submitted"
    REVIEWING = "reviewing"; CLOSED = "closed"; REJECTED = "rejected"
    CANCELED = "canceled"; TERMINATED = "terminated"
    # legacy alias kept for backward compat
    IN_REVIEW = "in_review"

class CreateTicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., description="Who is creating this ticket", min_length=1, max_length=100)
    title: str = Field(..., description="Short ticket title", min_length=1, max_length=200)
    description: str = Field(..., description="What needs to be done — be specific", min_length=1, max_length=5000)
    target_url: str = Field(..., description="URL the executor must navigate to", min_length=1, max_length=500)
    scope: str = Field(..., description="Execution scope: 'READ-ONLY', 'interactive-no-send', or 'interactive'", pattern="^(READ-ONLY|interactive-no-send|interactive)$")
    required_fields: List[str] = Field(..., description="Deliverables the executor MUST capture (e.g. ['console-log', 'screenshot-load'])", min_length=1)
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM)
    assigned_to: Optional[str] = Field(default=None, description="Agent name or platform to assign (e.g. 'cursor', 'codex'). Empty = any agent.")
    forbidden: Optional[List[str]] = Field(default_factory=list, description="Actions the executor must NOT take (e.g. ['submit form', 'delete'])")
    selector_hints: Optional[List[str]] = Field(default_factory=list, description="CSS/text hints to help locate UI elements")
    tags: Optional[List[str]] = Field(default_factory=list)
    related_files: Optional[List[str]] = Field(default_factory=list)

class ClaimTicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., min_length=1, max_length=100)
    ticket_id: str = Field(..., description="Ticket ID to claim", min_length=1)

class SubmitTicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., min_length=1, max_length=100)
    ticket_id: str = Field(..., min_length=1)
    summary: str = Field(..., description="What was done", min_length=1, max_length=5000)
    files_changed: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, description="Any additional notes for reviewer", max_length=2000)

class ReviewTicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    agent_name: str = Field(..., description="Reviewer agent name", min_length=1, max_length=100)
    ticket_id: str = Field(..., min_length=1)
    verdict: str = Field(..., description="'approve' or 'reject'", pattern="^(approve|reject)$")
    review_notes: str = Field(..., description="Review feedback", min_length=1, max_length=5000)
    fix_instructions: Optional[str] = Field(default=None, description="If rejected: how to fix", max_length=5000)

class ListTicketsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    status: Optional[TicketStatus] = Field(default=None, description="Filter by status")
    assigned_to: Optional[str] = Field(default=None, description="Filter by assignee")
    include_closed: Optional[bool] = Field(default=False, description="Include closed/rejected tickets")


@mcp.tool(name="memory_create_ticket", annotations={"title":"Create Ticket","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_create_ticket(params: CreateTicketInput) -> str:
    """Create a ticket requesting help from another agent.

    Ticket is saved as .md file in tickets/ (open queue).
    Assign to a specific agent/platform or leave open for anyone.

    Examples:
    - PM needs coder: assigned_to="cursor"
    - Coder needs review: assigned_to="claude"
    - Anyone can pick up: assigned_to=None
    """
    err = _require_joined(params.agent_name)
    if err: return err
    _touch_heartbeat(params.agent_name)
    _tickets_dir()
    ticket_id = f"TK-{_id()}"
    ticket_data = {
        "id": ticket_id,
        "title": params.title,
        "description": params.description,
        "target_url": params.target_url,
        "scope": params.scope,
        "required_fields": params.required_fields,
        "forbidden": params.forbidden or [],
        "selector_hints": params.selector_hints or [],
        "priority": params.priority,
        "status": TicketStatus.OPEN,
        "created_by": params.agent_name,
        "assigned_to": params.assigned_to,
        "claimed_by": None,
        "tags": params.tags or [],
        "related_files": params.related_files or [],
        "created_at": _now(),
        "updated_at": _now(),
        "timestamp": time.time(),
    }

    # Save .md file in tickets root (= open queue)
    _write_ticket_md(_tickets_dir() / f"{ticket_id}.md", ticket_data)

    # Update index
    idx = _load_ticket_index()
    idx.append(ticket_data)
    _save_ticket_index(idx)

    assign_str = f"→ assigned to **{params.assigned_to}**" if params.assigned_to else "→ open for any agent"
    pe = {"low":"🟢","medium":"🟡","high":"🟠","critical":"🔴"}[params.priority]
    return (
        f"🎫 Ticket created: `{ticket_id}`\n"
        f"{pe} **{params.priority.upper()}** | {params.title}\n"
        f"By `{params.agent_name}` {assign_str}\n"
        f"File: `tickets/{ticket_id}.md`"
    )


@mcp.tool(name="memory_claim_ticket", annotations={"title":"Claim Ticket","readOnlyHint":False,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_claim_ticket(params: ClaimTicketInput) -> str:
    """Claim an open ticket (sets to claimed). Call again on a claimed ticket to advance to in_progress (e.g. when spawning a subagent)."""
    err = _require_joined(params.agent_name)
    if err: return err
    idx = _load_ticket_index()
    _touch_heartbeat(params.agent_name)
    for t in idx:
        if t["id"] == params.ticket_id:
            if t["status"] == TicketStatus.CLAIMED and t.get("claimed_by") == params.agent_name:
                t["status"] = TicketStatus.IN_PROGRESS
                t["updated_at"] = _now()
                _save_ticket_index(idx)
                _write_ticket_md(_tickets_dir() / f"{t['id']}.md", t)
                return (
                    f"🔧 `{t['id']}` → **in_progress** by `{params.agent_name}`\n"
                    f"Subagent running. Use `memory_submit_ticket` when done."
                )
            if t["status"] not in (TicketStatus.OPEN,):
                return f"Ticket `{t['id']}` is already {t['status']}."
            t["status"] = TicketStatus.CLAIMED
            t["claimed_by"] = params.agent_name
            t["claimed_at"] = time.time()
            t["updated_at"] = _now()
            _save_ticket_index(idx)
            _write_ticket_md(_tickets_dir() / f"{t['id']}.md", t)
            return (
                f"📌 Claimed `{t['id']}`: **{t['title']}**\n"
                f"Status: claimed by `{params.agent_name}` (auto-advances to in_progress in 2 min)\n"
                f"Call again to advance immediately, or use `memory_submit_ticket` when done."
            )
    return f"Ticket `{params.ticket_id}` not found."


@mcp.tool(name="memory_submit_ticket", annotations={"title":"Submit Work for Review","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_submit_ticket(params: SubmitTicketInput) -> str:
    """Submit completed work on a ticket for review.

    Creates a submission report in tickets/review/ and moves ticket to review status.
    Another agent (reviewer/PM) will approve or reject.
    """
    err = _require_joined(params.agent_name)
    if err: return err
    idx = _load_ticket_index()
    _touch_heartbeat(params.agent_name)
    for t in idx:
        if t["id"] == params.ticket_id:
            if t["status"] not in (TicketStatus.CLAIMED, TicketStatus.IN_PROGRESS, TicketStatus.CREATING_REPORT, TicketStatus.REJECTED, TicketStatus.IN_REVIEW):
                return f"Ticket `{t['id']}` is {t['status']} — can only submit claimed/in_progress/creating_report tickets."
            t["status"] = TicketStatus.SUBMITTED
            t["updated_at"] = _now()
            _save_ticket_index(idx)

            # Update ticket .md
            _write_ticket_md(_tickets_dir() / f"{t['id']}.md", t)

            # Create submission report
            submit_lines = [
                f"# Submission: {t['title']}",
                f"**Ticket**: `{t['id']}`",
                f"**Submitted by**: `{params.agent_name}`",
                f"**Submitted at**: {_now()}",
                f"**Original request by**: `{t['created_by']}`",
            ]
            if params.files_changed:
                submit_lines.append(f"\n## Files Changed")
                for f in params.files_changed:
                    submit_lines.append(f"- `{f}`")
            submit_lines.append(f"\n## Summary")
            submit_lines.append(params.summary)
            if params.notes:
                submit_lines.append(f"\n## Notes")
                submit_lines.append(params.notes)

            submit_path = _tickets_dir() / "review" / f"{t['id']}-submit.md"
            submit_path.write_text("\n".join(submit_lines), encoding="utf-8")

            # Auto-handoff: agent submitted work, should leave for reviewer
            agents = _load_agt()
            for a in agents.values():
                if a.get("agent_name") == params.agent_name and a.get("status") == AgentStatus.ACTIVE:
                    a["status"] = AgentStatus.HANDED_OFF
                    a["handed_off_at"] = _now()
                    break
            _save_agt(agents)

            # Write handoff memory
            mem = _load_mem()
            mem.append({
                "id": _id(), "agent_name": params.agent_name,
                "memory_type": MemoryType.HANDOFF,
                "title": f"Auto-handoff after submitting {t['id']}",
                "content": (
                    f"## Summary\nSubmitted ticket `{t['id']}`: {t['title']}\n\n"
                    f"## What was done\n{params.summary}\n\n"
                    f"## Next Steps\n1. Reviewer: check `tickets/review/{t['id']}-submit.md`\n"
                    f"2. Approve → `memory_review_ticket(verdict='approve')`\n"
                    f"3. Reject → `memory_review_ticket(verdict='reject')`"
                ),
                "tags": ["handoff", "ticket", "auto"],
                "related_files": params.files_changed or [],
                "priority": 3, "pinned": True,
                "created_at": _now(), "timestamp": time.time()
            })
            _save_mem(mem)

            return (
                f"📤 Submitted `{t['id']}` for review!\n"
                f"**{t['title']}** by `{params.agent_name}`\n"
                f"Report: `tickets/review/{t['id']}-submit.md`\n\n"
                f"🤝 You're off board. Reviewer will pick this up."
            )
    return f"Ticket `{params.ticket_id}` not found."


@mcp.tool(name="memory_review_ticket", annotations={"title":"Review Submitted Ticket","readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False})
async def memory_review_ticket(params: ReviewTicketInput) -> str:
    """Review a submitted ticket. Approve → closed/ or Reject → rejected/.

    On approve: moves ticket + submission to closed/
    On reject: moves to rejected/ + creates rejection note with fix instructions.
    """
    err = _require_joined(params.agent_name)
    if err: return err
    tdir = _tickets_dir()
    idx = _load_ticket_index()
    _touch_heartbeat(params.agent_name)
    for t in idx:
        if t["id"] == params.ticket_id:
            if t["status"] not in (TicketStatus.SUBMITTED, TicketStatus.IN_REVIEW):
                return f"Ticket `{t['id']}` is {t['status']} — can only review submitted tickets."
            t["status"] = TicketStatus.REVIEWING
            t["updated_at"] = _now()
            _save_ticket_index(idx)

            ticket_file = tdir / f"{t['id']}.md"
            submit_file = tdir / "review" / f"{t['id']}-submit.md"

            if params.verdict == "approve":
                t["status"] = TicketStatus.CLOSED
                t["reviewed_by"] = params.agent_name
                t["reviewed_at"] = _now()
                t["updated_at"] = _now()
                _save_ticket_index(idx)

                # Move files to closed/
                dest = tdir / "closed"
                if ticket_file.exists():
                    shutil.move(str(ticket_file), str(dest / ticket_file.name))
                if submit_file.exists():
                    shutil.move(str(submit_file), str(dest / submit_file.name))

                # Write review result
                review_path = dest / f"{t['id']}-review.md"
                review_path.write_text("\n".join([
                    f"# ✅ Review: APPROVED",
                    f"**Ticket**: `{t['id']}` — {t['title']}",
                    f"**Reviewed by**: `{params.agent_name}`",
                    f"**Reviewed at**: {_now()}",
                    f"\n## Review Notes",
                    params.review_notes,
                ]), encoding="utf-8")

                # Log as memory
                mem = _load_mem()
                mem.append({
                    "id": _id(), "agent_name": params.agent_name,
                    "memory_type": MemoryType.PROGRESS,
                    "title": f"✅ Approved {t['id']}: {t['title']}",
                    "content": f"Ticket by `{t['created_by']}`, done by `{t.get('claimed_by','?')}`. {params.review_notes[:300]}",
                    "tags": ["ticket","approved"], "related_files": [],
                    "priority": 1, "pinned": False, "created_at": _now(), "timestamp": time.time()
                })
                _save_mem(mem)

                # Auto-handoff reviewer
                agents = _load_agt()
                for a in agents.values():
                    if a.get("agent_name") == params.agent_name and a.get("status") == AgentStatus.ACTIVE:
                        a["status"] = AgentStatus.HANDED_OFF
                        a["handed_off_at"] = _now()
                        break
                _save_agt(agents)

                return (
                    f"✅ Approved `{t['id']}`: **{t['title']}**\n"
                    f"Moved to `tickets/closed/`\n"
                    f"Reviewed by `{params.agent_name}`\n\n"
                    f"🤝 Ticket closed. You're off board."
                )

            else:  # reject
                t["status"] = TicketStatus.REJECTED
                t["reviewed_by"] = params.agent_name
                t["reviewed_at"] = _now()
                t["updated_at"] = _now()
                _save_ticket_index(idx)

                # Move files to rejected/
                dest = tdir / "rejected"
                if ticket_file.exists():
                    shutil.move(str(ticket_file), str(dest / ticket_file.name))
                if submit_file.exists():
                    shutil.move(str(submit_file), str(dest / submit_file.name))

                # Write rejection note with fix instructions
                reject_path = dest / f"{t['id']}-rejected.md"
                reject_lines = [
                    f"# ❌ Review: REJECTED",
                    f"**Ticket**: `{t['id']}` — {t['title']}",
                    f"**Rejected by**: `{params.agent_name}`",
                    f"**Rejected at**: {_now()}",
                    f"**Original assignee**: `{t.get('claimed_by', '?')}`",
                    f"\n## What went wrong",
                    params.review_notes,
                ]
                if params.fix_instructions:
                    reject_lines.extend([
                        f"\n## How to fix",
                        params.fix_instructions,
                    ])
                reject_lines.append(f"\n---\n*Re-claim this ticket with `memory_claim_ticket` and try again.*")
                reject_path.write_text("\n".join(reject_lines), encoding="utf-8")

                # Update ticket md in rejected/ for re-claiming
                t_copy = dict(t)
                t_copy["status"] = TicketStatus.OPEN  # reopen for next attempt
                _write_ticket_md(tdir / f"{t['id']}.md", t_copy)

                # Reopen in index so it shows up again
                t["status"] = TicketStatus.OPEN
                t["rejection_count"] = t.get("rejection_count", 0) + 1
                _save_ticket_index(idx)

                # Log as memory
                mem = _load_mem()
                mem.append({
                    "id": _id(), "agent_name": params.agent_name,
                    "memory_type": MemoryType.WARNING,
                    "title": f"❌ Rejected {t['id']}: {t['title']}",
                    "content": f"Rejected work by `{t.get('claimed_by','?')}`. {params.review_notes[:200]}\nFix: {(params.fix_instructions or 'See rejection note')[:200]}",
                    "tags": ["ticket","rejected"], "related_files": [],
                    "priority": 2, "pinned": True, "created_at": _now(), "timestamp": time.time()
                })
                _save_mem(mem)

                # Auto-handoff reviewer — ticket reopened, next agent will see it
                agents = _load_agt()
                for a in agents.values():
                    if a.get("agent_name") == params.agent_name and a.get("status") == AgentStatus.ACTIVE:
                        a["status"] = AgentStatus.HANDED_OFF
                        a["handed_off_at"] = _now()
                        break
                _save_agt(agents)

                return (
                    f"❌ Rejected `{t['id']}`: **{t['title']}**\n"
                    f"Rejection note: `tickets/rejected/{t['id']}-rejected.md`\n"
                    f"Ticket reopened for next agent to fix.\n"
                    f"Reviewed by `{params.agent_name}`\n\n"
                    f"🤝 You're off board. Next agent will get back on board and see this ticket."
                )
    return f"Ticket `{params.ticket_id}` not found."


@mcp.tool(name="memory_cancel_ticket", annotations={"title":"Cancel Ticket","readOnlyHint":False,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_cancel_ticket(agent_name: str, ticket_id: str, reason: str = "") -> str:
    """Cancel a ticket. Only the original creator can cancel."""
    err = _require_joined(agent_name)
    if err: return err
    _touch_heartbeat(agent_name)
    idx = _load_ticket_index()
    for t in idx:
        if t["id"] == ticket_id:
            if t["created_by"] != agent_name:
                return f"❌ Only the creator (`{t['created_by']}`) can cancel ticket `{ticket_id}`."
            if t["status"] in (TicketStatus.CLOSED, TicketStatus.CANCELED, TicketStatus.TERMINATED):
                return f"Ticket `{ticket_id}` is already {t['status']}."
            t["status"] = TicketStatus.CANCELED
            t["updated_at"] = _now()
            if reason:
                t["cancel_reason"] = reason
            _save_ticket_index(idx)
            _write_ticket_md(_tickets_dir() / f"{t['id']}.md", t)
            return f"🚫 Ticket `{ticket_id}` canceled by creator `{agent_name}`." + (f"\nReason: {reason}" if reason else "")
    return f"Ticket `{ticket_id}` not found."


@mcp.tool(name="memory_terminate_ticket", annotations={"title":"Terminate Ticket","readOnlyHint":False,"destructiveHint":True,"idempotentHint":True,"openWorldHint":False})
async def memory_terminate_ticket(agent_name: str, ticket_id: str, reason: str = "") -> str:
    """Forcefully terminate a ticket at any stage. Only the original creator can terminate."""
    err = _require_joined(agent_name)
    if err: return err
    _touch_heartbeat(agent_name)
    idx = _load_ticket_index()
    for t in idx:
        if t["id"] == ticket_id:
            if t["created_by"] != agent_name:
                return f"❌ Only the creator (`{t['created_by']}`) can terminate ticket `{ticket_id}`."
            if t["status"] in (TicketStatus.CLOSED, TicketStatus.CANCELED, TicketStatus.TERMINATED):
                return f"Ticket `{ticket_id}` is already {t['status']}."
            t["status"] = TicketStatus.TERMINATED
            t["updated_at"] = _now()
            if reason:
                t["terminate_reason"] = reason
            _save_ticket_index(idx)
            _write_ticket_md(_tickets_dir() / f"{t['id']}.md", t)
            return f"⛔ Ticket `{ticket_id}` terminated by creator `{agent_name}`." + (f"\nReason: {reason}" if reason else "")
    return f"Ticket `{ticket_id}` not found."


@mcp.tool(name="memory_list_tickets", annotations={"title":"List Tickets","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
async def memory_list_tickets(params: ListTicketsInput) -> str:
    """List tickets. Shows open/in_progress/in_review by default. Use include_closed for history."""
    idx = _load_ticket_index()
    _lazy_kia_sweep()
    if _auto_transition_claimed(idx):
        _save_ticket_index(idx)
    if not idx:
        return "No tickets yet. Use `memory_create_ticket` to create one."

    filtered = idx
    if params.status:
        filtered = [t for t in filtered if t["status"] == params.status]
    elif not params.include_closed:
        filtered = [t for t in filtered if t["status"] not in (TicketStatus.CLOSED, TicketStatus.CANCELED, TicketStatus.TERMINATED)]
    if params.assigned_to:
        filtered = [t for t in filtered if
                    params.assigned_to.lower() in (t.get("assigned_to") or "").lower() or
                    params.assigned_to.lower() in (t.get("claimed_by") or "").lower()]

    if not filtered:
        return "No tickets matching filters."

    pe = {"low":"🟢","medium":"🟡","high":"🟠","critical":"🔴"}
    se = {
        "open":"📭","claimed":"📌","in_progress":"🔧","creating_report":"📝",
        "submitted":"📤","reviewing":"🔍","in_review":"📤",
        "closed":"✅","rejected":"❌","canceled":"🚫","terminated":"⛔"
    }

    lines = [f"# 🎫 Tickets ({len(filtered)})\n"]
    for t in sorted(filtered, key=lambda x: ({"critical":0,"high":1,"medium":2,"low":3}.get(x["priority"],9), -x.get("timestamp",0))):
        s = se.get(t["status"],"❓"); p = pe.get(t["priority"],"⚪")
        assign = f"→ `{t['assigned_to']}`" if t.get("assigned_to") else "→ any"
        claimed = f" ⚡ `{t['claimed_by']}`" if t.get("claimed_by") else ""
        rej = f" (rejected {t['rejection_count']}x)" if t.get("rejection_count") else ""
        lines.append(f"### {s} {p} `{t['id']}` — {t['title']}{rej}")
        lines.append(f"*By `{t['created_by']}` {assign}{claimed} | {t['status']}*")
        lines.append(f"{t['description'][:200]}{'...' if len(t['description'])>200 else ''}\n---\n")

    # Show folder structure hint
    lines.append("📁 `tickets/` = open queue | `tickets/review/` = submitted | `tickets/closed/` = done | `tickets/rejected/` = failed")
    return "\n".join(lines)


@mcp.prompt(name="on-board", description="Join the project and get the full briefing — always run this first.")
def prompt_on_board(agent_name: str = "claude", agent_platform: str = "claude-desktop") -> str:
    return (
        f"You are joining a shared multi-agent project. Follow these steps in order:\n\n"
        f"1. Call `memory_onboard` with:\n"
        f"   - agent_name: \"{agent_name}\"\n"
        f"   - agent_platform: \"{agent_platform}\"\n"
        f"   - mode: \"normal\"\n\n"
        f"2. Report back: who is active, what tickets are open, and what was the last decision or handoff.\n\n"
        f"Do not start any work until `memory_onboard` has completed."
    )


if __name__ == "__main__":
    mcp.run()
