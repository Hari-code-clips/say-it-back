"""Cross-cutting API behaviour: health, catalog, errors, CORS, rate limit, eval, time budget."""

from __future__ import annotations

import json

from tests.fakes import FakeTtsClient, Scenario, rating, tone_wav, transcript
from tests.helpers import (
    ORIGIN,
    PANEL,
    SPOKEN,
    api_client,
    drive_to_round,
    error_of,
    make_app,
    seed_round,
)


class TestHealthCatalogAndErrors:
    def test_health(self, client):
        body = client.get("/api/health").json()
        assert body["ok"] is True and body["store"] == "local" and body["judgePasses"] == 2
        assert body["models"] == {
            "flash": "gemini-3.8-flash",
            "live": "gemini-3.8-live",
            "tts": "gemini-3.8-flash-tts",
        }
        assert body["backends"] == {
            "flash": "developer-api",
            "live": "developer-api",
            "tts": "developer-api",
        }
        assert body["promptVersion"]

    def test_catalog_has_no_reference_answers_over_http(self, client):
        text = client.get("/api/catalog").text
        assert (
            "referenceSteps" not in text
            and "demoScripts" not in text
            and "referenceQuestions" not in text
        )

    def test_unknown_paths_and_wrong_methods_use_the_error_shape(self, client):
        assert error_of(client.get("/api/nope")) == (404, "not_found")
        assert error_of(client.delete("/api/briefings"))[0] == 405

    def test_an_unexpected_error_is_a_generic_500_without_details(self, settings, monkeypatch):
        from sayitback.service import Briefings

        async def boom(self, body):
            raise RuntimeError("SECRET-INTERNAL-DETAIL")

        monkeypatch.setattr(Briefings, "create", boom)
        app, *_ = make_app(settings)
        response = api_client(app, raise_server_exceptions=False).post("/api/briefings", json=PANEL)
        assert error_of(response) == (500, "internal_error")
        assert "SECRET-INTERNAL-DETAIL" not in response.text

    def test_responses_are_not_cached_and_not_sniffed(self, client):
        response = client.get("/api/health")
        assert (
            response.headers["cache-control"] == "no-store"
            and response.headers["x-content-type-options"] == "nosniff"
        )


class TestCors:
    def test_the_configured_origin_is_allowed_including_preflight(self, client):
        response = client.options(
            "/api/briefings",
            headers={
                "origin": ORIGIN,
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            },
        )
        assert (
            response.status_code == 200
            and response.headers["access-control-allow-origin"] == ORIGIN
        )
        assert (
            client.get("/api/health", headers={"origin": ORIGIN}).headers[
                "access-control-allow-origin"
            ]
            == ORIGIN
        )

    def test_other_origins_get_no_cors_header(self, client):
        response = client.get("/api/health", headers={"origin": "https://evil.example"})
        assert "access-control-allow-origin" not in response.headers


class TestRateLimit:
    def tts_body(self, store, i: int = 5) -> dict:
        """A valid TTS request for a briefing the test caller owns: no call used up by setup."""
        return {"briefingId": seed_round(store), "n": 1, "text": SPOKEN[:i]}

    def test_gemini_backed_endpoints_are_limited_per_ip(self, settings):
        s = settings.with_overrides(rate_limit_per_min=2)
        app, _rt, _llm, store = make_app(s, tts_client=FakeTtsClient())
        client = api_client(app)
        body = self.tts_body(store)
        assert client.post("/api/tts", json=body).status_code == 200
        assert client.post("/api/tts", json=body).status_code == 200
        third = client.post("/api/tts", json=body)
        assert error_of(third) == (429, "rate_limited") and int(third.headers["retry-after"]) > 0
        assert client.get("/api/health").status_code == 200  # not Gemini-backed

    def test_each_ip_has_its_own_allowance(self, settings):
        s = settings.with_overrides(rate_limit_per_min=1)
        app, _rt, _llm, store = make_app(s, tts_client=FakeTtsClient())
        client = api_client(app)
        body = self.tts_body(store)
        # Behind Cloud Run's front end the last X-Forwarded-For entry is the client's address.
        one, two = {"x-forwarded-for": "1.1.1.1"}, {"x-forwarded-for": "2.2.2.2"}
        assert client.post("/api/tts", json=body, headers=one).status_code == 200
        assert client.post("/api/tts", json=body, headers=two).status_code == 200
        assert client.post("/api/tts", json=body, headers=one).status_code == 429

    def test_the_other_gemini_endpoints_are_limited_too(self, settings):
        app, *_ = make_app(settings.with_overrides(rate_limit_per_min=2))
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]  # a free write counts too
        assert client.post(f"/api/briefings/{bid}/steps/extract").status_code == 200
        assert client.post(f"/api/briefings/{bid}/steps/extract").status_code == 429
        audio = {"audio": ("a.wav", tone_wav(), "audio/wav")}
        assert client.post("/api/transcribe", files=audio, data={"lang": "en"}).status_code == 429


class TestEvalEndpoints:
    def make_eval(self, settings, extra_steps=None):
        testset = settings.eval_dir / "testset"
        (testset / "audio").mkdir(parents=True)
        (testset / "audio" / "x.wav").write_bytes(tone_wav())
        item = {"id": "panel-isolation.q1.ta.complete.clean", "taskId": "panel-isolation", "questionId": "q1", "workerLang": "ta",
                "pattern": "complete", "noise": "clean", "source": "synthetic_tts", "answer": "a", "answerGloss": "g",
                "gold": {"s1": "covered", "s2": "covered", "s3": "covered"}, "audio": "audio/x.wav"}  # fmt: skip
        (testset / "items.json").write_text(
            json.dumps(
                {
                    "version": "v",
                    "questions": {"panel-isolation": {"q1": {"ta": "கேள்வி?"}}},
                    "items": [item],
                }
            )
        )
        (settings.eval_dir / "reports").mkdir()
        (settings.eval_dir / "reports" / "latest.json").write_text(
            '{"nItems": 1, "passBar": {"passed": false}}'
        )
        return item["id"]

    def test_404_when_there_is_no_report_or_test_set(self, client):
        assert error_of(client.get("/api/eval/latest")) == (404, "no_report")
        assert error_of(client.get("/api/eval/items"))[0] == 404

    def test_report_items_and_audio(self, settings):
        item_id = self.make_eval(settings)
        app, *_ = make_app(settings)
        client = api_client(app)
        assert client.get("/api/eval/latest").json()["nItems"] == 1
        items = client.get("/api/eval/items").json()["items"]
        assert items[0]["id"] == item_id and "answer" not in items[0] and "audio" not in items[0]
        audio = client.get(f"/api/eval/items/{item_id}/audio")
        assert audio.headers["content-type"] == "audio/wav" and audio.content[:4] == b"RIFF"
        assert error_of(client.get("/api/eval/items/nope/audio"))[0] == 404

    def test_try_runs_the_real_check_on_the_stored_clip(self, settings):
        item_id = self.make_eval(settings)
        scenario = Scenario(
            transcripts=[transcript("q1", "பிரேக்கரை ஆஃப் பண்ணி லாக் போட்டு டெஸ்டர் வச்சு")],
            judge_a=[
                rating("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி"),
                rating("s2", "covered", "லாக் போட்டு"),
                rating("s3", "missed"),
            ],
        )
        app, *_ = make_app(settings, scenario)
        body = api_client(app).post(f"/api/eval/items/{item_id}/try").json()
        assert set(body) == {"item", "round", "agreement", "unsafe"}
        assert set(body["round"]) == {"transcripts", "passA", "passB", "ratings"}
        assert body["agreement"] == {"s1": True, "s2": True, "s3": False}
        assert body["unsafe"] is False and body["item"]["id"] == item_id
        assert {r["stepId"]: r["verdict"] for r in body["round"]["ratings"]} == {
            "s1": "covered",
            "s2": "covered",
            "s3": "missed",
        }

    def test_a_covered_rating_where_gold_says_missed_is_flagged_unsafe(self, settings):
        item_id = self.make_eval(settings)
        path = settings.eval_dir / "testset" / "items.json"
        data = json.loads(path.read_text())
        data["items"][0]["gold"] = {"s1": "covered", "s2": "missed", "s3": "covered"}
        path.write_text(json.dumps(data))
        scenario = Scenario(
            transcripts=[transcript("q1", "பிரேக்கரை ஆஃப் பண்ணி லாக் போட்டு")],
            judge_a=[
                rating("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி"),
                rating("s2", "covered", "லாக் போட்டு"),
                rating("s3", "covered", "பிரேக்கரை ஆஃப்"),
            ],
        )
        app, *_ = make_app(settings, scenario)
        body = api_client(app).post(f"/api/eval/items/{item_id}/try").json()
        assert body["unsafe"] is True and body["agreement"]["s2"] is False


class TestRequestBudget:
    """A whole /api call that chains model phases is bounded, so the client gets JSON, not Hosting's 504."""

    def test_a_slow_round_creation_is_a_503_before_the_hosting_limit(self, settings):
        s = settings.with_overrides(request_timeout_s=0.3)
        app, _rt, llm, _store = make_app(s)
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        steps = client.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
        client.put(f"/api/briefings/{bid}/steps", json={"steps": steps})
        llm.delay = 1.0
        response = client.post(f"/api/briefings/{bid}/rounds")
        assert error_of(response) == (503, "upstream_busy")
        llm.delay = 0.0
        assert (
            client.get(f"/api/briefings/{bid}").json()["status"] == "steps_confirmed"
        )  # nothing was half-written

    def test_a_fast_call_is_unaffected(self, settings):
        app, *_ = make_app(settings.with_overrides(request_timeout_s=30.0))
        client = api_client(app)
        drive_to_round(client)
