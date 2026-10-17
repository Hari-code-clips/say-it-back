"""API v0.4, "Delivery check" and guard rule 8: what Live said is checked against the approved
script for a dropped negation, a changed number and a long reply, and a step whose delivery fails
is never passed ("Ask again")."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from sayitback import catalog, guards, pipeline
from sayitback.delivery import (
    ascii_digits,
    count_terms,
    delivery_checks,
    negations,
    numbers,
    similarity,
)
from sayitback.models import DeliveryCheck, Question, Rating, Script
from tests.fakes import PANEL_SCRIPT, Scenario, panel_script, rating, tone_wav, transcript
from tests.flow_support import make_env
from tests.helpers import post_check

APPROVED_TA = "கரண்ட் இல்லை என்று டெஸ்டரில் சரிபார்த்த பிறகுதான் பேனலைத் திறங்கள்."
SAID_TA = "கரண்ட் என்று டெஸ்டரில் சரிபார்த்த பிறகுதான் பேனலைத் திறங்கள்."  # இல்லை dropped
TA = catalog.unicode_ranges("ta")
EN = catalog.unicode_ranges("en")


def one_segment(said: str, approved: str, lang: str = "ta", **kw) -> DeliveryCheck:
    script = Script(instruction=approved, questions=[], closing="")
    checks = delivery_checks(
        script,
        {"instruction": said},
        catalog.unicode_ranges(lang),
        min_script_share=0.7,
        min_similarity=kw.pop("min_similarity", 0.8),
        markers=catalog.markers(lang),
        **kw,
    )
    return checks[0]


class TestTheTamilNegationCase:
    def test_similarity_alone_would_pass_it(self):
        assert 0.94 <= similarity(SAID_TA, APPROVED_TA) <= 0.96

    def test_the_dropped_negation_is_negation_changed_and_not_ok(self):
        check = one_segment(SAID_TA, APPROVED_TA)
        assert check.similarity >= 0.8 and check.script_ok
        assert check.issues == ["negation_changed"] and check.ok is False
        assert check.said == SAID_TA

    def test_the_faithful_read_out_is_ok(self):
        check = one_segment(APPROVED_TA, APPROVED_TA)
        assert (check.ok, check.issues, check.similarity) == (True, [], 1.0)


class TestCounting:
    def test_tamil_matches_markers_inside_words(self):
        spec = catalog.markers("ta")
        assert spec.match == "substring"
        assert negations("லோடுக்கு அடியில் ஒருபோதும் போகாதீர்கள்", spec) == 2  # ஒருபோதும், ாதீர்கள்
        assert negations("லோடுக்கு அடியில் போங்கள்", spec) == 0

    def test_english_matches_whole_words_only(self):
        spec = catalog.markers("en")
        assert spec.match == "word"
        assert negations("Do not stand under the load", spec) == 1
        assert negations("Tie a knot. Note the nothing-burger.", spec) == 0 + 0  # "knot", "note"
        assert (
            negations("Don't stand there, never", spec) == 2
        )  # don't is normalised as the text is

    def test_markers_are_normalised_like_the_text(self):
        assert count_terms("DON’T go", ["don't"], "word") == {"dont": 1}

    def test_numbers_are_digit_runs_with_native_digits_and_number_words(self):
        spec = catalog.markers("ta")
        assert ascii_digits("௫ மீட்டர்") == "5 மீட்டர்"
        assert numbers("௫ மீட்டர்", spec.number_words, spec.match) == numbers(
            "5 மீட்டர்", spec.number_words, spec.match
        )
        assert numbers("5 மீட்டர்", (), "word") != numbers("10 மீட்டர்", (), "word")
        assert numbers("1,000 kg and 1.5 m", (), "word") == ["#1000", "#1.5"]
        assert numbers("1.50 kg, 007", (), "word") == ["#1.50", "#7"]
        assert numbers("ஐந்து மீட்டர்", spec.number_words, spec.match) != numbers(
            "பத்து மீட்டர்", spec.number_words, spec.match
        )

    def test_a_changed_number_is_number_changed(self):
        approved = "லோடிலிருந்து 5 மீட்டர் தள்ளி நில்லுங்கள்."
        check = one_segment("லோடிலிருந்து 3 மீட்டர் தள்ளி நில்லுங்கள்.", approved)
        assert check.similarity >= 0.8 and check.issues == ["number_changed"] and not check.ok
        assert one_segment("லோடிலிருந்து ௫ மீட்டர் தள்ளி நில்லுங்கள்.", approved).ok

    def test_hindi_and_chinese(self):
        hi = one_segment("यहाँ खड़े रहो", "यहाँ खड़े मत रहो", "hi", min_similarity=0.5)
        assert "negation_changed" in hi.issues
        zh = one_segment("站在吊物下面", "不要站在吊物下面", "zh", min_similarity=0.5)
        assert "negation_changed" in zh.issues

    def test_the_markers_come_from_the_catalog(self):
        for code in catalog.lang_codes():
            spec = catalog.markers(code)
            assert (
                spec.negation_markers and spec.number_words and spec.match in ("word", "substring")
            )


class TestTheIssues:
    def test_not_spoken(self):
        check = one_segment("", APPROVED_TA)
        assert (check.issues, check.ok, check.similarity, check.said) == (
            ["not_spoken"],
            False,
            0.0,
            None,
        )

    def test_wrong_script(self):
        check = one_segment("Current illai endru testeril", APPROVED_TA, min_similarity=0.0)
        assert "wrong_script" in check.issues and not check.ok and not check.script_ok

    def test_low_similarity_uses_the_setting(self):
        paraphrase = "டெஸ்டரில் பார்த்த பிறகு கரண்ட் இல்லை என்றால் திறங்கள்."
        assert one_segment(paraphrase, APPROVED_TA).issues == ["low_similarity"]
        near = one_segment(APPROVED_TA.replace("திறங்கள்", "திறக்கவும்"), APPROVED_TA)
        assert near.ok
        strict = one_segment(
            APPROVED_TA.replace("திறங்கள்", "திறக்கவும்"), APPROVED_TA, min_similarity=0.99
        )
        assert strict.issues == ["low_similarity"]

    def test_a_reply_carries_what_was_said_and_is_too_long_past_the_limit(self):
        script = Script(
            instruction="ஒன்று.", questions=[Question(id="q1", text="கேள்வி?")], closing="நன்றி."
        )
        delivered = {"instruction": "ஒன்று", "q1": "கேள்வி?", "q1.reply": "நன்றி.", "closing": "நன்றி"}
        long_reply = "நன்றி. சரியான பதில், லோடுக்கு அடியில் போகக்கூடாது என்பதையும் நினைவில் வையுங்கள்."
        kw = {"min_script_share": 0.7, "markers": catalog.markers("ta"), "reply_max_chars": 60}
        checks = {c.segment: c for c in delivery_checks(script, delivered, TA, **kw)}
        assert list(checks) == ["instruction", "q1", "q1.reply", "closing"]
        short = checks["q1.reply"]
        assert (short.ok, short.similarity, short.said, short.issues) == (True, 1.0, "நன்றி.", [])
        delivered["q1.reply"] = long_reply
        checks = {c.segment: c for c in delivery_checks(script, delivered, TA, **kw)}
        assert checks["q1.reply"].issues == ["reply_too_long"] and not checks["q1.reply"].ok
        assert checks["q1.reply"].said == long_reply

    def test_a_question_with_no_reply_has_no_reply_segment(self):
        script = Script(
            instruction="ஒன்று.", questions=[Question(id="q1", text="கேள்வி?")], closing="நன்றி."
        )
        checks = delivery_checks(script, {"q1": "கேள்வி?"}, TA, min_script_share=0.7)
        assert [c.segment for c in checks] == ["instruction", "q1", "closing"]


class TestRule8:
    QUESTIONS = [
        Question(id="q1", text="a", step_ids=["s1", "s2"]),
        Question(id="q2", text="b", step_ids=["s3"]),
    ]
    SCOPE = ["s1", "s2", "s3"]

    def ratings(self, *verdicts):
        return [
            Rating(step_id=f"s{i}", verdict=v, quote="x", flags=[])
            for i, v in enumerate(verdicts, 1)
        ]

    def check(self, segment, ok=False):
        return DeliveryCheck(
            segment=segment,
            similarity=1.0,
            script_ok=True,
            ok=ok,
            issues=[] if ok else ["low_similarity"],
        )

    def test_a_failed_instruction_touches_every_step_in_scope(self):
        out, action = guards.apply_delivery(
            self.ratings("covered", "covered", "covered"),
            [self.check("instruction")],
            self.QUESTIONS,
            self.SCOPE,
        )
        assert [r.verdict for r in out] == ["unclear"] * 3 and action == "reexplain"
        assert all(r.flags == ["delivery_mismatch"] and r.quote == "x" for r in out)

    def test_a_failed_question_touches_only_the_steps_it_checks(self):
        out, _ = guards.apply_delivery(
            self.ratings("covered", "covered", "covered"),
            [self.check("q2")],
            self.QUESTIONS,
            self.SCOPE,
        )
        assert [r.verdict for r in out] == ["covered", "covered", "unclear"]
        out, _ = guards.apply_delivery(
            self.ratings("covered", "covered", "covered"),
            [self.check("q1")],
            self.QUESTIONS,
            self.SCOPE,
        )
        assert [r.verdict for r in out] == ["unclear", "unclear", "covered"]

    def test_a_failed_reply_touches_its_question_and_every_later_one(self):
        """A hint said after q1's answer is heard before q2 is asked."""
        out, _ = guards.apply_delivery(
            self.ratings("covered", "covered", "covered"),
            [self.check("q1.reply")],
            self.QUESTIONS,
            self.SCOPE,
        )
        assert [r.verdict for r in out] == ["unclear", "unclear", "unclear"]
        out, _ = guards.apply_delivery(
            self.ratings("covered", "covered", "covered"),
            [self.check("q2.reply")],
            self.QUESTIONS,
            self.SCOPE,
        )
        assert [r.verdict for r in out] == ["covered", "covered", "unclear"]

    def test_a_failed_closing_touches_none(self):
        out, action = guards.apply_delivery(
            self.ratings("covered", "covered", "covered"),
            [self.check("closing")],
            self.QUESTIONS,
            self.SCOPE,
        )
        assert [r.verdict for r in out] == ["covered"] * 3 and action == "decide"

    def test_only_covered_becomes_unclear(self):
        out, _ = guards.apply_delivery(
            self.ratings("contradicted", "missed", "unclear"),
            [self.check("instruction")],
            self.QUESTIONS,
            self.SCOPE,
        )
        assert [r.verdict for r in out] == ["contradicted", "missed", "unclear"]
        assert all(r.flags == [] for r in out)

    def test_ok_checks_change_nothing(self):
        ratings = self.ratings("covered", "covered", "covered")
        checks = [
            self.check(s, ok=True) for s in ("instruction", "q1", "q1.reply", "q2", "closing")
        ]
        assert guards.apply_delivery(ratings, checks, self.QUESTIONS, self.SCOPE) == (
            ratings,
            "decide",
        )


# Rule 8 in the round's check, over the API --------------------------------------------------

SENTENCES = [PANEL_SCRIPT["sentences"][0], PANEL_SCRIPT["sentences"][1], APPROVED_TA]
ANSWER = "பிரேக்கரை ஆஃப் பண்ணுவேன், லாக் போட்டு டேக் மாட்டுவேன், டெஸ்டர் வச்சு கரண்ட் இல்லைன்னு பார்ப்பேன்"


@pytest.fixture
def scenario():
    return Scenario(
        script=panel_script(sentences=SENTENCES),
        transcripts=[transcript("q1", ANSWER), transcript("q2", ANSWER)],
        judge_a=[
            rating("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணுவேன்"),
            rating("s2", "covered", "லாக் போட்டு டேக் மாட்டுவேன்"),
            rating("s3", "covered", "டெஸ்டர் வச்சு கரண்ட் இல்லைன்னு பார்ப்பேன்"),
        ],
    )


@pytest.fixture
def env(settings, scenario):
    return make_env(settings, scenario)


def faithful(env) -> dict[str, str]:
    script = env.client.get(f"/api/briefings/{env.bid}").json()["rounds"][0]["script"]
    return {
        "instruction": " ".join(script["instruction"].split("\n")),
        "q1": script["questions"][0]["text"],
        "q1.reply": "நன்றி.",
        "q2": script["questions"][1]["text"],
        "q2.reply": "நன்றி.",
        "closing": script["closing"],
    }


def record_live(env, delivered: dict[str, str]) -> None:
    def change(raw):
        raw["rounds"][0]["live"] = {
            "model": "gemini-3.8-live", "startedAt": "2026-10-14T10:00:00.000Z",
            "delivered": delivered, "heard": {},
        }  # fmt: skip
        return raw

    asyncio.run(env.store.update(env.bid, change))


def live_check(env):
    response = post_check(env.client, env.bid, 1, mode="live", q1=tone_wav(), q2=tone_wav())
    assert response.status_code == 200, response.text
    return response.json()


class TestRule8InTheCheck:
    def test_a_faithful_delivery_passes_what_the_judges_passed(self, env):
        record_live(env, faithful(env))
        rnd = live_check(env)
        assert [r["verdict"] for r in rnd["ratings"]] == ["covered"] * 3
        assert rnd["nextAction"] == "decide" and all(d["ok"] for d in rnd["delivery"])

    def test_the_dropped_tamil_negation_turns_every_covered_step_into_ask_again(self, env):
        delivered = faithful(env)
        delivered["instruction"] = delivered["instruction"].replace("இல்லை ", "")
        record_live(env, delivered)
        rnd = live_check(env)
        instruction = next(d for d in rnd["delivery"] if d["segment"] == "instruction")
        assert instruction["similarity"] >= 0.9 and instruction["scriptOk"] is True
        assert instruction["issues"] == ["negation_changed"] and instruction["ok"] is False
        assert [(r["verdict"], r["flags"]) for r in rnd["ratings"]] == [
            ("unclear", ["delivery_mismatch"])
        ] * 3
        assert rnd["nextAction"] == "reexplain"
        briefing = env.client.get(f"/api/briefings/{env.bid}").json()
        assert set(briefing["latestVerdicts"].values()) == {"unclear"}
        judged = next(e for e in briefing["events"] if e["type"] == "round_judged")
        assert judged["data"]["deliveryOk"] is False and set(
            judged["data"]["verdicts"].values()
        ) == {"unclear"}

    def test_the_judges_own_passes_are_kept_as_they_were(self, env):
        delivered = faithful(env)
        delivered["instruction"] = delivered["instruction"].replace("இல்லை ", "")
        record_live(env, delivered)
        rnd = live_check(env)
        assert [r["verdict"] for r in rnd["passA"]] == ["covered"] * 3

    def test_a_long_reply_after_q2_touches_only_s3(self, env):
        delivered = faithful(env)
        delivered["q2.reply"] = "நன்றி. டெஸ்டர் வச்சு கரண்ட் இல்லைன்னு பார்த்த பிறகுதான் பேனலைத் திறக்கணும், சரியா?"
        record_live(env, delivered)
        rnd = live_check(env)
        assert [r["verdict"] for r in rnd["ratings"]] == ["covered", "covered", "unclear"]
        reply = next(d for d in rnd["delivery"] if d["segment"] == "q2.reply")
        assert reply["issues"] == ["reply_too_long", "reply_not_neutral"]
        assert reply["said"] == delivered["q2.reply"]

    def test_an_unspoken_closing_touches_no_step(self, env):
        delivered = faithful(env)
        del delivered["closing"]
        record_live(env, delivered)
        rnd = live_check(env)
        closing = next(d for d in rnd["delivery"] if d["segment"] == "closing")
        assert (
            closing["issues"] == ["not_spoken"]
            and [r["verdict"] for r in rnd["ratings"]] == ["covered"] * 3
        )

    def test_the_similarity_threshold_is_the_setting(self, settings, scenario):
        env = make_env(settings.with_overrides(delivery_min_similarity=1.0), scenario)
        delivered = faithful(env)
        delivered["q1"] = delivered["q1"].replace("செய்வீர்கள்", "செய்வீங்க")
        record_live(env, delivered)
        rnd = live_check(env)
        assert [r["verdict"] for r in rnd["ratings"]] == ["unclear", "unclear", "unclear"]

    def test_turn_mode_has_no_delivery_check(self, env):
        rnd = post_check(env.client, env.bid, 1, q1=tone_wav(), q2=tone_wav()).json()
        assert rnd["delivery"] == [] and rnd["nextAction"] == "decide"


def test_run_check_and_the_eval_interface_are_unchanged():
    params = list(inspect.signature(pipeline.run_check).parameters)
    assert params == [
        "steps", "questions", "clips", "worker_lang", "supervisor_lang", "script",
        "live_input_transcripts", "runtime", "before_call",
    ]  # fmt: skip
    assert "delivery" not in inspect.getsource(pipeline)
