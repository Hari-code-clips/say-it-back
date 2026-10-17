"""API v0.4, "Webhooks": up to 3 URLs, the JSON record signed with SIB_WEBHOOK_SECRET and carrying
the record's hash, Chat posts unchanged, and neither a URL nor the secret in any log line."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx
import pytest

from sayitback.models import Hazard, HazardAck
from sayitback.settings import ConfigError, Settings
from sayitback.webhook import WebhookSender, json_record
from tests.flow_support import round_1_scenario
from tests.helpers import api_client, drive_to_round, make_app, post_check
from tests.test_webhook import CHAT, decided

PERMITS = "https://ptw.example.com/webhook?site=sg&key=PERMITKEY"
OTHER = "https://hooks.example.org/sib/TOKEN789"
SECRET = "s3cr3t-webhook-value"
NOW = 1_792_000_000


class Recorder:
    def __init__(self, fail_host: str = "") -> None:
        self.requests: list[httpx.Request] = []
        self.fail_host = fail_host

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(500 if request.url.host == self.fail_host else 200)

    def to(self, url: str) -> httpx.Request:
        return next(r for r in self.requests if str(r.url) == url)


def sender(urls, recorder, secret=SECRET) -> WebhookSender:
    return WebhookSender(urls, 1.0, httpx.MockTransport(recorder), secret=secret, clock=lambda: NOW)


def with_hazards():
    b = decided()
    b.hazards = [
        Hazard(id="h1", kind="voice", original="கயிறு", translation="rope", detected_lang="ta",
               raised_at="t", ack=HazardAck(note="Fixed it now.", at="t")),
        Hazard(id="h2", kind="tap", raised_at="t"),
    ]  # fmt: skip
    b.record_hash = "ab" * 32
    return b


class TestTheJsonRecord:
    def test_it_carries_the_record_hash_the_event_count_the_hazards_and_the_time(self):
        record = json_record(with_hazards())
        assert record["recordHash"] == "ab" * 32 and record["events"] == 0
        assert record["decidedAt"] == "2026-10-14T10:00:00Z"
        assert record["hazards"] == [
            {"id": "h1", "kind": "voice", "acknowledged": True},
            {"id": "h2", "kind": "tap", "acknowledged": False},
        ]
        assert record["decision"]["openHazardIds"] == []

    def test_it_carries_no_hazard_text_or_note(self):
        blob = json.dumps(json_record(with_hazards()), ensure_ascii=False)
        for text in ("கயிறு", "rope", "Fixed it now."):
            assert text not in blob


class TestSeveralUrls:
    async def test_every_url_gets_its_own_shape(self):
        rec = Recorder()
        ok = await sender(f"{CHAT}, {PERMITS},{OTHER}", rec).send(with_hazards())
        assert ok and len(rec.requests) == 3
        assert set(json.loads(rec.to(CHAT).content)) == {"text"}
        for url in (PERMITS, OTHER):
            assert json.loads(rec.to(url).content)["recordHash"] == "ab" * 32

    async def test_one_failing_url_does_not_stop_the_others(self):
        rec = Recorder(fail_host="hooks.example.org")
        ok = await sender([PERMITS, OTHER], rec).send(with_hazards())
        assert ok is False and len(rec.requests) == 2

    def test_more_than_three_is_a_start_up_error(self):
        urls = ",".join(f"https://h{i}.example.com/x" for i in range(4))
        with pytest.raises(ConfigError, match="at most 3"):
            Settings.from_env({"SIB_WEBHOOK_URL": urls})
        assert (
            Settings.from_env({"SIB_WEBHOOK_URL": urls.rsplit(",", 1)[0]})
            .webhook_urls[2]
            .startswith("https://h2.")
        )

    def test_a_bad_entry_is_named_by_position_never_by_its_text(self):
        with pytest.raises(ConfigError) as err:
            Settings.from_env({"SIB_WEBHOOK_URL": f"{PERMITS}, ftp://files.example.com/SECRETPATH"})
        assert "entry 2" in str(err.value) and "SECRETPATH" not in str(err.value)


class TestTheSignature:
    async def test_a_json_post_is_signed_over_its_raw_body(self):
        rec = Recorder()
        await sender(PERMITS, rec).send(with_hazards())
        request = rec.to(PERMITS)
        assert request.headers["X-SIB-Timestamp"] == str(NOW)
        mac = hmac.new(SECRET.encode(), f"{NOW}.".encode() + request.content, hashlib.sha256)
        assert request.headers["X-SIB-Signature"] == f"sha256={mac.hexdigest()}"
        assert request.headers["content-type"] == "application/json"

    async def test_a_chat_post_is_not_signed(self):
        rec = Recorder()
        await sender(CHAT, rec).send(with_hazards())
        assert "X-SIB-Signature" not in rec.to(CHAT).headers
        assert "X-SIB-Timestamp" not in rec.to(CHAT).headers

    async def test_without_a_secret_nothing_is_signed(self):
        rec = Recorder()
        await sender(PERMITS, rec, secret="").send(with_hazards())
        assert "X-SIB-Signature" not in rec.to(PERMITS).headers

    async def test_a_changed_body_no_longer_matches(self):
        rec = Recorder()
        await sender(PERMITS, rec).send(with_hazards())
        request = rec.to(PERMITS)
        forged = request.content.replace(b'"go"', b'"no_go"')
        mac = hmac.new(SECRET.encode(), f"{NOW}.".encode() + forged, hashlib.sha256)
        assert request.headers["X-SIB-Signature"] != f"sha256={mac.hexdigest()}"

    def test_the_secret_is_read_from_the_environment_and_never_shown(self):
        s = Settings.from_env({"SIB_WEBHOOK_SECRET": f" {SECRET} ", "SIB_WEBHOOK_URL": PERMITS})
        assert s.webhook_secret == SECRET
        assert SECRET not in repr(s) and "PERMITKEY" not in repr(s)
        assert SECRET not in repr(sender(PERMITS, Recorder())) and "PERMITKEY" not in repr(
            sender(PERMITS, Recorder())
        )


async def test_no_url_path_query_or_secret_reaches_a_log_line(caplog):
    with caplog.at_level(logging.DEBUG):
        await sender([PERMITS, OTHER, CHAT], Recorder(fail_host="hooks.example.org")).send(
            with_hazards()
        )
    for secret in (SECRET, "PERMITKEY", "TOKEN789", "KEY123", "TOK456", "/webhook", "/sib/"):
        assert secret not in caplog.text
    assert "ptw.example.com" in caplog.text and "hooks.example.org" in caplog.text


def test_the_decision_posts_the_records_hash_signed_to_every_url(settings):
    rec = Recorder()
    s = settings.with_overrides(webhook_url=f"{PERMITS},{CHAT}", webhook_secret=SECRET)
    app, *_ = make_app(s, round_1_scenario(), webhook_transport=httpx.MockTransport(rec))
    client = api_client(app)
    bid = drive_to_round(client)[0]
    post_check(client, bid, 1)
    client.post(f"/api/briefings/{bid}/hazards")
    decided_body = client.post(f"/api/briefings/{bid}/decision", json={"value": "no_go"}).json()
    assert len(rec.requests) == 2
    request = rec.to(PERMITS)
    record = json.loads(request.content)
    assert record["recordHash"] == decided_body["recordHash"]
    assert record["recordHash"] == client.get(f"/api/briefings/{bid}/verify").json()["recordHash"]
    assert record["events"] == len(decided_body["events"])
    assert record["hazards"] == [{"id": "h1", "kind": "tap", "acknowledged": False}]
    assert record["decision"]["openHazardIds"] == ["h1"]
    stamp = request.headers["X-SIB-Timestamp"]
    mac = hmac.new(SECRET.encode(), f"{stamp}.".encode() + request.content, hashlib.sha256)
    assert request.headers["X-SIB-Signature"] == f"sha256={mac.hexdigest()}"
