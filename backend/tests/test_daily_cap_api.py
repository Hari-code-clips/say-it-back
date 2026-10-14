"""The daily Gemini cap through the HTTP API: what each endpoint reserves and when, what is refused
(429 `daily_limit`, Retry-After, no model call), the UTC day, the kill switch and the per-IP
limit. Instances and bursts: test_daily_cap_shared.py."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial

import pytest

from sayitback.store import LocalStore
from tests.cap_support import (
    TODAY,
    UNTIL_MIDNIGHT,
    Clock,
    confirmed,
    hear,
    judged,
    make_capped,
    new_briefing,
    script_for_open_steps,
    speak,
    write_eval_set,
)
from tests.fake_live import fake_opener
from tests.flow_support import round_1_scenario
from tests.helpers import ORIGIN, PANEL, api_client, drive_to_round, error_of, post_check
from tests.relay_support import Wire


def spend(env, send):
    """Send one request. Returns (response, the reservation it made, the model calls it made).
    The request must have reserved exactly once, and before its first model call."""
    entries, before = len(env.ledger.entries), env.ledger.model_calls()
    response = send()
    made = env.ledger.entries[entries:]
    assert len(made) == 1, made
    assert made[0].model_calls == before, "the reservation came after a model call"
    return response, made[0], env.ledger.model_calls() - before


class TestWhatEachEndpointCosts:
    """Each cost is the number of model calls the request really makes (counted on the fakes). A
    round whose script needs a retry reserves one more, just before it: test_daily_cap_retry.py."""

    def test_transcribe_is_one_call(self, settings):
        env = make_capped(settings)
        response, reservation, made = spend(env, partial(hear, env))
        assert (response.status_code, reservation.calls, made) == (200, 1, 1)

    def test_extract_is_one_call(self, settings):
        env = make_capped(settings)
        bid = new_briefing(env)
        send = partial(env.client.post, f"/api/briefings/{bid}/steps/extract")
        response, reservation, made = spend(env, send)
        assert (response.status_code, reservation.calls, made) == (200, 1, 1)

    def test_round_one_is_two_calls_the_script_and_its_back_translation(self, settings):
        env = make_capped(settings, round_1_scenario())
        bid = confirmed(env)
        response, reservation, made = spend(
            env, partial(env.client.post, f"/api/briefings/{bid}/rounds", json={})
        )
        assert (response.status_code, reservation.calls, made) == (200, 2, 2)

    @pytest.mark.parametrize(
        ("body", "calls"),
        [({"supervisorNote": "Lock it and test it."}, 2), ({}, 3)],
        ids=["with a supervisor note", "without one: the re-explain call comes first"],
    )
    def test_a_re_explain_round_is_two_calls_or_three_without_a_note(self, settings, body, calls):
        scenario = round_1_scenario()
        env = make_capped(settings, scenario)
        bid = judged(env)
        script_for_open_steps(scenario)
        response, reservation, made = spend(
            env, partial(env.client.post, f"/api/briefings/{bid}/rounds", json=body)
        )
        assert (response.status_code, reservation.calls, made) == (200, calls, calls)

    def test_a_live_ticket_is_four_and_the_socket_that_uses_it_costs_nothing_more(self, settings):
        handles = []
        env = make_capped(settings, live_opener=fake_opener(handles))
        bid = drive_to_round(env.client)[0]
        response, reservation, made = spend(
            env, partial(env.client.post, f"/api/briefings/{bid}/rounds/1/live-session")
        )
        assert (response.status_code, reservation.calls, made) == (200, 4, 0)
        spent = env.ledger.spent

        with env.client.websocket_connect(f"/api/live/{bid}/1", headers={"origin": ORIGIN}) as ws:
            assert Wire(ws).start(response.json()["ticket"])[1]["type"] == "ready"

        assert len(handles) == 1 and env.ledger.spent == spent  # a Live session ran, uncharged

    def test_tts_is_one_call(self, settings):
        env = make_capped(settings)
        response, reservation, made = spend(env, partial(speak, env, "hello"))
        assert (response.status_code, reservation.calls, made) == (200, 1, 1)

    @pytest.mark.parametrize("passes", [1, 2])
    def test_a_check_is_the_transcriber_plus_one_call_per_judge_pass(self, settings, passes):
        env = make_capped(settings, round_1_scenario(), judge_passes=passes)
        bid = drive_to_round(env.client)[0]
        response, reservation, made = spend(env, partial(post_check, env.client, bid, 1))
        assert (response.status_code, reservation.calls, made) == (200, 1 + passes, 1 + passes)

    @pytest.mark.parametrize("passes", [1, 2])
    def test_an_eval_try_costs_the_same_as_a_check(self, settings, passes):
        env = make_capped(settings, round_1_scenario(), judge_passes=passes)
        item = write_eval_set(settings)
        response, reservation, made = spend(
            env, partial(env.client.post, f"/api/eval/items/{item}/try")
        )
        assert (response.status_code, reservation.calls, made) == (200, 1 + passes, 1 + passes)


class TestWhenTheDayIsUsedUp:
    def test_the_request_is_429_daily_limit_with_retry_after_and_no_model_call(self, settings):
        env = make_capped(settings, limit=1)
        assert speak(env, "one").status_code == 200
        refused = speak(env, "two")
        assert error_of(refused) == (429, "daily_limit")
        assert refused.headers["retry-after"] == str(UNTIL_MIDNIGHT)  # the clock is at noon UTC
        assert len(env.tts.calls) == 1

    def test_a_request_that_does_not_fit_is_refused_whole_and_the_rest_is_still_usable(
        self, settings
    ):
        env = make_capped(settings, round_1_scenario(), limit=5)
        bid = drive_to_round(env.client)[0]  # extract 1 + round 2: three of the five
        calls = env.ledger.model_calls()

        refused = post_check(env.client, bid, 1)  # needs three, two are left

        assert error_of(refused) == (429, "daily_limit")
        assert env.ledger.model_calls() == calls  # not one call of the check was made
        assert env.client.get(f"/api/briefings/{bid}").json()["status"] == "briefing"
        ticket = env.client.post(f"/api/briefings/{bid}/rounds/1/live-session")
        assert error_of(ticket) == (429, "daily_limit")  # a live ticket needs four: refused whole
        assert [speak(env, t).status_code for t in "xy"] == [200, 200]  # the two left still work
        assert error_of(speak(env, "z")) == (429, "daily_limit")  # and now all of it is gone

    def test_every_gemini_backed_endpoint_refuses_at_zero_and_nothing_reaches_the_model(
        self, settings
    ):
        scenario = round_1_scenario()
        normal = make_capped(settings, scenario)  # builds the state the endpoints need
        draft, ready = new_briefing(normal), confirmed(normal)
        rounded = drive_to_round(normal.client)[0]
        item = write_eval_set(settings)
        off = make_capped(settings, scenario, limit=0, store=LocalStore(settings.data_dir))

        replies = {
            "transcribe": hear(off),
            "extract": off.client.post(f"/api/briefings/{draft}/steps/extract"),
            "round": off.client.post(f"/api/briefings/{ready}/rounds", json={}),
            "live ticket": off.client.post(f"/api/briefings/{rounded}/rounds/1/live-session"),
            "tts": speak(off, "x"),
            "check": post_check(off.client, rounded, 1),
            "eval try": off.client.post(f"/api/eval/items/{item}/try"),
        }

        refusals = {name: error_of(reply) for name, reply in replies.items()}
        assert refusals == dict.fromkeys(replies, (429, "daily_limit"))
        assert all(r.headers["retry-after"] == str(UNTIL_MIDNIGHT) for r in replies.values())
        assert off.ledger.model_calls() == 0

    def test_the_rest_of_the_api_keeps_working_at_zero(self, settings):
        normal = make_capped(settings)
        proposed = new_briefing(normal)
        steps = normal.client.post(f"/api/briefings/{proposed}/steps/extract").json()["steps"]
        off = make_capped(settings, limit=0, store=LocalStore(settings.data_dir))

        created = off.client.post("/api/briefings", json=PANEL)
        assert created.status_code == 200
        edit = {"instruction": "Isolate it first."}
        assert (
            off.client.patch(f"/api/briefings/{created.json()['id']}", json=edit).status_code == 200
        )
        confirm = off.client.put(f"/api/briefings/{proposed}/steps", json={"steps": steps})
        assert confirm.status_code == 200
        no_go = off.client.post(f"/api/briefings/{proposed}/decision", json={"value": "no_go"})
        assert no_go.status_code == 200
        for path in ("/api/health", "/api/catalog", "/api/briefings", "/api/export/briefings.csv"):
            assert off.client.get(path).status_code == 200
        assert off.ledger.entries == []  # none of it is Gemini-backed, so none of it reserves

    def test_a_cached_tts_clip_is_free_even_when_the_day_is_used_up(self, settings):
        env = make_capped(settings, limit=1)
        first, again = speak(env, "same"), speak(env, "same")  # a miss, then a hit
        assert first.content == again.content and len(env.ledger.entries) == 1
        assert error_of(speak(env, "other")) == (429, "daily_limit")
        assert speak(env, "same").status_code == 200  # the day is gone, the cached clip is not

    def test_a_store_failure_refuses_the_request_before_any_model_call(self, settings):
        env = make_capped(settings)

        async def down(day, calls, cap, **share):
            raise OSError("store down")

        env.store.reserve_calls = down
        broken = api_client(env.app, raise_server_exceptions=False)
        response = speak(env, "x", client=broken)
        assert error_of(response) == (500, "internal_error") and env.tts.calls == []


class TestTheUtcDay:
    def test_the_next_utc_day_has_a_fresh_cap(self, settings):
        clock = Clock()
        env = make_capped(settings, limit=1, clock=clock)
        assert speak(env, "a").status_code == 200
        assert error_of(speak(env, "b")) == (429, "daily_limit")

        clock.now = datetime(2026, 10, 15, 0, 0, 1, tzinfo=UTC)
        assert speak(env, "b").status_code == 200

        assert [(e.day, e.granted) for e in env.ledger.entries] == [
            (TODAY, True), (TODAY, False), ("20261015", True),
        ]  # fmt: skip

    def test_retry_after_counts_down_to_midnight(self, settings):
        clock = Clock(datetime(2026, 10, 14, 23, 59, 30, tzinfo=UTC))
        env = make_capped(settings, limit=0, clock=clock)
        assert speak(env, "a").headers["retry-after"] == "30"


class TestThePerIpLimitComesFirst:
    def test_a_per_ip_refusal_is_not_charged_and_is_answered_before_the_cap(self, settings):
        env = make_capped(settings, limit=0, rate_limit_per_min=1)
        assert error_of(speak(env, "a")) == (429, "daily_limit")  # the one request the IP had
        assert error_of(speak(env, "b")) == (429, "rate_limited")  # now the IP limit answers
        assert len(env.ledger.entries) == 1  # the second never reached the cap

    def test_only_the_requests_the_ip_limit_lets_through_are_charged(self, settings):
        env = make_capped(settings, rate_limit_per_min=2)
        assert [speak(env, t).status_code for t in "abc"] == [200, 200, 429]
        assert env.ledger.spent == 2
