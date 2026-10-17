"""Briefing repository: typed access to the store, always for one owner.

`mutate` is the only way a briefing changes. It runs inside the store's atomic read-modify-write,
so a callback that re-checks the state (as every service method does) is race-free. The record's
hash chain (chain.py) is append-only: a change that alters or drops an earlier event is refused.

A briefing belongs to the device key that created it (API.md, "Callers and ownership"): the record
carries the key's SHA-256 beside the briefing's own fields, and every read and write here takes the
owner and answers 404 to any other, exactly as for an unknown id. The owner is storage metadata, not
part of the `Briefing` type, so it cannot reach a response.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Any

from sayitback import catalog
from sayitback.errors import NotFound
from sayitback.models import Briefing, BriefingSummary, now_iso
from sayitback.store import Store
from sayitback.store.base import valid_briefing_id

NOT_FOUND = "Briefing not found."


def owns(raw: dict[str, Any], owner: str) -> bool:
    """Whether the stored record belongs to `owner`. One made before device keys has no owner, so it
    belongs to no one."""
    stored = raw.get("owner")
    return (
        bool(stored) and bool(owner) and hmac.compare_digest(str(stored).encode(), owner.encode())
    )


class Repo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def get(self, briefing_id: str, owner: str) -> Briefing:
        raw = await self.store.get(briefing_id) if valid_briefing_id(briefing_id) else None
        if raw is None or not owns(raw, owner):
            raise NotFound(NOT_FOUND)
        return Briefing.model_validate(raw)

    async def create(self, briefing: Briefing, owner: str) -> Briefing:
        if not owner:
            raise ValueError("a briefing needs an owner")
        await self.store.create({**briefing.stored(), "owner": owner})
        return briefing

    async def mutate(
        self, briefing_id: str, owner: str, change: Callable[[Briefing], None]
    ) -> Briefing:
        def apply(raw: dict) -> dict:
            if not owns(raw, owner):  # inside the atomic step: no write for another owner
                raise NotFound(NOT_FOUND)
            briefing = Briefing.model_validate(raw)
            history = [e.wire() for e in briefing.events]
            change(briefing)
            if [e.wire() for e in briefing.events[: len(history)]] != history:
                raise RuntimeError("the record chain is append-only")  # a bug, never a request
            briefing.updated_at = now_iso()
            return {**briefing.stored(), "owner": raw["owner"]}

        if not valid_briefing_id(briefing_id):
            raise NotFound(NOT_FOUND)
        try:
            return Briefing.model_validate(await self.store.update(briefing_id, apply))
        except KeyError:
            raise NotFound(NOT_FOUND) from None

    async def recent(self, limit: int, owner: str) -> list[Briefing]:
        """The owner's briefings, newest first."""
        return [Briefing.model_validate(raw) for raw in await self.store.recent(limit, owner)]


def summarise(b: Briefing) -> BriefingSummary:
    title = catalog.task_title(b.task_id, b.supervisor_lang, fallback=b.sop.title)
    return BriefingSummary(
        id=b.id,
        site_id=b.site_id,
        task_id=b.task_id,
        task_title=title,
        supervisor_lang=b.supervisor_lang,
        worker_lang=b.worker_lang,
        status=b.status,
        rounds=len(b.rounds),
        decision=b.decision,
        created_at=b.created_at,
        permit=b.permit,
    )
