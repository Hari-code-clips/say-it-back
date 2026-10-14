"""Endpoint 20: each cue and each answer window can be used once per session (API.md, "Live session
protocol"). A repeat is `invalid_state`, close 4409, and nothing is forwarded to Live: the fake
runner's `requests` is the LiveRequestQueue, so it shows exactly what would have reached the model."""

from __future__ import annotations

import pytest

from tests.fake_live import fake_opener
from tests.helpers import api_client, make_app
from tests.relay_support import (
    ORIGIN,
    Wire,
    connect,
    live_record,
    make_env,
    open_session,
    request_kind,
    ticket,
)

READ = {"type": "cue", "cue": "READ_INSTRUCTION"}
ASK1 = {"type": "cue", "cue": "ASK", "qid": "q1"}
ASK2 = {"type": "cue", "cue": "ASK", "qid": "q2"}
CLOSE = {"type": "cue", "cue": "CLOSE"}
OPEN1 = {"type": "answer_start", "qid": "q1"}
CUES = {"READ_INSTRUCTION": READ, "ASK q1": ASK1, "ASK q2": ASK2, "CLOSE": CLOSE}
# What one answer window of three PCM chunks puts on the queue, per turn-taking mode.
WINDOW = {
    "manual": ["start", "audio", "audio", "audio", "end"],
    "auto": ["audio", "audio", "audio", "stream_end"],
}
WALKTHROUGH = ["READ_INSTRUCTION", "ASK q1", "window q1", "ASK q2", "window q2", "CLOSE"]


@pytest.fixture
def env(settings):
    return make_env(settings)


def play(wire: Wire, step: str) -> None:
    """One step of a briefing, then wait for the model's turn to end: a cue or `window <qid>`."""
    if step.startswith("window"):
        qid = step.split()[1]
        wire.send(type="answer_start", qid=qid)
        wire.audio(3)
        wire.send(type="answer_end", qid=qid)
    else:
        wire.send(**CUES[step])
    wire.until("turn_complete")


def queued(handle) -> list[str]:
    """What reached the Live queue, in order."""
    return [request_kind(r) for r in handle.requests]


def queued_for(steps: list[str]) -> list[str]:
    """What `steps` put on the queue in manual turn-taking."""
    return [k for s in steps for k in (WINDOW["manual"] if s.startswith("window") else ["text"])]


def refused(wire: Wire) -> dict:
    """The one error frame a refused frame gets, then close 4409. Returns the error frame."""
    kind, frame = wire.next()
    assert kind == "json" and frame["type"] == "error", frame
    assert wire.next() == ("close", 4409)
    return frame


def until_closed(wire: Wire) -> list:
    """Every frame up to and including the close."""
    frames = []
    while not frames or frames[-1][0] != "close":
        frames.append(wire.next())
    return frames


# id -> (the steps played first, the frame sent next)
REPEATS = {
    "READ_INSTRUCTION again": (["READ_INSTRUCTION"], READ),
    "ASK q1 again": (["ASK q1"], ASK1),
    "CLOSE again": (["CLOSE"], CLOSE),
    "ASK q1 again after ASK q2": (["ASK q1", "ASK q2"], ASK1),
    "READ_INSTRUCTION again after a whole question": (
        ["READ_INSTRUCTION", "ASK q1", "window q1"],
        READ,
    ),
    "ASK q1 again after its answer window": (["ASK q1", "window q1"], ASK1),
    "a second answer window for q1": (["ASK q1", "window q1"], OPEN1),
}


class TestARepeatIsRefusedAndNeverForwarded:
    @pytest.mark.parametrize(("steps", "repeat"), list(REPEATS.values()), ids=list(REPEATS))
    def test_invalid_state_then_close_4409_and_nothing_reaches_live(self, env, steps, repeat):
        with connect(env) as ws:
            wire = open_session(env, ws)
            for step in steps:
                play(wire, step)
            wire.send(**repeat)
            frame = refused(wire)
        assert frame["code"] == "invalid_state" and "once per session" in frame["message"]
        handle = env.handles[0]
        assert handle.texts == [s for s in steps if not s.startswith("window")]
        assert queued(handle) == [*queued_for(steps), "close"]

    def test_a_burst_of_the_same_cue_forwards_only_the_first(self, env):
        with connect(env) as ws:
            wire = open_session(env, ws)
            for _ in range(5):
                wire.send(**ASK1)
            frames = until_closed(wire)
        errors = [f[1] for f in frames if f[0] == "json" and f[1]["type"] == "error"]
        assert [e["code"] for e in errors] == ["invalid_state"]
        assert frames[-1] == ("close", 4409)
        assert env.handles[0].texts == ["ASK q1"]

    def test_an_ordering_rule_answers_before_the_repeat_rule(self, env):
        """A repeated cue inside an open window still gets the existing ordering rule's message."""
        with connect(env) as ws:
            wire = open_session(env, ws)
            play(wire, "ASK q1")
            wire.send(**OPEN1)
            wire.send(**ASK1)
            frame = refused(wire)
        assert frame["message"] == "Close the answer window before the next cue."


class TestNothingIsLostOnARefusal:
    @pytest.mark.parametrize("repeat", [ASK1, OPEN1], ids=["a repeated cue", "a repeated window"])
    def test_round_live_keeps_what_was_delivered_and_heard(self, env, repeat):
        with connect(env) as ws:
            wire = open_session(env, ws)
            for step in ("READ_INSTRUCTION", "ASK q1", "window q1"):
                play(wire, step)
            wire.send(**repeat)
            refused(wire)
        live = live_record(env)
        assert live["endedAt"]
        assert live["delivered"] == {
            "instruction": "said:READ_INSTRUCTION",
            "q1": "said:ASK q1",
            "q1.reply": "said:THANKS",
        }
        assert live["heard"] == {"q1": "heard-answer"}  # and not twice

    def test_a_refused_cue_does_not_move_where_the_models_speech_is_recorded(self, env):
        """The model is still speaking q1's question when a repeated READ_INSTRUCTION is refused.
        What it goes on to say is still q1's: the refusal happens before anything is touched."""
        # A long drain costs nothing: the relay stops waiting as soon as the model's turn ends.
        s = env.settings.with_overrides(live_drain_s=3.0)
        app, *_ = make_app(s, live_opener=fake_opener([], delay=0.05), store=env.store)
        client = api_client(app)
        t = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session").json()["ticket"]
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            assert wire.start(t)[1]["type"] == "ready"
            play(wire, "READ_INSTRUCTION")
            wire.send(**ASK1)
            wire.send(**READ)
            frames = until_closed(wire)
        assert frames[-1] == ("close", 4409)
        assert live_record(env)["delivered"] == {
            "instruction": "said:READ_INSTRUCTION",
            "q1": "said:ASK q1",
        }


class TestTheNormalBriefingStillRuns:
    @pytest.mark.parametrize("mode", ["manual", "auto"])
    def test_every_cue_and_window_once_end_to_end(self, settings, mode):
        env = make_env(settings.with_overrides(live_turn_taking=mode))
        with connect(env) as ws:
            wire = Wire(ws)
            assert wire.start(ticket(env))[1]["turnTaking"] == mode
            for step in WALKTHROUGH:
                play(wire, step)
            wire.send(type="stop")
            assert wire.next() == ("close", 1000)

        handle, window = env.handles[0], WINDOW[mode]
        assert handle.texts == ["READ_INSTRUCTION", "ASK q1", "ASK q2", "CLOSE"]
        assert queued(handle) == ["text", "text", *window, "text", *window, "text", "close"]
        live = live_record(env)
        assert live["delivered"] == {
            "instruction": "said:READ_INSTRUCTION",
            "q1": "said:ASK q1",
            "q1.reply": "said:THANKS",
            "q2": "said:ASK q2",
            "q2.reply": "said:THANKS",
            "closing": "said:CLOSE",
        }
        assert live["heard"] == {"q1": "heard-answer", "q2": "heard-answer"}

    def test_a_new_session_for_the_same_round_starts_fresh(self, env):
        """Once per session, not once per round: a second ticket may read the instruction again."""
        for _ in range(2):
            with connect(env) as ws:
                wire = open_session(env, ws)
                play(wire, "READ_INSTRUCTION")
                wire.send(type="stop")
                assert wire.next() == ("close", 1000)
        assert [h.texts for h in env.handles] == [["READ_INSTRUCTION"]] * 2
