"""The store contract, run against the local JSON store and the Firestore store (over a fake)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from sayitback.settings import Settings
from sayitback.store import LocalStore, make_store
from sayitback.store.firestore_store import FirestoreStore
from tests.fake_firestore import FakeBackedStore, FakeFirestore

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
DIGEST = "a" * 64
OTHER = "b" * 64
DAY = "20261014"
OWNER = "1" * 64  # the SHA-256 of a device key, as a briefing stores it


def briefing(n: int, owner: str = OWNER) -> dict:
    return {
        "id": f"b_{'abcdefghijklmnopqrstuvwxyz'[n : n + 12]}",
        "createdAt": f"2026-10-14T10:0{n}:00.000Z",
        "status": "draft",
        "rounds": [],
        "owner": owner,
    }


@pytest.fixture(params=["local", "firestore"])
def store(request, tmp_path):
    return LocalStore(tmp_path / ".data") if request.param == "local" else FakeBackedStore()


@pytest.fixture(params=["local", "firestore"])
def instances(request, tmp_path):
    """Two service instances (or one before and one after a restart) over the same storage."""
    if request.param == "local":
        return LocalStore(tmp_path / ".data"), LocalStore(tmp_path / ".data")
    first = FakeBackedStore()
    return first, FakeBackedStore(first.fake)


async def test_create_and_get_round_trip(store):
    b = briefing(1)
    await store.create(b)
    assert await store.get(b["id"]) == b
    assert await store.get("b_zzzzzzzzzzzz") is None


async def test_recent_is_newest_first_and_limited(store):
    for n in (1, 3, 2):
        await store.create(briefing(n))
    rows = await store.recent(2, OWNER)
    assert [r["createdAt"][14:16] for r in rows] == ["03", "02"]


async def test_recent_holds_only_the_owners_briefings(store):
    mine, theirs = "1" * 64, "2" * 64
    for n, owner in ((1, mine), (2, theirs), (3, mine), (4, theirs)):
        await store.create(briefing(n, owner))
    ownerless = briefing(5)
    del ownerless["owner"]
    await store.create(ownerless)  # made before device keys: nobody's

    assert [r["createdAt"][14:16] for r in await store.recent(10, mine)] == ["03", "01"]
    assert [r["createdAt"][14:16] for r in await store.recent(10, theirs)] == ["04", "02"]
    assert [r["createdAt"][14:16] for r in await store.recent(1, theirs)] == ["04"]  # then limited
    assert await store.recent(10, "3" * 64) == []
    assert await store.recent(10, "") == []  # no owner is no one, not "every ownerless record"


async def test_update_is_a_read_modify_write(store):
    b = briefing(1)
    await store.create(b)
    updated = await store.update(b["id"], lambda cur: {**cur, "status": "steps_proposed"})
    assert updated["status"] == "steps_proposed"
    assert (await store.get(b["id"]))["status"] == "steps_proposed"


async def test_update_gets_a_copy_and_an_aborted_update_writes_nothing(store):
    b = briefing(1)
    await store.create(b)

    def mutate_then_fail(cur):
        cur["status"] = "decided"
        raise RuntimeError("abort")

    with pytest.raises(RuntimeError):
        await store.update(b["id"], mutate_then_fail)
    assert (await store.get(b["id"]))["status"] == "draft"


async def test_update_of_a_missing_briefing_is_a_key_error(store):
    with pytest.raises(KeyError):
        await store.update("b_zzzzzzzzzzzz", lambda cur: cur)


async def test_a_ticket_redeems_once_and_only_before_it_expires(store):
    record = {"briefingId": "b_x", "n": 1, "expiresAt": "2026-10-14T10:02:00.000Z"}
    assert await store.issue_ticket(DIGEST, record, key="b_x.1", max_per_round=2)
    assert await store.redeem_ticket(DIGEST, NOW + timedelta(seconds=10)) is not None
    assert await store.redeem_ticket(DIGEST, NOW + timedelta(seconds=11)) is None
    assert await store.issue_ticket(OTHER, record, key="b_x.1", max_per_round=2)
    assert await store.redeem_ticket(OTHER, NOW + timedelta(seconds=300)) is None  # expired


async def test_unknown_digests_are_refused(store):
    assert await store.redeem_ticket("c" * 64, NOW) is None


async def test_the_ticket_allowance_is_per_round(store):
    record = {"briefingId": "b_x", "n": 1, "expiresAt": "2026-10-14T10:02:00.000Z"}
    assert await store.issue_ticket("1" * 64, record, key="b_x.1", max_per_round=2)
    assert await store.issue_ticket("2" * 64, record, key="b_x.1", max_per_round=2)
    assert not await store.issue_ticket("3" * 64, record, key="b_x.1", max_per_round=2)
    assert await store.issue_ticket("4" * 64, record, key="b_x.2", max_per_round=2)


async def test_one_live_socket_per_round(store):
    assert await store.acquire_live("b_x.1", "owner-a", NOW, 660)
    assert not await store.acquire_live("b_x.1", "owner-b", NOW + timedelta(seconds=5), 660)
    assert await store.acquire_live(
        "b_x.1", "owner-a", NOW + timedelta(seconds=5), 660
    )  # re-entrant
    await store.release_live("b_x.1", "owner-b")  # not the holder: no effect
    assert not await store.acquire_live("b_x.1", "owner-b", NOW + timedelta(seconds=6), 660)
    await store.release_live("b_x.1", "owner-a")
    assert await store.acquire_live("b_x.1", "owner-b", NOW + timedelta(seconds=7), 660)


async def test_a_crashed_holders_lease_expires(store):
    assert await store.acquire_live("b_x.1", "owner-a", NOW, 60)
    assert not await store.acquire_live("b_x.1", "owner-b", NOW + timedelta(seconds=59), 60)
    assert await store.acquire_live("b_x.1", "owner-b", NOW + timedelta(seconds=61), 60)


async def test_reservations_fill_the_day_and_nothing_partial_is_counted(store):
    assert await store.reserve_calls(DAY, 3, cap=5)
    assert not await store.reserve_calls(DAY, 3, cap=5)  # 6 would pass the cap: nothing is added
    assert await store.reserve_calls(DAY, 2, cap=5)  # so 2 still fit
    assert not await store.reserve_calls(DAY, 1, cap=5)


async def test_each_utc_day_has_its_own_count(store):
    assert await store.reserve_calls("20261014", 5, cap=5)
    assert not await store.reserve_calls("20261014", 1, cap=5)
    assert await store.reserve_calls("20261015", 5, cap=5)


async def test_a_cap_of_zero_refuses_every_reservation(store):
    assert not await store.reserve_calls(DAY, 1, cap=0)


async def test_the_count_is_shared_by_every_instance_and_survives_a_restart(instances):
    first, second = instances
    assert await first.reserve_calls(DAY, 4, cap=5)
    assert not await second.reserve_calls(DAY, 2, cap=5)
    assert await second.reserve_calls(DAY, 1, cap=5)
    assert not await first.reserve_calls(DAY, 1, cap=5)


async def test_two_concurrent_reservations_that_would_cross_the_cap_let_exactly_one_through(store):
    results = await asyncio.gather(*(store.reserve_calls(DAY, 2, cap=3) for _ in range(2)))
    assert sorted(map(bool, results)) == [False, True]


async def test_a_burst_across_instances_spends_exactly_the_cap_and_never_more(instances):
    first, second = instances
    burst = [first, second] * 6
    results = await asyncio.gather(*(s.reserve_calls(DAY, 2, cap=7) for s in burst))
    assert sum(map(bool, results)) == 3  # 7 // 2, whichever instance won each one
    assert await first.reserve_calls(DAY, 1, cap=7)  # one unit was left over, and only one
    assert not await second.reserve_calls(DAY, 1, cap=7)


async def test_local_reservations_are_safe_across_threads_too(tmp_path):
    store = LocalStore(tmp_path / ".data")

    def reserve() -> bool:
        return bool(asyncio.run(store.reserve_calls(DAY, 1, cap=20)))

    results = await asyncio.gather(*(asyncio.to_thread(reserve) for _ in range(60)))
    assert results.count(True) == 20


async def test_the_fake_interleaves_reads_so_a_read_then_write_without_a_transaction_oversells():
    """Keeps the fake honest: if it stopped yielding on a read, the concurrency tests above would
    pass for any implementation, transactional or not."""
    ref = FakeFirestore().collection("gemini_calls").document(DAY)

    async def naive(calls: int, cap: int) -> bool:
        used = ((await ref.get()).to_dict() or {}).get("calls", 0)
        if used + calls > cap:
            return False
        await ref.set({"calls": used + calls})
        return True

    assert await asyncio.gather(naive(2, 3), naive(2, 3)) == [True, True]  # 4 spent against 3


async def test_the_daily_count_is_one_document_per_utc_day_in_firestore():
    store = FakeBackedStore()
    await store.reserve_calls(DAY, 2, cap=5)
    await store.reserve_calls("20261015", 1, cap=5)
    assert store.fake.docs[("gemini_calls", DAY)] == {"calls": 2}
    assert store.fake.docs[("gemini_calls", "20261015")] == {"calls": 1}


async def test_firestore_documents_hold_only_the_digest_never_a_ticket(tmp_path):
    store = FakeBackedStore()
    record = {"briefingId": "b_x", "n": 1, "expiresAt": "2026-10-14T10:02:00.000Z"}
    await store.issue_ticket(DIGEST, record, key="b_x.1", max_per_round=2)
    assert ("live_tickets", DIGEST) in store.fake.docs
    assert ("live_counters", "b_x.1") in store.fake.docs
    assert all("ticket" not in doc for doc in store.fake.docs.values())


async def test_local_store_rejects_path_tricks(tmp_path):
    store = LocalStore(tmp_path / ".data")
    assert await store.get("../../etc/passwd") is None
    assert await store.get("b_ABCDEFGHIJKL") is None
    with pytest.raises(KeyError):
        await store.update("../x", lambda cur: cur)
    assert await store.redeem_ticket("../../x", NOW) is None
    with pytest.raises(ValueError):
        await store.issue_ticket("../../x", {}, key="k", max_per_round=1)


def test_the_factory_picks_the_store_from_settings(tmp_path, monkeypatch):
    assert isinstance(make_store(Settings(data_dir=tmp_path)), LocalStore)
    sentinel = FakeBackedStore()
    monkeypatch.setattr(FirestoreStore, "from_env", classmethod(lambda cls: sentinel))
    assert make_store(Settings(store="firestore")) is sentinel
