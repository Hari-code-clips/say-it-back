"""PTW_STORE=firestore: permits in Firestore, so the board survives a new instance and scaling to
zero. Tested against a fake client (tests/fake_firestore.py); not yet run on Firestore.

Collections, in the project's (default) database, which the backend uses too:
- permits/{briefingId}: one permit per decided briefing, with `seq`, its number, for the order;
- permits/ref:<REF>: v0.5.2, one grouped permit per permit ref (upper-cased and URL-quoted, as a
  document id cannot hold "/"), its worker slots inside it;
- permit_counters/ptw: `{issued: <n>}`, the last permit number given out;
- permit_deliveries/{Idempotency-Key}: `{briefingId, permit}`, each delivery key taken, written in
  the same transaction as the permit, so a retried delivery is a duplicate on every instance.

A new permit is made in a transaction that reads the briefing's permit and the counter before it
writes either, so a retried post never makes a second permit and two instances never give out the
same number. A grouped permit's post reads and writes its one document in a transaction too, so
two workers' decisions arriving at once on two instances both land. The board lists permits by
`seq`, newest first: a single-field order, which needs no composite index. The service account
needs roles/datastore.user (deploy/04_deploy_ptw_stub.sh).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import quote

from ptw_stub.permits import (
    DecisionRecord,
    Duplicate,
    KeyReused,
    Permit,
    check_key,
    file_into,
    new_group,
    new_permit,
)

T = TypeVar("T")
PERMITS = "permits"
COUNTERS = "permit_counters"
COUNTER = "ptw"
DELIVERIES = "permit_deliveries"
ORDER = ("seq", "DESCENDING")  # the board: newest first (firestore.Query.DESCENDING)
GROUP_PREFIX = "ref:"


def group_id(key: str) -> str:
    """The document id of a grouped permit: its upper-cased ref, with "/" (and anything else a
    document id cannot hold) quoted."""
    return GROUP_PREFIX + quote(key, safe="")


class FirestorePermitBook:
    name = "firestore"

    def __init__(self, client: Any) -> None:
        self._db = client  # google.cloud.firestore.AsyncClient

    @classmethod
    def from_env(cls) -> FirestorePermitBook:
        """A client for the project Cloud Run runs in (Application Default Credentials)."""
        from google.cloud import firestore  # imported lazily: only PTW_STORE=firestore needs it

        return cls(firestore.AsyncClient())

    async def _txn(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        from google.cloud import firestore

        @firestore.async_transactional
        async def run(transaction: Any) -> T:
            return await fn(transaction)

        return await run(self._db.transaction())

    async def _seen(self, txn: Any, key: str | None, record: DecisionRecord) -> Any:
        """Read first (a transaction reads before it writes): raise Duplicate, or KeyReused, when
        the key was already taken; else the key's document (None without a key)."""
        if not key:
            return None
        kref = self._db.collection(DELIVERIES).document(key)
        snap = await kref.get(transaction=txn)
        if not snap.exists:
            return kref
        taken = snap.to_dict()
        if taken["briefingId"] != record.briefing_id:
            raise KeyReused("This Idempotency-Key was used for another briefing.")
        permit = await self._db.collection(PERMITS).document(taken["permit"]).get(transaction=txn)
        raise Duplicate(Permit.model_validate(permit.to_dict()))

    @staticmethod
    def _take(txn: Any, kref: Any, record: DecisionRecord, doc_id: str) -> None:
        if kref is not None:
            txn.set(kref, {"briefingId": record.briefing_id, "permit": doc_id})

    async def record(
        self, record: DecisionRecord, received_at: str | None = None, key: str | None = None
    ) -> tuple[Permit, bool]:
        """The permit for this decision, and whether it is new. Raises KeyMismatch when `key` (the
        post's Idempotency-Key) is not the record's own, and Duplicate when it was already taken,
        writing nothing."""
        check_key(record, key)  # before any read or write
        if record.permit is not None:
            return await self._file(record, received_at, key)
        ref = self._db.collection(PERMITS).document(record.briefing_id)
        counter = self._db.collection(COUNTERS).document(COUNTER)

        async def body(txn: Any) -> tuple[Permit, bool]:
            kref = await self._seen(txn, key, record)
            snap = await ref.get(transaction=txn)
            if snap.exists:
                self._take(txn, kref, record, record.briefing_id)
                return Permit.model_validate(snap.to_dict()), False
            issued = await counter.get(transaction=txn)
            number = int((issued.to_dict() or {}).get("issued", 0)) + 1 if issued.exists else 1
            permit = new_permit(record, number, received_at)
            txn.set(counter, {"issued": number})
            txn.set(ref, {**permit.model_dump(mode="json"), "seq": number})
            self._take(txn, kref, record, record.briefing_id)
            return permit, True

        return await self._txn(body)

    async def _file(
        self, record: DecisionRecord, received_at: str | None, key: str | None
    ) -> tuple[Permit, bool]:
        assert record.permit is not None
        doc_id = group_id(record.permit.key)
        ref = self._db.collection(PERMITS).document(doc_id)
        counter = self._db.collection(COUNTERS).document(COUNTER)

        async def body(txn: Any) -> tuple[Permit, bool]:
            kref = await self._seen(txn, key, record)
            snap = await ref.get(transaction=txn)
            if snap.exists:
                stored = snap.to_dict()
                permit = Permit.model_validate(stored)
                if file_into(permit, record, received_at):  # CrewMismatch: nothing written
                    txn.set(ref, {**permit.model_dump(mode="json"), "seq": stored["seq"]})
                self._take(txn, kref, record, doc_id)
                return permit, False
            issued = await counter.get(transaction=txn)
            number = int((issued.to_dict() or {}).get("issued", 0)) + 1 if issued.exists else 1
            permit = new_group(record, number, received_at)
            txn.set(counter, {"issued": number})
            txn.set(ref, {**permit.model_dump(mode="json"), "seq": number})
            self._take(txn, kref, record, doc_id)
            return permit, True

        return await self._txn(body)

    async def newest_first(self) -> list[Permit]:
        field, direction = ORDER
        query = self._db.collection(PERMITS).order_by(field, direction=direction)
        return [Permit.model_validate(snap.to_dict()) async for snap in query.stream()]
