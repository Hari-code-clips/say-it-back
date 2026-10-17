"""API v0.5, "Webhooks": the decision endpoint awaits the webhooks inline, all URLs at once, within
SIB_WEBHOOK_TIMEOUT_S in all. Cloud Run may stop an instance's CPU once the response is sent, so a
post left to run after it might never leave. A webhook that hangs, fails or raises never fails the
decision, never changes the record, and is logged without its URL, a key or a client address."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from sayitback.caller import owner_hash
from sayitback.settings import ConfigError, Settings
from tests.flow_support import round_1_scenario
from tests.helpers import CALLER, DEVICE, api_client, drive_to_round, make_app

HANGING = "https://hangs.example.com/hook?key=HANGKEY123"
FAILING = "https://fails.example.com/hook?key=FAILKEY456"
WORKING = "https://works.example.com/hook?key=WORKKEY789"
TIMEOUT_S = 0.5


class ResponseWatch:
    """ASGI wrapper that knows whether the current request's response has started."""

    def __init__(self, app) -> None:
        self.app = app
        self.started = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        self.started = False

        async def watched(message):
            if message["type"] == "http.response.start":
                self.started = True
            await send(message)

        await self.app(scope, receive, watched)


class FakeWebhook:
    """Stands in for WebhookSender: records each call and whether the response had started."""

    enabled = True

    def __init__(self, watch: ResponseWatch, behaviour: str = "ok") -> None:
        self.watch = watch
        self.behaviour = behaviour
        self.calls: list[tuple[str, bool]] = []
        self.cancelled = False

    async def send(self, b) -> bool:
        self.calls.append((b.id, self.watch.started))
        if self.behaviour == "hang":
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if self.behaviour == "raise":
            raise RuntimeError(f"post to {FAILING} from {CALLER.address} failed")
        return True


def app_with(settings, behaviour: str):
    app, *_ = make_app(settings.with_overrides(webhook_timeout_s=TIMEOUT_S), round_1_scenario())
    watch = ResponseWatch(app)
    fake = FakeWebhook(watch, behaviour)
    app.state.ctx.webhook = fake
    client = api_client(watch)
    bid, _ = drive_to_round(client)
    return client, bid, fake


def decide(client, bid):
    started = time.monotonic()
    response = client.post(f"/api/briefings/{bid}/decision", json={"value": "no_go", "by": "A"})
    return response, time.monotonic() - started


def secrets_in(text: str) -> list[str]:
    banned = ("HANGKEY123", "FAILKEY456", "WORKKEY789", "hangs.example.com/hook",
              "fails.example.com/hook", DEVICE, owner_hash(DEVICE), CALLER.address)  # fmt: skip
    return [s for s in banned if s in text]


class TestTheDecisionAwaitsItsWebhooks:
    def test_the_webhook_has_been_called_before_the_response_is_sent(self, settings):
        client, bid, fake = app_with(settings, "ok")
        response, _ = decide(client, bid)
        assert response.status_code == 200
        assert fake.calls == [(bid, False)]  # called inside the request, not after it

    def test_a_hanging_webhook_is_cut_off_at_the_timeout(self, settings):
        client, bid, fake = app_with(settings, "hang")
        response, elapsed = decide(client, bid)
        assert response.status_code == 200 and response.json()["status"] == "decided"
        assert elapsed < TIMEOUT_S + 1.0
        assert fake.cancelled
        stored = client.get(f"/api/briefings/{bid}").json()
        assert stored == response.json()  # the record is the decision's, unchanged
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True

    def test_a_raising_webhook_does_not_fail_the_decision(self, settings, caplog):
        client, bid, fake = app_with(settings, "raise")
        with caplog.at_level("DEBUG"):
            response, _ = decide(client, bid)
        assert response.status_code == 200 and response.json()["status"] == "decided"
        assert len(fake.calls) == 1
        assert secrets_in(caplog.text) == []
        assert "RuntimeError" in caplog.text

    def test_the_timeout_is_logged_without_a_url_or_an_address(self, settings, caplog):
        client, bid, _ = app_with(settings, "hang")
        with caplog.at_level("DEBUG"):
            decide(client, bid)
        assert "webhook" in caplog.text.lower()
        assert secrets_in(caplog.text) == []


class TestTheRealSenderUnderTheBound:
    """The real WebhookSender, three URLs: one hangs, one answers 500, one works."""

    @pytest.fixture
    def parts(self, settings):
        delivered: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "hangs.example.com":
                await asyncio.sleep(30)
            if request.url.host == "fails.example.com":
                return httpx.Response(500)
            delivered.append(request.url.host)
            return httpx.Response(200)

        s = settings.with_overrides(
            webhook_url=",".join((HANGING, FAILING, WORKING)), webhook_timeout_s=TIMEOUT_S
        )
        app, *_ = make_app(s, round_1_scenario(), webhook_transport=httpx.MockTransport(handler))
        client = api_client(app)
        bid, _ = drive_to_round(client)
        return client, bid, delivered

    def test_the_urls_are_posted_at_once_and_the_decision_returns_in_time(self, parts, caplog):
        client, bid, delivered = parts
        with caplog.at_level("DEBUG"):
            response, elapsed = decide(client, bid)
        assert response.status_code == 200
        assert elapsed < TIMEOUT_S + 1.0
        assert delivered == ["works.example.com"]  # not held back by the one that hangs
        assert secrets_in(caplog.text) == []


class TestTheSetting:
    def test_it_defaults_to_5_s_and_is_read_from_the_environment(self):
        assert Settings().webhook_timeout_s == 5.0 == Settings.from_env({}).webhook_timeout_s
        assert Settings.from_env({"SIB_WEBHOOK_TIMEOUT_S": "2.5"}).webhook_timeout_s == 2.5

    @pytest.mark.parametrize("bad", ["0", "-1", "soon"])
    def test_a_timeout_that_is_not_above_0_fails_at_start_up(self, bad):
        with pytest.raises(ConfigError, match="SIB_WEBHOOK_TIMEOUT_S"):
            Settings.from_env({"SIB_WEBHOOK_TIMEOUT_S": bad})

    @pytest.mark.parametrize("bad", ["10.5", "30", "120"])
    def test_a_timeout_over_10_s_fails_at_start_up(self, bad):
        """The browser gives up on the decision call after 20 s: the webhooks get half of it."""
        with pytest.raises(ConfigError, match="SIB_WEBHOOK_TIMEOUT_S"):
            Settings.from_env({"SIB_WEBHOOK_TIMEOUT_S": bad})

    def test_10_s_is_the_most_allowed(self):
        assert Settings.from_env({"SIB_WEBHOOK_TIMEOUT_S": "10"}).webhook_timeout_s == 10.0
