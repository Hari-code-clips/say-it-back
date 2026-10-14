"""The daily Gemini cap (API.md, "Daily cap"): the setting, the reservation, the UTC day, the log
line, and the two hooks (`run_check`, `Tts.speak`) the API reserves through."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from sayitback import pipeline
from sayitback.daily_cap import (
    LIVE_TICKET_CALLS,
    SCRIPT_RETRY_CALLS,
    DailyCap,
    check_calls,
    day_key,
    round_calls,
    seconds_until_utc_midnight,
)
from sayitback.errors import RateLimited, Unprocessable
from sayitback.pipeline import run_check
from sayitback.settings import ConfigError, Settings
from sayitback.store import LocalStore
from sayitback.tts import Tts
from tests.cap_support import NOON, UNTIL_MIDNIGHT, Clock
from tests.check_support import QUESTIONS, STEPS, scenario
from tests.fake_firestore import FakeBackedStore
from tests.fakes import FakeTtsClient, fake_runtime, tone_wav

ADDRESS = "203.0.113.7"


@pytest.fixture(params=["local", "firestore"])
def store(request, tmp_path):
    return LocalStore(tmp_path / ".data") if request.param == "local" else FakeBackedStore()


# The setting ---------------------------------------------------------------------------------


def test_the_cap_defaults_to_300_and_reads_the_environment():
    assert Settings.from_env({}).daily_gemini_calls == 300
    assert Settings.from_env({"SIB_DAILY_GEMINI_CALLS": " 50 "}).daily_gemini_calls == 50


def test_zero_is_valid_it_is_the_kill_switch():
    assert Settings.from_env({"SIB_DAILY_GEMINI_CALLS": "0"}).daily_gemini_calls == 0


@pytest.mark.parametrize("value", ["-1", " -5 ", "abc", "1.5", "1e3", "300 calls"])
def test_anything_but_an_integer_of_zero_or_more_fails_at_start_up(value):
    with pytest.raises(ConfigError, match="SIB_DAILY_GEMINI_CALLS"):
        Settings.from_env({"SIB_DAILY_GEMINI_CALLS": value})


# What each request is charged ----------------------------------------------------------------


def test_the_cost_table():
    assert round_calls("initial", "") == round_calls("initial", "a note") == 2
    assert round_calls("reexplain", "a note") == 2
    # No note: the re-explain call comes first, then script and back-translation.
    assert round_calls("reexplain", "") == 3
    # A script retry is one more call, reserved just before it runs (test_daily_cap_retry.py).
    assert SCRIPT_RETRY_CALLS == 1
    assert check_calls(Settings(judge_passes=2)) == 3
    assert check_calls(Settings(judge_passes=1)) == 2
    # A weight, not a call count: one Live session, bounded by the relay's once-per-session cues.
    assert LIVE_TICKET_CALLS == 4


# The reservation -----------------------------------------------------------------------------


async def test_a_reservation_that_fits_is_counted_and_one_that_does_not_is_refused_whole(store):
    cap = DailyCap(store, 5, Clock())
    await cap.reserve(3, ADDRESS)
    with pytest.raises(RateLimited) as err:
        await cap.reserve(3, ADDRESS)
    assert (err.value.status, err.value.code) == (429, "daily_limit")
    assert err.value.retry_after == UNTIL_MIDNIGHT
    await cap.reserve(2, ADDRESS)  # the refused three used nothing, so two still fit
    with pytest.raises(RateLimited):
        await cap.reserve(1, ADDRESS)


async def test_the_cap_starts_again_at_the_next_utc_midnight(store):
    clock = Clock(datetime(2026, 10, 14, 23, 59, 59, 500_000, tzinfo=UTC))
    cap = DailyCap(store, 2, clock)
    await cap.reserve(2, ADDRESS)
    with pytest.raises(RateLimited) as err:
        await cap.reserve(1, ADDRESS)
    assert err.value.retry_after == 1  # half a second to go, rounded up
    clock.now = datetime(2026, 10, 15, 0, 0, 0, tzinfo=UTC)
    await cap.reserve(2, ADDRESS)  # a new day: the whole cap again
    with pytest.raises(RateLimited) as err:
        await cap.reserve(1, ADDRESS)
    assert err.value.retry_after == 24 * 3600


async def test_zero_refuses_every_reservation(store):
    with pytest.raises(RateLimited) as err:
        await DailyCap(store, 0, Clock()).reserve(1, ADDRESS)
    assert err.value.code == "daily_limit"


async def test_concurrent_reservations_that_would_cross_the_cap_let_exactly_one_through(store):
    cap = DailyCap(store, 3, Clock())
    results = await asyncio.gather(
        cap.reserve(2, ADDRESS), cap.reserve(2, ADDRESS), return_exceptions=True
    )
    assert results.count(None) == 1
    assert sum(isinstance(r, RateLimited) for r in results) == 1


async def test_a_store_failure_propagates_so_the_request_is_refused_not_let_through(tmp_path):
    class Down(LocalStore):
        async def reserve_calls(self, day, calls, cap, **share):
            raise OSError("store down")

    with pytest.raises(OSError):
        await DailyCap(Down(tmp_path), 300, Clock()).reserve(1, ADDRESS)


async def test_a_reservation_is_at_least_one_call(store):
    for calls in (0, -2):  # a negative amount would refund, and nothing is refunded
        with pytest.raises(ValueError):
            await DailyCap(store, 300, Clock()).reserve(calls, ADDRESS)


# The UTC day ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "day", "seconds"),
    [
        (NOON, "20261014", 12 * 3600),
        (datetime(2026, 10, 14, 0, 0, 0, tzinfo=UTC), "20261014", 24 * 3600),  # midnight itself
        (datetime(2026, 10, 14, 23, 59, 59, tzinfo=UTC), "20261014", 1),
        (datetime(2026, 10, 14, 23, 59, 59, 999_999, tzinfo=UTC), "20261014", 1),  # never 0
        (datetime(2026, 12, 31, 18, 0, tzinfo=UTC), "20261231", 6 * 3600),  # a year end
        # 06:00 in Singapore on the 15th is still the 14th in UTC.
        (datetime(2026, 10, 15, 6, 0, tzinfo=timezone(timedelta(hours=8))), "20261014", 2 * 3600),
    ],
)
def test_the_day_and_the_seconds_to_the_next_midnight_are_in_utc(now, day, seconds):
    assert (day_key(now), seconds_until_utc_midnight(now)) == (day, seconds)


# The log line --------------------------------------------------------------------------------


async def test_the_first_refusal_each_utc_day_logs_one_warning_with_no_request_content(
    store, caplog
):
    clock = Clock()
    cap = DailyCap(store, 1, clock)
    await cap.reserve(1, ADDRESS)
    with caplog.at_level("WARNING", logger="sayitback.daily_cap"):
        for _ in range(3):
            with pytest.raises(RateLimited):
                await cap.reserve(1, ADDRESS)
        assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
            ("WARNING", "daily Gemini call cap reached: limit 1, UTC day 20261014")
        ]
        clock.now += timedelta(days=1)
        await cap.reserve(1, ADDRESS)
        with pytest.raises(RateLimited):
            await cap.reserve(1, ADDRESS)
    assert [r.getMessage()[-8:] for r in caplog.records] == ["20261014", "20261015"]


# The hooks the API reserves through ----------------------------------------------------------


def check_args(**overrides):
    args = dict(
        steps=STEPS, questions=QUESTIONS, clips={"q1": tone_wav()}, worker_lang="ta",
        supervisor_lang="en",
    )  # fmt: skip
    return args | overrides


async def test_run_check_awaits_before_call_once_inputs_are_valid_and_before_any_model_call(
    settings,
):
    rt, llm = fake_runtime(scenario(), settings)
    awaited = []

    async def before_call():
        awaited.append(len(llm.seen))

    await run_check(runtime=rt, before_call=before_call, **check_args())

    assert awaited == [0]  # once, with no model call made yet
    assert len(llm.seen) == 3


async def test_run_check_does_not_await_before_call_for_invalid_input(settings):
    rt, llm = fake_runtime(scenario(), settings)
    awaited = []

    async def before_call():
        awaited.append(True)

    with pytest.raises(Unprocessable):
        await run_check(runtime=rt, before_call=before_call, **check_args(clips={"q9": tone_wav()}))

    assert awaited == [] and llm.seen == []


async def test_a_refusing_hook_stops_run_check_before_any_model_call(settings):
    rt, llm = fake_runtime(scenario(), settings)

    async def refuse():
        raise RateLimited("no", code="daily_limit", retry_after=5)

    with pytest.raises(RateLimited):
        await run_check(runtime=rt, before_call=refuse, **check_args())

    assert llm.seen == []


async def test_tts_awaits_before_call_on_a_miss_and_never_on_a_cache_hit(settings):
    client = FakeTtsClient()
    rt, _ = fake_runtime(settings=settings, tts_client=client)
    tts, awaited = Tts(rt), []

    async def before_call():
        awaited.append(len(client.calls))

    await tts.speak("same text", before_call=before_call)
    await tts.speak("same text", before_call=before_call)  # a hit: free
    await tts.speak("other text", before_call=before_call)

    assert awaited == [0, 1] and len(client.calls) == 2


async def test_a_refusing_hook_stops_tts_before_the_model_call(settings):
    client = FakeTtsClient()
    rt, _ = fake_runtime(settings=settings, tts_client=client)

    async def refuse():
        raise RateLimited("no", code="daily_limit", retry_after=5)

    with pytest.raises(RateLimited):
        await Tts(rt).speak("text", before_call=refuse)

    assert client.calls == []


# The eval harness ----------------------------------------------------------------------------


async def test_the_eval_harness_is_never_capped(settings, monkeypatch):
    """eval/check_adapter.py awaits `pipeline.run_check` with no runtime and no hook, so it
    never reaches the cap, whatever SIB_DAILY_GEMINI_CALLS says."""
    monkeypatch.setenv("SIB_DAILY_GEMINI_CALLS", "0")
    assert Settings.from_env().daily_gemini_calls == 0
    rt, llm = fake_runtime(scenario(), settings)
    monkeypatch.setattr(pipeline, "get_runtime", lambda: rt)  # the adapter's default runtime

    result = await run_check(**check_args())

    assert [r.step_id for r in result.ratings] == ["s1", "s2", "s3"] and len(llm.seen) == 3
