"""An in-memory stand-in for google.cloud.firestore.AsyncClient, just enough for the permit book
(the same behaviour as backend/tests/fake_firestore.py).

Transactions behave as in Firestore's server client libraries: a document read inside a
transaction is locked until the transaction ends, writes are buffered and applied together at the
commit, and an error discards them. Reads outside a transaction are not blocked. Every read yields
to the event loop, as a network round trip would, so concurrent posts really interleave: a
read-then-write without a transaction gives out one permit number twice; one inside it does not.

The real `firestore.async_transactional` decorator is not exercised here (it needs a backend);
the book's logic (keys, the counter, one permit per briefing, the order) is.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from ptw_stub.firestore_book import FirestorePermitBook

Key = tuple[str, str]


class Snapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._data)


class DocRef:
    def __init__(self, db: FakeFirestore, collection: str, name: str) -> None:
        self.db, self.key = db, (collection, name)

    async def get(self, transaction: Txn | None = None) -> Snapshot:
        if transaction is not None:
            await transaction.lock(self.key)
        snapshot = Snapshot(self.db.docs.get(self.key))
        await asyncio.sleep(0)  # the reply is on its way: other tasks run, and may write, here
        return snapshot

    async def set(self, data: dict[str, Any]) -> None:
        self.db.docs[self.key] = deepcopy(data)


class Txn:
    def __init__(self, db: FakeFirestore) -> None:
        self.db = db
        self._held: dict[Key, asyncio.Lock] = {}
        self._writes: list[tuple[Key, dict[str, Any]]] = []

    async def lock(self, key: Key) -> None:
        if key not in self._held:
            lock = self.db.locks.setdefault(key, asyncio.Lock())
            await lock.acquire()
            self._held[key] = lock

    def set(self, ref: DocRef, data: dict[str, Any]) -> None:
        self._writes.append((ref.key, deepcopy(data)))

    def commit(self) -> None:
        for key, data in self._writes:
            self.db.docs[key] = data
        self._writes.clear()

    def release(self) -> None:
        for lock in self._held.values():
            lock.release()
        self._held.clear()


class Query:
    def __init__(self, db: FakeFirestore, collection: str, field: str = "", desc: bool = False):
        self.db, self.collection, self._field, self._desc = db, collection, field, desc

    def order_by(self, field: str, direction: str = "ASCENDING") -> Query:
        return Query(self.db, self.collection, field, direction == "DESCENDING")

    async def stream(self):
        self.db.orders.append((self.collection, self._field, self._desc))
        rows = [v for (c, _), v in self.db.docs.items() if c == self.collection]
        if self._field:
            rows.sort(key=lambda d: d[self._field], reverse=self._desc)
        for row in rows:
            await asyncio.sleep(0)
            yield Snapshot(row)


class Collection(Query):
    def document(self, name: str) -> DocRef:
        return DocRef(self.db, self.collection, name)


class FakeFirestore:
    def __init__(self) -> None:
        self.docs: dict[Key, dict[str, Any]] = {}
        self.locks: dict[Key, asyncio.Lock] = {}
        self.orders: list[tuple[str, str, bool]] = []  # every query's (collection, field, desc)

    def collection(self, name: str) -> Collection:
        return Collection(self, name)

    def transaction(self) -> Txn:
        return Txn(self)


class FakeBackedBook(FirestorePermitBook):
    """FirestorePermitBook whose transactions run directly against the fake. Books built on the
    same `fake` are separate service instances over one database."""

    def __init__(self, fake: FakeFirestore | None = None) -> None:
        self.fake = fake or FakeFirestore()
        super().__init__(self.fake)

    async def _txn(self, fn):  # type: ignore[override]
        txn = self.fake.transaction()
        try:
            result = await fn(txn)
            txn.commit()
            return result
        finally:
            txn.release()
