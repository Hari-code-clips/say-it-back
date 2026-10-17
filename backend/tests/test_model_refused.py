"""v0.5.1: a reply the model's safety filter blocked is not silence. Agent Platform can refuse a
worker's clip at the prompt level ("prompt is blocked due to safety", `prompt_feedback.block_reason`
SAFETY, whatever the safety settings). The check then has no transcript, and used to flag
`no_speech`: still "Ask again", but with a false reason, since the worker did speak. Now:

- a blocked transcriber flags each uploaded clip `model_refused` (not `no_speech`), and each step
  asked only of such clips is `unclear` + `model_refused` with a supervisor-language reason;
- a blocked judge leaves every step it would have passed `unclear` + `model_refused`;
- nothing a blocked reply touches is ever `covered`;
- a blocked hazard report or instruction transcript is a 502 that says so, not "no result".
"""

from __future__ import annotations

import pytest
from google.genai import types

from sayitback import phases, prompts
from sayitback.errors import UpstreamError
from sayitback.guards import MODEL_REFUSED, REFUSED_REASONS
from sayitback.llm_schemas import JudgeOut, TranscribeOut
from sayitback.wav import ClipStats
from tests.check_support import check, scenario
from tests.fakes import Reply, Scenario, fake_runtime, rating, tone_wav
from tests.flow_support import make_env, round_1_scenario
from tests.helpers import post_check

BLOCKED = Reply(blocked=types.BlockedReason.SAFETY)
FILTERED = Reply(payload=None, finish_reason=types.FinishReason.SAFETY)  # a candidate, no content


def blocking(llm, *, transcriber=None, judge_a=None, judge_b=None):
    """Make the named nodes' replies blocked; the others answer as the scenario says."""
    handler = llm.handler

    def reply(seen):
        if seen.schema is TranscribeOut and transcriber:
            return transcriber
        if seen.schema is JudgeOut and prompts.JUDGE_WITH_AUDIO in seen.system and judge_a:
            return judge_a
        if seen.schema is JudgeOut and prompts.JUDGE_NO_AUDIO in seen.system and judge_b:
            return judge_b
        return handler(seen)

    llm.handler = reply


class TestABlockedTranscriber:
    async def test_the_clip_is_model_refused_not_no_speech(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        blocking(llm, transcriber=BLOCKED)
        result = await check(rt)
        assert [t.flags for t in result.transcripts] == [[MODEL_REFUSED]]
        for r in result.ratings:
            assert r.verdict == "unclear", r.step_id
            assert MODEL_REFUSED in r.flags and "no_speech" not in r.flags, r.step_id
            assert r.reason == REFUSED_REASONS["en"]
        assert result.next_action == "reexplain"

    async def test_a_filtered_candidate_counts_too(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        blocking(llm, transcriber=FILTERED)
        result = await check(rt)
        assert [t.flags for t in result.transcripts] == [[MODEL_REFUSED]]
        assert all(MODEL_REFUSED in r.flags for r in result.ratings)

    async def test_judges_that_cover_anyway_cannot_pass_a_step(self, settings):
        sc = Scenario(transcripts=scenario().transcripts, judge_a=[
            rating(s, "covered", "ஆஃப் பண்ணிட்டு") for s in ("s1", "s2", "s3")
        ])  # fmt: skip
        rt, llm = fake_runtime(sc, settings)
        blocking(llm, transcriber=BLOCKED)
        result = await check(rt)
        assert {r.verdict for r in result.ratings} == {"unclear"}

    async def test_a_really_silent_clip_is_still_no_speech(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        blocking(llm, transcriber=BLOCKED)
        from sayitback.wav import make_wav

        silent = make_wav(b"\x00\x00" * 16000 * 2, 16000)
        result = await check(rt, silent)
        assert "no_speech" in result.transcripts[0].flags
        assert all("no_speech" in r.flags for r in result.ratings)

    async def test_an_empty_reply_that_was_not_blocked_is_still_no_speech(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        blocking(llm, transcriber=Reply(payload={"transcripts": []}))
        result = await check(rt)
        assert [t.flags for t in result.transcripts] == [["no_speech"]]
        assert all(MODEL_REFUSED not in r.flags for r in result.ratings)


class TestABlockedJudge:
    async def test_judge_b_blocked_leaves_judge_as_cover_unclear(self, settings):
        sc = Scenario(transcripts=scenario().transcripts, judge_a=[
            rating("s1", "covered", "ஆஃப் பண்ணிட்டு"), rating("s2", "missed"), rating("s3", "missed"),
        ])  # fmt: skip
        rt, llm = fake_runtime(sc, settings)
        blocking(llm, judge_b=BLOCKED)
        result = await check(rt)
        s1 = result.ratings[0]
        assert s1.verdict == "unclear" and MODEL_REFUSED in s1.flags
        assert s1.reason == REFUSED_REASONS["en"]
        # v0.5.3 rule 1: a blocked judge B is an `unclear` pass, so A's "missed" is a split, which
        # is `unclear` too (it no longer stands). The supervisor reads that the checker could not
        # process the answer, not a "Missed" that only one judge gave.
        for r in result.ratings[1:]:
            assert r.verdict == "unclear" and {MODEL_REFUSED, "passes_disagreed"} <= set(r.flags)
            assert r.reason == REFUSED_REASONS["en"]

    async def test_judge_a_blocked_keeps_judge_bs_contradiction(self, settings):
        sc = Scenario(transcripts=scenario().transcripts, judge_a=[
            rating("s1", "contradicted", "ஆஃப் பண்ணிட்டு"), rating("s2", "missed"),
            rating("s3", "missed"),
        ])  # fmt: skip
        rt, llm = fake_runtime(sc, settings)
        blocking(llm, judge_a=BLOCKED)
        result = await check(rt)
        assert result.ratings[0].verdict == "contradicted"
        assert result.ratings[0].quote == "ஆஃப் பண்ணிட்டு"


class TestTheReasonIsInTheSupervisorsLanguage:
    @pytest.mark.parametrize(
        ("lang", "key"), [("en", "en"), ("ta", "ta"), ("zh", "zh"), ("hi", "en")]
    )
    async def test_reason(self, settings, lang, key):
        from sayitback.pipeline import run_check
        from tests.check_support import QUESTIONS, STEPS

        rt, llm = fake_runtime(scenario(), settings)
        blocking(llm, transcriber=BLOCKED)
        result = await run_check(steps=STEPS, questions=QUESTIONS, clips={"q1": tone_wav()},
                                 worker_lang="ta", supervisor_lang=lang, runtime=rt)  # fmt: skip
        assert {r.reason for r in result.ratings} == {REFUSED_REASONS[key]}


class TestOverTheApi:
    def test_a_check_with_a_blocked_transcriber_answers_200_with_the_flag(self, settings):
        env = make_env(settings, round_1_scenario())
        blocking(env.llm, transcriber=BLOCKED)
        response = post_check(env.client, env.bid, 1)  # one clip, for q1
        assert response.status_code == 200, response.text
        body = response.json()
        flags = {t["questionId"]: t["flags"] for t in body["transcripts"]}
        assert flags.pop("q1") == [MODEL_REFUSED]
        assert all(f == ["no_speech"] for f in flags.values())  # no clip at all: really unheard
        asked_q1 = next(q["stepIds"] for q in body["script"]["questions"] if q["id"] == "q1")
        for r in body["ratings"]:
            assert r["verdict"] == "unclear"
            if r["stepId"] in asked_q1:
                assert MODEL_REFUSED in r["flags"] and r["reason"] == REFUSED_REASONS["en"]


class TestSinglePhases:
    async def test_a_blocked_hazard_report_is_a_502_that_says_so(self, settings):
        rt, llm = fake_runtime(Scenario(), settings)
        llm.handler = lambda seen: BLOCKED
        with pytest.raises(UpstreamError) as err:
            await phases.report_hazard(rt, tone_wav(), worker_lang="ta", supervisor_lang="en")
        assert (err.value.status, err.value.code) == (502, "upstream_error")
        assert "could not process" in err.value.message and "tap" in err.value.message

    async def test_a_blocked_instruction_transcript_is_a_502_that_says_so(self, settings):
        rt, llm = fake_runtime(Scenario(), settings)
        llm.handler = lambda seen: FILTERED
        with pytest.raises(UpstreamError) as err:
            await phases.transcribe_instruction(rt, tone_wav(), "en")
        assert err.value.status == 502
        assert "could not process" in err.value.message and "type" in err.value.message

    async def test_a_phase_with_no_result_and_no_block_keeps_its_old_message(self, settings):
        rt, llm = fake_runtime(Scenario(), settings)
        llm.handler = lambda seen: Reply(payload=None)  # nothing, but not a filter
        with pytest.raises(UpstreamError) as err:
            await phases.transcribe_instruction(rt, tone_wav(), "en")
        assert err.value.message == "The model returned no result."


def test_a_short_clip_with_a_blocked_transcriber_is_no_speech():
    """The stats decide silence; the empty transcript of a refusal does not."""
    from sayitback import catalog
    from sayitback.guards import GuardConfig, flag_transcript
    from sayitback.models import Transcript

    refused = Transcript(question_id="q1", original="", detected_lang="none", translation="",
                         flags=[MODEL_REFUSED])  # fmt: skip
    ranges = catalog.unicode_ranges("ta")
    loud = flag_transcript(
        refused, ClipStats(duration_s=2.0, peak_rms=3000.0), ranges, GuardConfig()
    )
    assert loud.flags == [MODEL_REFUSED]
    short = flag_transcript(
        refused, ClipStats(duration_s=0.3, peak_rms=3000.0), ranges, GuardConfig()
    )
    assert short.flags == [MODEL_REFUSED, "no_speech"]
