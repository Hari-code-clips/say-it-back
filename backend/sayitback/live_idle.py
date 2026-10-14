"""A Live socket's clocks and its per-address count (API.md, "Limits").

Idle means no frame the relay accepts, no event from the model and no model speech still playing.
Live sends the audio of a turn well ahead of real time and then goes quiet until the speech would
end (measured: a 31 s read-out was on the wire within 8 s, `turn_complete` 24 s after that), so
speech still playing is not idleness. A frame the relay drops, which is audio outside an answer
window, is not activity either: if it were, a socket could be held for the whole session limit by
sending what the model will never hear, with a Live connection and the round's lease held open.
Before its first cue the browser also has `first_cue_s` from `ready` to send one.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

IDLE_MESSAGE = "The live session was idle for too long."


class IdleClock:
    def __init__(self, idle_s: float, first_cue_s: float) -> None:
        self._idle_s = idle_s
        self._first_cue_s = first_cue_s
        self._last_activity = 0.0
        self._playback_until = 0.0  # loop time at which the model audio sent so far has played out
        self._cue_by: float | None = None  # until the first cue: when it is overdue

    @staticmethod
    def _now() -> float:
        return asyncio.get_running_loop().time()

    def start(self) -> None:
        """`ready` was sent: the browser's first-cue time starts."""
        self._last_activity = self._now()
        self._cue_by = self._last_activity + self._first_cue_s

    def cue_seen(self) -> None:
        self._cue_by = None

    def touch(self) -> None:
        """A frame the relay accepted, or an event from the model."""
        self._last_activity = self._now()

    def speak(self, seconds: float) -> None:
        """`seconds` of model speech were queued for the browser, which plays it back to back."""
        self._playback_until = max(self._playback_until, self._now()) + seconds

    def hush(self) -> None:
        """Barge-in: the browser drops what it had queued."""
        self._playback_until = 0.0

    def _left(self) -> float:
        now = self._now()
        left = self._idle_s - (now - max(self._last_activity, self._playback_until))
        return left if self._cue_by is None else min(left, self._cue_by - now)

    async def receive(
        self, receive: Callable[[], Awaitable[dict[str, Any]]]
    ) -> dict[str, Any] | None:
        """The next browser message, or None once the socket has been idle too long (`expiry` says
        which limit). Model output can extend the deadline while we wait, so it is looked at again
        whenever a wait runs out."""
        while (left := self._left()) > 0:
            try:
                return await asyncio.wait_for(receive(), left)
            except TimeoutError:
                continue
        return None

    def expiry(self) -> str:
        """The error message for the limit that ended `receive`."""
        if self._cue_by is not None and self._now() >= self._cue_by:
            return f"No cue arrived within {self._first_cue_s:g} s of ready."
        return IDLE_MESSAGE


class OpenSockets:
    """The Live sockets each client address holds open on this instance (SIB_MAX_SOCKETS_PER_IP).
    In memory and per instance, like the rate limiter. An address is in the table only while it
    has a socket open, so the table is never larger than the number of open sockets."""

    def __init__(self) -> None:
        self._open: Counter[str] = Counter()

    def admit(self, address: str, limit: int) -> bool:
        """Count one more open socket for `address`, unless it already holds `limit`."""
        if self._open[address] >= limit:
            return False
        self._open[address] += 1
        return True

    def release(self, address: str) -> None:
        self._open[address] -= 1
        if self._open[address] <= 0:
            del self._open[address]
