"""Single-use Live tickets (endpoints 11 and 20).

A ticket is 32 random bytes, valid 120 s, redeemable once. Only its SHA-256 is stored, so a leaked
store reveals nothing usable, and the value is never logged. The store keeps tickets, so they
work across Cloud Run instances.

The WebSocket carries no device key: the ticket is its capability. So the ticket's record names the
owner it was issued to (only the briefing's owner can get one), and the relay reads and writes the
briefing as that owner.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sayitback.errors import RateLimited
from sayitback.settings import Settings
from sayitback.store import Store
from sayitback.store.base import iso, round_key

TICKET_BYTES = 32


def new_ticket() -> str:
    return secrets.token_urlsafe(TICKET_BYTES)


def digest_of(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def ws_path(briefing_id: str, n: int) -> str:
    return f"/api/live/{briefing_id}/{n}"


def ws_url(settings: Settings, briefing_id: str, n: int) -> str:
    """Absolute with SIB_PUBLIC_WS_BASE, else a same-origin path the browser resolves."""
    return f"{settings.public_ws_base}{ws_path(briefing_id, n)}"


async def issue_ticket(
    store: Store,
    settings: Settings,
    briefing_id: str,
    n: int,
    *,
    owner: str,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Create a ticket for round `n`, for the briefing's `owner`. Returns (ticket, expiresAt).
    Raises 429 `limit` after two."""
    moment = now or datetime.now(UTC)
    ticket = new_ticket()
    expires = iso(moment + timedelta(seconds=settings.ticket_ttl_s))
    record = {
        "briefingId": briefing_id,
        "n": n,
        "owner": owner,
        "expiresAt": expires,
        "createdAt": iso(moment),
    }
    ok = await store.issue_ticket(
        digest_of(ticket),
        record,
        key=round_key(briefing_id, n),
        max_per_round=settings.max_tickets_per_round,
    )
    if not ok:
        raise RateLimited(
            f"At most {settings.max_tickets_per_round} live tickets can be issued per round.",
            code="limit",
        )
    return ticket, expires


async def redeem_ticket(
    store: Store, ticket: str, *, now: datetime | None = None
) -> dict[str, Any] | None:
    """The ticket's record if it exists, is unused and unexpired (it is then spent), else None."""
    return await store.redeem_ticket(digest_of(ticket), now or datetime.now(UTC))


def ticket_owner(record: dict[str, Any] | None, briefing_id: str, n: int) -> str | None:
    """The owner a redeemed ticket was issued to, if it is for this round and names one."""
    if not record or record.get("briefingId") != briefing_id or record.get("n") != n:
        return None
    return record.get("owner") or None
