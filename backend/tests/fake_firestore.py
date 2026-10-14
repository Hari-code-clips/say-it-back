"""An in-memory stand-in for google.cloud.firestore.AsyncClient, just enough for FirestoreStore.

Transactions behave as in Firestore's server client libraries: a document read inside a
transaction is locked until the transaction ends, writes are buffered and applied together at the
commit, and an error discards them. Reads outside a transaction are not blocked. Every read yields
to the event loop, as a network round trip would, so concurrent requests really interleave: a
read-then-write without a transaction oversells (see test_store.py), one inside it does not.

The real `firestore.async_transactional` decorator is not exercised here (it needs a backend);
the store's logic (keys, counters, single-use, leases, ordering, the daily call count) is.
"""

from __future__ import annotations

import asyncio
from copy import copy, deepcopy
from dataclasses import dataclass
from typing import Any

from sayitback.store.firestore_store import FirestoreStore

Key = tuple[str, str]


@dataclass(frozen=True)
class QueryShape:
    """What a composite index must cover: the collection, its equality-filtered fields, the order."""

    collection: str
    equals: tuple[tuple[str, str], ...]  # (field, operator)
    order: tuple[str, str] | None  # (field, direction)


class Snapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._data)


class DocRef:
    def __init__(self, db: FakeFirestore, collection: str, name: str) -> None:
        self.db, self.collection, self.name = db, collection, name
        self.key: Key = (collection, name)

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
        self._writes: list[tuple[Key, dict[str, Any] | None]] = []

    async def lock(self, key: Key) -> None:
        if key not in self._held:
            lock = self.db.locks.setdefault(key, asyncio.Lock())
            await lock.acquire()
            self._held[key] = lock

    def set(self, ref: DocRef, data: dict[str, Any]) -> None:
        self._writes.append((ref.key, deepcopy(data)))

    def delete(self, ref: DocRef) -> None:
        self._writes.append((ref.key, None))

    def commit(self) -> None:
        for key, data in self._writes:
            if data is None:
                self.db.docs.pop(key, None)
            else:
                self.db.docs[key] = data
        self._writes.clear()

    def release(self) -> None:
        for lock in self._held.values():
            lock.release()
        self._held.clear()


class Query:
    """A query builder like the real one: each step returns a new query. `where` takes only the
    `filter=` form (the positional one is deprecated in the client). Every stream is recorded in
    `db.queries` as its shape (collection, equality-filtered fields, ordering), which is what a
    composite index has to cover."""

    def __init__(self, db: FakeFirestore, collection: str) -> None:
        self.db, self.collection = db, collection
        self._field, self._desc, self._limit = "", False, None
        self._filters: list[tuple[str, str, Any]] = []

    def _next(self, **changes: Any) -> Query:
        clone = copy(self)
        clone._filters = list(self._filters)
        for name, value in changes.items():
            setattr(clone, name, value)
        return clone

    def where(self, *, filter: Any) -> Query:  # noqa: A002 - the client's own keyword
        clone = self._next()
        clone._filters.append((filter.field_path, filter.op_string, filter.value))
        return clone

    def order_by(self, field: str, direction: str = "ASCENDING") -> Query:
        return self._next(_field=field, _desc=direction == "DESCENDING")

    def limit(self, n: int) -> Query:
        return self._next(_limit=n)

    async def stream(self):
        self.db.queries.append(
            QueryShape(
                self.collection,
                tuple((f, op) for f, op, _ in self._filters),
                (self._field, "DESCENDING" if self._desc else "ASCENDING") if self._field else None,
            )
        )
        rows = [v for (c, _), v in self.db.docs.items() if c == self.collection]
        for field, op, value in self._filters:
            assert op == "==", f"the fake supports equality filters only, not {op!r}"
            rows = [r for r in rows if r.get(field) == value]
        rows.sort(key=lambda d: d[self._field], reverse=self._desc)
        for row in rows[: self._limit]:
            yield Snapshot(row)


class Collection(Query):
    def document(self, name: str) -> DocRef:
        return DocRef(self.db, self.collection, name)


class FakeFirestore:
    def __init__(self) -> None:
        self.docs: dict[Key, dict[str, Any]] = {}
        self.locks: dict[Key, asyncio.Lock] = {}
        self.queries: list[QueryShape] = []

    def collection(self, name: str) -> Collection:
        return Collection(self, name)

    def transaction(self) -> Txn:
        return Txn(self)


class FakeBackedStore(FirestoreStore):
    """FirestoreStore whose transactions run directly against the fake. Stores built on the same
    `fake` are separate service instances over one database."""

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
