"""The pilot e-permit adapter (docs/EPERMIT_ADAPTER.md): SIB_PTW_URL is one more target, the generic
adapter maps the decision record onto a vendor's field names (SIB_PTW_FIELD_MAP), SIB_PTW_TOKEN is
sent as a bearer token and never logged or shown, every JSON post carries the decision's
Idempotency-Key, and a receiver's answer is classified: 2xx or 409 `duplicate` delivered,
408/425/429/5xx retried, any other 4xx refused."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx
import pytest

from sayitback.settings import ConfigError, Settings
from sayitback.webhook import (
    IDEMPOTENCY_HEADER,
    WebhookSender,
    classify,
    idempotency_key,
    json_record,
    map_record,
    parse_field_map,
)
from tests.test_v04_webhooks import NOW, PERMITS, SECRET, Recorder, with_hazards
from tests.test_webhook import CHAT

VENDOR = "https://epermit.vendor.example/api/v2/clearances?tenant=SITEKEY42"
TOKEN = "vendor-bearer-0f9e8d7c6b5a"
MAP = {
    "externalRef": "briefingId",
    "permit.number": "permit.ref",
    "permit.worker": "permit.slot",
    "clearance": {"from": "decision.value", "map": {"go": "CLEARED", "no_go": "ON_HOLD"}},
    "openSteps": "decision.openStepIds",
    "evidenceHash": "recordHash",
    "source": {"const": "say-it-back"},
    "requestId": "$idempotencyKey",
    "missing": "sop.nothingHere",
}


def vendor_sender(recorder, field_map=MAP, token=TOKEN, urls=()) -> WebhookSender:
    return WebhookSender(
        list(urls), 1.0, httpx.MockTransport(recorder), secret=SECRET, clock=lambda: NOW,
        vendor_url=VENDOR, field_map=json.dumps(field_map) if field_map else "", vendor_token=token,
    )  # fmt: skip


def permit_briefing():
    from sayitback.models import PermitLink

    b = with_hazards()
    b.permit = PermitLink(ref="PTW-77/A", crew_size=3, slot=2)
    return b


class TestTheGenericMapping:
    def test_each_vendor_field_comes_from_the_record(self):
        b = permit_briefing()
        body = map_record(json_record(b), parse_field_map(json.dumps(MAP)), "KEY")
        assert body == {
            "externalRef": "b_abcdefghijkl",
            "permit": {"number": "PTW-77/A", "worker": 2},
            "clearance": "CLEARED",
            "openSteps": ["s3"],
            "evidenceHash": "ab" * 32,
            "source": "say-it-back",
            "requestId": "KEY",
            "missing": None,
        }

    def test_a_value_the_map_does_not_name_takes_the_default(self):
        fmap = {"state": {"from": "decision.value", "map": {"go": "OK"}, "default": "REVIEW"}}
        b = with_hazards()
        b.decision.value = "no_go"
        assert map_record(json_record(b), fmap, "k") == {"state": "REVIEW"}

    @pytest.mark.parametrize(
        ("raw", "why"),
        [
            ("{not json", "not JSON"),
            ("[]", "an object"),
            ("{}", "an object"),
            ('{"a": "transcript"}', "not valid"),  # no such record field: no content can leak in
            ('{"a": "steps.text.x.y.z"}', "not valid"),
            ('{"a": {"from": "decision.value", "map": {"go": {"x": 1}}}}', "not valid"),
            ('{"a": {"const": [1]}}', "not valid"),
            ('{"bad name!": "briefingId"}', "not a field name"),
            ('{"permit": "briefingId", "permit.ref": "permit.ref"}', "both a value and a parent"),
        ],
    )
    def test_a_malformed_map_stops_start_up(self, raw, why):
        with pytest.raises(ConfigError, match=why):
            Settings.from_env({"SIB_PTW_URL": VENDOR, "SIB_PTW_FIELD_MAP": raw})

    def test_an_empty_map_sends_the_native_record(self):
        rec = Recorder()
        assert vendor_sender(rec, field_map=None).targets[-1].adapter == "record"
        assert parse_field_map("  ") is None


class TestTheVendorPost:
    async def test_the_mapped_body_is_signed_keyed_and_carries_the_bearer_token(self):
        rec = Recorder()
        ok = await vendor_sender(rec, urls=[PERMITS]).send(permit_briefing())
        assert ok and len(rec.requests) == 2
        request = rec.to(VENDOR)
        body = json.loads(request.content)
        assert body["clearance"] == "CLEARED" and "briefingId" not in body
        mac = hmac.new(SECRET.encode(), f"{NOW}.".encode() + request.content, hashlib.sha256)
        assert request.headers["X-SIB-Signature"] == f"sha256={mac.hexdigest()}"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        key = idempotency_key(permit_briefing())
        assert request.headers[IDEMPOTENCY_HEADER] == key == body["requestId"]
        assert key == f"sib-b_abcdefghijkl-{'ab' * 8}"
        native = rec.to(PERMITS)  # the stub's post: the native record, no token
        assert "Authorization" not in native.headers
        assert native.headers[IDEMPOTENCY_HEADER] == key

    async def test_chat_gets_neither_a_key_nor_a_token(self):
        rec = Recorder()
        await vendor_sender(rec, urls=[CHAT]).send(permit_briefing())
        chat = rec.to(CHAT)
        assert IDEMPOTENCY_HEADER not in chat.headers and "Authorization" not in chat.headers

    async def test_the_token_and_the_url_never_reach_a_log_line_or_a_repr(self, caplog):
        with caplog.at_level(logging.DEBUG):
            await vendor_sender(Recorder(fail_host="epermit.vendor.example")).send(with_hazards())
            await vendor_sender(Recorder()).send(with_hazards())
        assert "epermit.vendor.example" in caplog.text and "http_500" in caplog.text
        for secret in (TOKEN, "SITEKEY42", "/clearances", SECRET):
            assert secret not in caplog.text
        sender = vendor_sender(Recorder())
        shown = repr(sender) + repr(sender.targets) + repr(Settings.from_env(ENV))
        assert TOKEN not in shown and "SITEKEY42" not in shown


# The link needs accounts (security fixes A, H1), so a service with it on runs in firebase mode.
ACCOUNTS = {"SIB_AUTH_MODE": "firebase", "SIB_AUTH_PROJECT": "sib-pilot", "SIB_AUTH_ORG": "acme"}
ENV = {**ACCOUNTS, "SIB_PTW_URL": VENDOR, "SIB_PTW_TOKEN": TOKEN, "SIB_PTW_FIELD_MAP": json.dumps(MAP)}


class TestTheSettings:
    def test_off_by_default(self):
        s = Settings.from_env({})
        assert (s.outbox, s.ptw_url, s.ptw_token, s.ptw_field_map, s.outbox_token) == (
            False, "", "", "", ""
        )  # fmt: skip

    def test_read_from_the_environment(self):
        s = Settings.from_env({**ENV, "SIB_OUTBOX": "true", "SIB_OUTBOX_MAX_ATTEMPTS": "3"})
        assert s.outbox and s.outbox_max_attempts == 3 and s.ptw_token == TOKEN

    def test_a_token_is_sent_only_over_https(self):
        http = VENDOR.replace("https://", "http://")
        with pytest.raises(ConfigError, match="https") as err:
            Settings.from_env({**ENV, "SIB_PTW_URL": http})
        assert TOKEN not in str(err.value) and "SITEKEY42" not in str(err.value)
        local = Settings.from_env({**ENV, "SIB_PTW_URL": "http://localhost:8090/webhook"})
        assert local.ptw_url.startswith("http://localhost")

    @pytest.mark.parametrize(
        "env",
        [
            {"SIB_PTW_TOKEN": TOKEN},
            {"SIB_PTW_FIELD_MAP": '{"a": "briefingId"}'},
            {"SIB_PTW_URL": "ftp://files.example/SITEKEY42"},
            {"SIB_OUTBOX_MAX_ATTEMPTS": "0"},
            {"SIB_OUTBOX_BACKOFF_S": "0"},
            {"SIB_OUTBOX_BACKOFF_S": "90", "SIB_OUTBOX_MAX_BACKOFF_S": "60"},
        ],
    )
    def test_bad_values_stop_start_up_without_echoing_a_secret(self, env):
        with pytest.raises(ConfigError) as err:
            Settings.from_env(env)
        assert TOKEN not in str(err.value) and "SITEKEY42" not in str(err.value)


def answer(status, body=None):
    return httpx.Response(status, json=body) if body is not None else httpx.Response(status)


class TestHowAnAnswerIsRead:
    @pytest.mark.parametrize("status", [200, 201, 202, 204])
    def test_2xx_is_delivered(self, status):
        assert classify(answer(status)).delivered

    def test_409_duplicate_is_delivered(self):
        outcome = classify(answer(409, {"error": {"code": "duplicate"}}))
        assert outcome.delivered and outcome.error == "duplicate"

    @pytest.mark.parametrize("body", [None, {"error": {"code": "crew_mismatch"}}, {"x": 1}])
    def test_any_other_409_is_a_refusal(self, body):
        outcome = classify(answer(409, body))
        assert (outcome.delivered, outcome.retry, outcome.error) == (False, False, "http_409")

    @pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
    def test_busy_or_broken_is_retried(self, status):
        outcome = classify(answer(status))
        assert (outcome.delivered, outcome.retry, outcome.error) == (False, True, f"http_{status}")

    @pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 413, 422])
    def test_a_refusal_is_never_retried(self, status):
        outcome = classify(answer(status))
        assert (outcome.delivered, outcome.retry) == (False, False)
