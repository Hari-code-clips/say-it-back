"""SIB_OUTBOX (outbox.py): every delivery is stored before it is sent, retried with exponential
backoff, never posted twice at once, carries one Idempotency-Key on every try, and shows on the
record without a URL, a key or a token. Over the local store and the fake Firestore."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from sayitback.outbox import NOTHING_DUE, Outbox, backoff_s
from sayitback.store import LocalStore
from sayitback.store.base import iso
from sayitback.webhook import IDEMPOTENCY_HEADER, WebhookSender, idempotency_key
from tests.fake_firestore import FakeBackedStore
from tests.test_v04_webhooks import SECRET, with_hazards

URL = "https://ptw.example.com/webhook?key=STUBKEY77"
OTHER = "https://other.example.com/hook"
START = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Receiver:
    """Answers each post with the next scripted status (or raises it), then 200."""

    def __init__(self, *script, delay_s: float = 0.0) -> None:
        self.script, self.delay_s = list(script), delay_s
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        await asyncio.sleep(self.delay_s)
        step = self.script.pop(0) if self.script else 200
        if isinstance(step, Exception):
            raise step
        return httpx.Response(step, json={"error": {"code": "duplicate"}} if step == 409 else {})


@pytest.fixture(params=["local", "firestore"])
def store(request, tmp_path):
    return LocalStore(tmp_path / ".data") if request.param == "local" else FakeBackedStore()


@pytest.fixture
def clock():
    return Clock()


def make_outbox(store, settings, receiver, clock, urls=(URL,), **overrides):
    sender = WebhookSender(list(urls), 1.0, httpx.MockTransport(receiver), secret=SECRET)
    return Outbox(store, sender, settings.with_overrides(outbox=True, **overrides), clock=clock)


async def stored_briefing(store):
    b = with_hazards()
    await store.create({**b.stored(), "owner": "o" * 64})
    return b


class TestDelivery:
    async def test_a_delivered_post_is_recorded_without_its_url(self, store, settings, clock):
        receiver = Receiver()
        b = await stored_briefing(store)
        status = await make_outbox(store, settings, receiver, clock).deliver(b)
        assert status == {
            "status": "delivered",
            "targets": [{"kind": "permit", "status": "delivered", "attempts": 1,
                         "lastError": None, "nextAttemptAt": None, "deliveredAt": iso(START)}],
        }  # fmt: skip
        doc = await store.outbox_get(b.id)
        assert doc["due"] == NOTHING_DUE and doc["targets"][0]["key"] == idempotency_key(b)
        assert "STUBKEY77" not in json.dumps(doc) and "ptw.example.com" not in json.dumps(doc)

    async def test_a_busy_receiver_is_retried_with_backoff_and_one_key(
        self, store, settings, clock
    ):
        receiver = Receiver(503, 503, 200)
        outbox = make_outbox(store, settings, receiver, clock)
        b = await stored_briefing(store)
        first = (await outbox.deliver(b))["targets"][0]
        assert (first["status"], first["attempts"], first["lastError"]) == ("pending", 1, "http_503")
        assert first["nextAttemptAt"] == iso(START + timedelta(seconds=30))
        clock.advance(29)
        assert (await outbox.retry_due())["checked"] == 0 and len(receiver.requests) == 1
        clock.advance(1)
        assert await outbox.retry_due() == {"checked": 1, "delivered": 0, "pending": 1, "failed": 0}
        second = (await outbox.status(b.id))["targets"][0]
        assert second["attempts"] == 2 and second["nextAttemptAt"] == iso(clock.now + timedelta(seconds=60))
        clock.advance(60)
        assert (await outbox.retry_due())["delivered"] == 1
        assert (await outbox.status(b.id))["status"] == "delivered"
        assert {r.headers[IDEMPOTENCY_HEADER] for r in receiver.requests} == {idempotency_key(b)}
        assert len(receiver.requests) == 3

    async def test_it_gives_up_after_the_last_attempt(self, store, settings, clock):
        receiver = Receiver(*[503] * 10)
        outbox = make_outbox(store, settings, receiver, clock, outbox_max_attempts=3)
        b = await stored_briefing(store)
        await outbox.deliver(b)
        for _ in range(5):
            clock.advance(3600)
            await outbox.retry_due()
        target = (await outbox.status(b.id))["targets"][0]
        assert (target["status"], target["attempts"], target["lastError"]) == ("failed", 3, "http_503")
        assert len(receiver.requests) == 3 and (await store.outbox_get(b.id))["due"] == NOTHING_DUE

    @pytest.mark.parametrize("status", [400, 401, 404, 422])
    async def test_a_refusal_fails_at_once_and_is_never_retried(self, store, settings, clock, status):
        receiver = Receiver(status)
        outbox = make_outbox(store, settings, receiver, clock)
        b = await stored_briefing(store)
        assert (await outbox.deliver(b))["status"] == "failed"
        clock.advance(86_400)
        assert (await outbox.retry_due())["checked"] == 0 and len(receiver.requests) == 1

    async def test_a_duplicate_answer_counts_as_delivered(self, store, settings, clock):
        b = await stored_briefing(store)
        status = await make_outbox(store, settings, Receiver(409), clock).deliver(b)
        assert status["status"] == "delivered" and status["targets"][0]["lastError"] == "duplicate"

    @pytest.mark.parametrize("error", [httpx.ConnectError("x"), httpx.ReadTimeout("x")])
    async def test_no_answer_is_retried(self, store, settings, clock, error):
        b = await stored_briefing(store)
        status = await make_outbox(store, settings, Receiver(error), clock).deliver(b)
        target = status["targets"][0]
        assert (target["status"], target["lastError"]) == ("pending", type(error).__name__)

    async def test_a_hanging_receiver_is_cut_off_at_the_timeout(self, store, settings, clock):
        receiver = Receiver(delay_s=5)
        outbox = make_outbox(store, settings, receiver, clock, webhook_timeout_s=0.05)
        outbox.sender.timeout_s = 0.05
        b = await stored_briefing(store)
        target = (await asyncio.wait_for(outbox.deliver(b), 2))["targets"][0]
        assert (target["status"], target["lastError"]) == ("pending", "timeout")

    def test_the_backoff_doubles_up_to_its_ceiling(self):
        assert [backoff_s(n, 30, 3600) for n in (1, 2, 3, 7, 8, 20)] == [
            30, 60, 120, 1920, 3600, 3600
        ]  # fmt: skip


class TestNeverTwiceByAccident:
    async def test_a_second_decision_post_keeps_the_first_deliveries(self, store, settings, clock):
        receiver = Receiver()
        outbox = make_outbox(store, settings, receiver, clock)
        b = await stored_briefing(store)
        await outbox.deliver(b)
        again = await outbox.deliver(b)
        assert again["status"] == "delivered" and len(receiver.requests) == 1

    async def test_two_passes_at_once_post_a_target_once(self, store, settings, clock):
        receiver = Receiver(503, 200, 200, delay_s=0.02)
        outbox = make_outbox(store, settings, receiver, clock)
        b = await stored_briefing(store)
        await outbox.deliver(b)
        clock.advance(30)
        await asyncio.gather(outbox.retry_due(), outbox.retry_due(), outbox.retry_due())
        assert len(receiver.requests) == 2
        assert (await outbox.status(b.id))["targets"][0]["attempts"] == 2

    async def test_every_target_is_tracked_on_its_own(self, store, settings, clock):
        receiver = Receiver(200, 503)
        outbox = make_outbox(store, settings, receiver, clock, urls=(URL, OTHER))
        b = await stored_briefing(store)
        status = await outbox.deliver(b)
        assert status["status"] == "pending"
        assert sorted(t["status"] for t in status["targets"]) == ["delivered", "pending"]
        clock.advance(30)
        await outbox.retry_due()
        assert len(receiver.requests) == 3 and (await outbox.status(b.id))["status"] == "delivered"


class TestWhatCannotBeDelivered:
    async def test_a_target_no_longer_configured_fails(self, store, settings, clock):
        b = await stored_briefing(store)
        await make_outbox(store, settings, Receiver(503), clock).deliver(b)
        moved = make_outbox(store, settings, Receiver(), clock, urls=(OTHER,))
        clock.advance(30)
        await moved.retry_due()
        target = (await moved.status(b.id))["targets"][0]
        assert (target["status"], target["lastError"]) == ("failed", "target_removed")

    async def test_a_briefing_no_longer_stored_fails(self, store, settings, clock):
        b = with_hazards()  # posted from the decision, but not in the store (retention removed it)
        receiver = Receiver(503)
        outbox = make_outbox(store, settings, receiver, clock)
        await outbox.deliver(b)
        clock.advance(30)
        await outbox.retry_due()
        target = (await outbox.status(b.id))["targets"][0]
        assert (target["status"], target["lastError"]) == ("failed", "briefing_gone")
        assert len(receiver.requests) == 1

    async def test_with_the_store_down_it_posts_directly(self, settings, clock, tmp_path):
        class Down(LocalStore):
            async def outbox_update(self, briefing_id, fn):
                raise ConnectionError("store down")

        receiver = Receiver()
        outbox = make_outbox(Down(tmp_path), settings, receiver, clock)
        assert await outbox.deliver(with_hazards()) is None and len(receiver.requests) == 1

    async def test_without_a_target_or_a_decision_nothing_is_stored(self, store, settings, clock):
        b = await stored_briefing(store)
        assert await make_outbox(store, settings, Receiver(), clock, urls=()).deliver(b) is None
        undecided = b.model_copy(update={"decision": None})
        assert await make_outbox(store, settings, Receiver(), clock).deliver(undecided) is None
        assert await store.outbox_get(b.id) is None
