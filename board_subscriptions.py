"""Cross-process invalidation for the native board resources (SEP-2575).

At protocol 2026-07-28 there is no standing GET stream: a client opts into
server events with `subscriptions/listen`. On Board runs one stdio process per
client over one shared `.agent-mem/` directory, so a write made by another
process is invisible to this process's SDK bus unless something watches the
files. `BoardSubscriptionBus` is that something:

- It composes the SDK's in-process `InMemorySubscriptionBus` (public API only -
  no private listener or session fields), so `MCPServer(subscriptions=bus)`
  gets the same fan-out semantics, plus a file watcher underneath.
- While at least one listener is attached, one AnyIO task started by the
  server lifespan compares `(st_ino, st_mtime_ns, st_size)` for the three
  `RESOURCE_FILES` paths every `interval_s` seconds and publishes one
  `ResourceUpdated(uri)` per resource whose fingerprint changed. Creation,
  deletion, in-place writes and atomic replace (`rename` over the path) all
  land as a changed fingerprint.
- With no listeners there is no stat scan at all, and the watcher is cancelled
  and joined when the lifespan exits.

Coalescing is intentional and lossy by design: an event means "refetch current
state", not one durable event per mutation, and a dropped stream is not
replayed - a client re-listens and refetches. This is an *additional*
invalidation surface; `memory_wait_for_event` and its durable cursors, own-action
suppression and heartbeat locking are untouched, and this bus never claims to
wake a host's model.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Callable

import anyio
from mcp.server import MCPServer
from mcp.server.subscriptions import InMemorySubscriptionBus, ResourceUpdated, ServerEvent

import a2a_wait
from board_resources import RESOURCE_FILES

_ABSENT = ("absent",)
"""Fingerprint of a path that does not exist. Distinct from every present one."""


def _fingerprint(path: Path) -> tuple:
    """Cheap change token for one watched file.

    `FileNotFoundError` is the ordinary absent case. Any other stat failure is
    recorded as a stable unreadable sentinel (with its errno) rather than
    raised: a permission change must invalidate the resource, not kill the
    watcher or the MCP server. Reading the resource itself still surfaces the
    real error.
    """
    try:
        info = path.stat()
    except FileNotFoundError:
        return _ABSENT
    except OSError as exc:
        return ("unreadable", exc.errno)
    return ("present", info.st_ino, info.st_mtime_ns, info.st_size)


class BoardSubscriptionBus:
    """The SDK subscription bus plus a watcher that turns cross-process writes into events."""

    def __init__(self, memory_dir: Path, *, interval_s: float = a2a_wait.DEFAULT_POLL_INTERVAL_S) -> None:
        self._memory_dir = Path(memory_dir)
        self._interval_s = interval_s
        self._inner = InMemorySubscriptionBus()
        self._listeners = 0
        self._baseline: dict[str, tuple] = {}

    # ── SubscriptionBus protocol ────────────────────────
    async def publish(self, event: ServerEvent) -> None:
        """Forward an event to the SDK's in-process fan-out."""
        await self._inner.publish(event)

    def subscribe(self, listener: Callable[[ServerEvent], None]) -> Callable[[], None]:
        """Register `listener` and return an idempotent unsubscribe callable.

        The first listener captures the baseline fingerprints before this
        returns, so an event published while the `subscriptions/listen` ack is
        still in flight is a real change, not the state the client is about to
        read anyway.
        """
        unsubscribe = self._inner.subscribe(listener)
        self._listeners += 1
        if self._listeners == 1:
            self._baseline = self._scan()
        unsubscribed = False

        def _unsubscribe() -> None:
            nonlocal unsubscribed
            if unsubscribed:
                return
            unsubscribed = True
            unsubscribe()
            self._listeners -= 1

        return _unsubscribe

    # ── Server lifespan ─────────────────────────────────
    @asynccontextmanager
    async def lifespan(self, server: MCPServer) -> AsyncIterator[None]:
        """Own the watcher for the server's lifetime.

        The task group joins the watcher on exit, so a shutdown or cancellation
        leaves no watcher task running.
        """
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(self._watch)
            try:
                yield
            finally:
                task_group.cancel_scope.cancel()

    # ── Watcher ─────────────────────────────────────────
    def _scan(self) -> dict[str, tuple]:
        return {uri: _fingerprint(self._memory_dir / name) for uri, name in RESOURCE_FILES.items()}

    async def _watch(self) -> None:
        while True:
            await anyio.sleep(self._interval_s)
            if self._listeners <= 0:
                continue
            current = self._scan()
            changed = [uri for uri in RESOURCE_FILES if current.get(uri) != self._baseline.get(uri)]
            self._baseline = current
            for uri in changed:
                await self.publish(ResourceUpdated(uri=uri))
