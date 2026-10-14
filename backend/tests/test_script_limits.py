"""The hard limits on a script's length (API.md, "Daily cap"): sentences per step, characters per
spoken line, and the question count. A script that breaks one is retried once with a fix note that
names the exact limit, then refused with 502 `script_incomplete`."""

from __future__ import annotations

import logging

import pytest

from sayitback.errors import UpstreamError
from sayitback.llm_schemas import BackOut, ScriptOut, ScriptQuestion, StepSentences
from sayitback.models import Step
from sayitback.script_checks import ScriptLimits, build_script
from sayitback.settings import Settings
from tests.fakes import PANEL_SCRIPT, fake_runtime, panel_script
from tests.test_phases import STEPS, script_for

LIMITS = ScriptLimits.from_settings(Settings())  # the contract's defaults: 3 per step, 160 chars
SCOPE = [Step(id=f"s{n}", text=f"step {n}") for n in (1, 2, 3)]
ALL_STEPS = ["s1", "s2", "s3"]
QUESTIONS = [("What will you do first?", ALL_STEPS), ("How will you know?", ["s3"])]
MARKER = "WORDSTHEMODELWROTE"


def lines(n: int) -> list[str]:
    return [f"Sentence {i}." for i in range(n)]


def out(
    sentences: list[str] | None = None,
    step_map: dict[str, list[int]] | None = None,
    questions: list[tuple[str, list[str]]] | None = None,
    closing: str = "Thank you.",
) -> ScriptOut:
    """A script that passes every check (two sentences a step, two questions), with changes."""
    step_map = step_map or {"s1": [0, 1], "s2": [2, 3], "s3": [4, 5]}
    return ScriptOut(
        sentences=sentences or lines(6),
        step_map=[StepSentences(step_id=k, sentence_indices=v) for k, v in step_map.items()],
        questions=[ScriptQuestion(text=t, step_ids=ids) for t, ids in questions or QUESTIONS],
        closing=closing,
    )


def build(script: ScriptOut, scope=SCOPE, q_range=(2, 3), limits=LIMITS):
    return build_script(script, scope, first_qnum=1, q_range=q_range, limits=limits)


class TestSentencesPerStep:
    def test_a_script_within_every_limit_has_no_problems(self):
        draft = build(out())
        assert (draft.hard, draft.soft) == ([], [])

    def test_a_step_delivered_by_more_sentences_than_the_limit_is_a_hard_problem(self):
        draft = build(out(step_map={"s1": [0, 1, 2, 3], "s2": [4], "s3": [5]}))
        assert draft.hard == ["Step s1 is delivered by 4 sentences; use at most 3 per step."]
        assert draft.soft == []

    def test_exactly_the_limit_for_every_step_passes(self):
        step_map = {"s1": [0, 1, 2], "s2": [3, 4, 5], "s3": [6, 7, 8]}
        draft = build(out(sentences=lines(9), step_map=step_map))
        assert (draft.hard, draft.soft) == ([], [])

    def test_a_sentence_that_delivers_no_step_still_counts_toward_the_total(self):
        """Each step is within its limit, so only the total (3 x 3 steps = 9) can stop the padding."""
        step_map = {"s1": [0], "s2": [1], "s3": [2]}
        draft = build(out(sentences=lines(10), step_map=step_map))
        assert draft.hard == [
            "The instruction has 10 sentences; use at most 9 in all (3 per step, 3 steps), "
            "counting every sentence."
        ]

    def test_the_total_is_per_step_in_the_rounds_scope(self):
        """A re-explain round with one open step may say 3 sentences, not 3 x all the steps."""
        one = [SCOPE[0]]
        two_questions = [("What will you do?", ["s1"])]
        ok = out(lines(3), {"s1": [0, 1, 2]}, two_questions)
        too_many = out(lines(4), {"s1": [0, 1, 2]}, two_questions)
        assert build(ok, one, (1, 2)).hard == []
        assert build(too_many, one, (1, 2)).hard == [
            "The instruction has 4 sentences; use at most 3 in all (3 per step, 1 step), "
            "counting every sentence."
        ]

    def test_a_21_sentence_script_fails_both_rules(self):
        step_map = {"s1": list(range(0, 7)), "s2": list(range(7, 14)), "s3": list(range(14, 21))}
        draft = build(out(sentences=lines(21), step_map=step_map))
        assert len(draft.hard) == 4  # three steps over 3 each, and 21 over 9 in all
        assert "use at most 9 in all" in draft.hard[-1]

    def test_the_limit_comes_from_settings(self):
        tight = ScriptLimits.from_settings(Settings(max_sentences_per_step=1))
        draft = build(out(), limits=tight)  # two sentences a step: over 1 each, and 6 over 3
        assert [p for p in draft.hard if "use at most 1 per step" in p] == [
            f"Step {s} is delivered by 2 sentences; use at most 1 per step." for s in ALL_STEPS
        ]
        assert any("use at most 3 in all (1 per step, 3 steps)" in p for p in draft.hard)


class TestCharactersPerLine:
    def test_a_sentence_of_exactly_the_limit_passes_and_one_more_character_fails(self):
        assert build(out(sentences=["a" * 160, *lines(5)])).hard == []
        draft = build(out(sentences=[*lines(1), "a" * 161, *lines(4)]))
        assert draft.hard == [
            "Over 160 characters: sentence 1. Every sentence (numbered from 0), question and the "
            "closing may have at most 160 characters."
        ]

    def test_a_question_and_the_closing_have_the_same_limit(self):
        long_question = [("q" * 161, ALL_STEPS), ("How will you know?", ["s3"])]
        assert build(out(questions=long_question)).hard == [
            "Over 160 characters: question q1. Every sentence (numbered from 0), question and "
            "the closing may have at most 160 characters."
        ]
        assert build(out(closing="c" * 161)).hard == [
            "Over 160 characters: the closing. Every sentence (numbered from 0), question and "
            "the closing may have at most 160 characters."
        ]
        assert build(out(questions=[("q" * 160, ALL_STEPS)] * 2, closing="c" * 160)).hard == []

    def test_every_long_line_is_named_in_one_note(self):
        draft = build(out(sentences=["a" * 200, "b", "c", "d" * 170, "e", "f"], closing="c" * 161))
        assert len(draft.hard) == 1
        assert draft.hard[0].startswith("Over 160 characters: sentence 0, sentence 3, the closing.")

    def test_the_line_is_measured_in_characters_after_whitespace_is_collapsed(self):
        spaced = "a  " * 70  # 210 characters as written, 139 once the runs of spaces are collapsed
        tamil = "அ" * 160  # 160 characters, 480 bytes
        assert build(out(sentences=[spaced, tamil, *lines(4)])).hard == []
        assert build(out(sentences=["அ" * 161, *lines(5)])).hard != []

    def test_the_limit_comes_from_settings(self):
        tight = ScriptLimits.from_settings(Settings(max_line_chars=25))
        draft = build(out(sentences=["a" * 26, *lines(5)]), limits=tight)
        assert draft.hard[0].startswith("Over 25 characters: sentence 0.")
        assert draft.hard[0].endswith("may have at most 25 characters.")


class TestQuestionCount:
    def test_more_questions_than_the_range_is_hard_and_the_range_top_is_not(self):
        three = [("One?", ALL_STEPS), ("Two?", ALL_STEPS), ("Three?", ALL_STEPS)]
        assert build(out(questions=three)).hard == []
        draft = build(out(questions=[*three, ("Four?", ALL_STEPS)]))
        assert draft.hard == ["Write at most 3 questions, not 4."] and draft.soft == []

    def test_fewer_questions_than_the_range_stays_soft(self):
        draft = build(out(questions=[("Only one?", ALL_STEPS)]))
        assert draft.hard == []
        assert draft.soft == ["Write between 2 and 3 questions, not 1."]

    def test_a_re_explain_round_allows_at_most_two(self):
        one_step = [SCOPE[0]]
        qs = [("One?", ["s1"]), ("Two?", ["s1"]), ("Three?", ["s1"])]
        script = out(lines(2), {"s1": [0, 1]}, qs)
        assert build(script, one_step, (1, 2)).hard == ["Write at most 2 questions, not 3."]
        assert build(out(lines(2), {"s1": [0, 1]}, qs[:2]), one_step, (1, 2)).hard == []


# make_script: the retry, the fix notes and the refusal ----------------------------------------


def scripts_written(llm) -> list:
    return [s for s in llm.seen if s.schema is ScriptOut]


BREAKS = {
    "sentences per step": (
        panel_script(
            sentences=lines(6),
            step_map=[
                {"step_id": "s1", "sentence_indices": [0, 1, 2, 3]},
                {"step_id": "s2", "sentence_indices": [4]},
                {"step_id": "s3", "sentence_indices": [5]},
            ],
        ),
        "Step s1 is delivered by 4 sentences; use at most 3 per step.",
    ),
    "sentences in all": (
        panel_script(sentences=lines(10)),
        "The instruction has 10 sentences; use at most 9 in all (3 per step, 3 steps)",
    ),
    "characters": (
        panel_script(closing="x" * 161),
        "Over 160 characters: the closing.",
    ),
    "questions": (
        panel_script(questions=[{"text": f"Q{i}?", "step_ids": ALL_STEPS} for i in range(4)]),
        "Write at most 3 questions, not 4.",
    ),
}


class TestRetryAndRefusal:
    @pytest.mark.parametrize(("broken", "note"), list(BREAKS.values()), ids=list(BREAKS))
    async def test_a_script_over_a_limit_is_retried_once_and_the_retry_is_told_the_limit(
        self, settings, scenario, broken, note
    ):
        scenario.script_drafts = [broken, PANEL_SCRIPT]
        rt, llm = fake_runtime(scenario, settings)

        script, _ = await script_for(rt)

        assert script.instruction == "\n".join(PANEL_SCRIPT["sentences"])
        first, retry = scripts_written(llm)
        assert "Your previous draft" not in first.system
        assert "Your previous draft had these problems" in retry.system and note in retry.system

    async def test_a_script_that_still_breaks_a_limit_is_script_incomplete(
        self, settings, scenario, caplog
    ):
        wordy = panel_script(sentences=[f"{MARKER} {i}." for i in range(21)])
        scenario.script_drafts = [wordy, wordy]  # the 21-sentence kind, again on the retry
        rt, llm = fake_runtime(scenario, settings)

        with caplog.at_level(logging.DEBUG), pytest.raises(UpstreamError) as err:
            await script_for(rt)

        assert (err.value.status, err.value.code) == (502, "script_incomplete")
        assert len(scripts_written(llm)) == 2  # the first try and one retry, never a third
        assert not [s for s in llm.seen if s.schema is BackOut]  # nothing is back-translated
        assert MARKER not in err.value.message and MARKER not in caplog.text

    async def test_more_questions_than_the_range_is_no_longer_accepted(self, settings, scenario):
        scenario.script = BREAKS["questions"][0]
        rt, llm = fake_runtime(scenario, settings)
        with pytest.raises(UpstreamError) as err:
            await script_for(rt)
        assert err.value.code == "script_incomplete" and len(scripts_written(llm)) == 2

    async def test_a_draft_with_too_few_questions_survives_a_worse_retry(self, settings, scenario):
        few = panel_script(questions=[{"text": "Only?", "step_ids": ALL_STEPS}])
        scenario.script_drafts = [few, BREAKS["characters"][0]]
        rt, _ = fake_runtime(scenario, settings)
        script, _ = await script_for(rt)
        assert [q.text for q in script.questions] == ["Only?"]  # soft fault only: the fallback

    async def test_the_limits_in_settings_reach_the_prompt_and_the_check(self, settings, scenario):
        tight = settings.with_overrides(max_sentences_per_step=2, max_line_chars=90)
        scenario.script = BREAKS["sentences per step"][0]  # step s1 has 4
        rt, llm = fake_runtime(scenario, tight)

        with pytest.raises(UpstreamError):
            await script_for(rt)

        prompt = scripts_written(llm)[0].system
        assert "At most 2 sentences for each step, 6 in all" in prompt
        assert "12 words and 90 characters each" in prompt
        assert "Step s1 is delivered by 4 sentences; use at most 2 per step." in (
            scripts_written(llm)[1].system
        )

    async def test_the_prompt_states_the_defaults_and_scales_the_total_to_the_scope(self, fake_rt):
        rt, llm = fake_rt
        await script_for(rt)
        await script_for(rt, steps=STEPS[1:], round_kind="reexplain", first_qnum=3)
        initial, reexplain = (s.system for s in scripts_written(llm))
        assert "At most 3 sentences for each step, 9 in all" in initial
        assert "At most 3 sentences for each step, 6 in all" in reexplain
        for prompt in (initial, reexplain):
            assert "12 words and 160 characters each" in prompt
            assert "each at most 160 characters" in prompt  # the questions
            assert "at most 160 characters, such as: Thank you" in prompt  # the closing

    async def test_the_default_script_passes_the_default_limits_without_a_retry(self, fake_rt):
        rt, llm = fake_rt
        await script_for(rt)
        assert len(scripts_written(llm)) == 1
