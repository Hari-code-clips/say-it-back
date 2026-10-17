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
ORG_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")  # auth.py: SIB_AUTH_ORG
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


def check_key_is_live(record: dict[str, Any] | None, now: datetime) -> bool:
    """An idempotency record holds until it expires (idempotency.py)."""
    return bool(record) and parse_iso(record["expiresAt"]) > now


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

    # Idempotent answer uploads (idempotency.py, 2026-10-16): one small record per SHA-256 hex
    # `digest` of (owner, briefing, round, Idempotency-Key), never the key. Not abstract, as above.

    async def claim_check_key(
        self, digest: str, record: dict[str, Any], now: datetime
    ) -> dict[str, Any] | None:
        """Atomically store `record` under `digest` unless an unexpired record is there. Returns
        that record (another upload's claim or its result), or None when this call stored its
        own."""
        raise NotImplementedError

    async def set_check_key(self, digest: str, record: dict[str, Any] | None) -> None:
        """Replace the record under `digest`, or drop it (None)."""
        raise NotImplementedError

    # The SOP library (sop_library.py, 2026-10-16): one document per (site, scope), named by a
    # SHA-256 hex `key`. Not abstract, so a store written before the library still constructs.

    async def get_sop_library(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def update_sop_library(
        self, key: str, fn: Callable[[dict[str, Any] | None], dict[str, Any]]
    ) -> dict[str, Any]:
        """Atomically apply `fn` to the stored document (None when there is none yet), store and
        return the result. `fn` may raise to abort, and then nothing is written."""
        raise NotImplementedError

    # Org members (auth.py, SIB_AUTH_MODE=firebase). Not abstract, so a store built only for
    # device mode (and every test fake) still constructs. The caller checks the ids: `org_id`
    # matches ORG_ID and `member_id` is a SHA-256 hex digest (DIGEST).

    async def member_get(self, org_id: str, member_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def member_update(
        self,
        org_id: str,
        member_id: str,
        fn: Callable[[dict[str, Any] | None], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        """Atomically apply `fn` to the member (None when there is none) and store what it returns.
        When `fn` returns None nothing is written and the current record is returned. `fn` may
        raise to abort."""
        raise NotImplementedError

    async def members_list(self, org_id: str, limit: int) -> list[dict[str, Any]]:
        """At most `limit` of the org's members, by member id."""
        raise NotImplementedError

    # Deletion (retention.py, privacy 16 Oct). Not abstract, so every older store still constructs.
    # The repository checks the owner first; deleting a briefing that is not there is a no-op.

    async def delete(self, briefing_id: str) -> None:
        raise NotImplementedError

    # The delivery outbox (outbox.py, the pilot e-permit link). Not abstract either. One document
    # per decided briefing: its targets' delivery states and `due`, the earliest next attempt (a
    # far-future stamp when nothing is pending), so the retry pass is one single-field query.

    async def outbox_get(self, briefing_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def outbox_update(
        self, briefing_id: str, fn: Callable[[dict[str, Any] | None], dict[str, Any] | None]
    ) -> dict[str, Any] | None:
        """Atomically apply `fn` to the briefing's outbox document (None when there is none) and
        store what it returns; when it returns None nothing is written and the current one is
        returned. `fn` may run more than once (a retried transaction) and may raise to abort."""
        raise NotImplementedError

    async def outbox_due(self, now: str, limit: int) -> list[str]:
        """The ids of at most `limit` briefings whose `due` is at or before `now`, earliest
        first."""
        raise NotImplementedError
