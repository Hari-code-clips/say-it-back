"""Retention and deletion of briefing records (privacy, 16 Oct; API.md Deviations).

- **Retention.** With SIB_RETENTION_DAYS (default 90; 0 = keep) each stored briefing carries
  `expireAt`, its creation time plus that many days, as storage metadata beside `owner` (never in
  the `Briefing` type or a response). It is set once, when the record is created, and no update can
  move or drop it. The local store deletes an expired record the first time it reads it; on
  Firestore a TTL policy on the field named exactly `expireAt` deletes it (deploy/01, the ops
  builder), and until that runs (TTL can lag by a day) the store treats it as gone.
- **Firestore type.** Firestore TTL deletes a document only when `expireAt` is a Timestamp, so the
  Firestore store writes it as a timezone-aware UTC `datetime` and reads it back as the same ISO
  string (`to_firestore`, `from_firestore`). Everything above the store sees the ISO string.
- **Deletion.** `DELETE /api/briefings/{id}` removes the owner's record at once, with its delivery
  outbox document (`outbox/{id}`, outbox.py) and any audio kept under SIB_KEEP_AUDIO. A copy already
  sent by webhook (Google Chat, the permit-to-work system) belongs to that system and is not
  reached from here.
- **The outbox** expires with its briefing: a new `outbox/{id}` takes the briefing's `expireAt`.
  On Firestore that needs a second TTL policy, on `outbox.expireAt` (the ops builder's deploy/01).

This module imports nothing from `sayitback.store`, which imports it.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sayitback.repo import Repo

FIELD = "expireAt"  # the ops builder's Firestore TTL policy names exactly this field


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def expire_at(created_at: str, days: int) -> str | None:
    """When a record created at `created_at` expires, or None when records are kept (0 days)."""
    return _iso(_parse(created_at) + timedelta(days=days)) if days > 0 else None


def stamp(record: dict[str, Any], days: int) -> dict[str, Any]:
    """The record as first stored: with `expireAt` from its `createdAt`, unless kept."""
    when = expire_at(str(record["createdAt"]), days)
    return {**record, FIELD: when} if when else dict(record)


def keep_expiry(current: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any]:
    """An update never moves or drops the expiry set at creation."""
    return {**updated, FIELD: current[FIELD]} if FIELD in current else dict(updated)


def inherit_expiry(
    current: dict[str, Any] | None, updated: dict[str, Any], briefing: dict[str, Any] | None
) -> dict[str, Any]:
    """A briefing's outbox document (outbox.py) expires with it: a new one takes the briefing's
    `expireAt`, and every later write keeps the one it has."""
    if current is not None:
        return keep_expiry(current, updated)
    if briefing and FIELD in briefing:
        return {**updated, FIELD: briefing[FIELD]}
    return dict(updated)


def is_expired(record: dict[str, Any] | None, now: datetime | None = None) -> bool:
    """True when the record's `expireAt` (ISO string or datetime) has passed. An unreadable value
    counts as expired: a record whose retention cannot be read is not served."""
    value = (record or {}).get(FIELD)
    if value is None:
        return False
    try:
        moment = value if isinstance(value, datetime) else _parse(str(value))
    except ValueError:
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment <= (now or datetime.now(UTC))


def to_firestore(record: dict[str, Any]) -> dict[str, Any]:
    """What Firestore stores: `expireAt` as a UTC datetime (a Timestamp), so its TTL can work."""
    value = record.get(FIELD)
    return {**record, FIELD: _parse(value)} if isinstance(value, str) else record


def from_firestore(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the store returns: `expireAt` back as the ISO string it was written from."""
    value = (record or {}).get(FIELD)
    if record is None or not isinstance(value, datetime):
        return record
    return {**record, FIELD: _iso(value)}


async def delete_briefing(repo: Repo, briefing_id: str, owner: str, data_dir: Path) -> None:
    """The owner's record, gone at once: 404 for any other caller, as for an unknown id. The
    owner never changes after creation, so a read then a delete cannot remove another's record."""
    await repo.get(briefing_id, owner)
    await repo.store.delete(briefing_id)
    shutil.rmtree(data_dir / "audio" / briefing_id, ignore_errors=True)
