"""Extract, script (+ back-translation), re-explain and the supervisor's speech-to-text."""

from __future__ import annotations

import copy

import pytest

from sayitback import catalog, phases
from sayitback.errors import UpstreamError
from sayitback.models import Rating, Sop, Step
from sayitback.script_checks import verified_sop_quote
from tests.fakes import PANEL_BACK, PANEL_EXTRACT, PANEL_SCRIPT, fake_runtime, tone_wav

SOP = Sop.model_validate(catalog.task("panel-isolation")["sop"])
STEPS = [Step.model_validate(s) for s in catalog.reference_steps("panel-isolation")]


async def script_for(rt, **kw):
    args = dict(
        steps=STEPS, basis="Isolate it.", round_kind="initial", supervisor_lang="en", worker_lang="ta",
        site_id="sg", first_qnum=1, previous_questions=[],
    )  # fmt: skip
    return await phases.make_script(rt, **(args | kw))


class TestExtract:
    async def test_steps_get_stable_ids_and_the_sop_flag(self, fake_rt):
        rt, llm = fake_rt
        steps, conflicts, meta = await phases.extract_steps(
            rt, instruction="Isolate the breaker.", supervisor_lang="en", sop=SOP
        )
        assert [s.id for s in steps] == ["s1", "s2", "s3"]
        assert [s.source for s in steps] == ["instruction", "both", "sop"]
        assert steps[0].sop_quote is None
        assert steps[2].sop_quote == (  # kept as written: it is verbatim in SOP-EL-04 v4, line 6
            "Before touching any conductor, test it dead with an approved voltage tester."
        )
        assert conflicts[0].step_id == "s3"
        assert meta.model_ids == {"extract": "fake-flash-001"}
        assert "Isolate the breaker." in llm.seen[0].system and SOP.text in llm.seen[0].system

    async def test_a_non_verbatim_sop_quote_is_replaced_by_the_closest_sop_line(
        self, settings, scenario
    ):
        scenario.extract = copy.deepcopy(PANEL_EXTRACT)
        scenario.extract["steps"][1]["sop_quote"] = (
            "fit your personal lock and danger tag on the breaker"
        )
        rt, _ = fake_runtime(scenario, settings)
        steps, _, _ = await phases.extract_steps(rt, instruction="x", supervisor_lang="en", sop=SOP)
        assert steps[1].sop_quote.startswith("4. Fit your personal lock and a danger tag")

    async def test_an_invented_sop_quote_is_dropped(self, settings, scenario):
        scenario.extract = copy.deepcopy(PANEL_EXTRACT)
        scenario.extract["steps"][2]["sop_quote"] = (
            "completely invented text that is nowhere in the SOP at all"
        )
        rt, _ = fake_runtime(scenario, settings)
        steps, _, _ = await phases.extract_steps(rt, instruction="x", supervisor_lang="en", sop=SOP)
        assert steps[2].source == "sop" and steps[2].sop_quote is None

    async def test_at_most_max_steps_and_empty_ones_are_dropped(self, settings, scenario):
        many = copy.deepcopy(PANEL_EXTRACT)
        many["steps"] = [dict(many["steps"][0], text=f"step {i}") for i in range(9)] + [
            dict(many["steps"][0], text="  ")
        ]
        scenario.extract = many
        rt, _ = fake_runtime(scenario, settings)
        steps, _, _ = await phases.extract_steps(rt, instruction="x", supervisor_lang="en", sop=SOP)
        assert len(steps) == 6

    async def test_no_steps_is_a_502(self, settings, scenario):
        scenario.extract = {"steps": [], "conflicts": []}
        rt, _ = fake_runtime(scenario, settings)
        with pytest.raises(UpstreamError):
            await phases.extract_steps(rt, instruction="x", supervisor_lang="en", sop=SOP)


class TestScript:
    async def test_round_1_script_has_a_step_map_covering_every_step_and_back_translation(
        self, fake_rt
    ):
        rt, llm = fake_rt
        script, meta = await script_for(rt)
        assert script.instruction == "\n".join(PANEL_SCRIPT["sentences"])
        assert set(script.step_map) == {"s1", "s2", "s3"}
        assert [q.id for q in script.questions] == ["q1", "q2"]
        assert script.questions[0].step_ids == ["s1", "s2", "s3"]
        assert script.instruction_back_translation == "\n".join(PANEL_BACK["sentences"])
        assert script.questions[0].back_translation == "What will you do before you open the panel?"
        assert set(meta.model_ids) == {"script", "back_translate"}
        assert len(llm.seen) == 2

    async def test_the_back_translator_never_sees_the_steps(self, fake_rt):
        rt, llm = fake_rt
        await script_for(rt)
        back = llm.seen[1]
        assert "Tamil" in back.system and "English" in back.system
        for text in ("Switch off (isolate)", "essential", "hazard", "Lock and tag"):
            assert text not in back.system

    async def test_the_script_prompt_carries_steps_site_and_language_rules(self, fake_rt):
        rt, llm = fake_rt
        await script_for(rt)
        prompt = llm.seen[0].system
        assert "Switch off (isolate) the supply at the breaker" in prompt
        assert "At most 12 words" in prompt and "Tamil" in prompt and "Singapore" in prompt

    async def test_a_script_that_skips_a_step_is_retried_once_with_the_problem_named(
        self, settings, scenario
    ):
        broken = copy.deepcopy(PANEL_SCRIPT)
        broken["step_map"] = broken["step_map"][:2]  # s3 is not delivered
        calls = []

        def handler(seen):
            calls.append(seen)
            if seen.schema.__name__ == "ScriptOut":
                n = sum(1 for c in calls if c.schema.__name__ == "ScriptOut")
                return broken if n == 1 else PANEL_SCRIPT
            return scenario.handler(seen)

        rt, llm = fake_runtime(scenario, settings)
        llm.handler = handler
        script, _ = await script_for(rt)
        assert set(script.step_map) == {"s1", "s2", "s3"}
        retry = [s for s in llm.seen if s.schema.__name__ == "ScriptOut"][1]
        assert "Step s3 is not delivered by any sentence" in retry.system

    async def test_a_script_that_never_covers_a_step_is_a_502(self, settings, scenario):
        broken = copy.deepcopy(PANEL_SCRIPT)
        broken["step_map"] = broken["step_map"][:2]
        scenario.script = broken
        rt, _ = fake_runtime(scenario, settings)
        with pytest.raises(UpstreamError) as err:
            await script_for(rt)
        assert err.value.code == "script_incomplete"

    async def test_a_step_not_asked_by_any_question_is_a_problem(self, settings, scenario):
        broken = copy.deepcopy(PANEL_SCRIPT)
        broken["questions"] = [
            {"text": "q", "step_ids": ["s1"]},
            {"text": "q2", "step_ids": ["s2"]},
        ]
        scenario.script = broken
        rt, llm = fake_runtime(scenario, settings)
        with pytest.raises(UpstreamError):
            await script_for(rt)
        assert any("Step s3 is not checked by any question" in s.system for s in llm.seen)

    async def test_a_step_that_cannot_be_checked_by_voice_is_delivered_but_not_asked(
        self, settings, scenario
    ):
        steps = [STEPS[0], STEPS[1], STEPS[2].model_copy(update={"speakable": False})]
        broken = copy.deepcopy(PANEL_SCRIPT)
        broken["questions"] = [
            {"text": "q1", "step_ids": ["s1", "s2", "s3"]},
            {"text": "q2", "step_ids": ["s2"]},
        ]
        scenario.script = broken
        rt, _ = fake_runtime(scenario, settings)
        script, _ = await script_for(rt, steps=steps)
        assert "s3" in script.step_map
        assert all("s3" not in q.step_ids for q in script.questions)

    async def test_only_a_wrong_question_count_is_accepted_after_one_retry(
        self, settings, scenario
    ):
        one_question = copy.deepcopy(PANEL_SCRIPT)
        one_question["questions"] = [{"text": "only", "step_ids": ["s1", "s2", "s3"]}]
        scenario.script = one_question
        rt, llm = fake_runtime(scenario, settings)
        script, _ = await script_for(rt)
        assert len(script.questions) == 1
        assert sum(1 for s in llm.seen if s.schema.__name__ == "ScriptOut") == 2

    async def test_a_reexplain_round_continues_question_numbering_and_avoids_old_questions(
        self, fake_rt
    ):
        rt, llm = fake_rt
        script, _ = await script_for(
            rt,
            steps=STEPS[1:],
            round_kind="reexplain",
            first_qnum=3,
            previous_questions=["old question text"],
        )
        assert [q.id for q in script.questions][0] == "q3"
        prompt = llm.seen[0].system
        assert "RE-EXPLANATION" in prompt and "old question text" in prompt
        assert "1 to 2 open questions" in prompt

    async def test_unknown_step_ids_in_the_output_are_ignored(self, settings, scenario):
        noisy = copy.deepcopy(PANEL_SCRIPT)
        noisy["step_map"].append({"step_id": "s9", "sentence_indices": [0, 77]})
        scenario.script = noisy
        rt, _ = fake_runtime(scenario, settings)
        script, _ = await script_for(rt)
        assert "s9" not in script.step_map


class TestReExplainAndTranscribe:
    async def test_the_explanation_prompt_names_only_the_open_steps_and_the_last_verdicts(
        self, fake_rt
    ):
        rt, llm = fake_rt
        ratings = {
            "s2": Rating(step_id="s2", verdict="contradicted", reason="Said clip on at the top.")
        }
        text, meta = await phases.explain(
            rt, steps=STEPS[1:], ratings=ratings, supervisor_lang="en", sop_title="Panel"
        )
        assert text == "Switch it off, lock it, and test it dead."
        prompt = llm.seen[0].system
        assert "s2:" in prompt and "s3:" in prompt and "s1:" not in prompt
        assert "contradicted (Said clip on at the top.)" in prompt
        assert "unclear" in prompt  # s3 had no rating
        assert meta.model_ids == {"re_explain": "fake-flash-001"}

    async def test_supervisor_speech_to_text_sends_the_audio_and_returns_clean_text(
        self, settings, scenario
    ):
        scenario.transcription_text = "  Isolate   the breaker \n now "
        rt, llm = fake_runtime(scenario, settings)
        assert (
            await phases.transcribe_instruction(rt, tone_wav(), "en") == "Isolate the breaker now"
        )
        assert llm.seen[0].has_audio and "English" in llm.seen[0].system


class TestSopQuote:
    def test_an_exact_substring_is_kept(self):
        assert verified_sop_quote("Switch off and isolate", SOP.text) == "Switch off and isolate"

    def test_a_blank_quote_is_none(self):
        assert verified_sop_quote("  ", SOP.text) is None
        assert verified_sop_quote(None, SOP.text) is None
