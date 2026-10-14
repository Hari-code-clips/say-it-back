"""The live-session endpoint, a check with a live record, and the decision with its webhook."""

from __future__ import annotations

import json

import httpx
import pytest

from tests.fakes import tone_wav
from tests.flow_support import (
    make_env,
    round_1_scenario,
)
from tests.helpers import api_client, drive_to_round, make_app, post_check


@pytest.fixture
def scenario():
    return round_1_scenario()


@pytest.fixture
def env(settings, scenario):
    return make_env(settings, scenario)


class TestLiveSessionEndpoint:
    def test_it_returns_a_ticket_ws_url_model_and_expiry(self, env):
        body = env.client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()
        assert set(body) == {"wsUrl", "ticket", "model", "expiresAt"}
        assert body["wsUrl"] == f"/api/live/{env.bid}/1" and body["model"] == "gemini-3.8-live"
        assert len(body["ticket"]) >= 43 and body["expiresAt"].endswith("Z")

    def test_the_ws_url_is_absolute_with_a_public_base(self, settings):
        s = settings.with_overrides(public_ws_base="wss://api-x.a.run.app")
        app, *_ = make_app(s)
        client = api_client(app)
        bid, _ = drive_to_round(client)
        assert (
            client.post(f"/api/briefings/{bid}/rounds/1/live-session").json()["wsUrl"]
            == f"wss://api-x.a.run.app/api/live/{bid}/1"
        )

    def test_a_third_ticket_for_the_same_round_is_429_limit(self, env):
        for _ in range(2):
            assert (
                env.client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").status_code
                == 200
            )
        third = env.client.post(f"/api/briefings/{env.bid}/rounds/1/live-session")
        assert (third.status_code, third.json()["error"]["code"]) == (429, "limit")

    def test_the_ticket_is_never_stored_with_the_briefing(self, env):
        body = env.client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()
        stored = "\n".join(p.read_text() for p in env.settings.data_dir.rglob("*.json"))
        assert body["ticket"] not in stored

    def test_409_for_a_judged_round_and_404_for_a_missing_one(self, env):
        post_check(env.client, env.bid, 1)
        assert env.client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").status_code == 409
        assert env.client.post(f"/api/briefings/{env.bid}/rounds/9/live-session").status_code in (
            404,
            409,
        )


class TestCheckWithLive:
    def record_live(self, env):
        def change(raw):
            raw["rounds"][0]["live"] = {
                "model": "gemini-3.8-live", "startedAt": "2026-10-14T10:00:00.000Z", "endedAt": "2026-10-14T10:01:00.000Z",
                "delivered": {"instruction": "பிரேக்கரை ஆஃப் செய்யுங்கள்\nலாக் போடுங்கள்", "q1": "பேனலைத் திறப்பதற்கு முன் என்ன செய்வீர்கள்?"},
                "heard": {"q1": "live heard this"},
            }  # fmt: skip
            return raw

        import asyncio

        asyncio.run(env.store.update(env.bid, change))

    def test_live_mode_takes_the_delivery_check_from_round_live(self, env):
        self.record_live(env)
        body = post_check(env.client, env.bid, 1, mode="live").json()
        assert body["mode"] == "live"
        by_segment = {d["segment"]: d for d in body["delivery"]}
        assert set(by_segment) == {"instruction", "q1", "q2", "closing"}
        assert by_segment["q1"]["similarity"] == 1.0 and by_segment["q1"]["scriptOk"] is True
        assert by_segment["closing"]["similarity"] == 0.0  # never spoken

    def test_the_heard_transcript_is_evidence_only_never_sent_to_the_judges(self, env):
        self.record_live(env)
        post_check(env.client, env.bid, 1, mode="live")
        assert all(
            "live heard this" not in s.system and "live heard this" not in s.text
            for s in env.llm.seen
        )

    def test_live_mode_without_a_live_record_is_409(self, env):
        assert post_check(env.client, env.bid, 1, mode="live").status_code == 409

    def test_the_browser_cannot_supply_a_delivery_check(self, env):
        files = [("q1", ("q1.wav", tone_wav(), "audio/wav"))]
        data = {
            "meta": json.dumps(
                {"mode": "turn", "delivery": [{"segment": "x"}], "transcripts": {"q1": "forged"}}
            )
        }
        body = env.client.post(
            f"/api/briefings/{env.bid}/rounds/1/check", files=files, data=data
        ).json()
        assert body["delivery"] == [] and "forged" not in json.dumps(body)


class TestDecisionAndWebhook:
    def test_go_with_open_steps_needs_a_reason(self, env):
        post_check(env.client, env.bid, 1)
        bare = env.client.post(f"/api/briefings/{env.bid}/decision", json={"value": "go"})
        assert (bare.status_code, bare.json()["error"]["code"]) == (422, "reason_required")
        short = env.client.post(
            f"/api/briefings/{env.bid}/decision", json={"value": "go", "reason": "ok"}
        )
        assert short.status_code == 422

    def test_a_recorded_decision_says_what_was_checked_and_decided(self, env):
        post_check(env.client, env.bid, 1)
        body = env.client.post(
            f"/api/briefings/{env.bid}/decision",
            json={"value": "go", "reason": "Verified by demonstration", "by": "Supervisor A"},
        ).json()
        assert body["status"] == "decided"
        assert body["decision"]["value"] == "go" and body["decision"]["openStepIds"] == ["s2", "s3"]
        assert (
            body["decision"]["reason"] == "Verified by demonstration"
            and body["decision"]["by"] == "Supervisor A"
        )
        assert body["decision"]["at"].endswith("Z")

    def test_the_decision_fires_the_google_chat_webhook(self, env):
        post_check(env.client, env.bid, 1)
        env.client.post(
            f"/api/briefings/{env.bid}/decision", json={"value": "no_go", "by": "Supervisor A"}
        )
        assert len(env.hooks) == 1 and set(env.hooks[0]) == {"text"}
        assert "NO-GO" in env.hooks[0]["text"] and "Covered 1 of 3 steps." in env.hooks[0]["text"]

    def test_nothing_is_writable_after_decided(self, env):
        env.client.post(f"/api/briefings/{env.bid}/decision", json={"value": "no_go"})
        again = env.client.post(f"/api/briefings/{env.bid}/decision", json={"value": "no_go"})
        assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_state"
        assert (
            env.client.patch(f"/api/briefings/{env.bid}", json={"instruction": "x"}).status_code
            == 409
        )
        assert (
            env.client.put(
                f"/api/briefings/{env.bid}/steps", json={"steps": [{"id": "s1", "text": "x"}]}
            ).status_code
            == 409
        )
        assert env.client.post(f"/api/briefings/{env.bid}/rounds").status_code == 409
        assert post_check(env.client, env.bid, 1).status_code == 409
        assert env.client.post(f"/api/briefings/{env.bid}/steps/extract").status_code == 409
        assert env.client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").status_code == 409
        assert len(env.hooks) == 1

    def test_a_failing_webhook_does_not_fail_the_decision(self, settings, scenario):
        transport = httpx.MockTransport(lambda r: httpx.Response(500))
        s = settings.with_overrides(webhook_url="https://hooks.example.com/x")
        app, *_ = make_app(s, scenario, webhook_transport=transport)
        client = api_client(app)
        bid, _ = drive_to_round(client)
        assert (
            client.post(f"/api/briefings/{bid}/decision", json={"value": "no_go"}).status_code
            == 200
        )

    def test_without_a_webhook_url_nothing_is_posted(self, settings, scenario):
        app, *_ = make_app(settings, scenario)
        client = api_client(app)
        bid, _ = drive_to_round(client)
        assert (
            client.post(f"/api/briefings/{bid}/decision", json={"value": "no_go"}).status_code
            == 200
        )
