"""17 Oct demo suites (build-notes/37-domain-suites.md): four more demo scripts with a stored answer to every question, in
four more work domains, voiced by Sarvam. The checks mirror tests/test_breadth.py, so every demo script with stored
answers to every question is checked the same way, and a new script must join one of the checked sets.

  sg-hydrojet    hydro-jetting     marine          Singapore  English -> Bengali
  sg-steam-line  steam-line-break  process plant   Singapore  English -> Tamil
  chennai-press  press-lockout     manufacturing   Chennai    Tamil -> Hindi
  chennai-tower  telecom-tower     telecom         Chennai    Tamil -> Telugu (the set's first Telugu items)

Their clips are rendered by the orchestrator after this build (`build_testset.py --vendor-only`), so every check here
holds both before the render (pending backTranslation and audio) and after it (pending backTranslation only)."""

import json

import pytest

from catalog_io import load_catalog, round_answers, task_map
from config import HELD_OUT_TASKS, SPEC_PATH, WORKER_LANGS
from items_io import clip_is_current, item_is_ready, load_clip_manifest, load_items, question_text
from sayitback.catalog import markers, unicode_ranges
from sayitback.delivery import negations
from sayitback.guards import script_shares
from vendor_tts import SARVAM_LANGS, parse_voice

SCRIPTS = {
    "sg-hydrojet": ("hydro-jetting", "sg", "en", "bn"),
    "sg-steam-line": ("steam-line-break", "sg", "en", "ta"),
    "chennai-press": ("press-lockout", "chennai", "ta", "hi"),
    "chennai-tower": ("telecom-tower", "chennai", "ta", "te"),
}
# The voices the brief named (bn, ta, hi: the voices of the earlier Sarvam clips); Telugu from Sarvam's v4-flash list.
VOICES = {
    "bn": "sarvam/bulbul:v4-flash/roopa_bn_conversational",
    "ta": "sarvam/bulbul:v4-flash/vijay_ta_narration",
    "hi": "sarvam/bulbul:v4-flash/rahul_hi_conversational",
    "te": "sarvam/bulbul:v4-flash/tarun_te_narration",
}
ROUND_1 = {
    "sg-hydrojet": {"s1": "covered", "s2": "contradicted", "s3": "covered"},
    "sg-steam-line": {"s1": "contradicted", "s2": "covered", "s3": "covered"},
    "chennai-press": {"s1": "covered", "s2": "covered", "s3": "covered", "s4": "contradicted"},
    "chennai-tower": {"s1": "covered", "s2": "missed", "s3": "covered"},
}
# Every catalog demo script and the test that checks it: the first three (16 Oct and before; sg-panel scripts one question
# only) in test_items.py and the backend's tests, breadth in test_breadth.py, the suites here.
EARLIER = ("sg-lead", "sg-panel", "chennai-second")
BREADTH = ("sg-hot-work", "chennai-trench")


@pytest.fixture(scope="module")
def doc() -> dict:
    return load_items()


@pytest.fixture(scope="module")
def catalog() -> dict:
    return load_catalog()


def suite_items(doc: dict) -> list[dict]:
    return [i for i in doc["items"] if i["demo"] and i["demo"]["script"] in SCRIPTS]


def script(catalog: dict, script_id: str) -> dict:
    return next(s for s in catalog["demoScripts"] if s["id"] == script_id)


def test_every_catalog_demo_script_is_in_a_checked_set(catalog):
    assert [s["id"] for s in catalog["demoScripts"]] == [*EARLIER, *BREADTH, *SCRIPTS]


def test_the_four_scripts_are_on_their_tasks_demo_pairs_and_never_on_a_held_out_task(catalog):
    tasks = task_map(catalog)
    for script_id, (task_id, site_id, supervisor, worker) in SCRIPTS.items():
        found = script(catalog, script_id)
        task = tasks[task_id]
        assert (found["taskId"], found["siteId"], found["supervisorLang"], found["workerLang"]) == (
            task_id, site_id, supervisor, worker)
        assert (task["demoSite"], task["demoPair"]) == (site_id, {"supervisorLang": supervisor, "workerLang": worker})
        assert task_id not in HELD_OUT_TASKS and worker in WORKER_LANGS
    assert not {s["taskId"] for s in catalog["demoScripts"]} & set(HELD_OUT_TASKS)


def test_round_1_gets_one_step_wrong_and_round_2_covers_every_step(catalog):
    for script_id in SCRIPTS:
        rounds = [{sid: v for a in round_answers(turn) for sid, v in a["expected"].items()}
                  for turn in script(catalog, script_id)["rounds"]]
        assert len(rounds) == 2 and rounds[0] == ROUND_1[script_id], script_id
        assert sum(v != "covered" for v in rounds[0].values()) == 1, script_id
        assert rounds[1] == dict.fromkeys(rounds[0], "covered"), script_id


def test_every_answer_answers_one_question_of_its_task_with_that_questions_steps(catalog):
    tasks = task_map(catalog)
    for script_id, (task_id, *_rest, worker) in SCRIPTS.items():
        steps = {q["id"]: set(q["stepIds"]) for q in tasks[task_id]["referenceQuestions"]}
        assert set().union(*steps.values()) == {s["id"] for s in tasks[task_id]["referenceSteps"]}, script_id
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
    (bn না, ta மாட்ட, hi नहीं, te కూడదు), counted the way the delivery check counts them."""
    for script_id, (*_rest, worker) in SCRIPTS.items():
        for a in round_answers(script(catalog, script_id)["rounds"][1]):
            assert negations(a["answer"][worker], markers(worker)) >= 1, (script_id, a["questionId"])


def test_the_sixteen_items_carry_the_catalog_text_gloss_and_gold(doc, catalog):
    items = suite_items(doc)
    assert len(items) == 16
    for item in items:
        turn = script(catalog, item["demo"]["script"])["rounds"][item["demo"]["round"]]
        answer = next(a for a in round_answers(turn) if a["questionId"] == item["questionId"])
        assert item["answer"] == answer["answer"][item["workerLang"]], item["id"]
        assert item["answerGloss"] == answer["answer"]["en"] and item["gold"] == answer["expected"], item["id"]
        assert item["heldOut"] is False and item["fidelity"] == "review" and item["source"] == "synthetic_tts"
        assert item["noise"] == "clean" and item["pattern"] == "demo", item["id"]


def test_each_language_is_voiced_on_bulbul_v4_flash_by_sarvam(doc):
    for item in suite_items(doc):
        assert item["voice"] == VOICES[item["workerLang"]], item["id"]
        model, _speaker = parse_voice(item["voice"])
        assert model == "bulbul:v4-flash" and item["workerLang"] in SARVAM_LANGS, item["id"]
    assert SARVAM_LANGS["te"] == "te-IN"


def test_their_questions_are_hand_written_in_their_own_languages_so_no_item_waits_for_a_translation(doc):
    """The eight question texts the items need are spec.json questionFixes (DRAFT), kept by the build's ledger: an item is
    runnable as soon as its clip is rendered, with Gemini offline."""
    fixes = json.loads(SPEC_PATH.read_text(encoding="utf-8"))["questionFixes"]
    clips = load_clip_manifest()
    for item in suite_items(doc):
        key = f"{item['taskId']}.{item['questionId']}.{item['workerLang']}"
        assert question_text(item, doc) == fixes[key], key
        assert key not in doc["pendingQuestions"], key
        assert item_is_ready(item, doc, clips) == clip_is_current(item, clips), item["id"]


def test_the_sixteen_are_rendered_and_back_translated(doc):
    """Their clips were voiced by Sarvam (render "sarvam") and the 17 Oct paid build added the Gemini back-translations,
    so nothing is pending and endpoint 24 lists them."""
    clips = load_clip_manifest()
    for item in suite_items(doc):
        assert item["backTranslation"], item["id"]
        assert item["pending"] == [], item["id"]
        assert clip_is_current(item, clips) and clips[item["id"]]["render"] == "sarvam", item["id"]
