"""Shared pieces of the daily-cap tests: a movable clock, a ledger of every reservation, and the API
built over them with fakes for the model layer."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx

from sayitback.settings import Settings
from sayitback.store import LocalStore, Store
from sayitback.store.base import Reserved
from tests.fakes import FakeTtsClient, Scenario, tone_wav
from tests.helpers import (
    DEVICE,
    PANEL,
    SPOKEN,
    api_client,
    drive_to_round,
    make_app,
    post_check,
    seed_round,
)

NOON = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
TODAY = "20261014"
UNTIL_MIDNIGHT = 12 * 3600  # NOON to the next 00:00 UTC
ITEM_ID = "panel-isolation.q1.ta.complete.clean"


class Clock:
    """A movable UTC clock: `clock()` reads it, `clock.now = ...` moves it."""

    def __init__(self, now: datetime = NOON) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@dataclass(frozen=True)
class Reservation:
    day: str
    calls: int
    granted: bool
    model_calls: int  # model calls the fakes had seen when the reservation was made
    outcome: Reserved = Reserved.GRANTED
    address: str = ""  # the hash the per-address count is kept under ("" when there is none)


class Ledger:
    """Records every `reserve_calls` on a store, and how many model calls had been made by then."""

    def __init__(self, store: Store) -> None:
        self.entries: list[Reservation] = []
        self.model_calls: Callable[[], int] = lambda: 0
        real = store.reserve_calls

        async def recording(day: str, calls: int, cap: int, **share: Any) -> Reserved:
            seen = self.model_calls()
            outcome = await real(day, calls, cap, **share)
            entry = Reservation(day, calls, bool(outcome), seen, outcome, share.get("address", ""))
            self.entries.append(entry)
            return outcome

        store.reserve_calls = recording  # type: ignore[method-assign]

    @property
    def spent(self) -> int:
        return sum(r.calls for r in self.entries if r.granted)


def write_eval_set(settings: Settings) -> str:
    """One stored clip for endpoint 19 under settings.eval_dir. Returns the item id."""
    testset = settings.eval_dir / "testset"
    (testset / "audio").mkdir(parents=True)
    (testset / "audio" / "x.wav").write_bytes(tone_wav())
    item = {"id": ITEM_ID, "taskId": "panel-isolation", "questionId": "q1", "workerLang": "ta",
            "pattern": "complete", "noise": "clean", "source": "synthetic_tts", "answer": "a",
            "answerGloss": "g", "gold": {"s1": "covered", "s2": "covered", "s3": "covered"},
            "audio": "audio/x.wav"}  # fmt: skip
    doc = {
        "version": "v",
        "questions": {"panel-isolation": {"q1": {"ta": "கேள்வி?"}}},
        "items": [item],
    }
    (testset / "items.json").write_text(json.dumps(doc), encoding="utf-8")
    return ITEM_ID


def new_briefing(env: SimpleNamespace) -> str:
    """A draft briefing. Creating one calls no model."""
    return env.client.post("/api/briefings", json=PANEL).json()["id"]


def confirmed(env: SimpleNamespace) -> str:
    """A briefing with its steps confirmed (one extract call), before round 1."""
    bid = new_briefing(env)
    steps = env.client.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
    env.client.put(f"/api/briefings/{bid}/steps", json={"steps": steps})
    return bid


def judged(env: SimpleNamespace) -> str:
    """A briefing whose round 1 is judged, with s2 and s3 still open (the round_1_scenario)."""
    bid = drive_to_round(env.client)[0]
    post_check(env.client, bid, 1)
    return bid


def script_for_open_steps(scenario: Scenario) -> None:
    """Make the next script cover s2 and s3 only, as a re-explain round's must."""
    steps = [m for m in scenario.script["step_map"] if m["step_id"] != "s1"]
    questions = [{"text": "புதிய கேள்வி?", "step_ids": ["s2", "s3"]}]
    scenario.script = {**scenario.script, "step_map": steps, "questions": questions}


def speak(env: SimpleNamespace, key: str = "a", client: Any = None):
    """POST /api/tts (endpoint 12) for one line of a briefing the test caller owns (seeded in the
    store on first use: no model call, no reservation). A key names a line: the same key is the same
    text (a cache hit the second time) and another key is another text. Every line is a prefix of
    the round's instruction, so the request is a valid one."""
    if env.speak_to is None:
        env.speak_to = seed_round(env.store)
    text = SPOKEN[: env.lines.setdefault(key, len(env.lines) + 1)]
    body = {"briefingId": env.speak_to, "n": 1, "text": text}
    return (client or env.client).post("/api/tts", json=body)


def hear(env: SimpleNamespace):
    """POST /api/transcribe (endpoint 3) with a two-second clip."""
    audio = {"audio": ("a.wav", tone_wav(), "audio/wav")}
    return env.client.post("/api/transcribe", files=audio, data={"lang": "en"})


def over_http(
    env: SimpleNamespace, device: str = DEVICE, peer: str = "127.0.0.1"
) -> httpx.AsyncClient:
    """An async client on the app (one browser at `peer`), for requests that really run at the same
    time."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=env.app, client=(peer, 123)),
        base_url="http://test",
        headers={"X-SIB-Device": device},
    )


def make_capped(
    settings: Settings,
    scenario: Scenario | None = None,
    *,
    limit: int = 300,
    clock: Callable[[], datetime] | None = None,
    store: Store | None = None,
    live_opener: Any = None,
    **overrides: object,
) -> SimpleNamespace:
    """The API over fakes with SIB_DAILY_GEMINI_CALLS=`limit` and a ledger on the store (the local
    store unless one is given). `overrides` are more Settings fields."""
    s = settings.with_overrides(daily_gemini_calls=limit, **overrides)
    store = store or LocalStore(s.data_dir)
    ledger = Ledger(store)
    tts = FakeTtsClient()
    app, _rt, llm, _store = make_app(
        s, scenario, store=store, tts_client=tts, clock=clock or Clock(), live_opener=live_opener
    )
    ledger.model_calls = lambda: len(llm.seen) + len(tts.calls)
    return SimpleNamespace(
        app=app, client=api_client(app), llm=llm, tts=tts, store=store, ledger=ledger, settings=s,
        speak_to=None, lines={},
    )  # fmt: skip
