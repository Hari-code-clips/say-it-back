"""Boundary hardening: streaming body limits, id checks and text validation (review fixes)."""

from __future__ import annotations

import json

import pytest

from sayitback.errors import NotFound
from sayitback.repo import Repo
from sayitback.store import LocalStore
from tests.helpers import ORIGIN, PANEL, api_client, drive_to_round, make_app

OWNER = "1" * 64

# Streaming body limits --------------------------------------------------------------------


def too_large(response) -> bool:
    return response.status_code == 413 and response.json()["error"]["code"] == "payload_too_large"


class TestBodyLimits:
    MULTIPART = {"content-type": "multipart/form-data; boundary=x"}

    @pytest.fixture
    def client(self, settings):
        app, *_ = make_app(settings)
        return api_client(app)

    @pytest.mark.parametrize(
        "path", ["/api/transcribe", "/api/briefings", "/api/briefings/b_aaaaaaaaaaaa/decision"]
    )
    def test_a_declared_length_over_the_limit_is_refused_without_reading_the_body(
        self, client, path
    ):
        # Only the header lies: the body is one byte. A refusal can therefore only come from the
        # up-front Content-Length check, not from counting bytes while the handler reads.
        headers = {**self.MULTIPART, "content-length": str(10 * 1024 * 1024)}

        assert too_large(client.post(path, content=b"x", headers=headers))

    def test_a_chunked_json_body_with_no_length_is_cut_off_as_it_streams(self, client):
        def chunks():
            for _ in range(40):
                yield b"x" * 10_000  # 400 KB in total, no Content-Length header

        response = client.post(
            "/api/briefings", content=chunks(), headers={"content-type": "application/json"}
        )

        assert too_large(response)  # FastAPI would have turned any other error into a 400

    def test_a_chunked_upload_is_cut_off_inside_the_form_parser_too(self, client, settings):
        def chunks():
            for _ in range(settings.max_audio_bytes // 100_000 + 2):
                yield b"x" * 100_000

        response = client.post("/api/transcribe", content=chunks(), headers=self.MULTIPART)

        assert too_large(response)

    def test_the_check_route_allows_three_files_but_not_a_flood(self, client, settings):
        bid, _ = drive_to_round(client)
        flood = b"x" * (3 * settings.max_audio_bytes + 64 * 1024 + 1)

        response = client.post(
            f"/api/briefings/{bid}/rounds/1/check", content=flood, headers=self.MULTIPART
        )

        assert too_large(response)

    def test_ordinary_requests_are_unaffected_and_a_refusal_carries_cors_headers(self, client):
        assert client.post("/api/briefings", json=PANEL).status_code == 200

        response = client.post(
            "/api/briefings",
            content=b"x" * 300_000,
            headers={"origin": ORIGIN, "content-type": "application/json"},
        )

        assert too_large(response)
        assert response.headers["access-control-allow-origin"] == ORIGIN

    def test_reads_are_never_limited(self, client):
        assert client.get("/api/health", headers={"content-length": "999999999"}).status_code == 200


# Ids and text at the boundary -------------------------------------------------------------


class TestIdsAndText:
    def test_an_id_with_a_trailing_newline_is_404_not_500(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app, raise_server_exceptions=False)
        for path in (
            "/api/briefings/b_aaaaaaaaaaaa%0A",
            "/api/briefings/b_aaaaaaaaaaaa%00",
            "/api/briefings/B_AAAAAAAAAAAA",
        ):
            assert client.get(path).status_code == 404
        assert (
            client.patch("/api/briefings/b_aaaaaaaaaaaa%0A", json={"instruction": "x"}).status_code
            == 404
        )

    async def test_the_repo_never_forwards_a_malformed_id_to_any_store(self):
        class SpyStore:
            """A real store also refuses these ids; only a spy can show the Repo checks first."""

            def __init__(self):
                self.asked: list[str] = []

            async def get(self, briefing_id):
                self.asked.append(briefing_id)

            async def update(self, briefing_id, change):
                self.asked.append(briefing_id)
                raise KeyError(briefing_id)

        spy = SpyStore()
        repo = Repo(spy)
        for bad in ("b_aaaaaaaaaaaa\n", "../x", "b_AAAAAAAAAAAA", ""):
            with pytest.raises(NotFound):
                await repo.get(bad, OWNER)
            with pytest.raises(NotFound):
                await repo.mutate(bad, OWNER, lambda b: None)

        assert spy.asked == []

    def test_a_step_id_with_a_trailing_newline_is_rejected(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        client.post(f"/api/briefings/{bid}/steps/extract")
        response = client.put(
            f"/api/briefings/{bid}/steps", json={"steps": [{"id": "s1\n", "text": "x"}]}
        )
        assert response.status_code == 422

    @staticmethod
    def raw(body: dict) -> dict:
        """json.dumps escapes a lone surrogate as \\ud800: the only way a client can send one."""
        return {"content": json.dumps(body), "headers": {"content-type": "application/json"}}

    def test_a_lone_surrogate_is_422_wherever_text_is_accepted(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app, raise_server_exceptions=False)
        bad = "text \ud800 text"

        created = client.post("/api/briefings", **self.raw({**PANEL, "instruction": bad}))
        assert (created.status_code, created.json()["error"]["code"]) == (422, "invalid_text")

        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        steps = client.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
        edited = client.put(
            f"/api/briefings/{bid}/steps", **self.raw({"steps": [{**steps[0], "text": bad}]})
        )
        assert (edited.status_code, edited.json()["error"]["code"]) == (422, "invalid_text")

        bid, _ = drive_to_round(client)
        for field in ("reason", "by"):
            body = {"value": "no_go", field: bad}
            decided = client.post(f"/api/briefings/{bid}/decision", **self.raw(body))
            assert (decided.status_code, decided.json()["error"]["code"]) == (422, "invalid_text")
        assert client.get(f"/api/briefings/{bid}").json()["status"] == "briefing"
        assert not list(settings.data_dir.rglob("*.tmp"))

    async def test_a_failed_write_leaves_no_temp_file(self, settings):
        store = LocalStore(settings.data_dir)
        with pytest.raises(UnicodeEncodeError):
            await store.create({"id": "b_aaaaaaaaaaaa", "createdAt": "x", "bad": "\ud800"})
        assert not list(settings.data_dir.rglob("*.tmp"))
