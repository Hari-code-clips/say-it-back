"""`run_check` (API.md, "Check workflow"): the ADK workflow end to end with a fake model."""

from __future__ import annotations

import pytest
from google.genai import errors as genai_errors

from sayitback import catalog
from sayitback.errors import Unprocessable, UpstreamBusy, UpstreamError
from sayitback.models import CheckResult, Question, Script, Step
from sayitback.pipeline import run_check
from tests.fakes import Scenario, fake_runtime, rating, silent_wav, tone_wav, transcript

ANSWER = "முதல்ல பிரேக்கரை ஆஃப் பண்ணுவேன், அப்புறம் லாக் போட்டு டேக் மாட்டுவேன், டெஸ்டர் வச்சு செக் பண்ணுவேன்"
STEPS = [Step.model_validate(s) for s in catalog.reference_steps("panel-isolation")]
QUESTIONS = [
    Question(id="q1", text="பேனலைத் திறப்பதற்கு முன் என்ன செய்வீர்கள்?", step_ids=["s1", "s2", "s3"]),
    Question(id="q2", text="கரண்ட் இல்லை என்று எப்படி தெரியும்?", step_ids=["s3"]),
]


def check(rt, **overrides):
    args = dict(
        steps=STEPS,
        questions=QUESTIONS,
        clips={"q1": tone_wav()},
        worker_lang="ta",
        supervisor_lang="en",
    )
    return run_check(runtime=rt, **(args | overrides))


def covered_scenario(**kw):
    rows = [rating("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணுவேன்"), rating("s2", "covered", "லாக் போட்டு"),
            rating("s3", "covered", "டெஸ்டர் வச்சு செக் பண்ணுவேன்")]  # fmt: skip
    return Scenario(transcripts=[transcript("q1", ANSWER)], judge_a=rows, **kw)


async def test_all_steps_covered_means_decide(settings):
    rt, llm = fake_runtime(covered_scenario(), settings)
    result = await check(rt)
    assert isinstance(result, CheckResult)
    assert [r.verdict for r in result.ratings] == ["covered"] * 3
    assert result.next_action == "decide"
    assert len(result.pass_a) == len(result.pass_b) == 3
    assert len(llm.seen) == 3  # transcriber, judge A, judge B


async def test_model_ids_and_timings_are_reported(settings):
    rt, _ = fake_runtime(covered_scenario(), settings)
    result = await check(rt)
    assert result.model_ids == {
        "transcribe": "fake-flash-001",
        "judge_a": "fake-flash-001",
        "judge_b": "fake-flash-001",
    }
    assert set(result.timings_ms) == {"transcribe", "judge_a", "judge_b", "check_total"}
    assert result.timings_ms["check_total"] > 0


async def test_the_catalog_demo_round_1_answer_covers_s1_only(settings):
    answer = "நான் அதை ஆஃப் பண்ணிட்டு திறப்பேன்."
    scenario = Scenario(
        transcripts=[transcript("q1", answer)],
        judge_a=[
            rating("s1", "covered", "ஆஃப் பண்ணிட்டு"),
            rating("s2", "missed"),
            rating("s3", "missed"),
        ],
    )
    rt, _ = fake_runtime(scenario, settings)
    result = await check(rt)
    assert {r.step_id: r.verdict for r in result.ratings} == {
        "s1": "covered",
        "s2": "missed",
        "s3": "missed",
    }
    assert result.next_action == "reexplain"
    assert result.ratings[0].quote == "ஆஃப் பண்ணிட்டு"


async def test_a_judge_that_disagrees_cannot_be_overruled(settings):
    scenario = covered_scenario()
    scenario.judge_b = [
        rating("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணுவேன்"),
        rating("s2", "unclear"),
        rating("s3", "covered", "டெஸ்டர் வச்சு செக் பண்ணுவேன்"),
    ]
    rt, _ = fake_runtime(scenario, settings)
    result = await check(rt)
    assert [r.verdict for r in result.ratings] == ["covered", "unclear", "covered"]
    assert "passes_disagreed" in result.ratings[1].flags
    assert result.next_action == "reexplain"


async def test_a_hallucinated_quote_is_caught_by_the_guard(settings):
    scenario = covered_scenario()
    scenario.judge_a[1] = rating("s2", "covered", "இது சொல்லவே இல்லை")
    scenario.judge_b = list(scenario.judge_a)
    rt, _ = fake_runtime(scenario, settings)
    result = await check(rt)
    assert result.ratings[1].verdict == "unclear"
    assert "quote_not_found" in result.ratings[1].flags


async def test_a_silent_clip_can_never_cover(settings):
    scenario = covered_scenario()
    rt, _ = fake_runtime(scenario, settings)
    result = await check(rt, clips={"q1": silent_wav(2.0)})
    assert {r.verdict for r in result.ratings} == {"unclear"}
    assert all("no_speech" in r.flags for r in result.ratings)
    assert "no_speech" in result.transcripts[0].flags


async def test_a_question_without_a_clip_gets_an_empty_no_speech_transcript(settings):
    rt, llm = fake_runtime(covered_scenario(), settings)
    result = await check(rt)
    assert [t.question_id for t in result.transcripts] == ["q1", "q2"]
    assert result.transcripts[1].original == "" and "no_speech" in result.transcripts[1].flags
    assert "q2" not in llm.seen[0].system  # only clips that exist are sent to the transcriber


async def test_the_answer_in_the_wrong_language_abstains(settings):
    scenario = covered_scenario()
    scenario.transcripts = [transcript("q1", "मैं पहले ब्रेकर बंद करूंगा और ताला लगाऊंगा", lang="hi")]
    scenario.judge_a = [rating(f"s{i}", "covered", "ब्रेकर बंद करूंगा") for i in (1, 2, 3)]
    rt, _ = fake_runtime(scenario, settings)
    result = await check(rt)
    assert all(r.verdict == "unclear" and "language_mismatch" in r.flags for r in result.ratings)


async def test_a_single_judge_pass_leaves_pass_b_empty(settings):
    rt, llm = fake_runtime(covered_scenario(), settings.with_overrides(judge_passes=1))
    result = await check(rt)
    assert result.pass_b == []
    assert len(llm.seen) == 2
    assert result.next_action == "decide"


async def test_the_script_and_live_transcripts_are_accepted(settings):
    script = Script(
        instruction="a\nb\nc",
        questions=QUESTIONS,
        step_map={"s1": [0], "s2": [1], "s3": [2]},
        closing="c",
    )
    rt, llm = fake_runtime(covered_scenario(), settings)
    result = await check(rt, script=script, live_input_transcripts={"q1": "heard it"})
    assert result.next_action == "decide"
    judge = next(s for s in llm.seen if "WHAT THE WORKER WAS TOLD" in s.system)
    assert "0: a" in judge.system
    assert all(
        "heard it" not in s.system and "heard it" not in s.text for s in llm.seen
    )  # evidence only


async def test_dict_inputs_are_accepted_like_the_eval_harness_sends_them(settings):
    rt, _ = fake_runtime(covered_scenario(), settings)
    steps = catalog.reference_steps("panel-isolation")
    questions = [{"id": "q1", "text": "t", "stepIds": ["s1", "s2", "s3"]}]
    result = await check(rt, steps=steps, questions=questions)
    assert result.next_action == "decide"


@pytest.mark.parametrize(
    "overrides",
    [
        {"steps": []},
        {"clips": {}},
        {"clips": {"q9": tone_wav()}},
        {"worker_lang": "xx"},
        {"supervisor_lang": "klingon"},
        {"steps": [STEPS[0], STEPS[0]]},
    ],
)
async def test_invalid_inputs_are_rejected_before_any_model_call(settings, overrides):
    rt, llm = fake_runtime(covered_scenario(), settings)
    with pytest.raises(Unprocessable):
        await check(rt, **overrides)
    assert llm.seen == []


async def test_a_clip_that_is_not_a_wav_is_invalid_audio(settings):
    rt, _ = fake_runtime(covered_scenario(), settings)
    with pytest.raises(Unprocessable) as err:
        await check(rt, clips={"q1": b"ID3 this is an mp3"})
    assert err.value.code == "invalid_audio"


async def test_a_busy_model_maps_to_503_upstream_busy(settings):
    scenario = covered_scenario()
    rt, llm = fake_runtime(scenario, settings)
    llm.handler = lambda seen: genai_errors.ServerError(
        503, {"error": {"message": "overloaded", "status": "UNAVAILABLE"}}
    )
    with pytest.raises(UpstreamBusy) as err:
        await check(rt)
    assert (err.value.status, err.value.code) == (503, "upstream_busy")


async def test_a_rate_limited_model_maps_to_503_upstream_busy(settings):
    rt, llm = fake_runtime(covered_scenario(), settings)
    llm.handler = lambda seen: genai_errors.ClientError(
        429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    )
    with pytest.raises(UpstreamBusy):
        await check(rt)


async def test_a_refused_request_maps_to_502_upstream_error(settings):
    rt, llm = fake_runtime(covered_scenario(), settings)
    llm.handler = lambda seen: genai_errors.ClientError(
        400, {"error": {"message": "bad", "status": "INVALID_ARGUMENT"}}
    )
    with pytest.raises(UpstreamError) as err:
        await check(rt)
    assert err.value.status == 502


async def test_a_model_that_returns_invalid_json_is_a_502_not_a_crash(settings):
    rt, llm = fake_runtime(covered_scenario(), settings)
    llm.handler = lambda seen: "this is not json"
    with pytest.raises(UpstreamError):
        await check(rt)


async def test_a_transcript_the_model_invents_for_a_clip_that_was_never_uploaded_is_ignored(
    settings,
):
    """q2 had no recording, but the model returns text for it and both judges cover s2 from it."""
    scenario = Scenario(
        transcripts=[transcript("q1", ""), transcript("q2", ANSWER)],
        judge_a=[
            rating("s1", "missed"),
            rating("s2", "covered", "லாக் போட்டு"),
            rating("s3", "missed"),
        ],
    )
    questions = [
        Question(id="q1", text="a", step_ids=["s1"]),
        Question(id="q2", text="b", step_ids=["s2", "s3"]),
    ]
    rt, llm = fake_runtime(scenario, settings)
    result = await check(rt, questions=questions, clips={"q1": tone_wav()})
    q2 = next(t for t in result.transcripts if t.question_id == "q2")
    assert q2.original == "" and "no_speech" in q2.flags
    by_step = {r.step_id: r for r in result.ratings}
    assert by_step["s2"].verdict == "unclear" and "quote_not_found" in by_step["s2"].flags
    judge = next(s for s in llm.seen if s.schema.__name__ == "JudgeOut")
    assert ANSWER not in judge.system  # the judges never see the invented text either
