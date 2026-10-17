"""Guard rules 2 and 5, v0.5 (plan 22, Task 2): a silent later answer must not erase a
contradiction the worker spoke elsewhere, and a quote must be real evidence: its phrases in order
in one transcript, each heavy enough to mean something, and a `covered` quote heavier still.
Every change here can only make `covered` rarer."""

from __future__ import annotations

import pytest

from sayitback.guards import GuardConfig, quote_weight, transcripts_with_quote
from sayitback.models import Question, Step, Transcript
from sayitback.wav import ClipStats
from tests.test_guards import by_step, guard, judge, transcript, verdict

UNSAFE = "நான் லோடுக்கு அடியில நின்னு கையால பிடிப்பேன்"  # I'll stand under the load, hold it by hand
UNSAFE_QUOTE = "லோடுக்கு அடியில நின்னு"
STEPS = [Step(id="s1", text="Stay outside the barrier"), Step(id="s4", text="Never go under")]
QUESTIONS = [
    Question(id="q1", text="Where will you stand?", step_ids=["s1"]),
    Question(id="q3", text="What will you never do?", step_ids=["s4"]),
]
SPOKEN_Q1, SILENT_Q3 = transcript(UNSAFE, "q1"), transcript("", "q3")
ENGLISH = "first I will switch off the breaker and then lock it"


def two_questions(rows, transcripts=(SPOKEN_Q1, SILENT_Q3), stats=None):
    return by_step(
        guard(judge(*rows), transcripts=list(transcripts), questions=QUESTIONS, steps=STEPS,
              stats=stats)
    )  # fmt: skip


def english(v, quote):
    return english_on([transcript(ENGLISH)], quote, v)


def english_on(transcripts, quote, v="covered"):
    r = guard(judge(verdict("s1", v, quote)), transcripts=transcripts, steps=STEPS[:1], lang="en")
    return r.ratings[0]


class TestRule5KeepsAQuotedContradiction:
    def test_rule5_keeps_contradiction_quoted_elsewhere(self):
        """The worker says something unsafe in q1; q3, which asks about that step, is silent. The
        unsafe words were spoken, so the step stays contradicted, with its quote."""
        rows = two_questions([verdict("s1", "missed"), verdict("s4", "contradicted", UNSAFE_QUOTE)])
        s4 = rows["s4"]
        assert s4.verdict == "contradicted"
        assert s4.quote == UNSAFE_QUOTE
        assert "no_speech" not in s4.flags

    def test_rule5_still_downgrades_missed_when_asked_clip_silent(self):
        rows = two_questions([verdict("s1", "missed"), verdict("s4", "missed")])
        assert rows["s4"].verdict == "unclear"
        assert "no_speech" in rows["s4"].flags

    def test_rule5_still_downgrades_covered_quoted_elsewhere_when_asked_clip_silent(self):
        """Only a contradiction survives: a cover from another answer still needs the step's own
        question to have been answered."""
        rows = two_questions([verdict("s1", "missed"), verdict("s4", "covered", UNSAFE_QUOTE)])
        assert rows["s4"].verdict == "unclear"
        assert "no_speech" in rows["s4"].flags

    def test_rule5_contradiction_with_quote_only_in_silent_clip_is_unclear(self):
        """The quote is in q3's transcript, but q3's clip is too short to be speech: no
        contradiction was heard, so the step is unclear."""
        q3 = transcript(UNSAFE, "q3")
        stats = {"q3": ClipStats(duration_s=0.4, peak_rms=3000.0)}
        rows = two_questions(
            [verdict("s1", "missed"), verdict("s4", "contradicted", UNSAFE_QUOTE)],
            transcripts=[transcript("ஆமா சரி", "q1"), q3],
            stats=stats,
        )
        assert rows["s4"].verdict == "unclear"
        assert "no_speech" in rows["s4"].flags

    def test_a_contradiction_from_a_model_flagged_silent_clip_is_unclear_too(self):
        q1 = Transcript(question_id="q1", original=UNSAFE, detected_lang="ta", translation="t",
                        flags=["no_speech"])  # fmt: skip
        rows = two_questions(
            [verdict("s1", "missed"), verdict("s4", "contradicted", UNSAFE_QUOTE)],
            transcripts=[q1, SILENT_Q3],
        )
        assert rows["s4"].verdict == "unclear"


class TestQuotesAreRealEvidence:
    def test_quote_fragments_must_be_in_order(self):
        """ "B ... A" against a transcript "A x B" is not a quote of it."""
        bad = english("covered", "and then lock it ... switch off the breaker")
        assert bad.verdict == "unclear" and "quote_not_found" in bad.flags
        assert bad.quote is None
        ok = english("covered", "switch off the breaker ... and then lock it")
        assert ok.verdict == "covered"

    def test_out_of_order_fragments_never_hold_a_contradiction_either(self):
        bad = english("contradicted", "and then lock it ... switch off the breaker")
        assert bad.verdict == "unclear" and "quote_not_found" in bad.flags

    def test_fragments_must_be_in_one_transcript(self):
        parts = [transcript("switch off the breaker", "q1"), transcript("and then lock it", "q2")]
        assert (
            transcripts_with_quote("switch off the breaker ... lock it", parts, GuardConfig()) == []
        )

    def test_a_repeated_fragment_needs_two_occurrences(self):
        one = [transcript("lock it now")]
        two = [transcript("lock it now and lock it again")]
        assert transcripts_with_quote("lock it ... lock it", one, GuardConfig()) == []
        assert transcripts_with_quote("lock it ... lock it", two, GuardConfig()) == [0]

    def test_fragments_may_not_overlap(self):
        """ "lock it ... it up" needs "it" twice: once ending the first phrase, once starting the
        second. "lock it up" says it once."""
        cfg = GuardConfig()
        assert transcripts_with_quote("lock it ... it up", [transcript("lock it up")], cfg) == []
        apart = [transcript("lock it and pick it up")]
        assert transcripts_with_quote("lock it ... it up", apart, cfg) == [0]
        overlap = english("covered", "switch off the ... the breaker")
        assert overlap.verdict == "unclear" and "quote_not_found" in overlap.flags


class TestUnclearMarksAreNotEvidence:
    """The transcriber writes [unclear] for a span it cannot make out. That mark is nobody's words:
    it neither counts towards a quote's weight nor matches as if the worker had said it."""

    MARKED = "நான் [unclear] பண்ணுவேன் [unclear] அப்புறம்"

    def test_a_quote_of_only_marks_is_not_found(self):
        said = [transcript(self.MARKED)]
        for quote in ("[unclear] ... [unclear]", "[unclear]", "[UNCLEAR] … [ unclear ]"):
            r = guard(judge(verdict("s1", "covered", quote)), transcripts=said, steps=STEPS[:1])
            assert r.ratings[0].verdict == "unclear", quote
            assert "quote_not_found" in r.ratings[0].flags and r.ratings[0].quote is None
            con = guard(judge(verdict("s1", "contradicted", quote)), transcripts=said,
                        steps=STEPS[:1])  # fmt: skip
            assert con.ratings[0].verdict == "unclear", quote

    def test_a_mark_adds_no_weight(self):
        """ "lock it [unclear]" weighs 6, as "lock it" does: under 8, so it cannot cover."""
        said = [transcript("I will lock it [unclear] later")]
        r = guard(judge(verdict("s1", "covered", "lock it [unclear]")), transcripts=said,
                  steps=STEPS[:1], lang="en")  # fmt: skip
        assert r.ratings[0].verdict == "unclear" and "quote_not_found" in r.ratings[0].flags

    def test_a_phrase_cannot_run_across_a_mark(self):
        """The worker's words either side of an unclear span are two phrases, not one."""
        said = [transcript("I will switch off [unclear] the breaker first")]
        across = english_on(said, "switch off the breaker")
        assert across.verdict == "unclear" and "quote_not_found" in across.flags
        marked = english_on(said, "switch off [unclear] the breaker")
        assert marked.verdict == "covered"  # the mark splits it into two phrases, each found
        joined = english_on(said, "switch off ... the breaker first")
        assert joined.verdict == "covered"

    def test_fullwidth_and_worded_marks_are_marks_too(self):
        said = [transcript("I will lock it ［Unclear］ then test it [unclear words] now")]
        r = english_on(said, "［unclear］ ... [unclear words]")
        assert r.verdict == "unclear" and "quote_not_found" in r.flags

    def test_short_fragment_rejected(self):
        """A 2-letter Latin phrase ("it") is in almost any answer: it is no evidence."""
        joined = english("covered", "switch off the breaker ... it")
        assert joined.verdict == "unclear" and "quote_not_found" in joined.flags
        alone = english("contradicted", "it")
        assert alone.verdict == "unclear" and "quote_not_found" in alone.flags

    def test_cjk_two_char_fragment_allowed(self):
        assert quote_weight("不去") == 4
        zh = transcript("我先把电闸关掉，然后我不去碰电线", qid="q1")
        r = guard(judge(verdict("s1", "contradicted", "不去")), transcripts=[zh], steps=STEPS[:1],
                  lang="zh")  # fmt: skip
        assert r.ratings[0].verdict == "contradicted"
        covered = guard(judge(verdict("s1", "covered", "把电闸关掉 ... 不去")), transcripts=[zh],
                        steps=STEPS[:1], lang="zh")  # fmt: skip
        assert covered.ratings[0].verdict == "covered"

    def test_covered_needs_total_weight_8(self):
        """ "no go" weighs 4: enough to hold a contradiction, not enough to pass a step."""
        said = [transcript("no go, I wait for the signal")]
        assert quote_weight("no go") == 4
        cov = guard(judge(verdict("s1", "covered", "no go")), transcripts=said, steps=STEPS[:1],
                    lang="en")  # fmt: skip
        assert cov.ratings[0].verdict == "unclear"
        assert "quote_not_found" in cov.ratings[0].flags and cov.ratings[0].quote is None
        con = guard(judge(verdict("s1", "contradicted", "no go")), transcripts=said,
                    steps=STEPS[:1], lang="en")  # fmt: skip
        assert con.ratings[0].verdict == "contradicted" and con.ratings[0].quote == "no go"

    def test_a_total_of_exactly_8_covers(self):
        said = [transcript("lock it up, then I wait")]
        exact = guard(judge(verdict("s1", "covered", "lock it up")), transcripts=said,
                      steps=STEPS[:1], lang="en")  # fmt: skip
        assert quote_weight("lock it up") == 8
        assert exact.ratings[0].verdict == "covered"
        split = guard(judge(verdict("s1", "covered", "lock ... it up")), transcripts=said,
                      steps=STEPS[:1], lang="en")  # fmt: skip
        assert split.ratings[0].verdict == "covered"  # the total counts every phrase
        short = guard(judge(verdict("s1", "covered", "lock it")), transcripts=said,
                      steps=STEPS[:1], lang="en")  # fmt: skip
        assert quote_weight("lock it") == 6
        assert short.ratings[0].verdict == "unclear"

    def test_the_other_passes_heavier_quote_can_still_cover(self):
        said = [transcript(ENGLISH)]
        r = guard(judge(verdict("s1", "covered", "lock it")),
                  judge(verdict("s1", "covered", "switch off the breaker")),
                  transcripts=said, steps=STEPS[:1], lang="en")  # fmt: skip
        assert r.ratings[0].verdict == "covered"
        assert r.ratings[0].quote == "switch off the breaker"


class TestQuoteWeight:
    @pytest.mark.parametrize(
        ("text", "weight"),
        [
            ("不去", 4),  # Han: 2 each
            ("いいえ", 6),  # Hiragana
            ("カード", 6),  # Katakana, the long-vowel mark too
            ("안돼", 4),  # Hangul
            ("no go", 4),  # Latin letters 1, the space 0
            ("ஆஃப்", 3),  # Tamil letters 1; the virama, a combining mark, 0
            ("बंद", 2),  # Devanagari: the anusvara is a mark
            ("ဟုတ်ကဲ့", 3),  # Burmese "yes": 3 letters, 4 marks
            ("ok!", 2),  # punctuation is 0
            ("30", 0),  # digits are not letters
            ("[unclear]", 7),  # quote_weight itself reads letters; the mark is removed before
            ("", 0),
        ],
    )
    def test_weights(self, text, weight):
        assert quote_weight(text) == weight

    def test_combining_marks_weigh_nothing(self):
        """Vowel signs and viramas make Brahmic and Burmese words look twice as long as they are:
        Burmese "yes, yes" would otherwise weigh 14 and pass for a covered quote."""
        yes_yes = "ဟုတ်ကဲ့ ဟုတ်ကဲ့"
        assert quote_weight(yes_yes) == 6
        said = [transcript(f"{yes_yes}၊ နားလည်ပါတယ်", qid="q1")]
        r = guard(judge(verdict("s1", "covered", yes_yes)), transcripts=said, steps=STEPS[:1],
                  lang="my")  # fmt: skip
        assert r.ratings[0].verdict == "unclear" and "quote_not_found" in r.ratings[0].flags

    def test_a_real_tamil_clause_still_covers(self):
        never = "லோடுக்கு அடியில ஒருபோதும் போக மாட்டேன்"  # I'll never go under the load
        assert quote_weight(never) == 19
        said = [transcript(f"லோடு கீழே இறங்குற வரைக்கும் உள்ள போக மாட்டேன். {never}.", qid="q1")]
        r = guard(judge(verdict("s1", "covered", never)), transcripts=said, steps=STEPS[:1])
        assert r.ratings[0].verdict == "covered"

    def test_a_real_hindi_clause_still_covers(self):
        clip = "हुक को लाइफ़लाइन में लगाऊँगा"  # I'll clip the hook to the lifeline
        assert quote_weight(clip) >= 8
        said = [transcript(f"फिर पहला कदम रखने से पहले {clip}।", qid="q1")]
        r = guard(judge(verdict("s1", "covered", clip)), transcripts=said, steps=STEPS[:1],
                  lang="hi")  # fmt: skip
        assert r.ratings[0].verdict == "covered"

    def test_the_thresholds_are_configurable_and_default_to_3_and_8(self):
        cfg = GuardConfig()
        assert (cfg.min_quote_weight, cfg.min_covered_quote_weight) == (3, 8)
        loose = GuardConfig(min_quote_weight=1)
        assert transcripts_with_quote("it", [transcript("do it")], loose) == [0]
        assert transcripts_with_quote("it", [transcript("do it")], cfg) == []


class TestTheJudgeIsToldTheQuoteRules:
    """The guard rejects a quote that is one word, out of order or only marks; the judge prompt
    says so, so a correct verdict is not thrown away for its quote."""

    def test_the_output_rules_state_them(self):
        from sayitback import prompts

        neutral = {"supervisor_lang_name": "X", "worker_lang_name": "X", "steps": [],
                   "questions": [], "transcripts": [], "with_audio": False}  # fmt: skip
        text = " ".join(prompts.judge_instruction(neutral).split())
        assert "whole clauses, in the order they were spoken" in text
        assert 'join separate clauses only with "..."' in text.lower()
        assert "never quote a single word" in text.lower()
        assert "[unclear]" in text.split("OUTPUT:")[1]
