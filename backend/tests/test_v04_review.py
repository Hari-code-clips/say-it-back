"""The v0.4 review fixes (API.md Deviations, "orchestrator, v0.4 review fixes"): sample answers never
count as the worker's, rule 8 whenever Live spoke, numbers in order, negations per sentence, replies
that must stay neutral, verify binding more, and Live sessions that append."""

from __future__ import annotations

import asyncio
import json

import pytest

from sayitback import catalog, chain
from sayitback.delivery import delivery_checks, negation_changed, numbers, reply_not_neutral
from sayitback.live_transcripts import LiveTranscripts
from sayitback.models import Briefing, LiveRecord, Script
from tests.fakes import PANEL_SCRIPT, Scenario, panel_script, rating, tone_wav, transcript
from tests.flow_support import make_env
from tests.helpers import api_client, approve_round, drive_to_round, error_of, make_app, post_check
from tests.test_webhook import decided

APPROVED_TA = "கரண்ட் இல்லை என்று டெஸ்டரில் சரிபார்த்த பிறகுதான் பேனலைத் திறங்கள்."
ANSWER = "பிரேக்கரை ஆஃப் பண்ணுவேன், லாக் போட்டு டேக் மாட்டுவேன், டெஸ்டர் வச்சு கரண்ட் இல்லைன்னு பார்ப்பேன்"
SIGNALMAN = "சிக்னல்மேன் சொல்வதை மட்டும் கேளுங்கள்."
HINT = "நன்றி. சிக்னல்மேன் சொல்வதை மட்டும் கேளுங்கள்."  # the reviewer's short hint after q1


def all_covered(script=None) -> Scenario:
    return Scenario(
        script=script or panel_script(sentences=[*PANEL_SCRIPT["sentences"][:2], APPROVED_TA]),
        transcripts=[transcript("q1", ANSWER), transcript("q2", ANSWER)],
        judge_a=[
            rating("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணுவேன்"),
            rating("s2", "covered", "லாக் போட்டு டேக் மாட்டுவேன்"),
            rating("s3", "covered", "டெஸ்டர் வச்சு கரண்ட் இல்லைன்னு பார்ப்பேன்"),
        ],
    )


def check_with_samples(client, bid, samples, n=1, **clips):
    clips = clips or {"q1": tone_wav(), "q2": tone_wav()}
    files = [(q, (f"{q}.wav", d, "audio/wav")) for q, d in clips.items()]
    files.append(("meta", (None, json.dumps({"mode": "turn", "sampleAnswers": samples}))))
    response = client.post(f"/api/briefings/{bid}/rounds/{n}/check", files=files)
    assert response.status_code == 200, response.text
    return response.json()


def record_live(env, delivered):
    def change(raw):
        raw["rounds"][0]["live"] = {"model": "gemini-3.8-live", "startedAt": "2026-10-14T10:00:00.000Z",
                                    "delivered": delivered, "heard": {}}  # fmt: skip
        return raw

    asyncio.run(env.store.update(env.bid, change))


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


# 1. Sample answers never count as the worker's -----------------------------------------------


class TestSampleAnswersAreNotTheWorkers:
    @pytest.fixture
    def env(self, settings):
        return make_env(settings, all_covered())

    def test_steps_covered_only_by_samples_are_listed_and_keep_their_verdict(self, env):
        check_with_samples(env.client, env.bid, ["q1", "q2"])
        b = env.client.get(f"/api/briefings/{env.bid}").json()
        assert b["sampleCoveredStepIds"] == ["s1", "s2", "s3"]
        assert set(b["latestVerdicts"].values()) == {"covered"}

    def test_go_without_a_reason_is_422_reason_required(self, env):
        """The reviewer's repro: a sample-only cover used to let Go through with no reason."""
        check_with_samples(env.client, env.bid, ["q1", "q2"])
        response = env.client.post(f"/api/briefings/{env.bid}/decision", json={"value": "go"})
        assert error_of(response) == (422, "reason_required")

    def test_go_with_a_reason_lists_them_as_open(self, env):
        check_with_samples(env.client, env.bid, ["q1", "q2"])
        body = env.client.post(
            f"/api/briefings/{env.bid}/decision", json={"value": "go", "reason": "Demo run."}
        ).json()
        assert body["decision"]["openStepIds"] == ["s1", "s2", "s3"]

    def test_a_worker_answer_that_holds_the_quote_makes_the_step_the_workers(self, env):
        """q1 (s1, s2, s3) is a sample; q2 (s3) is the worker's own and holds s3's quote."""
        check_with_samples(env.client, env.bid, ["q1"])
        b = env.client.get(f"/api/briefings/{env.bid}").json()
        assert b["sampleCoveredStepIds"] == ["s1", "s2"]
        body = env.client.post(f"/api/briefings/{env.bid}/decision", json={"value": "no_go"}).json()
        assert body["decision"]["openStepIds"] == ["s1", "s2"]

    def test_a_worker_answer_without_the_quote_lends_nothing(self, settings):
        sc = all_covered()
        sc.transcripts = [transcript("q1", ANSWER), transcript("q2", "தெரியலை")]
        env = make_env(settings, sc)
        check_with_samples(env.client, env.bid, ["q1"])
        b = env.client.get(f"/api/briefings/{env.bid}").json()
        assert b["sampleCoveredStepIds"] == ["s1", "s2", "s3"]

    def test_without_samples_the_list_is_empty_and_go_needs_no_reason(self, env):
        post_check(env.client, env.bid, 1, q1=tone_wav(), q2=tone_wav())
        assert env.client.get(f"/api/briefings/{env.bid}").json()["sampleCoveredStepIds"] == []
        assert (
            env.client.post(f"/api/briefings/{env.bid}/decision", json={"value": "go"}).status_code
            == 200
        )

    def test_re_explain_scope_is_unchanged(self, env):
        check_with_samples(env.client, env.bid, ["q1", "q2"])
        response = env.client.post(f"/api/briefings/{env.bid}/rounds", json={})
        assert error_of(response) == (
            409,
            "invalid_state",
        )  # every step is covered: nothing to re-explain

    def test_it_is_derived_never_stored_and_never_taken_from_the_store(self, env):
        check_with_samples(env.client, env.bid, ["q1", "q2"])
        path = env.settings.data_dir / "briefings" / f"{env.bid}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert "sampleCoveredStepIds" not in raw
        raw["sampleCoveredStepIds"] = []
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        assert env.client.get(f"/api/briefings/{env.bid}").json()["sampleCoveredStepIds"] == [
            "s1",
            "s2",
            "s3",
        ]

    def test_the_webhook_record_lists_the_sample_answers(self):
        b = decided()
        b.rounds[0].sample_answers = ["q1"]
        from sayitback.webhook import chat_payload, json_record

        assert json_record(b)["sampleAnswers"] == [{"round": 1, "questionId": "q1"}]
        assert "Demo: synthetic sample answers" in chat_payload(b)["text"]
        assert json_record(decided())["sampleAnswers"] == []


# 2. Rule 8 whenever round.live exists ---------------------------------------------------------


class TestRule8InTurnMode:
    def test_a_dropped_negation_live_said_counts_in_turn_mode(self, settings):
        """The reviewer's repro: the check came in as turn mode after Live had spoken."""
        env = make_env(settings, all_covered())
        delivered = faithful(env)
        delivered["instruction"] = delivered["instruction"].replace("இல்லை ", "")
        record_live(env, delivered)
        rnd = post_check(env.client, env.bid, 1, q1=tone_wav(), q2=tone_wav()).json()
        assert rnd["mode"] == "turn"
        assert [r["verdict"] for r in rnd["ratings"]] == ["unclear"] * 3
        assert "delivery_mismatch" in rnd["ratings"][0]["flags"]

    def test_segments_live_never_spoke_are_ignored_in_turn_mode(self, settings):
        env = make_env(settings, all_covered())
        record_live(env, {"instruction": faithful(env)["instruction"]})  # Live then dropped
        rnd = post_check(env.client, env.bid, 1, q1=tone_wav(), q2=tone_wav()).json()
        assert [d["segment"] for d in rnd["delivery"]] == ["instruction"]
        assert [r["verdict"] for r in rnd["ratings"]] == ["covered"] * 3

    def test_without_a_live_record_turn_mode_has_no_delivery_check(self, settings):
        env = make_env(settings, all_covered())
        rnd = post_check(env.client, env.bid, 1, q1=tone_wav(), q2=tone_wav()).json()
        assert rnd["delivery"] == [] and rnd["nextAction"] == "decide"


# 3. Numbers in order ---------------------------------------------------------------------------


def one(said, approved, lang):
    script = Script(instruction=approved, questions=[], closing="x")
    checks = delivery_checks(
        script, {"instruction": said, "closing": "x"}, catalog.unicode_ranges(lang),
        min_script_share=0.7, min_similarity=0.8, markers=catalog.markers(lang),
    )  # fmt: skip
    return checks[0]


class TestNumbersInOrder:
    def test_fifteen_metres_is_not_fifty_metres_in_chinese(self):
        """The reviewer's repro: 十五 and 五十 hold the same number words."""
        check = one("请保持五十米的距离，等吊物落地。", "请保持十五米的距离，等吊物落地。", "zh")
        assert "number_changed" in check.issues and not check.ok
        assert one("请保持十五米的距离，等吊物落地。", "请保持十五米的距离，等吊物落地。", "zh").ok

    def test_swapped_digits_are_a_change(self):
        spec = catalog.markers("en")
        assert numbers("5 m then 10 m", (), "word") != numbers("10 m then 5 m", (), "word")
        assert numbers("stay 3 metres back", spec.number_words, spec.match) == ["#3"]
        assert numbers("two then three", spec.number_words, spec.match) == ["two", "three"]


# 4. Negations per sentence --------------------------------------------------------------------


class TestNegationsPerSentence:
    APPROVED = "Never stand under the load. Stay outside the barrier until the load is landed. Follow only the signalman."

    def test_a_moved_negation_is_negation_changed(self):
        """The reviewer's repro: the totals match, the sentences do not."""
        said = "Stand under the load. Stay outside the barrier until the load is landed. Never follow only the signalman."
        check = one(said, self.APPROVED, "en")
        assert "negation_changed" in check.issues and not check.ok

    def test_the_faithful_read_out_is_ok(self):
        assert one(self.APPROVED, self.APPROVED, "en").ok

    def test_line_breaks_in_the_approved_script_are_sentence_ends(self):
        approved = "Never stand under the load\nStay outside the barrier\nFollow only the signalman"
        said = "Stand under the load. Never stay outside the barrier. Follow only the signalman."
        assert negation_changed(said, approved, catalog.markers("en"))

    def test_two_approved_sentences_said_as_one_are_compared_together(self):
        said = "Never stand under the load and stay outside the barrier until the load is landed. Follow only the signalman."
        assert not negation_changed(said, self.APPROVED, catalog.markers("en"))

    def test_sentences_that_cannot_be_aligned_fail_safe(self):
        assert negation_changed(
            "Something else entirely. Nothing like it.", self.APPROVED, catalog.markers("en")
        )
        # no negation anywhere, so only the alignment can fail it
        approved = "Stay outside the barrier. Follow only the signalman."
        assert negation_changed("Bring your lunch. Wear a hat.", approved, catalog.markers("en"))
        assert not negation_changed(approved, approved, catalog.markers("en"))

    def test_a_negation_moved_between_sentences_that_start_alike_is_negation_changed(self):
        """build-notes/34-breadth.md's repro. "never st" starts both said sentences, so both
        approved ones align with the second, whose count matches; the first said sentence is a
        piece of the first approved one without its "never"."""
        approved = "Never stand under the load. Stay outside the barrier until it is landed."
        said = "Stand under the load. Never stay outside the barrier until it is landed."
        check = one(said, approved, "en")
        assert check.similarity >= 0.8  # similarity alone would pass it
        assert "negation_changed" in check.issues and not check.ok
        approved_2 = "Stay outside the barrier until it is landed. Never stand under the load."
        said_2 = "Never stay outside the barrier until it is landed. Stand under the load."
        assert negation_changed(said_2, approved_2, catalog.markers("en"))
        uneven = "Never stand under the load or walk below the boom, stay back."
        assert negation_changed(
            "Stand under the load or walk below the boom. Never stay back.", uneven,
            catalog.markers("en"),
        )  # fmt: skip

    def test_pieces_that_keep_their_negations_still_pass(self):
        """A short sentence joined into a long one is not a piece of the long one, and a split
        whose pieces hold the sentence's negations passes as it did."""
        en = catalog.markers("en")
        approved = "Never stand under the load while the crane is slewing overhead. Do not run."
        said = "Never stand under the load while the crane is slewing overhead and do not run."
        assert not negation_changed(said, approved, en)
        uneven = "Never stand under the load or walk below the boom, stay back."
        assert not negation_changed(
            "Never stand under the load or walk below the boom. Stay back.", uneven, en
        )

    def test_tamil_and_hindi_sentence_ends(self):
        ta = "லோடுக்கு அடியில் ஒருபோதும் போகாதீர்கள். பேரிகேடுக்கு வெளியே நில்லுங்கள்."
        moved = "லோடுக்கு அடியில் போங்கள். பேரிகேடுக்கு வெளியே நிற்காதீர்கள் ஒருபோதும்."
        assert negation_changed(moved, ta, catalog.markers("ta"))
        hi = "लोड के नीचे मत जाओ। सिग्नलमैन की बात सुनो।"
        assert negation_changed("लोड के नीचे जाओ। सिग्नलमैन की बात मत सुनो।", hi, catalog.markers("hi"))
        assert not negation_changed(hi, hi, catalog.markers("hi"))


# 5. Replies stay neutral ----------------------------------------------------------------------

LIFT_SCRIPT = {
    "sentences": ["லோடுக்கு அடியில் ஒருபோதும் போகாதீர்கள்.", "லோடு கீழே இறங்கும் வரை பேரிகேடுக்கு வெளியே நில்லுங்கள்.", SIGNALMAN],
    "step_map": [{"step_id": "s1", "sentence_indices": [0]}, {"step_id": "s2", "sentence_indices": [1]},
                 {"step_id": "s3", "sentence_indices": [2]}],
    "questions": [{"text": "லோடு நகரும்போது நீங்கள் எங்கே இருப்பீர்கள்?", "step_ids": ["s1", "s2"]},
                  {"text": "லிஃப்ட் நடக்கும்போது யாருடைய வழிகாட்டுதலைப் பின்பற்றுவீர்கள்?", "step_ids": ["s3"]}],
    "closing": "நன்றி. மேற்பார்வையாளருக்காகக் காத்திருங்கள்.",
}  # fmt: skip
LIFT_ANSWER = "பேரிகேடுக்கு வெளியே நிப்பேன், லோடுக்கு அடியில போக மாட்டேன், சிக்னல்மேன் சொல்றதை கேப்பேன்"


class TestNeutralReplies:
    @pytest.fixture
    def env(self, settings):
        sc = Scenario(
            script=LIFT_SCRIPT,
            transcripts=[transcript("q1", LIFT_ANSWER), transcript("q2", LIFT_ANSWER)],
            judge_a=[
                rating("s1", "covered", "லோடுக்கு அடியில போக மாட்டேன்"),
                rating("s2", "covered", "பேரிகேடுக்கு வெளியே நிப்பேன்"),
                rating("s3", "covered", "சிக்னல்மேன் சொல்றதை கேப்பேன்"),
            ],
        )
        return make_env(settings, sc)

    def test_the_reviewers_short_hint_is_not_neutral_and_reaches_the_later_question(self, env):
        delivered = faithful(env)
        delivered["q1.reply"] = HINT
        record_live(env, delivered)
        rnd = post_check(env.client, env.bid, 1, mode="live", q1=tone_wav(), q2=tone_wav()).json()
        reply = next(d for d in rnd["delivery"] if d["segment"] == "q1.reply")
        assert reply["issues"] == ["reply_not_neutral"] and not reply["ok"]  # short: not too long
        verdicts = {r["stepId"]: (r["verdict"], r["flags"]) for r in rnd["ratings"]}
        assert verdicts["s3"] == (
            "unclear",
            ["delivery_mismatch"],
        )  # q2's step: heard after the hint
        assert verdicts["s1"][0] == verdicts["s2"][0] == "unclear"

    def test_a_neutral_thanks_passes(self, env):
        record_live(env, faithful(env))
        rnd = post_check(env.client, env.bid, 1, mode="live", q1=tone_wav(), q2=tone_wav()).json()
        assert all(d["ok"] for d in rnd["delivery"]) and rnd["nextAction"] == "decide"

    def test_thanks_words_from_the_catalog_never_count(self):
        script = "\n".join([*LIFT_SCRIPT["sentences"], "உங்கள் வேலை முடிந்ததும் என்ன செய்வீர்கள்?"])
        spec = catalog.markers("ta")
        assert "உங்கள்" in spec.thanks_words  # a word of the script and of a neutral thanks
        assert not reply_not_neutral("நன்றி. உங்கள் பதிலுக்கு நன்றி.", script, spec)
        assert reply_not_neutral("பேரிகேடுக்கு வெளியே", script, spec)

    def test_thanks_words_are_normalised_like_the_reply(self):
        from sayitback.catalog import LanguageMarkers

        spec = LanguageMarkers(
            match="word", negation_markers=(), number_words=(), thanks_words=("Wait.",)
        )
        assert not reply_not_neutral("WAIT, please.", "Wait for the signal.", spec)

    def test_chinese_has_no_spaces_so_three_character_runs_count(self):
        spec = catalog.markers("zh")
        assert spec.spaced is False
        script = "只听信号员的指挥。\n吊装过程中，你听谁的指挥？"
        assert not reply_not_neutral("谢谢你的回答，请等主管。", script, spec)
        assert reply_not_neutral("谢谢。只听信号员的。", script, spec)

    def test_english_words_under_three_letters_never_count(self):
        script = "Do it at the gate. Go to the gate."
        assert not reply_not_neutral("Thank you, go on.", script, catalog.markers("en"))
        assert reply_not_neutral("Thanks, the gate.", script, catalog.markers("en"))


# 6. Verify binds more -------------------------------------------------------------------------


class TestVerifyBindsMore:
    @pytest.fixture
    def env(self, settings):
        env = make_env(settings, all_covered())
        record_live(env, faithful(env))
        post_check(env.client, env.bid, 1, mode="live", q1=tone_wav(), q2=tone_wav())
        assert env.client.get(f"/api/briefings/{env.bid}/verify").json()["ok"] is True
        env.events = env.client.get(f"/api/briefings/{env.bid}").json()["events"]
        return env

    def tamper(self, env, edit):
        path = env.settings.data_dir / "briefings" / f"{env.bid}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        edit(raw)
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return env.client.get(f"/api/briefings/{env.bid}/verify").json()

    def seq(self, env, kind):
        return next(e["seq"] for e in env.events if e["type"] == kind)

    @pytest.mark.parametrize(
        ("what", "edit", "event", "reason"),
        [
            ("latestVerdicts", lambda raw: raw.update(latestVerdicts={k: "missed" for k in raw["latestVerdicts"]}), "round_judged", "verdicts_mismatch"),
            ("a transcript", lambda raw: raw["rounds"][0]["transcripts"][0].update(original="edited"), "round_judged", "evidence_mismatch"),
            ("nextAction", lambda raw: raw["rounds"][0].update(nextAction="reexplain"), "round_judged", "evidence_mismatch"),
            ("the delivery", lambda raw: raw["rounds"][0].update(delivery=[]), "round_judged", "evidence_mismatch"),
            ("pass B", lambda raw: raw["rounds"][0]["passB"][0].update(verdict="covered", reason="x"), "round_judged", "evidence_mismatch"),
            ("round.live", lambda raw: raw["rounds"][0]["live"]["delivered"].update(instruction="x"), "round_judged", "live_mismatch"),
            ("approvedBy", lambda raw: raw["rounds"][0].update(approvedBy="Mallory"), "script_approved", "approval_mismatch"),
            ("the site", lambda raw: raw.update(siteId="chennai"), "created", "created_mismatch"),
            ("the worker language", lambda raw: raw.update(workerLang="hi"), "created", "created_mismatch"),
        ],
    )  # fmt: skip
    def test_an_edit_is_found_at_the_event_that_binds_it(self, env, what, edit, event, reason):
        result = self.tamper(env, edit)
        assert (result["ok"], result["brokenAt"], result["reason"]) == (
            False,
            self.seq(env, event),
            reason,
        ), what

    def test_the_events_hold_the_new_bindings(self, env):
        created = next(e for e in env.events if e["type"] == "created")["data"]
        assert (created["siteId"], created["taskId"], created["supervisorLang"], created["workerLang"]) == (
            "sg", "panel-isolation", "en", "ta",
        )  # fmt: skip
        judged = next(e for e in env.events if e["type"] == "round_judged")["data"]
        b = Briefing.model_validate(env.client.get(f"/api/briefings/{env.bid}").json())
        assert judged["evidenceSha256"] == chain.evidence_sha(b.rounds[0])
        assert judged["liveSha256"] == chain.digest(b.rounds[0].live.wire())
        approved = next(e for e in env.events if e["type"] == "script_approved")["data"]
        assert "by" in approved

    def test_a_round_without_live_binds_null(self, settings):
        env = make_env(settings, all_covered())
        post_check(env.client, env.bid, 1, q1=tone_wav(), q2=tone_wav())
        events = env.client.get(f"/api/briefings/{env.bid}").json()["events"]
        assert next(e for e in events if e["type"] == "round_judged")["data"]["liveSha256"] is None

    def test_verdicts_before_any_judgement_must_be_empty(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app)
        bid, _ = drive_to_round(client)
        path = settings.data_dir / "briefings" / f"{bid}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["latestVerdicts"] = {"s1": "covered"}
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["ok"], result["reason"]) == (False, "unrecorded_change")

    def test_a_reexplained_briefing_still_verifies(self, settings):
        from tests.cap_support import script_for_open_steps
        from tests.flow_support import round_1_scenario, round_2_answers

        sc = round_1_scenario()
        env = make_env(settings, sc)
        post_check(env.client, env.bid, 1)
        script_for_open_steps(sc)
        env.client.post(f"/api/briefings/{env.bid}/rounds", json={"supervisorNote": "again"})
        approve_round(env.client, env.bid, 2, by="Sam")
        round_2_answers(sc)
        post_check(env.client, env.bid, 2, q3=tone_wav())
        assert env.client.get(f"/api/briefings/{env.bid}/verify").json()["ok"] is True


# 7. Live sessions append ----------------------------------------------------------------------


def test_a_second_live_session_appends_to_the_first():
    b = decided()
    b.status, b.decision = "briefing", None
    for rnd in b.rounds:
        rnd.judged_at = None
    first, second = LiveTranscripts(), LiveTranscripts()
    first.start_cue("instruction")
    first.model_final("Read once.")
    first.record_into(b, 1, model="m", started_at="t")
    second.start_cue("instruction")
    second.model_final("Read again, differently.")
    second.start_cue("q1")
    second.model_final("Question?")
    second.record_into(b, 1, model="m", started_at="t")
    assert b.rounds[0].live.delivered == {
        "instruction": "Read once. Read again, differently.",
        "q1": "Question?",
    }


def test_the_relay_merge_never_replaces_what_a_first_session_heard():
    b = decided()
    b.status, b.decision = "briefing", None
    b.rounds[0].judged_at = None
    b.rounds[0].live = LiveRecord(model="m", started_at="t", heard={"q1": "first answer"})
    t = LiveTranscripts()
    t.open_window("q1")
    t.worker_final("second answer")
    t.record_into(b, 1, model="m", started_at="t")
    assert b.rounds[0].live.heard == {"q1": "first answer second answer"}
