"""SIB_OUTBOX over the API: the decision (14) and the record (6) carry `delivery`, the retry route
POST /admin/outbox/retry takes only its bearer token, and against the real permit-to-work stub a
delivery survives the stub being down and a lost answer, with one permit and no duplicate."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from sayitback.outbox import Outbox
from tests.flow_support import round_1_scenario
from tests.helpers import api_client, drive_to_round, make_app
from tests.test_outbox import Clock, Receiver

STUB = Path(__file__).resolve().parents[2] / "integrations" / "ptw-stub"
URL = "http://ptw.internal/webhook?key=STUBKEY77"
SECRET = "outbox-contract-secret"
RETRY_TOKEN = "retry-bearer-5e4d3c2b1a"
AUTH = {"Authorization": f"Bearer {RETRY_TOKEN}"}


def build(settings, transport, clock=None, **overrides):
    on = {"outbox": True, "webhook_url": URL, "webhook_secret": SECRET, "outbox_token": RETRY_TOKEN}
    s = settings.with_overrides(**{**on, **overrides})
    app, *_ = make_app(s, round_1_scenario(), webhook_transport=transport)
    ctx = app.state.ctx
    if clock is not None and ctx.outbox is not None:
        ctx.outbox = Outbox(ctx.repo.store, ctx.webhook, s, clock=clock)
    return app, api_client(app)


def decide(client):
    bid, _ = drive_to_round(client)
    response = client.post(f"/api/briefings/{bid}/decision", json={"value": "no_go", "by": "A"})
    assert response.status_code == 200, response.text
    return bid, response.json()


class TestTheRecordShowsTheDelivery:
    def test_the_decision_and_the_record_carry_it(self, settings):
        _, client = build(settings, httpx.MockTransport(Receiver()))
        bid, decided = decide(client)
        assert decided["delivery"]["status"] == "delivered"
        assert client.get(f"/api/briefings/{bid}").json()["delivery"] == decided["delivery"]
        shown = client.get(f"/api/briefings/{bid}").text + str(decided)
        for hidden in ("STUBKEY77", "ptw.internal", SECRET, RETRY_TOKEN, "sib-b_"):
            assert hidden not in shown

    def test_retrying_shows_as_pending(self, settings):
        _, client = build(settings, httpx.MockTransport(Receiver(503)))
        _, decided = decide(client)
        (target,) = decided["delivery"]["targets"]
        assert decided["delivery"]["status"] == "pending" and target["lastError"] == "http_503"

    def test_before_a_decision_it_is_null(self, settings):
        _, client = build(settings, httpx.MockTransport(Receiver()))
        bid, _ = drive_to_round(client)
        assert client.get(f"/api/briefings/{bid}").json()["delivery"] is None

    def test_off_by_default_nothing_changes(self, settings):
        receiver = Receiver()
        s = settings.with_overrides(webhook_url=URL, webhook_secret=SECRET)
        app, *_ = make_app(s, round_1_scenario(), webhook_transport=httpx.MockTransport(receiver))
        client = api_client(app)
        bid, decided = decide(client)
        assert "delivery" not in decided and "delivery" not in client.get(f"/api/briefings/{bid}").json()
        assert len(receiver.requests) == 1 and app.state.ctx.outbox is None


class TestTheRetryRoute:
    def test_it_takes_its_bearer_token_and_no_device_key(self, settings):
        app, _ = build(settings, httpx.MockTransport(Receiver()))
        bare = TestClient(app)  # no X-SIB-Device: a machine calls it
        assert bare.post("/admin/outbox/retry").status_code == 401
        wrong = bare.post("/admin/outbox/retry", headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "unauthorized"
        ok = bare.post("/admin/outbox/retry", headers=AUTH)
        assert ok.json() == {"checked": 0, "delivered": 0, "pending": 0, "failed": 0}

    @pytest.mark.parametrize("overrides", [{"outbox_token": ""}, {"outbox": False}])
    def test_without_the_outbox_or_a_token_it_does_not_exist(self, settings, overrides):
        app, _ = build(settings, httpx.MockTransport(Receiver()), **overrides)
        assert TestClient(app).post("/admin/outbox/retry", headers=AUTH).status_code == 404

    def test_a_pass_retries_what_is_due(self, settings):
        clock, receiver = Clock(), Receiver(503)
        app, client = build(settings, httpx.MockTransport(receiver), clock=clock)
        bid, _ = decide(client)
        clock.advance(30)
        summary = TestClient(app).post("/admin/outbox/retry", headers=AUTH).json()
        assert summary == {"checked": 1, "delivered": 1, "pending": 0, "failed": 0}
        assert client.get(f"/api/briefings/{bid}").json()["delivery"]["status"] == "delivered"
        assert len(receiver.requests) == 2

    def test_the_token_never_reaches_a_log_line(self, settings, caplog):
        app, _ = build(settings, httpx.MockTransport(Receiver()))
        with caplog.at_level("DEBUG"):
            TestClient(app).post("/admin/outbox/retry", headers={"Authorization": "Bearer guess"})
            TestClient(app).post("/admin/outbox/retry", headers=AUTH)
        assert RETRY_TOKEN not in caplog.text and "guess" not in caplog.text


class Flaky(httpx.AsyncBaseTransport):
    """The network to the stub: `down` answers 503 without reaching it; `lost` reaches it, then
    loses its answer (the stub took the permit, the backend saw a timeout)."""

    def __init__(self, inner: httpx.AsyncBaseTransport, *plan: str) -> None:
        self.inner, self.plan = inner, list(plan)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        step = self.plan.pop(0) if self.plan else "ok"
        if step == "down":
            return httpx.Response(503)
        response = await self.inner.handle_async_request(request)
        if step == "lost":
            await response.aread()
            raise httpx.ReadTimeout("the answer was lost", request=request)
        return response


@pytest.fixture
def stub():
    if not (STUB / "ptw_stub").is_dir():
        pytest.skip("needs integrations/ptw-stub")
    sys.path.insert(0, str(STUB))
    try:
        from ptw_stub.app import create_app

        yield create_app(secret=SECRET)
    finally:
        sys.path.remove(str(STUB))


class TestAgainstThePermitStub:
    def test_a_stub_that_was_down_gets_its_permit_once(self, settings, stub):
        clock = Clock()
        app, client = build(settings, Flaky(httpx.ASGITransport(app=stub), "down"), clock=clock)
        bid, decided = decide(client)
        assert decided["delivery"]["status"] == "pending"
        board = TestClient(stub)
        assert board.get("/api/permits").json() == {"permits": []}
        clock.advance(30)
        TestClient(app).post("/admin/outbox/retry", headers=AUTH)
        (permit,) = board.get("/api/permits").json()["permits"]
        assert permit["briefingId"] == bid and permit["status"] == "held"
        assert client.get(f"/api/briefings/{bid}").json()["delivery"]["status"] == "delivered"

    def test_a_lost_answer_is_retried_and_the_stub_answers_duplicate(self, settings, stub):
        clock = Clock()
        app, client = build(settings, Flaky(httpx.ASGITransport(app=stub), "lost"), clock=clock)
        bid, decided = decide(client)
        assert decided["delivery"]["targets"][0]["lastError"] == "ReadTimeout"
        clock.advance(30)
        TestClient(app).post("/admin/outbox/retry", headers=AUTH)
        delivery = client.get(f"/api/briefings/{bid}").json()["delivery"]
        assert delivery["status"] == "delivered" and delivery["targets"][0]["lastError"] == "duplicate"
        assert len(TestClient(stub).get("/api/permits").json()["permits"]) == 1
