"""Endpoint 20: turn-taking fallback, a broken model stream, barge-in and the idle timeout."""

from __future__ import annotations

import asyncio

import pytest

from sayitback.live_relay import PLAYBACK_BYTES_PER_S
from tests.fake_live import TURN_COMPLETE, FakeRunnerHandle, audio_response, fake_opener, to_event
from tests.helpers import api_client, make_app
from tests.relay_support import (
    ORIGIN,
    Wire,
    live_record,
    make_env,
    request_kind,
)


@pytest.fixture
def env(settings):
    return make_env(settings)


class BurstThenQuiet(FakeRunnerHandle):
    """Live as it really behaves: all of a turn's audio at once, then nothing on the socket until the
    speech would end. Measured against gemini-3.8-live: 31 s of speech was on the wire within 8 s,
    then the socket was silent for 24 s before `turn_complete`."""

    def __init__(self, on_connected, state, *, speech_s: float, quiet_s: float) -> None:
        super().__init__(on_connected, state)
        self.speech_s, self.quiet_s = speech_s, quiet_s

    async def events(self, queue, config):
        self.configs.append(config)
        self.on_connected()
        while True:
            request = await queue.get()
            self.requests.append(request)
            if request.close:
                return
            if request.content:
                yield to_event(audio_response(int(self.speech_s * PLAYBACK_BYTES_PER_S)))
                await asyncio.sleep(self.quiet_s)
                yield to_event(TURN_COMPLETE)


def burst_opener(*, speech_s: float, quiet_s: float):
    async def opener(rt, state, on_connected):
        return BurstThenQuiet(on_connected, state, speech_s=speech_s, quiet_s=quiet_s)

    return opener


class TestTurnTakingAndFailures:
    def test_if_live_rejects_manual_activity_the_relay_falls_back_to_auto_vad(self, env):
        handles = []
        s = env.settings
        app, *_ = make_app(s, live_opener=fake_opener(handles, fail_manual=True), store=env.store)
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            assert wire.start(t)[1]["turnTaking"] == "auto"
            wire.send(type="cue", cue="ASK", qid="q1")
            wire.until("turn_complete")
            wire.send(type="answer_start", qid="q1")
            wire.audio(2)
            wire.send(type="answer_end", qid="q1")
            wire.until("turn_complete")
        assert len(handles) == 2
        auto = handles[1]
        assert auto.configs[0].realtime_input_config is None
        kinds = [request_kind(r) for r in auto.requests]
        assert kinds == ["text", "audio", "audio", "stream_end", "close"]

    def test_auto_can_be_chosen_from_the_start(self, env):
        handles = []
        s = env.settings.with_overrides(live_turn_taking="auto")
        app, *_ = make_app(s, live_opener=fake_opener(handles), store=env.store)
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            assert Wire(ws).start(t)[1]["turnTaking"] == "auto"
        assert len(handles) == 1

    def test_when_both_modes_fail_the_error_is_upstream_busy_and_nothing_is_recorded(self, env):
        app, *_ = make_app(
            env.settings, live_opener=fake_opener([], fail_always=True), store=env.store
        )
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket=t)
            assert wire.next()[1]["code"] == "upstream_busy"
            assert wire.next() == ("close", 4503)
        assert live_record(env) is None

    def test_a_model_stream_that_breaks_mid_session_is_reported_and_what_was_said_is_kept(
        self, env
    ):
        app, *_ = make_app(
            env.settings, live_opener=fake_opener([], crash_after_cues=1), store=env.store
        )
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            assert wire.start(t)[1]["type"] == "ready"
            wire.send(type="cue", cue="READ_INSTRUCTION")
            wire.until("turn_complete")
            wire.send(type="cue", cue="ASK", qid="q1")
            frame = wire.next()
            while frame[0] != "json" or frame[1]["type"] != "error":
                frame = wire.next()
            assert frame[1]["code"] == "upstream_busy"
        assert live_record(env)["delivered"] == {"instruction": "said:READ_INSTRUCTION"}

    def test_a_barge_in_is_forwarded_as_interrupted(self, env):
        from google.adk.models.llm_response import LlmResponse

        from tests.fake_live import TURN_COMPLETE, audio_response

        def reply(text):
            return [audio_response(), LlmResponse(interrupted=True), TURN_COMPLETE]

        app, *_ = make_app(env.settings, live_opener=fake_opener([], reply=reply), store=env.store)
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.start(t)
            wire.send(type="cue", cue="READ_INSTRUCTION")
            kinds = [j["type"] for j in wire.jsons(wire.until("turn_complete"))]
        assert "interrupted" in kinds


class TestIdleTimeoutCountsModelSpeech:
    def test_a_long_read_out_does_not_trip_the_idle_timeout(self, env):
        """Live reading a long script keeps the socket busy even though the browser sends nothing."""
        s = env.settings.with_overrides(ws_idle_s=0.4)
        app, *_ = make_app(s, live_opener=fake_opener([], delay=0.25), store=env.store)
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            assert wire.start(t)[1]["type"] == "ready"
            wire.send(type="cue", cue="READ_INSTRUCTION")
            frames = wire.until(
                "turn_complete"
            )  # four events over about a second, past the 0.4 s limit
            assert frames[-1] == ("json", {"type": "turn_complete"})
            assert not [f for f in wire.jsons(frames) if f["type"] == "error"]

    def test_a_silent_browser_is_still_idle_once_the_model_is_quiet(self, env):
        s = env.settings.with_overrides(ws_idle_s=0.3)
        app, *_ = make_app(s, live_opener=fake_opener([]), store=env.store)
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.start(t)
            wire.send(type="cue", cue="READ_INSTRUCTION")
            wire.until("turn_complete")
            error = wire.next()
            assert error[1]["code"] == "limit" and "idle" in error[1]["message"]

    def test_speech_that_is_still_playing_is_not_idle(self, env):
        """The audio of a long read-out arrives at once and the socket then goes quiet while the browser
        plays it. That is not an idle session, however long the speech: 1.2 s of speech outlasts a 0.8 s
        silence even with a 0.3 s idle limit."""
        s = env.settings.with_overrides(ws_idle_s=0.3)
        app, *_ = make_app(s, live_opener=burst_opener(speech_s=1.2, quiet_s=0.8), store=env.store)
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            assert wire.start(t)[1]["type"] == "ready"
            wire.send(type="cue", cue="READ_INSTRUCTION")
            frames = wire.until("turn_complete")
            assert frames[-1] == ("json", {"type": "turn_complete"})
            assert not [f for f in wire.jsons(frames) if f["type"] == "error"]

    def test_the_allowance_lasts_only_as_long_as_the_speech_it_covers(self, env):
        """Short speech followed by a long silence is still an idle session."""
        s = env.settings.with_overrides(ws_idle_s=0.3)
        app, *_ = make_app(s, live_opener=burst_opener(speech_s=0.05, quiet_s=0.8), store=env.store)
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.start(t)
            wire.send(type="cue", cue="READ_INSTRUCTION")
            errors = [f for f in wire.jsons(wire.until("turn_complete")) if f["type"] == "error"]
            assert errors and errors[0]["code"] == "limit" and "idle" in errors[0]["message"]
