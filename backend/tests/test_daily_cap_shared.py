"""The daily Gemini cap is one count for every instance of the service, and it holds under a burst.

`instances` is the local store twice (a restart) or a Firestore fake twice (two instances)."""

from __future__ import annotations

import asyncio

import pytest

from sayitback.store import LocalStore
from tests.cap_support import confirmed, make_capped, over_http, speak
from tests.fake_firestore import FakeBackedStore
from tests.flow_support import round_1_scenario
from tests.helpers import PANEL, error_of


@pytest.fixture(params=["local", "firestore"])
def instances(request, settings):
    """Two service instances (or one before and one after a restart) over one store."""
    if request.param == "local":
        return LocalStore(settings.data_dir), LocalStore(settings.data_dir)
    first = FakeBackedStore()
    return first, FakeBackedStore(first.fake)


class TestSharedByEveryInstance:
    def test_a_second_instance_sees_what_the_first_spent(self, settings, instances):
        first, second = (make_capped(settings, limit=1, store=s) for s in instances)
        assert speak(first, "a").status_code == 200
        assert error_of(speak(second, "b")) == (429, "daily_limit")
        assert second.tts.calls == []


class TestABurst:
    """Concurrent requests with slow model calls: a cap that checked first and counted after the
    call would let them all through."""

    async def test_a_burst_spends_exactly_the_cap_and_never_more(self, settings, instances):
        env = make_capped(settings, limit=4, store=instances[0])
        env.llm.delay = 0.05
        async with over_http(env) as http:
            ids = [(await http.post("/api/briefings", json=PANEL)).json()["id"] for _ in range(10)]
            replies = await asyncio.gather(
                *(http.post(f"/api/briefings/{i}/steps/extract") for i in ids)
            )
        assert sorted(r.status_code for r in replies) == [200] * 4 + [429] * 6
        assert len(env.llm.seen) == 4 and env.ledger.spent == 4

    async def test_a_burst_across_two_instances_spends_exactly_the_cap(self, settings, instances):
        envs = [make_capped(settings, limit=3, store=s) for s in instances]
        for env in envs:
            env.llm.delay = 0.05
        async with over_http(envs[0]) as one, over_http(envs[1]) as two:
            ids = [(await one.post("/api/briefings", json=PANEL)).json()["id"] for _ in range(8)]
            replies = await asyncio.gather(
                *(
                    (one, two)[n % 2].post(f"/api/briefings/{bid}/steps/extract")
                    for n, bid in enumerate(ids)
                )
            )
        assert sorted(r.status_code for r in replies) == [200] * 3 + [429] * 5
        assert sum(len(env.llm.seen) for env in envs) == 3

    async def test_two_requests_that_would_cross_the_cap_together_let_exactly_one_through(
        self, settings, instances
    ):
        env = make_capped(settings, round_1_scenario(), limit=5, store=instances[0])
        ids = [confirmed(env), confirmed(env)]  # two extracts: three of the five are left
        env.llm.delay = 0.05
        async with over_http(env) as http:
            replies = await asyncio.gather(
                *(http.post(f"/api/briefings/{i}/rounds", json={}) for i in ids)
            )
        assert sorted(r.status_code for r in replies) == [200, 429]
        assert env.ledger.spent == 4  # two extracts and one round: the other round took nothing
