"""Rounds, uploads, the live check and the relay's closing order (review fixes)."""

from __future__ import annotations

import asyncio

import pytest

from sayitback import live_relay
from sayitback.errors import InvalidState
from sayitback.live_relay import LiveRelay
from sayitback.models import CreateRound, DecisionBody
from sayitback.tts import Tts
from sayitback.webhook import chat_payload
from tests import fake_live
from tests.fake_live import DISCONNECT, FakeWebSocket, fake_opener, text_message
from tests.fakes import FakeTtsClient, fake_runtime, tone_wav
from tests.helpers import (
    CALLER,
    PANEL,
    api_client,
    check_files,
    drive_to_round,
    make_app,
    post_check,
)
from tests.test_webhook import decided

LIVE_RECORD = {
    "model": "m",
    "startedAt": "2026-10-14T10:00:00.000Z",
    "delivered": {"instruction": "x"},
    "heard": {},
}


class TestRoundsAndChecks:
    async def test_a_round_written_for_stale_steps_is_refused(self, settings):
        app, _rt, llm, _store = make_app(settings)
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        steps = client.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
        client.put(f"/api/briefings/{bid}/steps", json={"steps": steps})
        llm.delay = 0.3
        creating = asyncio.create_task(app.state.ctx.rounds.create(bid, CreateRound(), CALLER))
        await asyncio.sleep(0.1)  # the script is being written
        steps[0]["text"] = "Edited while the script was written"
        edit = await asyncio.to_thread(
            client.put, f"/api/briefings/{bid}/steps", json={"steps": steps}
        )

        assert edit.status_code == 200
        with pytest.raises(InvalidState, match="steps were edited"):
            await creating
        assert client.get(f"/api/briefings/{bid}").json()["rounds"] == []

    def test_a_fifth_file_is_a_clean_422_not_a_400(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app)
        bid, _ = drive_to_round(client)
        clips = {f"q{i}": tone_wav() for i in range(1, 6)}

        response = client.post(f"/api/briefings/{bid}/rounds/1/check", files=check_files(**clips))

        assert (response.status_code, response.json()["error"]["code"]) == (422, "too_many_files")

    def test_an_unknown_round_is_404_even_with_a_bad_upload(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app)
        bid, _ = drive_to_round(client)
        bad = [("q1", ("q1.webm", b"\x1aE\xdf\xa3" * 50, "audio/webm"))]

        response = client.post(f"/api/briefings/{bid}/rounds/9/check", files=bad)

        assert (response.status_code, response.json()["error"]["code"]) == (404, "round_not_found")
        assert post_check(client, "b_aaaaaaaaaaaa", 1).status_code == 404

    async def test_a_live_check_waits_for_the_relay_to_write_round_live(self, settings):
        """The browser can post the check the moment it sends `stop`, before round.live exists."""
        app, _rt, _llm, store = make_app(settings.with_overrides(live_record_wait_s=3.0))
        client = api_client(app)
        bid, _ = drive_to_round(client)

        def write_live(raw):
            raw["rounds"][0]["live"] = LIVE_RECORD
            return raw

        async def relay_finishes_late():
            await asyncio.sleep(0.5)
            await store.update(bid, write_live)

        late = asyncio.create_task(relay_finishes_late())
        judged = await asyncio.to_thread(post_check, client, bid, 1, "live")
        await late

        assert judged.status_code == 200 and judged.json()["mode"] == "live"

    def test_a_live_check_with_no_live_session_is_409_with_its_own_code(self, settings):
        app, *_ = make_app(settings.with_overrides(live_record_wait_s=0.3))
        client = api_client(app)
        bid, _ = drive_to_round(client)

        response = post_check(client, bid, 1, "live")

        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "live_not_recorded",
        )


class TestRelayFinalize:
    @pytest.fixture
    def env(self, settings):
        s = settings.with_overrides(max_tickets_per_round=10)
        app, _rt, _llm, store = make_app(s, live_opener=fake_opener([]))
        client = api_client(app)
        bid, _ = drive_to_round(client)
        return app, client, bid, store

    async def run_session(self, env, *, before_disconnect=None) -> FakeWebSocket:
        """Start, read the instruction aloud, then drop the socket (the tab was closed)."""
        app, client, bid, _ = env
        ticket = client.post(f"/api/briefings/{bid}/rounds/1/live-session").json()["ticket"]
        ws = FakeWebSocket(
            [
                text_message(type="start", ticket=ticket),
                text_message(type="cue", cue="READ_INSTRUCTION"),
            ]
        )
        task = asyncio.create_task(LiveRelay(ws, app.state.ctx.relay, bid, 1).run())
        for _ in range(500):  # bounded wait for the first turn
            if any(kind == "json" and f.get("type") == "turn_complete" for kind, f in ws.sent):
                break
            await asyncio.sleep(0.01)
        if before_disconnect:
            await before_disconnect()
        ws._incoming.put_nowait(DISCONNECT)
        await asyncio.wait_for(task, 5)
        return ws

    async def test_round_live_is_written_before_the_runner_is_closed(self, env, monkeypatch):
        _, _, bid, store = env
        seen: dict[str, bool] = {}
        original = fake_live.FakeRunnerHandle.close

        async def close_and_look(handle):
            raw = await store.get(bid)
            # setdefault: only the first close counts, a later one would always see the record
            seen.setdefault("live_already_written", raw["rounds"][0].get("live") is not None)
            await original(handle)

        monkeypatch.setattr(fake_live.FakeRunnerHandle, "close", close_and_look)

        await self.run_session(env)

        assert seen == {"live_already_written": True}

    async def test_nothing_is_written_to_a_briefing_decided_while_the_socket_was_open(self, env):
        app, _, bid, store = env

        async def decide():
            await app.state.ctx.briefings.decide(bid, DecisionBody(value="no_go"), CALLER)

        await self.run_session(env, before_disconnect=decide)

        raw = await store.get(bid)
        assert raw["status"] == "decided" and "live" not in raw["rounds"][0]

    async def test_a_failed_persist_is_logged_not_silent(self, env, caplog, monkeypatch):
        async def broken(self):
            raise RuntimeError("store down")

        monkeypatch.setattr(live_relay.LiveRelay, "_persist", broken)

        with caplog.at_level("WARNING", logger="sayitback.live"):
            await self.run_session(env)

        assert "could not persist round.live: RuntimeError" in caplog.text


async def test_the_tts_cache_byte_count_survives_a_concurrent_miss_for_the_same_text(settings):
    s = settings.with_overrides(tts_cache_max_bytes=10_000)
    rt, _ = fake_runtime(settings=s, tts_client=FakeTtsClient())
    tts = Tts(rt)

    for _ in range(50):  # the same key stored again and again (concurrent misses)
        tts._remember("same-key", b"x" * 1000)
    assert tts._bytes == 1000 and len(tts._cache) == 1

    for i in range(20):
        tts._remember(f"k{i}", b"x" * 1000)
    assert tts._bytes <= 10_000 and tts._bytes == sum(map(len, tts._cache.values()))


def test_google_chat_markup_in_supervisor_text_is_neutralised():
    b = decided(
        reason="<users/all> please read <https://evil.example|your invoice> *now* `x` _y_",
        by="<users/all>",
    )
    b.steps[2] = b.steps[2].model_copy(update={"text": "Test it <https://evil.example|click>"})

    text = chat_payload(b)["text"]

    body = text.split("\n", 1)[1]
    for markup in ("<", ">", "*now*", "`", "_y_"):
        assert markup not in body
    assert "users/all" in text  # the words stay, the markup goes
    assert text.startswith("*Say It Back: GO*")  # our own bold heading is untouched
