"""Guard rules 1-7 (API.md, "Guard rules"), one test group per rule."""

from __future__ import annotations

import pytest

from sayitback import catalog
from sayitback.guards import (
    GuardConfig,
    is_language_mismatch,
    normalise,
    run_guards,
    script_shares,
)
from sayitback.models import Question, Script, Step, Transcript
from sayitback.wav import ClipStats

TAMIL = "நான் பிரேக்கரை ஆஃப் பண்ணி லாக் போட்டு டெஸ்டர் வைத்து செக் பண்ணுவேன்"
CFG = GuardConfig(min_confidence=0.75)
STEPS = [Step(id="s1", text="Isolate"), Step(id="s2", text="Lock"), Step(id="s3", text="Test")]
ASK_ALL = [Question(id="q1", text="What will you do?", step_ids=["s1", "s2", "s3"])]


def verdict(step_id, v="covered", quote="", conf=0.9):
    return {
        "step_id": step_id,
        "verdict": v,
        "quote": quote,
        "quote_translation": "",
        "reason": "r",
        "confidence": conf,
    }


def judge(*rows):
    return {"ratings": list(rows)}


def covered_all(quote="பிரேக்கரை ஆஃப் பண்ணி", conf=0.9):
    return judge(*(verdict(s.id, "covered", quote, conf) for s in STEPS))


def transcript(original=TAMIL, qid="q1", flags=None):
    return Transcript(
        question_id=qid, original=original, detected_lang="ta", translation="t", flags=flags or []
    )


def guard(
    raw_a,
    raw_b="same",
    transcripts=None,
    *,
    questions=ASK_ALL,
    stats=None,
    lang="ta",
    script=None,
    steps=STEPS,
):
    raw_b = raw_a if raw_b == "same" else raw_b
    return run_guards(
        steps=steps,
        questions=questions,
        transcripts=transcripts if transcripts is not None else [transcript()],
        raw_a=raw_a,
        raw_b=raw_b,
        stats=stats or {},
        worker_ranges=catalog.unicode_ranges(lang),
        cfg=CFG,
        script=script,
    )


def by_step(result):
    return {r.step_id: r for r in result.ratings}


class TestRule1Combine:
    """The table of all 16 pairs, and which quote and reason a split shows, is in
    test_guards_rule1.py."""

    def test_both_covered_stays_covered(self):
        r = guard(covered_all())
        assert [x.verdict for x in r.ratings] == ["covered"] * 3
        assert all("passes_disagreed" not in x.flags for x in r.ratings)

    def test_agreement_on_missed_is_not_flagged(self):
        r = guard(judge(verdict("s1", "missed")), judge(verdict("s1", "missed")), steps=STEPS[:1])
        assert r.ratings[0].flags == []

    def test_single_pass_uses_judge_a_alone(self):
        r = run_guards(
            steps=STEPS[:1], questions=ASK_ALL, transcripts=[transcript()],
            raw_a=judge(verdict("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி")), raw_b=None,
            stats={}, worker_ranges=catalog.unicode_ranges("ta"), cfg=GuardConfig(passes=1),
        )  # fmt: skip
        assert r.pass_b == []
        assert r.ratings[0].verdict == "covered"
        assert r.ratings[0].flags == []

    def test_with_two_passes_configured_a_missing_judge_b_output_can_never_cover(self):
        """If judge B returns nothing (blocked, empty, thought-only), the check must not quietly
        become a one-judge check."""
        r = guard(judge(verdict("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி")), raw_b=None, steps=STEPS[:1])
        assert [x.verdict for x in r.pass_b] == ["unclear"] and r.pass_b[0].confidence == 0.0
        assert r.ratings[0].verdict == "unclear"
        assert "passes_disagreed" in r.ratings[0].flags

    def test_a_judge_that_rates_a_step_twice_is_held_to_its_worst_verdict(self):
        quote = "பிரேக்கரை ஆஃப் பண்ணி"
        twice = judge(verdict("s1", "missed"), verdict("s1", "covered", quote))
        assert guard(twice, steps=STEPS[:1]).ratings[0].verdict == "missed"
        assert (
            guard(
                judge(verdict("s1", "covered", quote), verdict("s1", "contradicted", quote)),
                steps=STEPS[:1],
            )
            .ratings[0]
            .verdict
            == "contradicted"
        )

    def test_a_contradicted_verdict_never_shows_the_other_passes_covering_quote(self):
        good = "பிரேக்கரை ஆஃப் பண்ணி"
        r = guard(
            judge(verdict("s1", "covered", good)),
            judge(verdict("s1", "contradicted", "made up quote")),
            steps=STEPS[:1],
        )
        assert r.ratings[0].verdict == "unclear" and "quote_not_found" in r.ratings[0].flags
        assert r.ratings[0].quote is None

    def test_a_missing_rating_is_unclear(self):
        r = guard(judge(verdict("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி")), steps=STEPS[:2])
        assert by_step(r)["s2"].verdict == "unclear"
        assert by_step(r)["s2"].confidence is None

    def test_a_garbage_verdict_is_unclear(self):
        r = guard(judge(verdict("s1", "definitely")), steps=STEPS[:1])
        assert r.ratings[0].verdict == "unclear"


class TestRule2Quote:
    def test_covered_needs_a_quote_found_in_a_transcript(self):
        r = guard(covered_all(quote="இது பேச்சில் இல்லை"))
        assert {x.verdict for x in r.ratings} == {"unclear"}
        assert all("quote_not_found" in x.flags and x.quote is None for x in r.ratings)

    def test_an_empty_quote_is_not_found(self):
        r = guard(covered_all(quote=""), steps=STEPS[:1])
        assert r.ratings[0].verdict == "unclear"
        assert "quote_not_found" in r.ratings[0].flags

    def test_matching_ignores_case_punctuation_whitespace_and_width(self):
        original = "I will switch OFF the breaker, then   lock it!"
        quote = "switch off the breaker then lock it"
        r = guard(
            judge(verdict("s1", "covered", quote)),
            transcripts=[transcript(original)],
            steps=STEPS[:1],
            lang="en",
        )
        assert r.ratings[0].verdict == "covered"
        full = guard(
            judge(verdict("s1", "covered", "ＳＷＩＴＣＨ　ＯＦＦ")),
            transcripts=[transcript(original)],
            steps=STEPS[:1],
            lang="en",
        )
        assert full.ratings[0].verdict == "covered"

    def test_phrases_joined_by_an_ellipsis_must_each_be_verbatim(self):
        original = "first the breaker off and then the lock goes on"
        ok = guard(judge(verdict("s1", "covered", "the breaker off ... the lock goes on")),
                   transcripts=[transcript(original)], steps=STEPS[:1], lang="en")  # fmt: skip
        bad = guard(judge(verdict("s1", "covered", "the breaker off ... then the tester")),
                    transcripts=[transcript(original)], steps=STEPS[:1], lang="en")  # fmt: skip
        assert ok.ratings[0].verdict == "covered"
        assert bad.ratings[0].verdict == "unclear"

    def test_a_one_character_quote_is_not_evidence(self):
        r = guard(judge(verdict("s1", "covered", "ப")), steps=STEPS[:1])
        assert r.ratings[0].verdict == "unclear"

    def test_contradicted_also_needs_a_real_quote(self):
        r = guard(judge(verdict("s1", "contradicted", "invented words")), steps=STEPS[:1])
        assert r.ratings[0].verdict == "unclear"
        assert "quote_not_found" in r.ratings[0].flags

    def test_a_missed_verdict_keeps_its_verdict_and_drops_an_unverifiable_quote(self):
        r = guard(judge(verdict("s1", "missed", "invented words")), steps=STEPS[:1])
        assert r.ratings[0].verdict == "missed"
        assert r.ratings[0].quote is None

    def test_the_other_passes_quote_is_used_when_only_it_is_verbatim(self):
        good = "பிரேக்கரை ஆஃப் பண்ணி"
        r = guard(
            judge(verdict("s1", "covered", "made up")),
            judge(verdict("s1", "covered", good)),
            steps=STEPS[:1],
        )
        assert r.ratings[0].verdict == "covered"
        assert r.ratings[0].quote == good


class TestRule3Confidence:
    def test_low_confidence_in_either_pass_abstains(self):
        quote = "பிரேக்கரை ஆஃப் பண்ணி"
        r = guard(
            judge(verdict("s1", "covered", quote, 0.95)),
            judge(verdict("s1", "covered", quote, 0.6)),
            steps=STEPS[:1],
        )
        assert r.ratings[0].verdict == "unclear"
        assert "low_confidence" in r.ratings[0].flags

    def test_exactly_the_threshold_passes(self):
        r = guard(covered_all(conf=0.75), steps=STEPS[:1])
        assert r.ratings[0].verdict == "covered"

    def test_a_missing_confidence_counts_as_zero(self):
        row = verdict("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி")
        del row["confidence"]
        assert guard(judge(row), steps=STEPS[:1]).ratings[0].verdict == "unclear"


class TestRule4Language:
    def test_odia_worker_answering_in_hindi_is_a_mismatch(self):
        hindi = "मैं पहले ब्रेकर बंद करूंगा और फिर ताला लगाऊंगा"
        odia_ranges = catalog.unicode_ranges("or")
        assert is_language_mismatch(hindi, odia_ranges, CFG)
        r = guard(
            judge(verdict("s1", "covered", "ब्रेकर बंद करूंगा")), transcripts=[transcript(hindi)],
            steps=STEPS[:1], lang="or",
        )  # fmt: skip
        assert r.ratings[0].verdict == "unclear"
        assert "language_mismatch" in r.ratings[0].flags
        assert "language_mismatch" in r.transcripts[0].flags

    def test_odia_script_for_an_odia_worker_is_fine(self):
        odia = "ମୁଁ ପ୍ରଥମେ ବ୍ରେକର ବନ୍ଦ କରିବି ଏବଂ ତାଲା ଲଗାଇବି"
        assert not is_language_mismatch(odia, catalog.unicode_ranges("or"), CFG)
        r = guard(
            judge(verdict("s1", "covered", "ବ୍ରେକର ବନ୍ଦ କରିବି")),  # weight 10 (v0.5)
            transcripts=[transcript(odia)],
            steps=STEPS[:1],
            lang="or",
        )
        assert r.ratings[0].verdict == "covered"

    def test_neighbouring_scripts_are_told_apart(self):
        tamil, odia = "நான் பிரேக்கரை ஆஃப் பண்ணுவேன்", "ମୁଁ ବ୍ରେକର ବନ୍ଦ କରିବି"
        assert is_language_mismatch(tamil, catalog.unicode_ranges("or"), CFG)
        assert is_language_mismatch(odia, catalog.unicode_ranges("ta"), CFG)

    def test_latin_text_for_a_tamil_worker_is_a_mismatch(self):
        assert is_language_mismatch(
            "I will switch off the breaker first", catalog.unicode_ranges("ta"), CFG
        )

    def test_code_switching_with_enough_worker_script_is_not_a_mismatch(self):
        mixed = "நான் breaker off பண்ணுவேன் then lock போடுவேன்"
        shares = script_shares(mixed, catalog.unicode_ranges("ta"))
        assert shares[0] >= 0.3
        assert not is_language_mismatch(mixed, catalog.unicode_ranges("ta"), CFG)

    def test_unclear_marks_and_digits_do_not_count_as_latin(self):
        assert not is_language_mismatch("[unclear] [unclear] 10", catalog.unicode_ranges("ta"), CFG)
        assert script_shares("[unclear]", catalog.unicode_ranges("ta")) == (0.0, 0.0, 0.0)

    def test_a_step_covered_by_a_good_transcript_survives_a_mismatched_one(self):
        good, bad = transcript(TAMIL, "q1"), transcript("I will switch off the breaker", "q2")
        questions = [
            Question(id="q1", text="a", step_ids=["s1"]),
            Question(id="q2", text="b", step_ids=["s1"]),
        ]
        r = guard(judge(verdict("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி")), transcripts=[good, bad],
                  questions=questions, steps=STEPS[:1])  # fmt: skip
        assert r.ratings[0].verdict == "covered"
        assert "language_mismatch" in r.transcripts[1].flags


class TestRule5NoSpeech:
    def test_an_empty_transcript_is_flagged_and_cannot_cover(self):
        r = guard(
            judge(verdict("s1", "covered", "anything")),
            transcripts=[transcript("")],
            steps=STEPS[:1],
        )
        assert "no_speech" in r.transcripts[0].flags
        assert r.ratings[0].verdict == "unclear"
        assert "no_speech" in r.ratings[0].flags

    def test_the_model_flag_counts(self):
        r = guard(
            covered_all(), transcripts=[transcript(TAMIL, flags=["no_speech"])], steps=STEPS[:1]
        )
        assert r.ratings[0].verdict == "unclear"

    def test_a_clip_shorter_than_0_8_s_is_no_speech(self):
        stats = {"q1": ClipStats(duration_s=0.5, peak_rms=3000.0)}
        r = guard(covered_all(), stats=stats, steps=STEPS[:1])
        assert "no_speech" in r.transcripts[0].flags
        assert r.ratings[0].verdict == "unclear"

    def test_a_near_silent_clip_is_no_speech(self):
        stats = {"q1": ClipStats(duration_s=3.0, peak_rms=20.0)}
        r = guard(covered_all(), stats=stats, steps=STEPS[:1])
        assert "no_speech" in r.transcripts[0].flags

    def test_a_judged_missed_step_asked_only_of_a_silent_clip_is_unclear_not_missed(self):
        r = guard(judge(verdict("s1", "missed")), transcripts=[transcript("")], steps=STEPS[:1])
        assert r.ratings[0].verdict == "unclear"
        assert "no_speech" in r.ratings[0].flags

    def test_another_answer_can_still_cover_the_step(self):
        silent, spoken = transcript("", "q1"), transcript(TAMIL, "q2")
        questions = [
            Question(id="q1", text="a", step_ids=["s1"]),
            Question(id="q2", text="b", step_ids=["s1"]),
        ]
        r = guard(judge(verdict("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி")), transcripts=[silent, spoken],
                  questions=questions, steps=STEPS[:1])  # fmt: skip
        assert r.ratings[0].verdict == "covered"

    def test_a_clip_of_normal_length_and_level_is_speech(self):
        stats = {"q1": ClipStats(duration_s=2.0, peak_rms=1500.0)}
        r = guard(covered_all(), stats=stats)
        assert "no_speech" not in r.transcripts[0].flags


class TestRule6NotAsked:
    def test_a_step_with_no_question_is_unclear_not_asked(self):
        asked = [Question(id="q1", text="a", step_ids=["s1"])]
        r = guard(covered_all(), questions=asked)
        rows = by_step(r)
        assert rows["s1"].verdict == "covered"
        for sid in ("s2", "s3"):
            assert rows[sid].verdict == "unclear"
            assert "not_asked" in rows[sid].flags
            assert rows[sid].quote is None

    def test_a_step_the_script_never_delivered_is_not_asked(self):
        script = Script(
            instruction="a", questions=ASK_ALL, step_map={"s1": [0], "s2": [0]}, closing="c"
        )
        r = guard(covered_all(), script=script)
        assert by_step(r)["s3"].verdict == "unclear"
        assert "not_asked" in by_step(r)["s3"].flags

    def test_an_empty_step_map_means_unknown_not_undelivered(self):
        script = Script(instruction="a", questions=ASK_ALL, closing="c")
        assert guard(covered_all(), script=script).next_action == "decide"


class TestRule7NextAction:
    def test_decide_only_when_every_step_in_scope_is_covered(self):
        assert guard(covered_all()).next_action == "decide"

    @pytest.mark.parametrize("bad", ["missed", "contradicted", "unclear"])
    def test_one_open_step_means_reexplain(self, bad):
        rows = [verdict("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணி"), verdict("s2", bad, "பிரேக்கரை ஆஃப் பண்ணி"),
                verdict("s3", "covered", "பிரேக்கரை ஆஃப் பண்ணி")]  # fmt: skip
        assert guard(judge(*rows)).next_action == "reexplain"


class TestNormalise:
    def test_nfkc_casefold_punctuation_whitespace(self):
        assert normalise("  Ｈello,  WORLD!! ") == "hello world"

    def test_format_marks_are_dropped(self):
        assert normalise("a‍b") == "ab"

    def test_combining_marks_are_kept(self):
        assert normalise("பிரேக்கர்") == "பிரேக்கர்"
