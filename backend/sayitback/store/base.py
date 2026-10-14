"""The store interface: briefing records, Live tickets, the one-socket-per-round lease and the
daily counts of Gemini calls.

Briefings are plain JSON dicts in wire (camelCase) form, plus an `owner` (the SHA-256 of the device
key that created them) that the repository keeps out of the `Briefing` type. Every write to an
existing briefing goes through `update(id, fn)`, an atomic read-modify-write, so two instances of
the service never lose an update. Tickets, leases and the call counts live here too, which is what
makes them work across Cloud Run instances.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any

BRIEFING_ID = re.compile(r"^b_[a-z2-7]{12}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
Briefing = dict[str, Any]


class Reserved(Enum):
    """What `Store.reserve_calls` did. Only GRANTED counts the calls, and only GRANTED is truthy."""

    GRANTED = "granted"
    ADDRESS_FULL = "address"  # the caller's own daily allowance would be passed
    GLOBAL_FULL = "global"  # the day's shared cap would be passed

    def __bool__(self) -> bool:
        return self is Reserved.GRANTED


def valid_briefing_id(value: str) -> bool:
    return BRIEFING_ID.fullmatch(value) is not None


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def round_key(briefing_id: str, n: int) -> str:
    return f"{briefing_id}.{n}"


def ticket_is_live(record: dict[str, Any] | None, now: datetime) -> bool:
    """A ticket can be redeemed once, before it expires."""
    return bool(record) and not record.get("usedAt") and parse_iso(record["expiresAt"]) > now


class Store(ABC):
    @abstractmethod
    async def create(self, briefing: Briefing) -> None: ...

    @abstractmethod
    async def get(self, briefing_id: str) -> Briefing | None: ...

    @abstractmethod
    async def update(self, briefing_id: str, fn: Callable[[Briefing], Briefing]) -> Briefing:
        """Atomically apply `fn` to the stored briefing and return the result. `fn` may raise
        to abort. Raises KeyError when the briefing does not exist."""

    @abstractmethod
    async def recent(self, limit: int, owner: str) -> list[Briefing]:
        """The briefings whose `owner` field is `owner`, newest first by createdAt. Firestore needs
        a composite index for this (owner ascending, createdAt descending)."""

    @abstractmethod
    async def issue_ticket(
        self, digest: str, record: dict[str, Any], *, key: str, max_per_round: int
    ) -> bool:
        """Store a ticket (by the SHA-256 digest only). False once `max_per_round` exist."""

    @abstractmethod
    async def redeem_ticket(self, digest: str, now: datetime) -> dict[str, Any] | None:
        """Single use: mark the ticket used and return it, or None if unknown, used or expired."""

    @abstractmethod
    async def acquire_live(self, key: str, owner: str, now: datetime, ttl_s: float) -> bool:
        """Take the lease for one live socket per round. False if another owner holds it."""

    @abstractmethod
    async def release_live(self, key: str, owner: str) -> None: ...

    @abstractmethod
    async def reserve_calls(
        self, day: str, calls: int, cap: int, *, address: str = "", address_cap: int = 0
    ) -> Reserved:
        """The daily Gemini cap. Atomically add `calls` to the count kept for the UTC `day`
        ("YYYYMMDD") unless the count would then pass `cap`; then nothing is added and the result
        says which cap refused. One counter per day, so a new day starts from zero.

        With an `address` (a SHA-256 of the day and the client address, never the address itself),
        the same calls also go to that address's own count, which may not pass `address_cap`. Both
        counts move together or neither does, and the address's is checked first, so a client over
        its own allowance is refused before the shared count is even read."""
