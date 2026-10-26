"""Read-only native MCP resources for the On Board board.

Three static resources expose the project's board as bounded JSON:

    onboard://project         -> .agent-mem/project.json
    onboard://tickets         -> .agent-mem/tickets/_index.json
    onboard://memory/summary  -> .agent-mem/memories.json

They are a read surface and nothing else. Reading one never initializes the
board: no directory creation, no store ensure, no board lock, no heartbeat and
no KIA sweep. A missing file yields the explicit uninitialized/empty
projection; a malformed one raises a resource error instead of fabricating
empty success.

Payloads are projections, never dumps. Whole-board totals stay whole while
per-item lists are bounded and flagged `truncated`, previews are cut to a fixed
character budget, and raw memory bodies, archives, absolute paths and
configuration secrets are never included. A serialized payload over
`MAX_RESPONSE_BYTES` is refused rather than streamed.

`RESOURCE_FILES` values are paths relative to the `.agent-mem/` memory
directory, which is also what `BoardSubscriptionBus` watches.
"""

from __future__ import annotations

import json
import stat
from enum import Enum
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ResourceError

import ticket_roles

# ── Resource identity ───────────────────────────────────
PROJECT_URI = "onboard://project"
TICKETS_URI = "onboard://tickets"
MEMORY_URI = "onboard://memory/summary"

RESOURCE_FILES = {
    PROJECT_URI: "project.json",
    TICKETS_URI: "tickets/_index.json",
    MEMORY_URI: "memories.json",
}

MIME_TYPE = "application/json"

# ── Projection bounds ───────────────────────────────────
PROJECT_DESCRIPTION_PREVIEW_CHARS = 500
PROJECT_TECH_STACK_PREVIEW_CHARS = 200
TITLE_PREVIEW_CHARS = 200
OPEN_ITEMS_LIMIT = 50
LATEST_MEMORIES_LIMIT = 10
MAX_RESPONSE_BYTES = 65_536

# Same order the board's own listings use; anything unrecognised sorts last.
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_UNKNOWN_PRIORITY = 9


# ── Projections (pure) ──────────────────────────────────
def project_summary(project: dict, *, initialized: bool) -> dict:
    """Identity and a cut-down description/tech stack. No root path, no timestamps."""
    return {
        "initialized": bool(initialized),
        "description_preview": _preview(project.get("description"), PROJECT_DESCRIPTION_PREVIEW_CHARS),
        "tech_stack_preview": _preview(project.get("tech_stack"), PROJECT_TECH_STACK_PREVIEW_CHARS),
    }


def ticket_summary(tickets: list[dict], *, initialized: bool) -> dict:
    """Whole-board counts plus a bounded, priority-ordered open queue.

    `counts` is keyed by the stored status label (including legacy `in_review`);
    `open_total` and `total` count every ticket, while `open_items` carries at
    most `OPEN_ITEMS_LIMIT` non-terminal ones.
    """
    counts: dict[str, int] = {}
    open_tickets: list[dict] = []
    for ticket in tickets:
        status = _ticket_status(ticket)
        counts[status] = counts.get(status, 0) + 1
        if status not in ticket_roles.TERMINAL:
            open_tickets.append(ticket)
    open_tickets.sort(key=_open_ticket_sort_key)
    return {
        "initialized": bool(initialized),
        "total": len(tickets),
        "open_total": len(open_tickets),
        "counts": counts,
        "open_items": [_ticket_item(ticket) for ticket in open_tickets[:OPEN_ITEMS_LIMIT]],
        "truncated": len(open_tickets) > OPEN_ITEMS_LIMIT,
    }


def memory_summary(memories: list[dict], *, initialized: bool) -> dict:
    """Type/pin counts plus the newest `LATEST_MEMORIES_LIMIT` entries, metadata only.

    Titles are previews; `content` and every other body field stay on disk.
    """
    by_type: dict[str, int] = {}
    pinned = 0
    for memory in memories:
        memory_type = _memory_type(memory)
        by_type[memory_type] = by_type.get(memory_type, 0) + 1
        if memory.get("pinned"):
            pinned += 1
    ordered = sorted(memories, key=_memory_sort_key)
    return {
        "initialized": bool(initialized),
        "total": len(memories),
        "by_type": by_type,
        "pinned": pinned,
        "latest": [_memory_item(memory) for memory in ordered[:LATEST_MEMORIES_LIMIT]],
        "truncated": len(memories) > LATEST_MEMORIES_LIMIT,
    }


# ── Registration ────────────────────────────────────────
def register_resources(mcp, *, store, memory_dir: Path) -> None:
    """Register the three resources on `mcp`, reading through `store`.

    `store` is the board's `JsonMemoryStore` (the same reader the tools use, so
    resource reads see exactly what the tools see). `memory_dir` is the
    `.agent-mem/` directory the `RESOURCE_FILES` paths are relative to.

    Callbacks are named async functions: the installed SDK rejects unnamed
    (lambda) resource functions at registration time.
    """
    memory_dir = Path(memory_dir)
    project_path = memory_dir / RESOURCE_FILES[PROJECT_URI]
    tickets_path = memory_dir / RESOURCE_FILES[TICKETS_URI]
    memory_path = memory_dir / RESOURCE_FILES[MEMORY_URI]

    @mcp.resource(PROJECT_URI, name="project", description="Project identity: description and tech stack previews.", mime_type=MIME_TYPE)
    async def read_project() -> str:
        initialized = _file_exists(project_path)
        project = _read_object(store, project_path) if initialized else {}
        return _encode(project_summary(project, initialized=initialized))

    @mcp.resource(TICKETS_URI, name="tickets", description="Board ticket counts and the bounded open queue.", mime_type=MIME_TYPE)
    async def read_tickets() -> str:
        tickets = _read_object_list(store, tickets_path, "tickets")
        return _encode(ticket_summary(tickets, initialized=_file_exists(project_path)))

    @mcp.resource(MEMORY_URI, name="memory_summary", description="Shared-memory counts and the newest entry metadata.", mime_type=MIME_TYPE)
    async def read_memory_summary() -> str:
        memories = _read_object_list(store, memory_path, "entries")
        return _encode(memory_summary(memories, initialized=_file_exists(project_path)))


# ── File access ─────────────────────────────────────────
def _file_exists(path: Path) -> bool:
    """Only an absent path is an empty resource; other filesystem failures surface."""
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ResourceError(f"{path.name} could not be inspected: {exc.strerror}") from exc
    if not stat.S_ISREG(mode):
        raise ResourceError(f"{path.name} must be a regular JSON file")
    return True


def _read_json(store, path: Path) -> Any:
    """Load one board file through the store's reader, surfacing real failures.

    `JsonMemoryStore.load` only ever reads; it creates nothing. Anything it
    cannot parse or open becomes a resource error, so a damaged board is
    visible instead of silently reported as empty.
    """
    try:
        return store.load(path)
    except json.JSONDecodeError as exc:
        raise ResourceError(f"{path.name} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ResourceError(f"{path.name} could not be read: {exc}") from exc


def _read_object(store, path: Path) -> dict:
    """The file's top-level JSON object, or `{}` when the file is absent."""
    if not _file_exists(path):
        return {}
    data = _read_json(store, path)
    if not isinstance(data, dict):
        raise ResourceError(f"{path.name} must contain a JSON object")
    return data


def _read_object_list(store, path: Path, key: str) -> list[dict]:
    """The list stored under `key`, or `[]` when the file is absent.

    A missing key is an empty list (an initialized board may have no tickets
    yet); a wrong-shaped value is an error, never a silent empty result.
    """
    if not _file_exists(path):
        return []
    data = _read_json(store, path)
    if not isinstance(data, dict):
        raise ResourceError(f"{path.name} must contain a JSON object")
    items = data.get(key, [])
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ResourceError(f"{path.name} field {key!r} must be a list of JSON objects")
    return items


def _encode(payload: dict) -> str:
    """Serialize a projection to JSON, refusing a payload past the response cap."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ResourceError(f"resource payload exceeds the {MAX_RESPONSE_BYTES}-byte response cap")
    return text


# ── Projection helpers ──────────────────────────────────
def _label(value: object, default: str = "") -> str:
    """A stored string as-is.

    Enum members are unwrapped because `str()` on a str-mixin Enum yields
    `TicketStatus.OPEN`, not `open`. Files always hold plain strings, so this
    only matters when a caller projects an in-memory board.
    """
    if value is None:
        return default
    if isinstance(value, Enum):
        value = value.value
    return value if isinstance(value, str) else str(value)


def _preview(value: object, limit: int) -> str:
    return _label(value)[:limit]


def _number(value: object) -> float:
    """Numeric timestamp, or 0.0 for anything missing or non-numeric."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _ticket_status(ticket: dict) -> str:
    return _label(ticket.get("status"), "?")


def _open_ticket_sort_key(ticket: dict) -> tuple:
    priority = _label(ticket.get("priority"))
    return (
        PRIORITY_ORDER.get(priority, _UNKNOWN_PRIORITY),
        -_number(ticket.get("timestamp")),
        _label(ticket.get("id")),
    )


def _ticket_item(ticket: dict) -> dict:
    return {
        "id": _label(ticket.get("id")),
        "title_preview": _preview(ticket.get("title"), TITLE_PREVIEW_CHARS),
        "status": _ticket_status(ticket),
        "priority": _label(ticket.get("priority")),
        "assigned_to": ticket.get("assigned_to"),
        "claimed_by": ticket.get("claimed_by"),
    }


def _memory_type(memory: dict) -> str:
    return _label(memory.get("memory_type"), "?")


def _memory_sort_key(memory: dict) -> tuple:
    """Newest numeric timestamp first; the id breaks ties deterministically."""
    return (-_number(memory.get("timestamp")), _label(memory.get("id")))


def _memory_item(memory: dict) -> dict:
    return {
        "id": _label(memory.get("id")),
        "title_preview": _preview(memory.get("title"), TITLE_PREVIEW_CHARS),
        "memory_type": _memory_type(memory),
    }
