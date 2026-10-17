"""Security fixes B, L1 (build-notes/36-security-fixes-b.md): a retry that finds another upload's
check still running polls the store with backoff, 0.25 s doubling to 2 s, not every 250 ms for
the whole request budget. Over the 120 s production budget that is 64 claim reads, not 481."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from sayitback.errors import InvalidState
from sayitback.idempotency import POLL_MAX_S, POLL_S, idempotent_check, key_digest
from sayitback.store import LocalStore
from sayitback.store.base import iso
from tests.fake_firestore import FakeBackedStore
from tests.helpers import CALLER, seed_round
from tests.test_idempotency import KEY, fake_request

BUDGET_S = 120.0  # the production SIB_REQUEST_TIMEOUT_S


class FakeTime:
    """The wait's clock and sleep: a sleep moves the clock at once and is written down."""

    def __init__(self) -> None:
        self.now, self.waits = 0.0, []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


def held_forever(store, bid: str) -> list[int]:
    """Another upload's pending claim that outlives the test; returns the list the claims count."""
    later = iso(datetime.now(UTC) + timedelta(hours=1))
    pending = {"state": "pending", "expiresAt": later}
    asyncio.run(store.set_check_key(key_digest(CALLER.owner, bid, 1, KEY), pending))
    claims, real = [], store.claim_check_key

    async def counted(*args, **kwargs):
        claims.append(1)
        return await real(*args, **kwargs)

    store.claim_check_key = counted
    return claims


async def never_run():
    raise AssertionError("the waiting retry must not run the check")


@pytest.mark.parametrize("make_store", [LocalStore, None], ids=["local", "firestore"])
def test_a_wait_over_the_whole_budget_makes_64_claims_not_481(make_store, settings):
    store = make_store(settings.data_dir) if make_store else FakeBackedStore()
    bid = seed_round(store)
    claims = held_forever(store, bid)
    time = FakeTime()
    request = fake_request(store, settings.with_overrides(request_timeout_s=BUDGET_S))

    with pytest.raises(InvalidState) as refused:
        asyncio.run(
            idempotent_check(request, bid, 1, CALLER, never_run, sleep=time.sleep, clock=time.clock)
        )

    assert refused.value.code == "check_in_progress"
    assert len(claims) <= 64
    assert time.waits[:5] == [0.25, 0.5, 1.0, 2.0, 2.0]
    assert max(time.waits) == POLL_MAX_S and time.waits[0] == POLL_S
    assert sum(time.waits) == pytest.approx(BUDGET_S)  # it gives up at the budget, not after


def test_the_wait_still_returns_the_first_uploads_round_as_soon_as_it_is_seen(settings):
    """Backoff only spaces the reads: a done claim is answered at the next one."""
    store = LocalStore(settings.data_dir)
    bid = seed_round(store)
    held_forever(store, bid)
    time = FakeTime()
    digest = key_digest(CALLER.owner, bid, 1, KEY)

    async def finish_during_the_third_wait(seconds: float) -> None:
        await time.sleep(seconds)
        if len(time.waits) == 3:  # the first upload judges its round and marks its claim done
            await store.update(bid, judged)
            done = {"state": "done", "expiresAt": iso(datetime.now(UTC) + timedelta(hours=1))}
            await store.set_check_key(digest, done)

    def judged(raw: dict) -> dict:
        raw["rounds"][0]["judgedAt"], raw["status"] = "2026-10-16T12:00:00.000Z", "judged"
        return raw

    request = fake_request(store, settings.with_overrides(request_timeout_s=BUDGET_S))
    found = asyncio.run(
        idempotent_check(
            request, bid, 1, CALLER, never_run, sleep=finish_during_the_third_wait, clock=time.clock
        )
    )

    assert found.judged_at == "2026-10-16T12:00:00.000Z"
    assert time.waits == [0.25, 0.5, 1.0]
