"""16 Oct breadth (build-notes/34-breadth.md): two more demo scripts with a stored answer to every question, hot work in
Bengali (Singapore, sg-hot-work) and trench entry in Odia (Chennai, chennai-trench), voiced by Sarvam.

Their clips are rendered by the orchestrator after this build (`build_testset.py --vendor-only`), so every check here
holds both before the render (pending backTranslation and audio) and after it (pending backTranslation only)."""

import pytest

from catalog_io import load_catalog, round_answers, task_map
from config import HELD_OUT_TASKS
from items_io import clip_is_current, load_clip_manifest, load_items
from sayitback.catalog import markers, unicode_ranges
from sayitback.delivery import negations
from sayitback.guards import script_shares
from vendor_tts import SARVAM_LANGS, parse_voice

SCRIPTS = {"sg-hot-work": ("hot-work", "sg", "en", "bn"), "chennai-trench": ("trench-entry", "chennai", "ta", "or")}
# Bengali is Roopa: Arnab said কাটিং (cutting) so that two STT models heard প্যাটিং (16 Oct check).
VOICES = {"bn": "sarvam/bulbul:v4-flash/roopa_bn_conversational", "or": "sarvam/bulbul:v3/shubh"}
ROUND_1 = {"sg-hot-work": {"s1": "covered", "s2": "covered", "s3": "contradicted"},
           "chennai-trench": {"s1": "missed", "s2": "covered", "s3": "covered"}}


@pytest.fixture(scope="module")
def doc() -> dict:
    return load_items()


@pytest.fixture(scope="module")
def catalog() -> dict:
    return load_catalog()


def breadth_items(doc: dict) -> list[dict]:
    return [i for i in doc["items"] if i["demo"] and i["demo"]["script"] in SCRIPTS]


def script(catalog: dict, script_id: str) -> dict:
    return next(s for s in catalog["demoScripts"] if s["id"] == script_id)


def test_the_two_scripts_are_on_their_tasks_demo_pairs_and_never_on_a_held_out_task(catalog):
    tasks = task_map(catalog)
    for script_id, (task_id, site_id, supervisor, worker) in SCRIPTS.items():
        found = script(catalog, script_id)
        task = tasks[task_id]
        assert (found["taskId"], found["siteId"], found["supervisorLang"], found["workerLang"]) == (
            task_id, site_id, supervisor, worker)
        assert (task["demoSite"], task["demoPair"]) == (site_id, {"supervisorLang": supervisor, "workerLang": worker})
        assert task_id not in HELD_OUT_TASKS
    assert not {s["taskId"] for s in catalog["demoScripts"]} & set(HELD_OUT_TASKS)


def test_round_1_gets_one_step_wrong_and_round_2_covers_every_step(catalog):
    for script_id in SCRIPTS:
        rounds = [{sid: v for a in round_answers(turn) for sid, v in a["expected"].items()}
                  for turn in script(catalog, script_id)["rounds"]]
        assert rounds[0] == ROUND_1[script_id], script_id
        assert sum(v != "covered" for v in rounds[0].values()) == 1, script_id
        assert rounds[1] == dict.fromkeys(rounds[0], "covered"), script_id


def test_every_answer_answers_one_question_of_its_task_with_that_questions_steps(catalog):
    tasks = task_map(catalog)
    for script_id, (task_id, *_rest, worker) in SCRIPTS.items():
        steps = {q["id"]: set(q["stepIds"]) for q in tasks[task_id]["referenceQuestions"]}
        for turn in script(catalog, script_id)["rounds"]:
            answers = round_answers(turn)
            assert [a["questionId"] for a in answers] == list(steps), script_id  # every question, in order
            for a in answers:
                assert set(a["expected"]) == steps[a["questionId"]], (script_id, a["questionId"])
                assert a["answer"][worker] and a["answer"]["en"], (script_id, a["questionId"])


def test_every_answer_is_in_the_worker_script_so_guard_rule_4_never_flags_it(catalog):
    for script_id, (*_rest, worker) in SCRIPTS.items():
        for turn in script(catalog, script_id)["rounds"]:
            for a in round_answers(turn):
                share, latin, _ = script_shares(a["answer"][worker], unicode_ranges(worker))
                assert share >= 0.9 and latin == 0.0, (script_id, a["questionId"], share)


def test_every_round_2_answer_says_its_negation(catalog):
    """'Every negation spelled out': each complete answer carries at least one of its language's catalog negation markers
    (bn না, or ନାହିଁ), counted the way the delivery check counts them."""
    for script_id, (*_rest, worker) in SCRIPTS.items():
        for a in round_answers(script(catalog, script_id)["rounds"][1]):
            assert negations(a["answer"][worker], markers(worker)) >= 1, (script_id, a["questionId"])


def test_the_eight_items_carry_the_catalog_text_gloss_and_gold(doc, catalog):
    items = breadth_items(doc)
    assert len(items) == 8
    for item in items:
        turn = script(catalog, item["demo"]["script"])["rounds"][item["demo"]["round"]]
        answer = next(a for a in round_answers(turn) if a["questionId"] == item["questionId"])
        assert item["answer"] == answer["answer"][item["workerLang"]], item["id"]
        assert item["answerGloss"] == answer["answer"]["en"] and item["gold"] == answer["expected"], item["id"]
        assert item["heldOut"] is False and item["fidelity"] == "review" and item["source"] == "synthetic_tts"


def test_bengali_is_voiced_on_bulbul_v4_flash_and_odia_on_v3_by_sarvam(doc):
    """v4-flash speaks no Odia (Sarvam's voice list, 16 Oct), so Odia goes to bulbul:v3."""
    for item in breadth_items(doc):
        assert item["voice"] == VOICES[item["workerLang"]], item["id"]
        model, _speaker = parse_voice(item["voice"])
        assert item["workerLang"] in SARVAM_LANGS
        assert model == ("bulbul:v3" if item["workerLang"] == "or" else "bulbul:v4-flash"), item["id"]


def test_the_eight_are_rendered_and_back_translated(doc):
    """Their clips were voiced by Sarvam (render "sarvam") and the 17 Oct paid build added the Gemini back-translations,
    so nothing is pending and endpoint 24 lists them."""
    clips = load_clip_manifest()
    for item in breadth_items(doc):
        assert item["backTranslation"], item["id"]
        assert item["pending"] == [], item["id"]
        assert clip_is_current(item, clips) and clips[item["id"]]["render"] == "sarvam", item["id"]
