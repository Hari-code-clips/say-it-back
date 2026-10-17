"""API v0.4, endpoint 23: the supervisor's script approval is a server-side gate. Nothing is
spoken (live ticket, TTS, the Live socket) or judged (check) before it."""

from __future__ import annotations

import pytest

from tests.fakes import FakeTtsClient, tone_wav
from tests.helpers import (
    SPOKEN,
    api_client,
    approve_round,
    drive_to_round,
    error_of,
    make_app,
    post_check,
    run_sync,
    seed_round,
)
from tests.relay_support import Wire, connect


@pytest.fixture
def unapproved(settings):
    tts = FakeTtsClient()
    app, rt, llm, store = make_app(settings, tts_client=tts)
    client = api_client(app)
    bid, rnd = drive_to_round(client, approve=False)
    return client, bid, rnd, tts, store


class TestTheGate:
    def test_a_new_round_is_not_approved(self, unapproved):
        _, _, rnd, *_ = unapproved
        assert "approvedAt" not in rnd and "approvedBy" not in rnd

    def test_no_live_ticket_before_approval(self, unapproved):
        client, bid, *_ = unapproved
        response = client.post(f"/api/briefings/{bid}/rounds/1/live-session")
        assert error_of(response) == (409, "script_not_approved")

    def test_no_tts_before_approval_and_no_model_call(self, unapproved):
        client, bid, _, tts, _ = unapproved
        response = client.post("/api/tts", json={"briefingId": bid, "n": 1, "text": SPOKEN})
        assert error_of(response) == (409, "script_not_approved")
        assert tts.calls == []

    def test_no_check_before_approval_and_no_model_call(self, unapproved, settings):
        client, bid, *_ = unapproved
        response = post_check(client, bid, 1, q1=tone_wav())
        assert error_of(response) == (409, "script_not_approved")

    def test_after_approval_all_three_work(self, unapproved):
        client, bid, _, tts, _ = unapproved
        approve_round(client, bid, 1)
        assert client.post(f"/api/briefings/{bid}/rounds/1/live-session").status_code == 200
        tts_reply = client.post("/api/tts", json={"briefingId": bid, "n": 1, "text": SPOKEN})
        assert tts_reply.status_code == 200 and len(tts.calls) == 1
        assert post_check(client, bid, 1, q1=tone_wav()).status_code == 200

    def test_a_reexplain_round_needs_its_own_approval(self, settings):
        from tests.flow_support import round_1_scenario

        app, *_ = make_app(settings, round_1_scenario())
        client = api_client(app)
        bid, _ = drive_to_round(client)
        post_check(client, bid, 1, q1=tone_wav())
        assert (
            client.post(
                f"/api/briefings/{bid}/rounds", json={"supervisorNote": "again"}
            ).status_code
            == 200
        )
        assert error_of(post_check(client, bid, 2, q3=tone_wav())) == (409, "script_not_approved")
        approve_round(client, bid, 2)
        assert post_check(client, bid, 2, q3=tone_wav()).status_code == 200

    def test_the_live_socket_refuses_a_round_that_lost_its_approval(self, settings):
        """Defence in depth: the relay re-checks what the ticket checked when it was issued."""
        app, _rt, _llm, store = make_app(settings)
        client = api_client(app)
        bid, _ = drive_to_round(client)
        ticket = client.post(f"/api/briefings/{bid}/rounds/1/live-session").json()["ticket"]

        def unapprove(raw):
            raw["rounds"][0].pop("approvedAt")
            return raw

        run_sync(store.update(bid, unapprove))
        with connect(type("E", (), {"client": client, "bid": bid})()) as ws:
            wire = Wire(ws)
            kind, frame = wire.start(ticket)
            assert (kind, frame["type"], frame["code"]) == ("json", "error", "invalid_state")
            assert wire.next() == ("close", 4409)


class TestApprove:
    def test_it_sets_approved_at_and_by_and_returns_the_round(self, unapproved):
        client, bid, *_ = unapproved
        response = client.post(f"/api/briefings/{bid}/rounds/1/approve", json={"by": "  Sam  "})
        body = response.json()
        assert response.status_code == 200 and body["n"] == 1
        assert body["approvedAt"].endswith("Z") and body["approvedBy"] == "Sam"
        stored = client.get(f"/api/briefings/{bid}").json()["rounds"][0]
        assert stored["approvedAt"] == body["approvedAt"]

    def test_the_body_is_optional(self, unapproved):
        client, bid, *_ = unapproved
        body = client.post(f"/api/briefings/{bid}/rounds/1/approve").json()
        assert body["approvedAt"] and "approvedBy" not in body

    def test_a_second_approval_is_a_no_op(self, unapproved):
        client, bid, *_ = unapproved
        first = approve_round(client, bid, 1, by="Sam")
        second = approve_round(client, bid, 1, by="Someone else")
        assert second["approvedAt"] == first["approvedAt"] and second["approvedBy"] == "Sam"
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        assert [e["type"] for e in events].count("script_approved") == 1

    def test_an_unknown_round_is_404(self, unapproved):
        client, bid, *_ = unapproved
        for n in (0, 2, 9):
            response = client.post(f"/api/briefings/{bid}/rounds/{n}/approve")
            assert error_of(response) == (404, "round_not_found"), n

    def test_another_device_gets_404(self, unapproved):
        _, bid, *_ = unapproved
        client, *_ = unapproved
        other = api_client(client.app, device="someone-else-device-key-0000")
        assert error_of(other.post(f"/api/briefings/{bid}/rounds/1/approve")) == (404, "not_found")

    def test_a_judged_round_that_was_never_approved_cannot_be_approved(self, settings):
        app, _rt, _llm, store = make_app(settings)
        client = api_client(app)
        bid = seed_round(store, approved=False)

        def judged(raw):
            raw["status"], raw["rounds"][0]["judgedAt"] = "judged", "2026-10-14T10:00:00.000Z"
            return raw

        run_sync(store.update(bid, judged))
        assert error_of(client.post(f"/api/briefings/{bid}/rounds/1/approve")) == (
            409,
            "invalid_state",
        )

    def test_by_is_capped(self, unapproved):
        client, bid, *_ = unapproved
        response = client.post(f"/api/briefings/{bid}/rounds/1/approve", json={"by": "x" * 81})
        assert error_of(response) == (422, "too_long")

    def test_it_is_a_free_write_under_the_per_minute_limit(self, settings):
        app, *_ = make_app(settings.with_overrides(rate_limit_per_min=1))
        client = api_client(app)
        url = "/api/briefings/b_aaaaaaaaaaaa/rounds/1/approve"
        assert error_of(client.post(url)) == (404, "not_found")  # the one write this minute
        assert error_of(client.post(url)) == (429, "rate_limited")
