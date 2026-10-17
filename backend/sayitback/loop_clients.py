"""Each event loop closes its own Gemini clients, inside the loop, before the loop closes (v0.5.1).

ADK keeps one google-genai client per running event loop (its PerLoopCachedProperty) and, when a
later loop reads the model, drops a closed loop's client without closing it. A process that runs
each check in its own loop (eval/ calls asyncio.run per item; so do tests) then sees that client's
`__del__` schedule `aclose()` on the new loop, where the old loop's sockets cannot be closed:
"Task exception was never retrieved ... RuntimeError: Event loop is closed", and "unclosed
transport" warnings at exit.

`track(client)` registers a client with the running loop (backends.FlashGemini does it whenever it
hands ADK its client), and one async generator per loop closes them all while the loop still runs:
asyncio.run finalises every live async generator (`loop.shutdown_asyncgens`) before it closes the
loop. A loop that lives as long as the process (the API server) keeps its clients, as before.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import weakref
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("sayitback.run")


@dataclass
class _LoopClients:
    clients: list[Any] = field(default_factory=list)
    closer: AsyncGenerator[None] | None = None


_LOOPS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopClients] = (
    weakref.WeakKeyDictionary()
)


async def _close_at_shutdown(entry: _LoopClients) -> AsyncGenerator[None]:
    """Waits at its `yield` until the loop finalises it, then closes the loop's clients."""
    try:
        yield
    finally:
        for client in entry.clients:
            with contextlib.suppress(Exception):  # closing is best effort, never a failure
                await client.aio.aclose()
        entry.clients.clear()


async def _start(closer: AsyncGenerator[None]) -> None:
    """Runs the closer to its `yield`, which registers it with the loop's async-generator hooks."""
    await anext(closer)


def track(client: Any) -> None:
    """Close `client` in the running loop when that loop shuts down. Outside a loop, nothing."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    entry = _LOOPS.get(loop)
    if entry is None:
        entry = _LoopClients()
        entry.closer = _close_at_shutdown(entry)  # held here: the loop keeps only a weak reference
        _LOOPS[loop] = entry
        loop.create_task(_start(entry.closer))
    if not any(known is client for known in entry.clients):
        entry.clients.append(client)


def tracked(loop: asyncio.AbstractEventLoop) -> list[Any]:
    """The clients `loop` will close at shutdown (for tests)."""
    entry = _LOOPS.get(loop)
    return list(entry.clients) if entry else []
