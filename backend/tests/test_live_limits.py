"""What a Live socket may hold, and for how long (API.md v0.3, "Limits"; security review S4).

The first message within 5 s and a cue within 30 s of `ready`; only frames the relay accepts reset the
idle clock (audio it drops outside a window does not); at most `SIB_MAX_SOCKETS_PER_IP` open sockets
per client address on one instance, refused before any ticket is read or Live is opened. The
once-per-session rules and the playback-aware idle logic are untouched: test_live_order.py,
test_live_relay_once.py and test_live_relay_failures.py.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from sayitback.live_idle import IDLE_MESSAGE, IdleClock, OpenSockets
from sayitback.settings import ConfigError, Settings
from tests.fake_live import fake_opener
from tests.helpers import api_client, make_app
from tests.relay_support import ORIGIN, Wire, live_record, make_env


@pytest.fixture
def env(settings):
    return make_env(settings)


def at(env, address: str, **headers):
    """A browser at another address, on the same app."""
    return api_client(env.app, client=(address, 5000), headers=headers)


def ticket_for(env, client=None) -> str:
    client = client or env.client
    reply = client.post(f"/api/briefings/{env.bid}/rounds/1/live-session")
    assert reply.status_code == 200, reply.text
    return reply.json()["ticket"]


def drained(app, timeout: float = 3.0) -> None:
    """Wait until every Live socket of the app has finished closing. A client that leaves a `with`
    block does not wait for the server's side of it."""
    sockets = app.state.ctx.relay.sockets
    deadline = time.monotonic() + timeout
    while sockets._open and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sockets._open == {}


def with_limits(env, **overrides):
    """The same briefing and store under other relay settings, with a recording Live opener."""
    handles: list = []
    s = env.settings.with_overrides(**overrides)
    app, *_ = make_app(s, live_opener=fake_opener(handles), store=env.store)
    return app, handles, api_client(app)


def test_the_defaults_are_the_contracts():
    s = Settings()
    assert (s.ws_first_message_s, s.ws_first_cue_s, s.ws_idle_s) == (5.0, 30.0, 60.0)
    assert (s.max_sockets_per_ip, s.ws_max_session_s) == (4, 600.0)


class TestTheSocketCap:
    def test_the_cap_defaults_to_4_and_is_read_from_the_environment(self):
        assert Settings.from_env({}).max_sockets_per_ip == 4
        assert Settings.from_env({"SIB_MAX_SOCKETS_PER_IP": " 2 "}).max_sockets_per_ip == 2

    @pytest.mark.parametrize("value", ["0", "-1", "four", "1.5"])
    def test_a_bad_value_fails_at_start_up(self, value):
        with pytest.raises(ConfigError, match="SIB_MAX_SOCKETS_PER_IP"):
            Settings.from_env({"SIB_MAX_SOCKETS_PER_IP": value})

    def test_review_f6_ticketless_sockets_are_held_only_up_to_the_cap(self, settings):
        """Five ticketless sockets were accepted and held, none reaching Live. Now four are held
        (until their first message is overdue) and the fifth is refused at once."""
        env = make_env(settings.with_overrides(ws_first_message_s=1.0, max_sockets_per_ip=4))
        first: dict[int, tuple] = {}
        started = threading.Barrier(5, timeout=10)

        def connect_and_wait(i):
            url = f"/api/live/{env.bid}/1"
            with env.client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
                started.wait()  # all five are open before any reads
                wire = Wire(ws)
                first[i] = (time.monotonic(), wire.next(), wire.next())

        threads = [threading.Thread(target=connect_and_wait, args=(i,)) for i in range(5)]
        t0 = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(15)

        codes = sorted(frame[1][1]["code"] for frame in first.values())
        assert codes == ["bad_message"] * 4 + ["limit"]
        refused = next(f for f in first.values() if f[1][1]["code"] == "limit")
        assert refused[2] == ("close", 4429) and refused[0] - t0 < 0.9  # at once, not after 1 s
        assert env.handles == []  # none reached Live

    def test_the_socket_over_the_cap_is_refused_with_limit_4429_before_the_ticket_is_read(
        self, env
    ):
        app, handles, client = with_limits(env, max_sockets_per_ip=2)
        t = ticket_for(env, client)
        url = f"/api/live/{env.bid}/1"
        with client.websocket_connect(url, headers={"origin": ORIGIN}):  # holds one
            with client.websocket_connect(url, headers={"origin": ORIGIN}):  # holds two
                with client.websocket_connect(url, headers={"origin": ORIGIN}) as refused:
                    wire = Wire(refused)
                    wire.send(type="start", ticket=t)  # never read: the socket is already refused
                    error = wire.next()
                    assert error[0] == "json" and error[1]["code"] == "limit"
                    assert wire.next() == ("close", 4429)
        assert handles == []  # no Live connection was opened for any of them
        drained(app)
        # The ticket was not spent by the refused socket: it still opens a session.
        with client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
            assert Wire(ws).start(t)[1]["type"] == "ready"

    def test_another_address_is_not_affected(self, env):
        app, handles, client = with_limits(env, max_sockets_per_ip=1)
        other = api_client(app, client=("203.0.113.5", 5000))
        url = f"/api/live/{env.bid}/1"
        with client.websocket_connect(url, headers={"origin": ORIGIN}):
            with other.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
                wire = Wire(ws)
                wire.send(type="start", ticket="x" * 43)
                assert (
                    wire.next()[1]["code"] == "bad_ticket"
                )  # past the cap, refused for its ticket

    def test_the_address_is_the_one_the_front_end_appended_not_what_the_caller_wrote(self, env):
        app, handles, _ = with_limits(env, max_sockets_per_ip=1)
        url = f"/api/live/{env.bid}/1"
        held = api_client(app, headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.9"})
        forger = api_client(app, headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.9"})
        elsewhere = api_client(app, headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.10"})
        with held.websocket_connect(url, headers={"origin": ORIGIN}):
            with forger.websocket_connect(url, headers={"origin": ORIGIN}) as refused:
                assert (
                    Wire(refused).next()[1]["code"] == "limit"
                )  # a new leftmost entry buys nothing
            with elsewhere.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
                wire = Wire(ws)
                wire.send(type="start", ticket="x" * 43)
                assert wire.next()[1]["code"] == "bad_ticket"  # a different client is let in

    def test_every_way_a_socket_ends_gives_its_slot_back(self, env):
        app, handles, client = with_limits(env, max_sockets_per_ip=1, ws_first_message_s=0.3)
        url = f"/api/live/{env.bid}/1"
        for _ in range(3):  # a bad ticket, a silent socket (first message times out), a clean stop
            with client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
                wire = Wire(ws)
                wire.send(type="start", ticket="x" * 43)
                assert wire.next()[1]["code"] == "bad_ticket"
                assert wire.next() == ("close", 4401)
            with client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
                assert Wire(ws).next()[1]["code"] == "bad_message"
            drained(app)
            with client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
                wire = Wire(ws)
                assert wire.start(ticket_for(env, client))[1]["type"] == "ready"
                wire.send(type="stop")
                assert wire.next() == ("close", 1000)
        drained(app)  # the table holds an address only while it has a socket open

    async def test_a_tab_closed_without_a_stop_frame_gives_its_slot_back_too(self, env):
        from sayitback.live_relay import LiveRelay
        from tests.fake_live import DISCONNECT, FakeWebSocket, text_message

        app, handles, client = with_limits(env, max_sockets_per_ip=1)
        t = ticket_for(env, client)
        ws = FakeWebSocket([text_message(type="start", ticket=t)])
        relay = LiveRelay(ws, app.state.ctx.relay, env.bid, 1)
        task = asyncio.create_task(relay.run())
        for _ in range(500):  # bounded wait for `ready`
            if any(kind == "json" and f.get("type") == "ready" for kind, f in ws.sent):
                break
            await asyncio.sleep(0.01)
        assert app.state.ctx.relay.sockets._open == {"203.0.113.7": 1}  # held while it runs
        ws._incoming.put_nowait(DISCONNECT)  # the tab was closed: no stop frame
        await asyncio.wait_for(task, 5)
        assert app.state.ctx.relay.sockets._open == {}

    def test_a_refused_origin_does_not_count(self, env):
        app, handles, client = with_limits(env, max_sockets_per_ip=1)
        url = f"/api/live/{env.bid}/1"
        for _ in range(3):
            with (
                pytest.raises(WebSocketDisconnect),
                client.websocket_connect(url, headers={"origin": "https://evil.example"}),
            ):
                pass
        assert app.state.ctx.relay.sockets._open == {}


class TestOpenSockets:
    def test_an_address_may_hold_up_to_the_limit(self):
        sockets = OpenSockets()
        assert [sockets.admit("a", 2) for _ in range(3)] == [True, True, False]
        assert sockets.admit("b", 2)  # another address

    def test_a_released_slot_can_be_taken_again_and_the_table_empties(self):
        sockets = OpenSockets()
        sockets.admit("a", 1)
        assert not sockets.admit("a", 1)
        sockets.release("a")
        assert sockets.admit("a", 1)
        sockets.release("a")
        assert sockets._open == {}

    def test_releasing_what_was_never_taken_leaves_nothing_behind(self):
        sockets = OpenSockets()
        sockets.release("never")
        assert sockets._open == {}


class TestTheFirstCue:
    def session(self, env, **overrides):
        app, handles, client = with_limits(env, **overrides)
        return handles, client, ticket_for(env, client)

    def test_no_cue_within_the_time_ends_the_session_and_frees_the_round(self, env):
        handles, client, t = self.session(env, ws_first_cue_s=0.3, ws_idle_s=5.0)
        started = time.monotonic()
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            assert wire.start(t)[1]["type"] == "ready"
            error = wire.next()
            assert (
                error[1]["code"] == "limit" and "No cue arrived within 0.3 s" in error[1]["message"]
            )
            assert wire.next() == ("close", 4429)
        assert time.monotonic() - started < 2.0  # at 0.3 s, not at the 5 s idle limit
        assert handles[0].texts == []  # nothing reached the model
        # The round's lease was released: its second ticket opens a session at once.
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            assert Wire(ws).start(ticket_for(env, client))[1]["type"] == "ready"

    def test_audio_before_the_first_cue_does_not_extend_it(self, env):
        handles, client, t = self.session(env, ws_first_cue_s=0.5, ws_idle_s=5.0)
        done = threading.Event()
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.start(t)

            def stream():  # dropped outside a window: not even activity
                while not done.is_set():
                    ws.send_bytes(b"\x00\x00")
                    done.wait(0.1)

            sender = threading.Thread(target=stream, daemon=True)
            sender.start()
            started = time.monotonic()
            error = wire.next()
            done.set()
            sender.join(2)
            assert error[1]["code"] == "limit" and "No cue arrived" in error[1]["message"]
            assert time.monotonic() - started < 2.0  # at 0.5 s, whatever was streamed meanwhile

    def test_a_cue_in_time_ends_the_first_cue_deadline(self, env):
        handles, client, t = self.session(env, ws_first_cue_s=0.4, ws_idle_s=5.0)
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.start(t)
            time.sleep(0.2)
            wire.send(type="cue", cue="READ_INSTRUCTION")
            wire.until("turn_complete")
            time.sleep(0.5)  # past 0.4 s from ready: the session is alive, idle is 5 s
            wire.send(type="stop")
            assert wire.next() == ("close", 1000)
        assert live_record(env)["delivered"] == {"instruction": "said:READ_INSTRUCTION"}


class TestOnlyAcceptedFramesResetTheIdleClock:
    def test_review_f5_audio_the_relay_drops_does_not_keep_a_session_alive(self, env):
        """It held a session past three times the idle limit with no cue and nothing for the model."""
        app, handles, client = with_limits(env, ws_idle_s=0.6, ws_first_cue_s=30.0)
        t = ticket_for(env, client)
        done = threading.Event()
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.start(t)

            def stream():  # outside any answer window, a frame every 0.2 s: a third of the idle limit
                while not done.is_set():
                    ws.send_bytes(b"\x00\x00")
                    done.wait(0.2)

            sender = threading.Thread(target=stream, daemon=True)
            sender.start()
            started = time.monotonic()
            error = wire.next()
            waited = time.monotonic() - started
            done.set()
            sender.join(2)
            assert error[1]["code"] == "limit" and "idle" in error[1]["message"]
            assert wire.next() == ("close", 4429)
        assert waited < 1.5  # about 0.6 s: the frames the relay dropped bought no time
        assert handles[0].texts == [] and not any(r.blob for r in handles[0].requests)

    def test_audio_that_reached_the_model_does_keep_it_alive(self, env):
        app, handles, client = with_limits(env, ws_idle_s=0.5)
        t = ticket_for(env, client)
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.start(t)
            wire.send(type="cue", cue="ASK", qid="q1")
            wire.until("turn_complete")
            wire.send(type="answer_start", qid="q1")
            for _ in range(
                8
            ):  # 1.2 s of answer, more than twice the idle limit, a frame each 0.15 s
                time.sleep(0.15)
                wire.audio(1)
            wire.send(type="answer_end", qid="q1")
            frames = wire.until("turn_complete")
            assert not [f for f in wire.jsons(frames) if f["type"] == "error"]
            wire.send(type="stop")
            assert wire.next() == ("close", 1000)

    def test_a_cue_resets_it_so_the_wait_runs_from_the_cue_not_from_ready(self, env):
        app, handles, client = with_limits(env, ws_idle_s=0.5, ws_first_cue_s=30.0)
        t = ticket_for(env, client)
        with client.websocket_connect(f"/api/live/{env.bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.start(t)
            time.sleep(0.35)  # nearly idle
            wire.send(type="cue", cue="READ_INSTRUCTION")
            wire.until("turn_complete")
            started = time.monotonic()
            error = wire.next()
            assert error[1]["code"] == "limit" and "idle" in error[1]["message"]
            assert time.monotonic() - started > 0.3  # a fresh half second, not what was left


class TestTheIdleClock:
    """The clock on its own, with short times."""

    async def test_it_runs_from_the_last_accepted_frame_and_touch_pushes_it_back(self):
        clock = IdleClock(idle_s=0.3, first_cue_s=30.0)
        clock.start()
        clock.cue_seen()
        await asyncio.sleep(0.2)
        clock.touch()
        await asyncio.sleep(0.2)  # 0.4 s since start, 0.2 since the touch: not idle yet
        assert clock._left() > 0

        async def never():
            await asyncio.sleep(10)

        assert await clock.receive(never) is None and clock.expiry() == IDLE_MESSAGE

    async def test_playing_speech_is_not_idleness_and_a_barge_in_ends_the_allowance(self):
        clock = IdleClock(idle_s=0.2, first_cue_s=30.0)
        clock.start()
        clock.cue_seen()
        clock.speak(1.0)  # a second of queued speech
        await asyncio.sleep(0.5)
        assert clock._left() > 0.4  # still playing: the idle time starts when it has played out
        clock.hush()
        assert clock._left() < 0  # flushed: quiet since 0.5 s ago, over the 0.2 s limit

    async def test_the_first_cue_has_its_own_deadline_from_ready(self):
        clock = IdleClock(idle_s=10.0, first_cue_s=0.2)
        clock.start()
        clock.touch()
        assert 0 < clock._left() <= 0.2
        await asyncio.sleep(0.25)
        assert clock._left() < 0 and "No cue arrived within 0.2 s of ready" in clock.expiry()
        clock.cue_seen()
        assert clock._left() > 9  # the cue was too late for the message, but a seen cue ends it

    async def test_a_message_that_arrives_in_time_is_returned_whole(self):
        clock = IdleClock(idle_s=1.0, first_cue_s=30.0)
        clock.start()

        async def message():
            return {"type": "websocket.receive", "text": "{}"}

        assert await clock.receive(message) == {"type": "websocket.receive", "text": "{}"}
