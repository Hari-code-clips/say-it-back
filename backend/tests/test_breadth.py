"""16 Oct breadth (build-notes/34-breadth.md): English as an evaluator's worker language on both sites, and the two new
demo scripts (hot work in Bengali, trench entry in Odia).

English is offered for an evaluator who plays the worker, never as a worker language of the product: it is in each
site's `evaluatorLanguages`, not its `workerLanguages`. The backend needed no code for it; these tests pin that an English
worker briefing runs end to end offline, and that guard rule 4 still catches an answer in the wrong language."""

from __future__ import annotations

import pytest

from sayitback import catalog, validators
from sayitback.delivery import negation_changed, numbers
from sayitback.guards import GuardConfig, is_language_mismatch
from sayitback.live_runner import briefer_state
from sayitback.models import CreateBriefing, Question, Script
from sayitback.prompts import briefer_instruction
from tests.fakes import FakeTtsClient, Scenario, panel_script, rating, tone_wav, transcript
from tests.helpers import PANEL, api_client, drive_to_round, make_app, post_check

EN = catalog.unicode_ranges("en")
EN_SCRIPT = panel_script(
    sentences=[
        "Switch off the breaker.",
        "Put your lock on the breaker.",
        "Test it with the tester before you touch anything.",
    ],
    questions=[
        {"text": "What will you do before you open the panel?", "step_ids": ["s1", "s2", "s3"]},
        {"text": "How will you know there is no power?", "step_ids": ["s3"]},
    ],
    closing="Thank you. Please wait for your supervisor.",
)
EN_ANSWER = "First I will switch off the breaker and put my lock on it."
EN_ANSWER_2 = "I will test it with the tester before I touch anything."
TA_ANSWER = "முதல்ல பிரேக்கரை ஆஃப் பண்ணுவேன், லாக் போடுவேன்."
TA_ANSWER_2 = "டெஸ்டர் வச்சு செக் பண்ணிட்டுதான் தொடுவேன்."


# The catalog and validation ------------------------------------------------------------------


def test_english_is_each_sites_evaluator_language_and_never_one_of_its_worker_languages():
    for site in catalog.load_catalog()["sites"]:
        assert site["evaluatorLanguages"] == ["en"], site["id"]
        assert "en" not in site["workerLanguages"], site["id"]


def test_the_public_catalog_carries_the_evaluator_languages_for_the_start_screen():
    sites = catalog.public_view()["sites"]
    assert [s["evaluatorLanguages"] for s in sites] == [["en"], ["en"]]


def test_english_has_the_markers_the_delivery_check_counts():
    spec = catalog.markers("en")
    assert spec.match == "word" and spec.spaced
    assert {"not", "never", "don't", "won't"} <= set(spec.negation_markers)
    assert {"ten", "thirty"} <= set(spec.number_words) and spec.thanks_words


@pytest.mark.parametrize("site_id", ["sg", "chennai"])
def test_an_english_worker_briefing_is_valid_on_both_sites(settings, site_id):
    site = catalog.site(site_id)
    for supervisor in site["supervisorLanguages"]:
        body = CreateBriefing.model_validate(
            {**PANEL, "siteId": site_id, "supervisorLang": supervisor, "workerLang": "en"}
        )
        assert validators.briefing_request(body, settings).id == "SOP-EL-04"


# Guard rule 4, the delivery check and the briefer, in English ------------------------------------


def test_rule_4_takes_an_english_answer_as_the_right_language_for_an_english_worker():
    cfg = GuardConfig()
    assert not is_language_mismatch(EN_ANSWER, EN, cfg)
    assert is_language_mismatch(TA_ANSWER, EN, cfg)  # a Tamil answer to an English worker
    assert is_language_mismatch(EN_ANSWER, catalog.unicode_ranges("ta"), cfg)  # and the reverse


def test_the_delivery_check_counts_english_negations_and_numbers_as_words():
    spec = catalog.markers("en")
    assert negation_changed("Stand under the load.", "Never stand under the load.", spec)
    assert not negation_changed("Don't stand under it.", "Do not stand under it.", spec)
    assert negation_changed("Stand under it.", "Don't stand under it.", spec)  # a contraction dropped
    said = numbers("Watch for three minutes.", spec.number_words, spec.match)
    assert said != numbers("Watch for thirty minutes.", spec.number_words, spec.match)
    assert numbers("Clear 10 metres.", spec.number_words, spec.match) == ["#10"]


def test_the_live_briefer_speaks_only_english_to_an_english_worker():
    script = Script(
        instruction="Switch off the breaker.",
        questions=[Question(id="q1", text="What will you do first?")],
        closing="Thank you.",
    )
    text = briefer_instruction(briefer_state(script, "en"))
    assert "Speak only English. RESPOND IN ENGLISH." in text
    assert "a short neutral thanks in English" in text


# End to end over the API, offline ----------------------------------------------------------------


def english_world(settings, answers: tuple[str, str], lang: str):
    """An English worker briefing (Singapore, English supervisor) driven to an approved round 1."""
    scenario = Scenario(
        script=EN_SCRIPT,
        transcripts=[transcript("q1", answers[0], lang=lang), transcript("q2", answers[1], lang=lang)],
    )
    tts = FakeTtsClient()
    app, *_ = make_app(settings, scenario, tts_client=tts)
    client = api_client(app)
    bid, rnd = drive_to_round(client, {**PANEL, "workerLang": "en"})
    return client, bid, rnd, scenario, tts


def test_an_english_worker_answer_in_english_is_judged_and_can_be_covered(settings):
    client, bid, rnd, scenario, _ = english_world(settings, (EN_ANSWER, EN_ANSWER_2), "en")
    scenario.judge_a = [
        rating("s1", "covered", "switch off the breaker"),
        rating("s2", "covered", "put my lock on it"),
        rating("s3", "covered", "test it with the tester before I touch anything"),
    ]

    response = post_check(client, bid, rnd["n"], q1=tone_wav(), q2=tone_wav())

    assert response.status_code == 200, response.text
    body = response.json()
    assert {r["stepId"]: r["verdict"] for r in body["ratings"]} == dict.fromkeys(("s1", "s2", "s3"), "covered")
    assert not any("language_mismatch" in t["flags"] for t in body["transcripts"])
    assert client.get(f"/api/briefings/{bid}").json()["workerLang"] == "en"


def test_a_tamil_answer_to_an_english_worker_is_flagged_and_never_covered(settings):
    client, bid, rnd, scenario, _ = english_world(settings, (TA_ANSWER, TA_ANSWER_2), "ta")
    scenario.judge_a = [
        rating("s1", "covered", "பிரேக்கரை ஆஃப் பண்ணுவேன்"),
        rating("s2", "covered", "பண்ணுவேன், லாக் போடுவேன்"),  # rule 2: a covered quote weighs 8+ letters
        rating("s3", "covered", "டெஸ்டர் வச்சு செக் பண்ணிட்டுதான்"),
    ]

    response = post_check(client, bid, rnd["n"], q1=tone_wav(), q2=tone_wav())

    assert response.status_code == 200, response.text
    body = response.json()
    assert all("language_mismatch" in t["flags"] for t in body["transcripts"])
    for r in body["ratings"]:
        assert r["verdict"] == "unclear" and "language_mismatch" in r["flags"], r


def test_turn_mode_speaks_an_english_line_of_the_approved_script(settings):
    client, bid, rnd, _, tts = english_world(settings, (EN_ANSWER, EN_ANSWER_2), "en")

    spoken = client.post("/api/tts", json={"briefingId": bid, "n": rnd["n"], "text": "Switch off the breaker."})
    refused = client.post("/api/tts", json={"briefingId": bid, "n": rnd["n"], "text": "Something else."})

    assert spoken.status_code == 200 and spoken.headers["content-type"] == "audio/wav"
    assert refused.status_code == 422
    assert [c["text"] for c in tts.calls] == ["Switch off the breaker."]


# The two new demo scripts ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("script_id", "task_id", "worker"),
    [("sg-hot-work", "hot-work", "bn"), ("chennai-trench", "trench-entry", "or")],
)
def test_the_new_demo_scripts_answer_every_question_and_are_marked_draft(script_id, task_id, worker):
    script = catalog.demo_script(script_id)
    questions = [q["id"] for q in catalog.reference_questions(task_id)]
    assert script["taskId"] == task_id and script["workerLang"] == worker
    assert "DRAFT" in script["note"] and "native review" in script["note"]
    for turn in script["rounds"]:
        answers = catalog.round_answers(task_id, turn)
        assert [a["questionId"] for a in answers] == questions
        assert all(set(a["answer"]) == {worker, "en"} for a in answers)
