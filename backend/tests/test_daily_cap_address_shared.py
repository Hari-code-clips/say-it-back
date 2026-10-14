"""The per-address allowance and the shared cap are one transaction over two documents.

`FakeFirestore` yields on every read and locks a document from its first transactional read to the
commit, as the real server library does. So a reservation that reads both counts and then writes
them without a transaction oversells (shown first, on the fake), and one made of two transactions
charges a request the other count then refuses (shown second). The store's single transaction does
neither, under a burst, across instances and with the counts all agreeing at the end.
"""

from __future__ import annotations

import asyncio
import random

import pytest

from sayitback.daily_cap import address_key
from sayitback.store import LocalStore
from sayitback.store.base import Reserved
from sayitback.store.firestore_store import ADDRESS_CALLS, CALLS
from tests.cap_support import TODAY, make_capped, over_http
from tests.fake_firestore import FakeBackedStore, FakeFirestore
from tests.fakes import tone_wav

DAY = TODAY
A, B, C = (address_key(DAY, f"203.0.113.{n}") for n in (7, 8, 9))


def count(db: FakeFirestore, collection: str, name: str) -> int:
    return db.docs.get((collection, name), {}).get("calls", 0)


async def naive_reserve(db, address, calls, cap, address_cap) -> bool:
    """Both counts read, then both written, with no transaction: what the fake must break."""
    shared = db.collection(CALLS).document(DAY)
    mine = db.collection(ADDRESS_CALLS).document(address)
    used = ((await shared.get()).to_dict() or {}).get("calls", 0)
    mine_used = ((await mine.get()).to_dict() or {}).get("calls", 0)
    if used + calls > cap or mine_used + calls > address_cap:
        return False
    await shared.set({"calls": used + calls})
    await mine.set({"calls": mine_used + calls})
    return True


async def two_step_reserve(store, address, calls, cap, address_cap) -> bool:
    """The address's count in one transaction, the shared count in another: not atomic together."""
    if not await store.reserve_calls(DAY, calls, 10**9, address=address, address_cap=address_cap):
        return False
    return bool(await store.reserve_calls(DAY, calls, cap))


class TestTheFakeBreaksWhatIsNotOneTransaction:
    async def test_a_read_then_write_over_two_documents_oversells_both(self):
        """If this stopped overselling, every concurrency test below would pass for anything."""
        db = FakeFirestore()
        both = await asyncio.gather(
            *(naive_reserve(db, A, 2, cap=3, address_cap=3) for _ in range(2))
        )
        assert both == [True, True]  # four calls granted against a cap of three, on both counts

    async def test_two_transactions_charge_a_request_that_the_second_one_refuses(self):
        store = FakeBackedStore()
        await store.reserve_calls(DAY, 4, 4, address=B, address_cap=100)  # the shared cap is full
        assert await two_step_reserve(store, A, 1, cap=4, address_cap=100) is False
        assert count(store.fake, ADDRESS_CALLS, A) == 1  # refused, yet charged to A

    async def test_the_real_reservation_charges_a_refused_request_nothing(self):
        store = FakeBackedStore()
        await store.reserve_calls(DAY, 4, 4, address=B, address_cap=100)
        assert not await store.reserve_calls(DAY, 1, 4, address=A, address_cap=100)
        assert (ADDRESS_CALLS, A) not in store.fake.docs  # not even an empty document

    async def test_nor_does_a_refusal_by_the_address_move_the_shared_count(self):
        store = FakeBackedStore()
        await store.reserve_calls(DAY, 2, 100, address=A, address_cap=2)
        assert not await store.reserve_calls(DAY, 1, 100, address=A, address_cap=2)
        assert count(store.fake, CALLS, DAY) == 2 and count(store.fake, ADDRESS_CALLS, A) == 2


class TestABurst:
    async def test_one_address_across_two_instances_spends_exactly_its_allowance(self):
        first = FakeBackedStore()
        second = FakeBackedStore(first.fake)
        results = await asyncio.gather(
            *(s.reserve_calls(DAY, 2, 1000, address=A, address_cap=7) for s in [first, second] * 10)
        )
        assert sum(map(bool, results)) == 3  # 7 // 2
        assert count(first.fake, ADDRESS_CALLS, A) == 6 and count(first.fake, CALLS, DAY) == 6
        assert all(r in (Reserved.GRANTED, Reserved.ADDRESS_FULL) for r in results)

    async def test_many_addresses_spend_exactly_the_shared_cap_and_never_more(self):
        first = FakeBackedStore()
        second = FakeBackedStore(first.fake)
        addresses = [address_key(DAY, f"198.51.100.{n}") for n in range(12)]
        jobs = [
            [first, second][i % 2].reserve_calls(DAY, 1, 10, address=a, address_cap=100)
            for i in range(3)
            for a in addresses
        ]
        results = await asyncio.gather(*jobs)
        assert sum(map(bool, results)) == 10
        assert count(first.fake, CALLS, DAY) == 10
        spent = [count(first.fake, ADDRESS_CALLS, a) for a in addresses]
        assert sum(spent) == 10  # every granted call is on exactly one address

    async def test_a_mixed_load_keeps_every_count_in_agreement(self):
        rng = random.Random(7)
        first = FakeBackedStore()
        second = FakeBackedStore(first.fake)
        addresses = [address_key(DAY, f"192.0.2.{n}") for n in range(5)]
        asked = [(rng.choice(addresses), rng.choice([1, 2, 3])) for _ in range(80)]
        results = await asyncio.gather(
            *(
                [first, second][i % 2].reserve_calls(DAY, c, 25, address=a, address_cap=8)
                for i, (a, c) in enumerate(asked)
            )
        )
        granted = [(a, c) for (a, c), r in zip(asked, results, strict=True) if r]
        total = sum(c for _, c in granted)
        assert total == count(first.fake, CALLS, DAY) <= 25
        for a in addresses:
            mine = sum(c for who, c in granted if who == a)
            assert mine == count(first.fake, ADDRESS_CALLS, a) <= 8
        assert sum(count(first.fake, ADDRESS_CALLS, a) for a in addresses) == total

    async def test_a_client_over_its_allowance_never_waits_on_the_shared_document(self):
        """Review S8: every caller contends on one document. A refused client must not join in."""
        store = FakeBackedStore()
        assert await store.reserve_calls(DAY, 1, 100, address=A, address_cap=1)
        lock = store.fake.locks.setdefault((CALLS, DAY), asyncio.Lock())
        await lock.acquire()  # somebody holds the shared document
        try:
            over = store.reserve_calls(DAY, 1, 100, address=A, address_cap=1)
            assert await asyncio.wait_for(over, 1) is Reserved.ADDRESS_FULL  # answered at once
            fresh = store.reserve_calls(DAY, 1, 100, address=B, address_cap=1)
            with pytest.raises(TimeoutError):  # a client with room does have to wait its turn
                await asyncio.wait_for(fresh, 0.2)
        finally:
            lock.release()


class TestThroughTheApi:
    @pytest.fixture(params=["local", "firestore"])
    def instances(self, request, settings):
        if request.param == "local":
            return LocalStore(settings.data_dir), LocalStore(settings.data_dir)
        first = FakeBackedStore()
        return first, FakeBackedStore(first.fake)

    async def test_a_burst_from_one_address_across_two_instances_stays_within_its_allowance(
        self, settings, instances
    ):
        envs = [make_capped(settings, limit=100, store=s, daily_calls_per_ip=4) for s in instances]
        audio = {"audio": ("a.wav", tone_wav(), "audio/wav")}
        async with over_http(envs[0], peer="203.0.113.7") as one:  # the same address on both
            async with over_http(envs[1], peer="203.0.113.7") as two:
                posts = [
                    (one, two)[n % 2].post("/api/transcribe", files=audio, data={"lang": "en"})
                    for n in range(12)
                ]
                replies = await asyncio.gather(*posts)
        assert sorted(r.status_code for r in replies) == [200] * 4 + [429] * 8
        assert sum(len(e.llm.seen) for e in envs) == 4
