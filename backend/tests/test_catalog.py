"""The catalog and its public view: no reference answers leak (API.md endpoint 2)."""

from __future__ import annotations

import json

import pytest

from sayitback import catalog
from sayitback.errors import Unprocessable

SECRET_KEYS = ("referenceSteps", "referenceQuestions", "demoScripts", "designNote")


def test_public_view_has_the_documented_shape():
    view = catalog.public_view()
    assert set(view) == {"version", "languages", "sites", "tasks"}
    assert set(view["languages"]) == {"en", "zh", "ta", "bn", "my", "hi", "or", "te"}
    assert {t["id"] for t in view["tasks"]} == {t["id"] for t in catalog.load_catalog()["tasks"]}


def test_public_tasks_carry_exactly_the_documented_fields():
    for task in catalog.public_view()["tasks"]:
        assert set(task) == {
            "id",
            "icon",
            "domain",  # 2026-10-17: the Start screen groups its task picker by it
            "title",
            "demoSite",
            "demoPair",
            "sop",
            "sampleInstruction",
        }


def test_no_reference_answer_leaks_anywhere_in_the_public_json():
    text = json.dumps(catalog.public_view(), ensure_ascii=False)
    for key in SECRET_KEYS:
        assert key not in text
    # nor the content of one reference step
    assert "Switch off (isolate) the supply at the breaker" not in text
    assert "Check that the shoring is in place before going in" not in text


def test_the_catalog_file_itself_still_has_the_answers():
    raw = catalog.load_catalog()
    assert "demoScripts" in raw
    assert all("referenceSteps" in t for t in raw["tasks"])


def test_unicode_ranges_come_from_the_catalog():
    assert catalog.unicode_ranges("or") == ((0x0B00, 0x0B7F),)
    assert catalog.unicode_ranges("ta") == ((0x0B80, 0x0BFF),)
    assert catalog.unicode_ranges("hi") == ((0x0900, 0x097F),)
    assert catalog.unicode_ranges("te") == ((0x0C00, 0x0C7F),)


def test_language_validation_names_the_field():
    assert catalog.require_lang("ta") == "ta"
    with pytest.raises(Unprocessable) as err:
        catalog.require_lang("xx", "workerLang")
    assert "workerLang" in err.value.message
    assert err.value.code == "unsupported_language"


def test_task_title_falls_back_to_english():
    assert catalog.task_title("panel-isolation", "ta").startswith("டிஸ்ட்ரிபியூஷன்")
    assert catalog.task_title("panel-isolation", "zh") == "Open a distribution panel"
    assert catalog.task_title("custom", "en", fallback="My SOP") == "My SOP"


# The worker's everyday word (2026-10-16.12, build-notes/27): a Tamil sample instruction, which a
# supervisor says and a script is written from, no longer spells an English technical term letter
# for letter in Tamil script. What a WORKER says (demo and eval answers) is not held to it: workers
# do say those words, the judge accepts them, and the answers have rendered clips.
SPELLED_OUT_TA = {  # stems, without a final pulli: "வாட்சரும்" holds "வாட்சர", not "வாட்சர்"
    "scaffold-harness": ("ஹார்னஸ", "லைஃப்லைன", "கிளிப்"),
    "fragile-roof": ("ஹார்னஸ", "லைஃப்லைன", "கிளிப்", "கிராலிங்"),
    "hot-work": ("ஃபயர் வாட்சர",),
    "trench-entry": ("டிரெஞ்ச",),
    "panel-isolation": ("லாக்",),
}


@pytest.mark.parametrize("task_id", sorted(SPELLED_OUT_TA))
def test_a_reworded_tamil_sample_spells_no_english_term_letter_for_letter(task_id):
    task = catalog.task(task_id)
    for term in SPELLED_OUT_TA[task_id]:
        assert term not in task["sampleInstruction"]["ta"], term


@pytest.mark.parametrize("task_id", sorted(SPELLED_OUT_TA))
def test_a_reworded_tamil_sample_is_marked_draft_for_native_review(task_id):
    tasks = {t["id"]: t for t in catalog.load_catalog()["tasks"]}
    note = tasks[task_id]["designNote"]
    assert "DRAFT" in note and "16 Oct" in note and "native review" in note


def test_the_harness_samples_pin_the_belt_down_and_name_the_rope_and_hook():
    """The everyday word for a harness can also mean a waist belt, which is not allowed for fall
    arrest: the sample says it is the one worn round the whole body."""
    for task_id in ("scaffold-harness", "fragile-roof"):
        text = catalog.task(task_id)["sampleInstruction"]["ta"]
        assert "உடல் முழுவதும் மாட்டும் பெல்ட்" in text, task_id
        assert "கொக்கி" in text and "கயிற்றில்" in text, task_id


def test_the_scripted_worker_answers_keep_the_words_workers_say():
    answers = {
        s["id"]: [r["answer"] for r in s["rounds"]] for s in catalog.load_catalog()["demoScripts"]
    }
    assert "பேரிகேடுக்கு" in answers["sg-lead"][1]["ta"]
    assert "லாக் போட்டு டேக் மாட்டுவேன்" in answers["sg-panel"][1]["ta"]
    assert "लाइफ़लाइन" in answers["chennai-second"][1]["hi"]


# 2026-10-16: a demo round answers every question of its task (the round's own answer plus its
# `followUps`), so an evaluator with stored sample answers needs to speak none of them.


def test_every_scripted_demo_answer_answers_one_reference_question_and_labels_its_steps():
    for script in catalog.load_catalog()["demoScripts"]:
        steps = {q["id"]: q["stepIds"] for q in catalog.reference_questions(script["taskId"])}
        for n, turn in enumerate(script["rounds"], start=1):
            where = f"{script['id']} round {n}"
            answers = catalog.round_answers(script["taskId"], turn)
            ids = [a["questionId"] for a in answers]
            assert len(ids) == len(set(ids)) and set(ids) <= set(steps), where
            assert ids == sorted(ids, key=list(steps).index), where  # reference question order
            assert [a["own"] for a in answers].count(True) == 1 and turn["questionId"] in ids
            for a in answers:
                assert set(a["expected"]) == set(steps[a["questionId"]]), (where, a["questionId"])
                assert set(a["expected"].values()) <= {"covered", "missed", "contradicted"}
                assert set(a["answer"]) == {script["workerLang"], "en"}, (where, a["questionId"])
                assert all(a["answer"].values()), (where, a["questionId"])


def test_both_demos_now_answer_every_question_in_both_rounds_with_the_expected_verdicts():
    def verdicts(script_id, index):
        script = catalog.demo_script(script_id)
        answers = catalog.round_answers(script["taskId"], script["rounds"][index])
        return {sid: v for a in answers for sid, v in a["expected"].items()}

    assert verdicts("sg-lead", 0) == {
        "s1": "contradicted", "s2": "missed", "s3": "covered", "s4": "contradicted",
    }  # fmt: skip
    assert verdicts("sg-lead", 1) == dict.fromkeys(("s1", "s2", "s3", "s4"), "covered")
    assert verdicts("chennai-second", 0) == {"s1": "covered", "s2": "missed", "s3": "contradicted"}
    assert verdicts("chennai-second", 1) == dict.fromkeys(("s1", "s2", "s3"), "covered")


def test_the_follow_up_answers_are_marked_draft_for_native_review():
    for script in catalog.load_catalog()["demoScripts"]:
        for turn in script["rounds"]:
            for follow_up in turn.get("followUps", []):
                note = follow_up["note"]
                assert "DRAFT" in note and "native review" in note, script["id"]


def test_round_answers_puts_a_round_s_answers_in_reference_question_order():
    """Endpoint 24 lists them in this order, and the web breaks a tie by it: follow-ups written out
    of order still come back q1, q2, q3, and an answer to an unknown question goes last."""
    turn = {
        "questionId": "q1", "answer": {}, "expected": {},
        "followUps": [
            {"questionId": "q9", "answer": {}, "expected": {}},
            {"questionId": "q3", "answer": {}, "expected": {}},
            {"questionId": "q2", "answer": {}, "expected": {}},
        ],
    }  # fmt: skip
    answers = catalog.round_answers("lifting-zone", turn)
    assert [(a["questionId"], a["own"]) for a in answers] == [
        ("q1", True), ("q2", False), ("q3", False), ("q9", False),
    ]  # fmt: skip


def test_a_round_s_own_answer_is_kept_as_it_was_rendered():
    """The rendered clips and the deck quote these: adding follow-ups changed none of them."""
    lead = catalog.demo_script("sg-lead")["rounds"][0]
    assert lead["questionId"] == "q1" and lead["expected"] == {"s1": "contradicted", "s2": "missed"}
    assert lead["answer"]["ta"] == "லோடுக்கு அடியில நின்னு, கையால பிடிச்சு அதை நேரா வைப்பேன்."
