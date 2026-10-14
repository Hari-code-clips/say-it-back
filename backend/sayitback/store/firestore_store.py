"""Firestore store (SIB_STORE=firestore). Tested against a fake client; not yet run on Firestore.

Collections: briefings/{id}, live_tickets/{sha256}, live_counters/{id.n}, live_locks/{id.n},
gemini_calls/{YYYYMMDD}, gemini_calls_ip/{sha256 of the day and a client address}.
Every read-modify-write runs in a Firestore transaction, so single-use tickets, the two-ticket cap,
the one-socket lease and the daily Gemini cap (one small document per UTC day, and one per client
address that spent a call that day) hold across Cloud Run instances. The runtime service account
needs roles/datastore.user. A caller's list of briefings (owner ==, createdAt descending) needs a
composite index on briefings(owner, createdAt desc): deploy/01_setup_project.sh creates it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, TypeVar

from sayitback.store.base import Briefing, Reserved, Store, iso, parse_iso, ticket_is_live

T = TypeVar("T")
BRIEFINGS = "briefings"
TICKETS = "live_tickets"
COUNTERS = "live_counters"
LOCKS = "live_locks"
CALLS = "gemini_calls"
ADDRESS_CALLS = "gemini_calls_ip"


class FirestoreStore(Store):
    def __init__(self, client: Any) -> None:
        self._db = client  # google.cloud.firestore.AsyncClient

    @classmethod
    def from_env(cls) -> FirestoreStore:
        from google.cloud import firestore  # imported lazily: only SIB_STORE=firestore needs it

        return cls(firestore.AsyncClient())

    async def _txn(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        from google.cloud import firestore

        @firestore.async_transactional
        async def run(transaction: Any) -> T:
            return await fn(transaction)

        return await run(self._db.transaction())

    def _ref(self, collection: str, name: str) -> Any:
        return self._db.collection(collection).document(name)

    # Briefings -------------------------------------------------------------------------------

    async def create(self, briefing: Briefing) -> None:
        await self._ref(BRIEFINGS, briefing["id"]).set(briefing)

    async def get(self, briefing_id: str) -> Briefing | None:
        snap = await self._ref(BRIEFINGS, briefing_id).get()
        return snap.to_dict() if snap.exists else None

    async def update(self, briefing_id: str, fn: Callable[[Briefing], Briefing]) -> Briefing:
        ref = self._ref(BRIEFINGS, briefing_id)

        async def body(txn: Any) -> Briefing:
            snap = await ref.get(transaction=txn)
            if not snap.exists:
                raise KeyError(briefing_id)
            updated = fn(deepcopy(snap.to_dict()))
            txn.set(ref, updated)
            return updated

        return await self._txn(body)

    async def recent(self, limit: int, owner: str) -> list[Briefing]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = (
            self._db.collection(BRIEFINGS)
            .where(filter=FieldFilter("owner", "==", owner))
            .order_by("createdAt", direction="DESCENDING")
        )
        return [snap.to_dict() async for snap in query.limit(limit).stream()]

    # Tickets and the live lease ---------------------------------------------------------------

    async def issue_ticket(
        self, digest: str, record: dict[str, Any], *, key: str, max_per_round: int
    ) -> bool:
        counter = self._ref(COUNTERS, key)

        async def body(txn: Any) -> bool:
            snap = await counter.get(transaction=txn)
            count = (snap.to_dict() or {}).get("tickets", 0) if snap.exists else 0
            if count >= max_per_round:
                return False
            txn.set(counter, {"tickets": count + 1})
            txn.set(self._ref(TICKETS, digest), record)
            return True

        return await self._txn(body)

    async def redeem_ticket(self, digest: str, now: datetime) -> dict[str, Any] | None:
        ref = self._ref(TICKETS, digest)

        async def body(txn: Any) -> dict[str, Any] | None:
            snap = await ref.get(transaction=txn)
            record = snap.to_dict() if snap.exists else None
            if not ticket_is_live(record, now):
                return None
            assert record is not None
            record["usedAt"] = iso(now)
            txn.set(ref, record)
            return record

        return await self._txn(body)

    async def acquire_live(self, key: str, owner: str, now: datetime, ttl_s: float) -> bool:
        ref = self._ref(LOCKS, key)

        async def body(txn: Any) -> bool:
            snap = await ref.get(transaction=txn)
            held = snap.to_dict() if snap.exists else None
            if held and held["owner"] != owner and parse_iso(held["expiresAt"]) > now:
                return False
            txn.set(ref, {"owner": owner, "expiresAt": iso(now + timedelta(seconds=ttl_s))})
            return True

        return await self._txn(body)

    async def release_live(self, key: str, owner: str) -> None:
        ref = self._ref(LOCKS, key)

        async def body(txn: Any) -> None:
            snap = await ref.get(transaction=txn)
            held = snap.to_dict() if snap.exists else None
            if held and held["owner"] == owner:
                txn.delete(ref)

        await self._txn(body)

    # The daily Gemini call counts ---------------------------------------------------------------

    async def reserve_calls(
        self, day: str, calls: int, cap: int, *, address: str = "", address_cap: int = 0
    ) -> Reserved:
        shared = self._ref(CALLS, day)
        mine = self._ref(ADDRESS_CALLS, address) if address else None

        async def used(ref: Any, txn: Any) -> int:
            snap = await ref.get(transaction=txn)
            return (snap.to_dict() or {}).get("calls", 0) if snap.exists else 0

        async def body(txn: Any) -> Reserved:
            # One transaction over both documents. All reads come first (Firestore requires it),
            # the address's before the shared one, so a client over its own allowance never reads
            # or locks the document every other caller contends on.
            mine_used = await used(mine, txn) if mine is not None else 0
            if mine is not None and mine_used + calls > address_cap:
                return Reserved.ADDRESS_FULL
            shared_used = await used(shared, txn)
            if shared_used + calls > cap:
                return Reserved.GLOBAL_FULL
            txn.set(shared, {"calls": shared_used + calls})
            if mine is not None:
                txn.set(mine, {"calls": mine_used + calls})
            return Reserved.GRANTED

        return await self._txn(body)
