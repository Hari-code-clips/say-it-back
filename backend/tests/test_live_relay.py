"""Endpoint 20, WS /api/live/{id}/{n}: handshake, round state and a full relayed briefing."""

from __future__ import annotations

import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

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


@pytest.fixture
def env(settings):
    return make_env(settings)


class TestHandshake:
    def test_ready_reports_the_model_and_the_turn_taking_mode(self, env):
        with connect(env) as ws:
            assert Wire(ws).start(ticket(env)) == (
                "json",
                {"type": "ready", "model": "gemini-3.8-live", "turnTaking": "manual"},
            )

    @pytest.mark.parametrize(
        "origin", [None, "https://evil.example", "http://localhost:5174", "null"]
    )
    def test_a_disallowed_or_missing_origin_is_refused_at_the_handshake(self, env, origin):
        with pytest.raises(WebSocketDisconnect) as err, connect(env, origin=origin):
            pass
        assert err.value.code == 1008
        assert env.handles == []

    def test_an_allowed_origin_with_a_trailing_slash_is_fine(self, env):
        with connect(env, origin=ORIGIN + "/") as ws:
            assert Wire(ws).start(ticket(env))[1]["type"] == "ready"

    def test_a_random_ticket_is_bad_ticket_and_closes_4401(self, env):
        with connect(env) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket="not-a-ticket")
            assert wire.next() == (
                "json",
                {"type": "error", "code": "bad_ticket", "message": "The ticket is not valid."},
            )
            assert wire.next() == ("close", 4401)
        assert env.handles == []

    def test_a_ticket_works_once(self, env):
        t = ticket(env)
        with connect(env) as ws:
            assert Wire(ws).start(t)[1]["type"] == "ready"
        with connect(env) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket=t)
            assert wire.next()[1]["code"] == "bad_ticket"
            assert wire.next() == ("close", 4401)

    def test_a_ticket_for_another_round_is_not_valid_here(self, env):
        t = ticket(env)
        with env.client.websocket_connect(
            f"/api/live/{env.bid}/2", headers={"origin": ORIGIN}
        ) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket=t)
            assert wire.next()[1]["code"] == "bad_ticket"

    def test_an_expired_ticket_is_refused(self, env, monkeypatch):
        from datetime import timedelta

        from sayitback import live_session

        real = live_session.redeem_ticket

        async def late(store, ticket, *, now=None):
            from datetime import UTC, datetime

            return await real(store, ticket, now=datetime.now(UTC) + timedelta(seconds=121))

        monkeypatch.setattr(live_session, "redeem_ticket", late)
        t = ticket(env)
        with connect(env) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket=t)
            assert wire.next()[1]["code"] == "bad_ticket"

    @pytest.mark.parametrize(
        "first", ['{"type":"cue","cue":"CLOSE"}', "not json", '{"type":"start"}', "[]"]
    )
    def test_the_first_frame_must_be_start_with_a_ticket(self, env, first):
        with connect(env) as ws:
            wire = Wire(ws)
            wire.raw(first)
            code = wire.next()[1]["code"]
            assert code in {"bad_ticket", "bad_message"}
            assert wire.next()[0] == "close"

    def test_a_missing_start_frame_times_out(self, env):
        s = env.settings.with_overrides(ws_first_message_s=0.2)
        app, *_ = make_app(s, live_opener=fake_opener([]), store=env.store)
        client = api_client(app)
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            assert wire.next()[1]["code"] == "bad_message"
            assert wire.next() == ("close", 4400)

    def test_the_ticket_value_is_never_logged(self, env, caplog):
        t = ticket(env)
        with caplog.at_level("DEBUG"), connect(env) as ws:
            Wire(ws).start(t)
        assert t not in caplog.text


class TestRoundState:
    def test_a_judged_round_cannot_go_live(self, env):
        from tests.helpers import post_check

        t = ticket(env)  # issued while the round is still open
        assert post_check(env.client, env.bid, 1).status_code == 200
        with connect(env) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket=t)
            frame = wire.next()
            assert frame[1]["code"] == "invalid_state"
            assert wire.next() == ("close", 4409)

    def test_only_one_live_socket_per_round_at_a_time(self, env):
        with connect(env) as first:
            holder = open_session(env, first)
            with connect(env) as second:
                wire = Wire(second)
                wire.send(type="start", ticket=ticket(env))
                frame = wire.next()
                assert frame[1]["code"] == "invalid_state"
                assert "already has a live session" in frame[1]["message"]
                assert wire.next() == ("close", 4409)
            holder.send(type="stop")
            assert holder.next() == ("close", 1000)
        with connect(env) as third:  # the lease was released when the first socket closed
            assert open_session(env, third)


class TestRelay:
    def test_a_full_briefing_is_relayed_and_recorded(self, env):
        with connect(env) as ws:
            wire = open_session(env, ws)
            wire.send(type="cue", cue="READ_INSTRUCTION")
            read = wire.until("turn_complete")
            wire.send(type="cue", cue="ASK", qid="q1")
            ask = wire.until("turn_complete")
            wire.send(type="answer_start", qid="q1")
            wire.audio(3)
            wire.send(type="answer_end", qid="q1")
            thanks = wire.until("turn_complete")
            wire.send(type="cue", cue="CLOSE")
            closing = wire.until("turn_complete")
            wire.send(type="stop")
            assert wire.next() == ("close", 1000)

        assert any(f[0] == "bin" and f[1] for f in read), "model speech is relayed as binary frames"
        captions = [c for c in wire.jsons(read) if c["type"] == "caption"]
        assert captions[0] == {"type": "caption", "role": "model", "text": "said:R", "final": False}
        assert captions[-1] == {
            "type": "caption",
            "role": "model",
            "text": "said:READ_INSTRUCTION",
            "final": True,
        }
        assert {
            "type": "caption",
            "role": "model",
            "text": "said:ASK q1",
            "final": True,
        } in wire.jsons(ask)
        assert {
            "type": "caption",
            "role": "worker",
            "text": "heard-answer",
            "final": True,
        } in wire.jsons(thanks)
        assert {
            "type": "caption",
            "role": "model",
            "text": "said:CLOSE",
            "final": True,
        } in wire.jsons(closing)

        handle = env.handles[0]
        assert handle.texts == ["READ_INSTRUCTION", "ASK q1", "CLOSE"]
        kinds = [request_kind(r) for r in handle.requests]
        assert kinds == ["text", "text", "start", "audio", "audio", "audio", "end", "text", "close"]
        assert all(r.blob.mime_type == "audio/pcm;rate=16000" for r in handle.requests if r.blob)

    def test_round_live_is_written_when_the_socket_closes(self, env):
        with connect(env) as ws:
            wire = open_session(env, ws)
            for cue in ({"cue": "READ_INSTRUCTION"}, {"cue": "ASK", "qid": "q1"}):
                wire.send(type="cue", **cue)
                wire.until("turn_complete")
            wire.send(type="answer_start", qid="q1")
            wire.audio(2)
            wire.send(type="answer_end", qid="q1")
            wire.until("turn_complete")
            wire.send(type="cue", cue="CLOSE")
            wire.until("turn_complete")
            wire.send(type="stop")
            wire.next()
        live = live_record(env)
        assert live["model"] == "gemini-3.8-live"
        assert live["startedAt"] and live["endedAt"]
        assert live["delivered"] == {
            "instruction": "said:READ_INSTRUCTION",
            "q1": "said:ASK q1",
            "q1.reply": "said:THANKS",
            "closing": "said:CLOSE",
        }
        assert live["heard"] == {"q1": "heard-answer"}

    async def test_round_live_is_written_even_if_the_browser_just_disconnects(self, env):
        from sayitback.live_relay import LiveRelay
        from tests.fake_live import DISCONNECT, FakeWebSocket, text_message

        ws = FakeWebSocket([text_message(type="start", ticket=ticket(env)),
                            text_message(type="cue", cue="READ_INSTRUCTION")])  # fmt: skip
        relay = LiveRelay(ws, env.app.state.ctx.relay, env.bid, 1)
        task = asyncio.create_task(relay.run())
        for _ in range(500):  # wait (bounded) for the first turn to finish
            if any(k == "json" and f.get("type") == "turn_complete" for k, f in ws.sent):
                break
            await asyncio.sleep(0.01)
        ws._incoming.put_nowait(DISCONNECT)  # the tab was closed: no stop frame
        await asyncio.wait_for(task, 5)
        assert live_record(env)["delivered"] == {"instruction": "said:READ_INSTRUCTION"}
        assert env.handles[0].closed

    def test_a_session_that_never_became_ready_writes_no_live_record(self, env):
        with connect(env) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket="bad")
            wire.next()
        assert live_record(env) is None

    def test_audio_outside_an_answer_window_never_reaches_the_model(self, env):
        with connect(env) as ws:
            wire = open_session(env, ws)
            wire.audio(5)
            wire.send(type="cue", cue="READ_INSTRUCTION")
            wire.until("turn_complete")
            wire.send(type="stop")
            wire.next()
        assert not any(r.blob for r in env.handles[0].requests)

    def test_the_briefers_state_is_the_script_only(self, env):
        with connect(env) as ws:
            open_session(env, ws)
        state = env.handles[0].state
        assert set(state) == {"lang_name", "instruction", "questions", "closing"}
        assert state["lang_name"] == "Tamil"
        assert all(set(q) == {"id", "text"} for q in state["questions"])
        assert state["instruction"] == " ".join(env.rnd["script"]["instruction"].split("\n"))
