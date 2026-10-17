"""v0.5.1: the prompt-level SAFETY block is not deterministic (the same clip and request passed,
then were blocked, then passed), so a blocked reply is asked for again, SIB_REFUSAL_RETRIES more
times (1; 0 = never), with the same backoff as the HTTP retries and inside the phase timeout. Only
a reply still blocked on the last attempt is `model_refused` (the check) or the clear 502 (the
hazard report, the instruction transcript). Only the blocked node is asked again, not the whole
check: the others' answers stand.

Two levels: the fakes (FakeLlm shares the production retry, backends.RefusalRetry) drive the whole
check and the phases, and the real google-genai client plus ADK's Gemini over a mock HTTP
transport show that a real blocked body (`promptFeedback`, no candidates) is retried the same way.
"""

from __future__ import annotations

import json
import time
from collections import Counter

import httpx
import pytest
from google import genai
from google.genai import types

from sayitback import backends, phases, prompts
from sayitback.errors import UpstreamBusy, UpstreamError
from sayitback.guards import MODEL_REFUSED
from sayitback.llm_schemas import HazardOut, JudgeOut, TranscribeOut
from sayitback.runtime import Runtime
from sayitback.settings import ConfigError, Settings
from tests.check_support import check, scenario
from tests.fakes import Reply, Scenario, fake_runtime, tone_wav

BLOCKED = Reply(blocked=types.BlockedReason.SAFETY)


def node(seen) -> str:
    if seen.schema is TranscribeOut:
        return "blind_transcriber"
    if seen.schema is JudgeOut:
        return "judge_a" if prompts.JUDGE_WITH_AUDIO in seen.system else "judge_b"
    return "other"


def blocked_first(llm, target: str, times: int):
    """`target`'s first `times` replies are blocked, then it answers as before. Counts calls."""
    handler, calls = llm.handler, Counter()

    def reply(seen):
        name = node(seen)
        calls[name] += 1
        if name == target and calls[name] <= times:
            return BLOCKED
        return handler(seen)

    llm.handler = reply
    return calls


class TestTheCheck:
    async def test_blocked_then_ok_is_a_normal_result(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        calls = blocked_first(llm, "blind_transcriber", 1)
        result = await check(rt)
        assert calls == Counter({"blind_transcriber": 2, "judge_a": 1, "judge_b": 1})
        assert [r.verdict for r in result.ratings] == ["covered", "missed", "missed"]
        assert all(MODEL_REFUSED not in r.flags for r in result.ratings)
        assert result.transcripts[0].flags == []

    async def test_blocked_twice_is_model_refused(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        calls = blocked_first(llm, "blind_transcriber", 2)
        result = await check(rt)
        assert calls["blind_transcriber"] == 2  # one retry (SIB_REFUSAL_RETRIES=1), never more
        assert result.transcripts[0].flags == [MODEL_REFUSED]
        assert {r.verdict for r in result.ratings} == {"unclear"}
        assert all(MODEL_REFUSED in r.flags for r in result.ratings)

    async def test_more_retries_when_configured(self, settings):
        rt, llm = fake_runtime(scenario(), settings.with_overrides(refusal_retries=2))
        calls = blocked_first(llm, "blind_transcriber", 2)
        result = await check(rt)
        assert calls["blind_transcriber"] == 3 and result.transcripts[0].flags == []

    async def test_a_judge_is_asked_again_too(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        calls = blocked_first(llm, "judge_b", 1)
        result = await check(rt)
        assert calls["judge_b"] == 2
        assert result.ratings[0].verdict == "covered"

    async def test_zero_retries_means_no_second_call(self, settings):
        rt, llm = fake_runtime(scenario(), settings.with_overrides(refusal_retries=0))
        calls = blocked_first(llm, "blind_transcriber", 1)
        result = await check(rt)
        assert calls["blind_transcriber"] == 1
        assert result.transcripts[0].flags == [MODEL_REFUSED]

    async def test_the_retry_stays_inside_the_phase_timeout(self, settings):
        """The wait before asking again is inside the phase's own bound: a phase that runs out
        is the existing 503 upstream_busy, never a check that runs on."""
        s = settings.with_overrides(retry_backoff_s=5.0, phase_timeout_s=0.5, call_timeout_s=0.5)
        rt, llm = fake_runtime(scenario(), s)
        calls = blocked_first(llm, "blind_transcriber", 1)
        started = time.monotonic()
        with pytest.raises(UpstreamBusy):
            await check(rt)
        assert time.monotonic() - started < 2.0
        assert calls["blind_transcriber"] == 1  # cut off while waiting to ask again

    async def test_an_answer_is_never_asked_for_twice(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        calls = blocked_first(llm, "nobody", 0)
        await check(rt)
        assert calls == Counter({"blind_transcriber": 1, "judge_a": 1, "judge_b": 1})

    @pytest.mark.parametrize(
        "empty",
        [Reply(payload={"transcripts": []}), Reply(payload=None)],  # no clips; no content at all
        ids=["no-clips", "no-content"],
    )
    async def test_an_empty_reply_that_was_not_blocked_is_not_retried(self, settings, empty):
        rt, llm = fake_runtime(scenario(), settings)
        handler, calls = llm.handler, Counter()

        def reply(seen):
            calls[node(seen)] += 1
            return empty if node(seen) == "blind_transcriber" else handler(seen)

        llm.handler = reply
        result = await check(rt)
        assert calls["blind_transcriber"] == 1 and result.transcripts[0].flags == ["no_speech"]


class TestTheSinglePhases:
    def hazard_after(self, settings, times: int):
        hazard = {
            "original": "கயிறு அறுந்திருக்கு",
            "detected_lang": "ta",
            "translation": "The rope is cut",
        }
        rt, llm = fake_runtime(Scenario(), settings)
        seen = []

        def reply(s):
            seen.append(s.schema)
            return BLOCKED if len(seen) <= times else hazard

        llm.handler = reply
        return rt, seen

    async def test_a_hazard_report_blocked_once_then_heard(self, settings):
        rt, seen = self.hazard_after(settings, 1)
        original, lang, translation = await phases.report_hazard(
            rt, tone_wav(), worker_lang="ta", supervisor_lang="en"
        )
        assert (lang, translation) == ("ta", "The rope is cut") and original
        assert seen == [HazardOut] * 2

    async def test_a_hazard_report_blocked_twice_is_the_502(self, settings):
        rt, seen = self.hazard_after(settings, 2)
        with pytest.raises(UpstreamError) as err:
            await phases.report_hazard(rt, tone_wav(), worker_lang="ta", supervisor_lang="en")
        assert err.value.status == 502 and "could not process" in err.value.message
        assert len(seen) == 2

    async def test_a_hazard_report_with_zero_retries_is_the_502_at_once(self, settings):
        rt, seen = self.hazard_after(settings.with_overrides(refusal_retries=0), 1)
        with pytest.raises(UpstreamError):
            await phases.report_hazard(rt, tone_wav(), worker_lang="ta", supervisor_lang="en")
        assert len(seen) == 1

    async def test_the_instruction_transcript_is_asked_again(self, settings):
        rt, llm = fake_runtime(Scenario(), settings)
        replies = iter([BLOCKED, {"text": "Never go under the load."}])
        llm.handler = lambda seen: next(replies)
        assert (
            await phases.transcribe_instruction(rt, tone_wav(), "en") == "Never go under the load."
        )


# The real google-genai client and ADK's Gemini, over a mock transport --------------------------

OK_BODY = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [{"text": json.dumps({"explanation": "Do it safely."})}],
            },
            "finishReason": "STOP",
        }
    ],
    "modelVersion": "gemini-3.8-flash",
}
BLOCKED_BODY = {
    "promptFeedback": {
        "blockReason": "SAFETY",
        "blockReasonMessage": "Prompt is blocked due to safety.",
    },
    "modelVersion": "gemini-3.8-flash",
}


def real_runtime(blocked: int, settings) -> tuple[Runtime, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=BLOCKED_BODY if len(seen) <= blocked else OK_BODY)

    s = settings.with_overrides(retry_backoff_s=0.01)
    client = genai.Client(
        api_key="test-key-not-real",
        http_options=types.HttpOptions(
            retry_options=backends.retry_options(s),
            httpx_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ),
    )
    flash = backends.FlashGemini(model=s.flash_model, client=client, **backends.refusal_retry(s))
    return Runtime(s, flash, lambda cb: None, lambda: None), seen


async def explain(rt):
    return await phases.explain(rt, steps=[], ratings={}, supervisor_lang="en", sop_title="SOP")


class TestTheRealClient:
    async def test_a_real_blocked_body_then_an_answer(self, settings):
        rt, seen = real_runtime(1, settings)
        text, _ = await explain(rt)
        assert text == "Do it safely." and len(seen) == 2

    async def test_a_real_blocked_body_every_time_is_the_clear_502(self, settings):
        rt, seen = real_runtime(5, settings)
        with pytest.raises(UpstreamError) as err:
            await explain(rt)
        assert "could not process" in err.value.message
        assert len(seen) == 2

    def test_production_models_carry_the_refusal_retry(self):
        s = Settings(retry_attempts=3, retry_backoff_s=1.5, refusal_retries=2)
        for model in (backends.make_flash(s), backends.make_flash(s, "gemini-3.1-flash-lite")):
            assert isinstance(model, backends.FlashGemini)
            assert (model.refusal_attempts, model.refusal_backoff_s) == (3, 1.5)
            assert model.retry_options == backends.retry_options(s)  # the HTTP retries, unchanged
        assert not isinstance(backends.make_live(s), backends.RefusalRetry)  # Live is not retried


class TestTheSetting:
    def test_default_environment_and_bounds(self):
        assert Settings().refusal_retries == 1 == Settings.from_env({}).refusal_retries
        assert Settings.from_env({"SIB_REFUSAL_RETRIES": "0"}).refusal_retries == 0
        assert backends.refusal_retry(Settings(refusal_retries=0))["refusal_attempts"] == 1
        for bad in ("-1", "4", "one"):
            with pytest.raises(ConfigError, match="SIB_REFUSAL_RETRIES"):
                Settings.from_env({"SIB_REFUSAL_RETRIES": bad})
