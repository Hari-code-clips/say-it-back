"""The permit-to-work stub: it takes only signed, fresh decision records, releases a permit for a Go,
holds one for a No-go, and shows them as JSON and on an HTML board that loads nothing else."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import pytest
from fastapi.testclient import TestClient

from ptw_stub import board
from ptw_stub.app import create_app

SECRET = "shared-test-secret"
NOW = 1_792_000_000
HASH = "a1" * 32


def record(value="go", bid="b_abcdefghijkl", open_steps=(), open_hazards=(), **extra):
    return {
        "event": "briefing_decided", "briefingId": bid, "siteId": "sg", "taskId": "lifting-zone",
        "sop": {"id": "SOP-LF-03", "version": "v2"}, "supervisorLang": "en", "workerLang": "ta", "rounds": 1,
        "steps": [{"id": "s1", "text": "Never stand or walk under the load", "source": "instruction", "finalVerdict": "covered"},
                  {"id": "s4", "text": "Use the tag line <never your hand>", "source": "sop", "finalVerdict": "unclear"}],
        "decision": {"value": value, "reason": "Checked in person.", "by": "Sam", "openStepIds": list(open_steps),
                     "openHazardIds": list(open_hazards), "at": "2026-10-14T10:00:00.000Z"},
        "decidedAt": "2026-10-14T10:00:00.000Z", "hazards": [], "events": 9, "recordHash": HASH,
        "promptVersion": "p", **extra,
    }  # fmt: skip


def signed(body: bytes, stamp: int = NOW, secret: str = SECRET) -> dict[str, str]:
    mac = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-SIB-Timestamp": str(stamp), "X-SIB-Signature": f"sha256={mac}", "Content-Type": "application/json"}


@pytest.fixture
def make(tmp_path):
    def build(**kw):
        kw.setdefault("secret", SECRET)
        kw.setdefault("clock", lambda: NOW)
        return TestClient(create_app(**kw))

    return build


@pytest.fixture
def client(make):
    return make()


def post(client, payload, headers=None):
    body = json.dumps(payload).encode()
    return client.post("/webhook", content=body, headers=headers if headers is not None else signed(body))


class TestTheSignature:
    def test_a_signed_fresh_record_is_accepted(self, client):
        response = post(client, record())
        assert response.status_code == 201 and response.json()["created"] is True

    @pytest.mark.parametrize(
        ("headers", "code"),
        [
            ({}, "unsigned"),
            ({"X-SIB-Timestamp": str(NOW)}, "unsigned"),
            ({"X-SIB-Timestamp": "soon", "X-SIB-Signature": "sha256=00"}, "bad_timestamp"),
            ({"X-SIB-Timestamp": str(NOW), "X-SIB-Signature": "sha256=" + "0" * 64}, "bad_signature"),
            ({"X-SIB-Timestamp": str(NOW), "X-SIB-Signature": "sha256=ö".encode("latin-1")}, "bad_signature"),
        ],
    )
    def test_an_unsigned_or_badly_signed_post_is_401(self, client, headers, code):
        response = post(client, record(), headers)
        assert response.status_code == 401 and response.json()["error"]["code"] == code
        assert client.get("/api/permits").json() == {"permits": []}

    def test_the_signature_covers_the_raw_body(self, client):
        body = json.dumps(record("go")).encode()
        forged = body.replace(b'"go"', b'"no_go"', 1)
        response = client.post("/webhook", content=forged, headers=signed(body))
        assert response.json()["error"]["code"] == "bad_signature"

    def test_another_secret_is_refused(self, client):
        body = json.dumps(record()).encode()
        response = client.post("/webhook", content=body, headers=signed(body, secret="other"))
        assert response.json()["error"]["code"] == "bad_signature"

    @pytest.mark.parametrize("skew", [301, -301, 10_000])
    def test_a_timestamp_more_than_300_s_away_is_refused(self, client, skew):
        body = json.dumps(record()).encode()
        response = client.post("/webhook", content=body, headers=signed(body, NOW - skew))
        assert response.status_code == 401 and response.json()["error"]["code"] == "stale"

    @pytest.mark.parametrize("skew", [300, -300, 0])
    def test_within_the_window_is_fine(self, client, skew):
        body = json.dumps(record()).encode()
        assert client.post("/webhook", content=body, headers=signed(body, NOW - skew)).status_code == 201

    def test_without_a_secret_every_post_is_refused(self, make):
        client = make(secret="", allow_unsigned=False)
        response = post(client, record(), headers={"Content-Type": "application/json"})
        assert response.status_code == 503 and response.json()["error"]["code"] == "not_configured"

    def test_unsigned_posts_only_when_allowed_for_a_local_try(self, make):
        client = make(secret="", allow_unsigned=True)
        assert post(client, record(), headers={"Content-Type": "application/json"}).status_code == 201

    def test_the_secret_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("SIB_WEBHOOK_SECRET", SECRET)
        client = TestClient(create_app(clock=lambda: NOW))
        assert post(client, record()).status_code == 201
        assert client.get("/healthz").json()["signed"] is True

    def test_the_secret_never_reaches_a_log_line_or_a_response(self, client, caplog):
        with caplog.at_level(logging.DEBUG):
            post(client, record())
            post(client, record(), headers={"X-SIB-Timestamp": str(NOW), "X-SIB-Signature": "sha256=00"})
            pages = client.get("/").text + client.get("/api/permits").text + client.get("/healthz").text
        assert SECRET not in caplog.text and SECRET not in pages


class TestPermits:
    def test_go_releases_and_no_go_holds(self, client):
        post(client, record("go", bid="b_aaaaaaaaaaaa"))
        post(client, record("no_go", bid="b_bbbbbbbbbbbb", open_steps=["s4"], open_hazards=["h1"]))
        permits = client.get("/api/permits").json()["permits"]
        assert [(p["id"], p["status"]) for p in permits] == [("PTW-2", "held"), ("PTW-1", "released")]
        held = permits[0]
        assert held["briefingId"] == "b_bbbbbbbbbbbb" and (held["siteId"], held["taskId"]) == ("sg", "lifting-zone")
        assert held["openSteps"] == [{"id": "s4", "text": "Use the tag line <never your hand>"}]
        assert held["openHazards"] == ["h1"] and held["recordHash"] == HASH
        assert held["receivedAt"].endswith("Z") and held["demo"] is None and held["sampleAnswers"] == []

    def test_a_repeat_post_for_the_same_briefing_returns_its_permit(self, client):
        first = post(client, record()).json()["permit"]
        again = post(client, record("no_go"))
        assert again.status_code == 200 and again.json() == {"permit": first, "created": False}
        assert len(client.get("/api/permits").json()["permits"]) == 1

    @pytest.mark.parametrize(
        "bad",
        [
            {"event": "something_else"},
            {"briefingId": "../etc/passwd"},
            {"recordHash": "not-a-hash"},
            {"decision": {"value": "approved"}},
        ],
    )
    def test_a_record_that_is_not_a_decision_is_422(self, client, bad):
        response = post(client, {**record(), **bad})
        assert response.status_code == 422 and response.json()["error"]["code"] == "bad_record"

    def test_a_body_that_is_not_json_is_422(self, client):
        body = b"not json"
        assert client.post("/webhook", content=body, headers=signed(body)).status_code == 422

    def test_a_body_over_64_kb_is_413(self, client):
        body = json.dumps({**record(), "pad": "x" * 70_000}).encode()
        assert client.post("/webhook", content=body, headers=signed(body)).status_code == 413

    def test_permits_can_be_kept_in_a_json_file(self, make, tmp_path):
        path = tmp_path / "permits.json"
        post(make(store_file=path), record())
        reopened = make(store_file=path)
        assert [p["id"] for p in reopened.get("/api/permits").json()["permits"]] == ["PTW-1"]
        post(reopened, record(bid="b_cccccccccccc"))
        assert json.loads(path.read_text())["permits"][1]["id"] == "PTW-2"


class TestTheBoard:
    def test_it_lists_each_permit_with_what_was_open(self, client):
        post(client, record("go", bid="b_aaaaaaaaaaaa"))
        post(client, record("no_go", bid="b_bbbbbbbbbbbb", open_steps=["s4"], open_hazards=["h1", "h2"]))
        html = client.get("/").text
        assert "PTW-1" in html and "PTW-2" in html and "1 released · 1 held" in html
        assert "b_bbbbbbbbbbbb" in html and HASH in html and "h1, h2" in html
        assert "The supervisor decided No-go." in html and "Held" in html and "Released" in html

    def test_every_value_is_escaped(self, client):
        post(client, record(bid="b_aaaaaaaaaaaa", open_steps=["s4"], siteId="<script>x</script>"))
        html = client.get("/").text
        assert "<script>" not in html and "&lt;script&gt;" in html
        assert "&lt;never your hand&gt;" in html

    def test_it_loads_nothing_and_runs_no_script(self, client):
        response = client.get("/")
        html = response.text
        assert "<script" not in html and "http://" not in html and "https://" not in html
        csp = response.headers["content-security-policy"]
        assert "default-src 'none'" in csp and f"'sha256-{board.STYLE_SHA256}'" in csp
        assert "unsafe-inline" not in csp and response.headers["x-frame-options"] == "DENY"

    def test_the_style_hash_is_the_hash_of_the_inline_style(self, client):
        import base64

        html = client.get("/").text
        style = html.split("<style>", 1)[1].split("</style>", 1)[0]
        assert base64.b64encode(hashlib.sha256(style.encode()).digest()).decode() == board.STYLE_SHA256

    def test_an_empty_board_says_what_will_appear(self, client):
        html = client.get("/").text
        assert "No permits yet" in html and "0 released · 0 held" in html

    def test_it_never_claims_the_ai_approved_anything(self, client):
        post(client, record("go"))
        html = client.get("/").text.lower()
        for word in ("approved", "passed", "understood"):
            assert word not in html


class TestWhatIsShown:
    def test_the_deciders_name_is_neither_shown_nor_served_but_kept(self, make, tmp_path):
        path = tmp_path / "permits.json"
        client = make(store_file=path)
        post(client, record("no_go"))
        assert "Sam" not in client.get("/").text
        assert "decidedBy" not in client.get("/api/permits").text and "Sam" not in client.get("/api/permits").text
        assert json.loads(path.read_text())["permits"][0]["decided_by"] == "Sam"  # the stub's own record

    def test_a_permit_from_sample_answers_is_marked_demo(self, client):
        samples = [{"round": 1, "questionId": "q1"}, {"round": 2, "questionId": "q3"}]
        post(client, record("go", bid="b_aaaaaaaaaaaa", sampleAnswers=samples))
        post(client, record("go", bid="b_bbbbbbbbbbbb"))
        demo, real = sorted(client.get("/api/permits").json()["permits"], key=lambda p: p["briefingId"])
        assert demo["demo"] == "Demo: synthetic sample answers" and demo["sampleAnswers"] == samples
        assert real["demo"] is None and real["sampleAnswers"] == []
        html = client.get("/").text
        assert html.count("Demo: synthetic sample answers") == 1 and "round 1 q1, round 2 q3" in html
