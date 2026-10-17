"""Guard rule 1, v0.5.3 (build-notes/23): two passes that agree give that verdict; either pass
`contradicted` gives `contradicted`; ANY other disagreement is `unclear` + `passes_disagreed`.
A split can never be `covered`, and `missed` no longer outranks `unclear`: a judge that heard
the worker touch the step is not overruled by one that heard nothing (it was the more severe
verdict winning that turned "I'll join the wire and step onto it carefully" into "Missed")."""

from __future__ import annotations

import pytest

from sayitback.guards import combine
from sayitback.models import Rating
from tests.test_guards import STEPS, by_step, guard, judge, verdict

VERDICTS = ("covered", "unclear", "missed", "contradicted")
QUOTE = "பிரேக்கரை ஆஃப் பண்ணி"  # a verbatim phrase of tests.test_guards.TAMIL, weight over 8

# (pass A, pass B) -> the final verdict; every one of the 16 pairs, written out.
TABLE = {
    ("covered", "covered"): "covered",
    ("covered", "unclear"): "unclear",
    ("covered", "missed"): "unclear",
    ("covered", "contradicted"): "contradicted",
    ("unclear", "covered"): "unclear",
    ("unclear", "unclear"): "unclear",
    ("unclear", "missed"): "unclear",
    ("unclear", "contradicted"): "contradicted",
    ("missed", "covered"): "unclear",
    ("missed", "unclear"): "unclear",
    ("missed", "missed"): "missed",
    ("missed", "contradicted"): "contradicted",
    ("contradicted", "covered"): "contradicted",
    ("contradicted", "unclear"): "contradicted",
    ("contradicted", "missed"): "contradicted",
    ("contradicted", "contradicted"): "contradicted",
}


def rating(v, quote=None, reason="", conf=0.9):
    return Rating(step_id="s1", verdict=v, quote=quote, reason=reason, confidence=conf)


def test_the_table_has_every_pair_once():
    assert set(TABLE) == {(a, b) for a in VERDICTS for b in VERDICTS} and len(TABLE) == 16


@pytest.mark.parametrize(("a", "b"), sorted(TABLE))
def test_combine_gives_the_tables_verdict_and_flags_only_a_split(a, b):
    work = combine(rating(a, QUOTE), rating(b, QUOTE))
    assert work.verdict == TABLE[(a, b)]
    assert ("passes_disagreed" in work.flags) == (a != b)


@pytest.mark.parametrize(("a", "b"), sorted(TABLE))
def test_the_whole_guard_gives_the_same_verdict(a, b):
    """Through rules 2 to 6 as well: both passes quote a real phrase with high confidence."""
    r = guard(judge(verdict("s1", a, QUOTE)), judge(verdict("s1", b, QUOTE)), steps=STEPS[:1])
    assert r.ratings[0].verdict == TABLE[(a, b)]
    assert ("passes_disagreed" in r.ratings[0].flags) == (a != b)


@pytest.mark.parametrize(("a", "b"), [p for p in sorted(TABLE) if p[0] != p[1]])
def test_a_split_is_never_covered(a, b):
    r = guard(judge(verdict("s1", a, QUOTE)), judge(verdict("s1", b, QUOTE)), steps=STEPS[:1])
    assert r.ratings[0].verdict != "covered"
    assert r.next_action == "reexplain"


class TestASplitThatBecomesUnclear:
    """Which quote and which reason the supervisor reads next to "Ask again"."""

    SAID = "Said to join the wire before stepping on, but not what clips to it."

    def test_covered_against_unclear_shows_the_unclear_passes_quote_and_reason(self):
        for passes in (("covered", "unclear"), ("unclear", "covered")):
            by_verdict = {
                "covered": rating("covered", "covered quote", "The worker states every element."),
                "unclear": rating("unclear", "unclear quote", self.SAID),
            }
            work = combine(*(by_verdict[v] for v in passes))
            assert work.verdict == "unclear"
            assert work.reason == self.SAID
            assert work.quotes[0][0] == "unclear quote"

    def test_covered_against_unclear_falls_back_to_the_covered_passes_quote(self):
        work = combine(
            rating("covered", "covered quote", "all stated"), rating("unclear", None, "x")
        )
        assert [q for q, _ in work.quotes] == ["covered quote"] and work.reason == "x"

    def test_covered_against_missed_keeps_the_covered_quote_and_the_missed_reason(self):
        """The covered pass's reason ("states every element") would contradict the chip beside it;
        the missed pass's names what is not there. The quote is still checked by rule 2."""
        for passes in (("covered", "missed"), ("missed", "covered")):
            by_verdict = {
                "covered": rating("covered", QUOTE, "The worker states every element."),
                "missed": rating("missed", None, "Nothing is said about the lifeline."),
            }
            work = combine(*(by_verdict[v] for v in passes))
            assert work.verdict == "unclear"
            assert work.reason == "Nothing is said about the lifeline."
            assert [q for q, _ in work.quotes] == [QUOTE]

    def test_unclear_against_missed_shows_the_unclear_passes_reason(self):
        for passes in (("unclear", "missed"), ("missed", "unclear")):
            by_verdict = {
                "unclear": rating("unclear", None, self.SAID),
                "missed": rating("missed", None, "The answer does not address the step."),
            }
            work = combine(*(by_verdict[v] for v in passes))
            assert (work.verdict, work.reason) == ("unclear", self.SAID)

    def test_the_covered_quote_goes_through_rule_2(self):
        """A covered pass whose quote is not in the transcript shows no quote, and the step is
        still just unclear (an unclear step needs no quote, so no `quote_not_found`)."""
        r = guard(
            judge(verdict("s1", "covered", "made up words that are not said")),
            judge(verdict("s1", "missed")),
            steps=STEPS[:1],
        )
        only = r.ratings[0]
        assert only.verdict == "unclear" and only.quote is None
        assert "quote_not_found" not in only.flags and "passes_disagreed" in only.flags

    def test_a_verbatim_covered_quote_reaches_the_rating(self):
        r = guard(
            judge(verdict("s1", "covered", QUOTE)), judge(verdict("s1", "missed")), steps=STEPS[:1]
        )
        assert r.ratings[0].verdict == "unclear" and r.ratings[0].quote == QUOTE


class TestAnEmptyReasonNeverBorrowsTheCoveredPassesSentence:
    """A blocked or missing judge B is an `unclear` pass with confidence 0 and no reason."""

    def test_a_missed_reason_stands_in_for_the_empty_unclear_one(self):
        for passes in (("missed", "unclear"), ("unclear", "missed")):
            by_verdict = {"missed": rating("missed", None, "Nothing about the lifeline."),
                          "unclear": rating("unclear", None, "", conf=0.0)}  # fmt: skip
            work = combine(*(by_verdict[v] for v in passes))
            assert (work.verdict, work.reason) == ("unclear", "Nothing about the lifeline.")

    def test_a_covered_reason_is_never_shown_beside_ask_again(self):
        for passes in (("covered", "unclear"), ("unclear", "covered")):
            by_verdict = {"covered": rating("covered", QUOTE, "The worker states every element."),
                          "unclear": rating("unclear", None, "", conf=0.0)}  # fmt: skip
            work = combine(*(by_verdict[v] for v in passes))
            assert (work.verdict, work.reason) == ("unclear", "")
            assert [q for q, _ in work.quotes] == [QUOTE]  # what was said still shows

    def test_two_empty_reasons_give_an_empty_one(self):
        work = combine(rating("missed", None, ""), rating("unclear", None, ""))
        assert work.reason == ""


class TestAgreementAndContradictionAreAsBefore:
    def test_agreement_keeps_pass_as_reason_and_both_quotes(self):
        a, b = rating("covered", "quote a", "reason a"), rating("covered", "quote b", "reason b")
        work = combine(a, b)
        assert work.reason == "reason a" and [q for q, _ in work.quotes] == ["quote a", "quote b"]
        assert work.flags == []

    def test_a_contradiction_shows_only_the_contradicting_passes_quote_and_reason(self):
        for passes in (("covered", "contradicted"), ("contradicted", "covered")):
            by_verdict = {
                "covered": rating("covered", "good quote", "covers it"),
                "contradicted": rating("contradicted", "unsafe quote", "says an unsafe thing"),
            }
            work = combine(*(by_verdict[v] for v in passes))
            assert work.verdict == "contradicted" and work.reason == "says an unsafe thing"
            assert [q for q, _ in work.quotes] == ["unsafe quote"]
            assert work.flags == ["passes_disagreed"]

    def test_a_single_pass_is_unchanged(self):
        for v in VERDICTS:
            work = combine(rating(v, "q", "r"), None)
            assert (work.verdict, work.reason, work.flags) == (v, "r", [])
            assert [q for q, _ in work.quotes] == ["q"]


class TestTheLeadCase:
    """A worker who touched the step ("I'll join the wire and step onto it carefully"): one pass
    heard that and said unclear, the transcript-only pass said missed. Before v0.5.3 the step
    read "Missed"; it must read "Ask again", with the judge's own sentence."""

    def test_one_judge_missing_the_touch_cannot_overrule_the_one_that_heard_it(self):
        heard = Rating(
            step_id="s1", verdict="unclear", reason="Said to join the wire before stepping on.",
            confidence=0.8,
        )  # fmt: skip
        nothing = rating("missed", None, "The worker only mentioned climbing carefully.")
        work = combine(heard, nothing)
        assert (work.verdict, work.flags) == ("unclear", ["passes_disagreed"])
        assert work.reason == heard.reason

    def test_the_result_is_ask_again_not_missed_end_to_end(self):
        r = guard(judge(verdict("s1", "unclear")), judge(verdict("s1", "missed")), steps=STEPS[:1])
        assert by_step(r)["s1"].verdict == "unclear"
