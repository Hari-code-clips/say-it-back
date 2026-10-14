"""A script retry reserves its own call from the daily Gemini cap (API.md, "Daily cap"): 1 call, just
before the retry runs. If the cap refuses, the round is 429 `daily_limit` and the retry is never made.
Every reservation is compared with the model calls the fakes actually saw."""

from __future__ import annotations

import pytest

from sayitback.errors import RateLimited
from sayitback.llm_schemas import BackOut, ScriptOut
from tests.cap_support import UNTIL_MIDNIGHT, confirmed, judged, make_capped, script_for_open_steps
from tests.fakes import PANEL_SCRIPT, fake_runtime, panel_script
from tests.flow_support import round_1_scenario
from tests.helpers import error_of
from tests.test_phases import script_for

ALL_STEPS = ["s1", "s2", "s3"]
# Why a first script is not good enough: it breaks a limit (hard), or has too few questions (soft).
TOO_LONG = panel_script(closing="x" * 161)
TOO_FEW_QUESTIONS = panel_script(questions=[{"text": "Only one?", "step_ids": ALL_STEPS}])
CAUSES = pytest.mark.parametrize(
    "first", [TOO_LONG, TOO_FEW_QUESTIONS], ids=["a limit is broken", "too few questions"]
)


def post_round(env, bid, body=None):
    """POST a round. Returns (response, the reservations it made, the model calls it made)."""
    entries, before = len(env.ledger.entries), env.ledger.model_calls()
    response = env.client.post(f"/api/briefings/{bid}/rounds", json=body or {})
    return response, env.ledger.entries[entries:], env.ledger.model_calls() - before


class TestTheRetryIsReservedThroughTheApi:
    @CAUSES
    def test_a_round_that_needs_a_retry_is_two_then_one_and_matches_the_calls_made(
        self, settings, first
    ):
        scenario = round_1_scenario()
        env = make_capped(settings, scenario)
        bid = confirmed(env)
        scenario.script_drafts = [first]  # the retry then gets the scenario's good script

        response, made, calls = post_round(env, bid)

        assert response.status_code == 200
        assert [(r.calls, r.granted) for r in made] == [(2, True), (1, True)]
        assert calls == 3 == sum(r.calls for r in made)  # script, script again, back-translation
        # The retry was paid for after the first script was written and before it was rewritten.
        assert made[1].model_calls == made[0].model_calls + 1

    def test_a_script_that_passes_first_time_reserves_no_retry(self, settings):
        env = make_capped(settings, round_1_scenario())
        response, made, calls = post_round(env, confirmed(env))
        assert (response.status_code, [r.calls for r in made], calls) == (200, [2], 2)

    def test_a_re_explain_round_with_no_note_and_a_retry_is_three_then_one(self, settings):
        scenario = round_1_scenario()
        env = make_capped(settings, scenario)
        bid = judged(env)
        script_for_open_steps(scenario)
        scenario.script_drafts = [{**scenario.script, "closing": "x" * 161}]

        response, made, calls = post_round(env, bid)

        assert response.status_code == 200
        assert [(r.calls, r.granted) for r in made] == [(3, True), (1, True)]
        assert calls == 4  # re-explain, script, script again, back-translation

    @CAUSES
    def test_a_cap_that_refuses_the_retry_makes_the_round_429_and_no_retry_call(
        self, settings, first
    ):
        scenario = round_1_scenario()
        env = make_capped(settings, scenario, limit=3)  # extract 1 and the round's 2: all of it
        bid = confirmed(env)
        scenario.script_drafts = [first]

        response, made, calls = post_round(env, bid)

        assert error_of(response) == (429, "daily_limit")
        assert response.headers["retry-after"] == str(UNTIL_MIDNIGHT)
        assert [(r.calls, r.granted) for r in made] == [(2, True), (1, False)]
        assert calls == 1  # the first script, and nothing after the refusal
        body = env.client.get(f"/api/briefings/{bid}").json()
        assert (body["status"], body["rounds"]) == ("steps_confirmed", [])

    def test_a_retry_that_fails_too_is_counted_and_nothing_is_refunded(self, settings):
        env = make_capped(settings, round_1_scenario())
        bid = confirmed(env)
        env.llm.handler = lambda seen: TOO_LONG if seen.schema is ScriptOut else {}

        response, made, calls = post_round(env, bid)

        assert error_of(response) == (502, "script_incomplete")
        assert [(r.calls, r.granted) for r in made] == [(2, True), (1, True)]
        assert calls == 2  # the back-translation that was reserved never ran, and is not refunded


class TestTheHookOnMakeScript:
    async def test_before_retry_runs_once_after_the_first_script_and_only_for_a_retry(
        self, settings, scenario
    ):
        scenario.script_drafts = [TOO_LONG]
        rt, llm = fake_runtime(scenario, settings)
        awaited = []

        async def before_retry():
            awaited.append(len(llm.seen))

        await script_for(rt, before_retry=before_retry)
        assert awaited == [1]  # one model call made so far: the first script

        scenario.script_drafts = []
        await script_for(rt, before_retry=before_retry)  # passes first time: no retry, no await
        assert awaited == [1]

    async def test_a_refusing_hook_stops_the_retry_before_its_model_call(self, settings, scenario):
        scenario.script_drafts = [TOO_LONG, PANEL_SCRIPT]
        rt, llm = fake_runtime(scenario, settings)

        async def refuse():
            raise RateLimited("no", code="daily_limit", retry_after=5)

        with pytest.raises(RateLimited):
            await script_for(rt, before_retry=refuse)

        assert [s.schema for s in llm.seen] == [ScriptOut]  # no second script, no back-translation
        assert BackOut not in [s.schema for s in llm.seen]

    async def test_without_a_hook_the_retry_still_runs(self, settings, scenario):
        """eval/ and the adk web dev UI pass no hook: no cap applies there."""
        scenario.script_drafts = [TOO_LONG]
        rt, llm = fake_runtime(scenario, settings)
        await script_for(rt)
        assert [s.schema for s in llm.seen].count(ScriptOut) == 2
