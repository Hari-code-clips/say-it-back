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

from sayitback import retention
from sayitback.store.base import (
    Briefing,
    Reserved,
    Store,
    check_key_is_live,
    iso,
    parse_iso,
    ticket_is_live,
)

T = TypeVar("T")
BRIEFINGS = "briefings"
TICKETS = "live_tickets"
COUNTERS = "live_counters"
LOCKS = "live_locks"
CALLS = "gemini_calls"
ADDRESS_CALLS = "gemini_calls_ip"
OUTBOX = "outbox"  # outbox.py: one document per decided briefing
SOP_LIBRARY = "sop_library"  # 2026-10-16, sop_library.py
ORGS, MEMBERS = "orgs", "members"  # 2026-10-16, auth.py: orgs/{orgId}/members/{memberId}
CHECK_KEYS = "check_keys"  # 2026-10-16, idempotency.py: check_keys/{sha256}


class FirestoreStore(Store):
    def __init__(self, client: Any, retention_days: int = 0) -> None:
        self._db = client  # google.cloud.firestore.AsyncClient
        self.retention_days = retention_days  # retention.py: 0 = keep; make_store sets it

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

    # `expireAt` (retention.py) is a Timestamp in Firestore, so its TTL policy can delete the
    # document, and the ISO string it was written from everywhere above this store. An expired
    # document the TTL has not removed yet (it can lag by a day) is treated as gone.

    async def create(self, briefing: Briefing) -> None:
        stored = retention.stamp(briefing, self.retention_days)
        await self._ref(BRIEFINGS, briefing["id"]).set(retention.to_firestore(stored))

    async def get(self, briefing_id: str) -> Briefing | None:
        snap = await self._ref(BRIEFINGS, briefing_id).get()
        raw = retention.from_firestore(snap.to_dict()) if snap.exists else None
        return None if retention.is_expired(raw) else raw

    async def delete(self, briefing_id: str) -> None:
        ref = self._ref(BRIEFINGS, briefing_id)

        async def body(txn: Any) -> None:
            await ref.get(transaction=txn)  # held until the deletes commit
            txn.delete(ref)
            txn.delete(self._ref(OUTBOX, briefing_id))  # outbox.py: its deliveries go with it

        await self._txn(body)

    async def update(self, briefing_id: str, fn: Callable[[Briefing], Briefing]) -> Briefing:
        ref = self._ref(BRIEFINGS, briefing_id)

        async def body(txn: Any) -> Briefing:
            snap = await ref.get(transaction=txn)
            current = retention.from_firestore(snap.to_dict()) if snap.exists else None
            if current is None or retention.is_expired(current):
                raise KeyError(briefing_id)
            updated = retention.keep_expiry(current, fn(deepcopy(current)))
            txn.set(ref, retention.to_firestore(updated))
            return updated

        return await self._txn(body)

    async def recent(self, limit: int, owner: str) -> list[Briefing]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = (
            self._db.collection(BRIEFINGS)
            .where(filter=FieldFilter("owner", "==", owner))
            .order_by("createdAt", direction="DESCENDING")
        )
        rows = [retention.from_firestore(s.to_dict()) async for s in query.limit(limit).stream()]
        return [r for r in rows if r is not None and not retention.is_expired(r)]

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

    # Idempotent answer uploads (idempotency.py): check_keys/{sha256} ------------------------------

    async def claim_check_key(
        self, digest: str, record: dict[str, Any], now: datetime
    ) -> dict[str, Any] | None:
        ref = self._ref(CHECK_KEYS, digest)

        async def body(txn: Any) -> dict[str, Any] | None:
            snap = await ref.get(transaction=txn)
            held = snap.to_dict() if snap.exists else None
            if check_key_is_live(held, now):
                return held
            txn.set(ref, record)
            return None

        return await self._txn(body)

    async def set_check_key(self, digest: str, record: dict[str, Any] | None) -> None:
        ref = self._ref(CHECK_KEYS, digest)

        async def body(txn: Any) -> None:
            if record is None:
                txn.delete(ref)
            else:
                txn.set(ref, record)

        await self._txn(body)

    # The SOP library (sop_library.py): sop_library/{sha256 of site and scope} ------------------

    async def get_sop_library(self, key: str) -> dict[str, Any] | None:
        snap = await self._ref(SOP_LIBRARY, key).get()
        return snap.to_dict() if snap.exists else None

    async def update_sop_library(
        self, key: str, fn: Callable[[dict[str, Any] | None], dict[str, Any]]
    ) -> dict[str, Any]:
        ref = self._ref(SOP_LIBRARY, key)

        async def body(txn: Any) -> dict[str, Any]:
            snap = await ref.get(transaction=txn)
            updated = fn(snap.to_dict() if snap.exists else None)
            txn.set(ref, updated)
            return updated

        return await self._txn(body)

    # Org members (auth.py): orgs/{orgId}/members/{memberId} --------------------------------------

    def _members(self, org_id: str) -> Any:
        return self._db.collection(f"{ORGS}/{org_id}/{MEMBERS}")

    async def member_get(self, org_id: str, member_id: str) -> dict[str, Any] | None:
        snap = await self._members(org_id).document(member_id).get()
        return snap.to_dict() if snap.exists else None

    async def member_update(
        self,
        org_id: str,
        member_id: str,
        fn: Callable[[dict[str, Any] | None], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        ref = self._members(org_id).document(member_id)

        async def body(txn: Any) -> dict[str, Any] | None:
            snap = await ref.get(transaction=txn)
            current = snap.to_dict() if snap.exists else None
            updated = fn(deepcopy(current))
            if updated is None:
                return current
            txn.set(ref, updated)
            return updated

        return await self._txn(body)

    async def members_list(self, org_id: str, limit: int) -> list[dict[str, Any]]:
        query = self._members(org_id).order_by("memberId").limit(limit)
        return [snap.to_dict() async for snap in query.stream()]

    # The delivery outbox (outbox.py): outbox/{briefingId} ---------------------------------------

    async def outbox_get(self, briefing_id: str) -> dict[str, Any] | None:
        snap = await self._ref(OUTBOX, briefing_id).get()
        return retention.from_firestore(snap.to_dict()) if snap.exists else None

    async def outbox_update(
        self, briefing_id: str, fn: Callable[[dict[str, Any] | None], dict[str, Any] | None]
    ) -> dict[str, Any] | None:
        ref = self._ref(OUTBOX, briefing_id)

        async def body(txn: Any) -> dict[str, Any] | None:
            snap = await ref.get(transaction=txn)
            current = retention.from_firestore(snap.to_dict()) if snap.exists else None
            parent = None  # retention.py: a new outbox document expires with its briefing
            if current is None:
                found = await self._ref(BRIEFINGS, briefing_id).get(transaction=txn)
                parent = retention.from_firestore(found.to_dict()) if found.exists else None
            updated = fn(deepcopy(current))
            if updated is None:
                return current
            updated = retention.inherit_expiry(current, updated, parent)
            txn.set(ref, retention.to_firestore(updated))
            return updated

        return await self._txn(body)

    async def outbox_due(self, now: str, limit: int) -> list[str]:
        """Ordered by `due` alone, a single-field order: no composite index."""
        query = self._db.collection(OUTBOX).order_by("due").limit(limit)
        rows = [snap.to_dict() async for snap in query.stream()]
        return [row["briefingId"] for row in rows if row["due"] <= now]
