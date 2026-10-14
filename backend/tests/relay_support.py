"""Shared pieces of the Live relay tests: a WebSocket test client and the app under test.

The fake runner consumes the real LiveRequestQueue, so `handle.requests` is exactly what would
have reached Gemini Live.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from tests.fake_live import fake_opener
from tests.helpers import ORIGIN, api_client, drive_to_round, make_app

PCM = b"\x01\x00" * 320  # 20 ms at 16 kHz


class Wire:
    """A thin test client over the Starlette WebSocket session."""

    def __init__(self, ws):
        self.ws = ws

    def send(self, **frame):
        self.ws.send_text(json.dumps(frame))

    def raw(self, text: str):
        self.ws.send_text(text)

    def audio(self, n_frames: int = 1, data: bytes = PCM):
        for _ in range(n_frames):
            self.ws.send_bytes(data)

    def next(self):
        message = self.ws.receive()
        if message["type"] == "websocket.close":
            return ("close", message["code"])
        if message.get("bytes") is not None:
            return ("bin", message["bytes"])
        return ("json", json.loads(message["text"]))

    def until(self, kind: str):
        """Frames up to and including the first JSON frame of `type == kind`."""
        got = []
        while True:
            frame = self.next()
            got.append(frame)
            if frame[0] == "close" or (frame[0] == "json" and frame[1]["type"] == kind):
                return got

    def jsons(self, frames):
        return [f[1] for f in frames if f[0] == "json"]

    def start(self, ticket: str):
        self.send(type="start", ticket=ticket)
        return self.next()


def make_env(settings) -> SimpleNamespace:
    """An app with fakes, a driven-to-round-1 briefing and a recording Live opener."""
    s = settings.with_overrides(max_tickets_per_round=20)
    handles = []
    app, _rt, llm, store = make_app(s, live_opener=fake_opener(handles))
    client = api_client(app)
    bid, rnd = drive_to_round(client)
    return SimpleNamespace(
        client=client, handles=handles, bid=bid, rnd=rnd, store=store, settings=s, app=app, llm=llm
    )


def ticket(env, n=1) -> str:
    response = env.client.post(f"/api/briefings/{env.bid}/rounds/{n}/live-session")
    assert response.status_code == 200, response.text
    return response.json()["ticket"]


def connect(env, n=1, origin=ORIGIN):
    headers = {"origin": origin} if origin else {}
    return env.client.websocket_connect(f"/api/live/{env.bid}/{n}", headers=headers)


def open_session(env, ws):
    wire = Wire(ws)
    assert wire.start(ticket(env))[1]["type"] == "ready"
    return wire


def request_kind(r) -> str:
    """What one LiveRequest on the queue is."""
    for name, kind in (("activity_start", "start"), ("activity_end", "end"), ("blob", "audio")):
        if getattr(r, name):
            return kind
    if r.audio_stream_end:
        return "stream_end"
    return "text" if r.content else "close"


def live_record(env):
    return env.client.get(f"/api/briefings/{env.bid}").json()["rounds"][0].get("live")
