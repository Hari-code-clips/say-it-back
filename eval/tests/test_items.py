"""Contract checks on the generated item set, and on the catalog-derived steps and questions."""

import copy
import re
from collections import Counter

import pytest

from catalog_io import load_catalog, steps_for_question, task_map
from config import AUDIO_DIR, PATTERNS, TESTSET_DIR
from items_io import load_items, problems


@pytest.fixture(scope="module")
def doc() -> dict:
    return load_items()


@pytest.fixture(scope="module")
def catalog() -> dict:
    return load_catalog()


def genuine(item: dict) -> bool:
    """Wrong-language items are spoken in another language; their gloss says so."""
    return not item["answerGloss"].startswith("[Spoken in")


def test_items_pass_the_contract(doc, catalog):
    assert problems(doc, catalog) == []


def test_language_minimums_count_genuine_answers(doc):
    counts = Counter(item["workerLang"] for item in doc["items"] if genuine(item))

    assert all(counts[lang] >= 6 for lang in ("ta", "bn", "hi"))
    assert all(counts[lang] >= 4 for lang in ("or", "my", "zh"))


def test_every_task_is_covered_and_bn_appears_on_both_sites(doc, catalog):
    tasks = {item["taskId"] for item in doc["items"]}
    bn_tasks = {item["taskId"] for item in doc["items"] if item["workerLang"] == "bn"}
    sg_tasks = {t["id"] for t in catalog["tasks"] if t["demoSite"] == "sg"}
    chennai_tasks = {t["id"] for t in catalog["tasks"] if t["demoSite"] == "chennai"}

    assert tasks == set(task_map(catalog))
    assert bn_tasks & sg_tasks and bn_tasks & chennai_tasks


def test_every_pattern_appears_and_about_a_third_is_noisy(doc):
    patterns = {item["pattern"] for item in doc["items"]}
    noisy_share = sum(item["noise"] != "clean" for item in doc["items"]) / len(doc["items"])

    assert patterns == set(PATTERNS)
    assert 0.25 <= noisy_share <= 0.40


def test_demo_items_are_the_four_catalog_answers(doc, catalog):
    demo_answers = {
        script["rounds"][index]["answer"][script["workerLang"]]
        for script in catalog["demoScripts"]
        for index in range(len(script["rounds"]))
    }
    items = [item for item in doc["items"] if item["pattern"] == "demo"]

    assert len(items) == 4
    assert {item["answer"] for item in items} == demo_answers


def test_silence_items_have_no_text_and_no_voice(doc):
    silent = [item for item in doc["items"] if item["pattern"] == "silence"]

    assert silent and all(item["answer"] == "" and item["voice"] is None for item in silent)


def test_steps_and_questions_are_scoped_to_the_question(catalog):
    task = task_map(catalog)["scaffold-harness"]

    steps = steps_for_question(task, "q2")

    assert [step["id"] for step in steps] == ["s3"]


def test_sop_quotes_are_verbatim_numbered_sop_lines(catalog):
    for task in catalog["tasks"]:
        sop_lines = {
            re.sub(r"^\d+\.\s*", "", line.strip())
            for line in task["sop"]["text"].splitlines()
            if re.match(r"^\s*\d+\.", line)
        }
        for step in task["referenceSteps"]:
            if step["source"] in ("sop", "both"):
                quote = steps_for_question(task, _question_for(task, step["id"]))
                sop_quote = next(s["sopQuote"] for s in quote if s["id"] == step["id"])
                assert sop_quote in sop_lines, (task["id"], step["id"])


def test_every_item_has_its_audio_file(doc):
    if not AUDIO_DIR.exists() or not any(AUDIO_DIR.glob("*.wav")):
        pytest.skip("audio not built yet")

    missing = [item["audio"] for item in doc["items"] if not (TESTSET_DIR / item["audio"]).exists()]

    assert missing == []


ABSTAIN_IDS = {
    "lifting-zone.q1.zh.silence.clean",
    "trench-entry.q2.bn.silence.clean",
    "trench-entry.q1.or.wrong_language.clean",
    "trench-entry.q2.or.wrong_language.clean",
}


def test_gold_unclear_marks_exactly_the_four_abstain_items_on_every_step(doc):
    unclear_ids = {item["id"] for item in doc["items"] if "unclear" in item["gold"].values()}

    assert unclear_ids == ABSTAIN_IDS
    for item in doc["items"]:
        if item["id"] in ABSTAIN_IDS:
            assert set(item["gold"].values()) == {"unclear"}


def test_contract_rejects_gold_unclear_on_an_ordinary_item(doc, catalog):
    broken = copy.deepcopy(doc)
    ordinary = next(item for item in broken["items"] if item["pattern"] == "complete")
    ordinary["gold"] = {step: "unclear" for step in ordinary["gold"]}

    found = problems(broken, catalog)

    assert any("gold unclear is only for silence and wrong_language items" in line for line in found)


def test_contract_rejects_an_abstain_item_with_a_firm_label(doc, catalog):
    broken = copy.deepcopy(doc)
    silent = next(item for item in broken["items"] if item["pattern"] == "silence")
    silent["gold"][next(iter(silent["gold"]))] = "missed"

    found = problems(broken, catalog)

    assert any("silence items are gold unclear on every step" in line for line in found)


def _question_for(task: dict, step_id: str) -> str:
    return next(q["id"] for q in task["referenceQuestions"] if step_id in q["stepIds"])
