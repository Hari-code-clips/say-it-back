"""Contract checks on the generated item set, and on the catalog-derived steps and questions."""

import copy
import json
import re
from collections import Counter

import pytest

import build_testset
from catalog_io import load_catalog, round_answers, site_worker_langs, steps_for_question, task_map
from config import AUDIO_DIR, HELD_OUT_TASKS, PATTERNS, SPEC_PATH
from items_io import clip_is_current, file_sha256, load_clip_manifest, load_items, problems


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
    """Demo items are clean by design: they are the stored sample answers an evaluator hears. Since the four demo suites
    (17 Oct, 36 of 88 items) the noisy share is measured over the other items, where it was set (0.38). Recordings are
    noise clean by rule (their noise is real, or added on a copy), so the share is over the synthetic items."""
    patterns = {item["pattern"] for item in doc["items"]}
    judged = [item for item in doc["items"] if item["pattern"] != "demo" and item["source"] == "synthetic_tts"]
    noisy_share = sum(item["noise"] != "clean" for item in judged) / len(judged)

    assert patterns == set(PATTERNS)
    assert 0.25 <= noisy_share <= 0.40
    assert all(item["noise"] == "clean" for item in doc["items"] if item["pattern"] == "demo")


def test_demo_items_are_the_catalog_demo_answers_keyed_by_task_language_round_and_question(doc, catalog):
    """Endpoint 24's key is (taskId, workerLang, demo.round + 1, questionId): demo.round indexes the script's rounds,
    and the question picks the round's own answer or one of its followUps (16 Oct)."""
    expected = {
        (script["taskId"], script["workerLang"], index + 1, answer["questionId"]): (script["id"], answer)
        for script in catalog["demoScripts"]
        for index, turn in enumerate(script["rounds"])
        for answer in round_answers(turn)
    }
    items = {(i["taskId"], i["workerLang"], i["demo"]["round"] + 1, i["questionId"]): i
             for i in doc["items"] if i["pattern"] == "demo"}

    # 12 + breadth's 8 + the four demo suites' 16 (17 Oct)
    assert len(items) == len([i for i in doc["items"] if i["pattern"] == "demo"]) == len(expected) == 36
    assert set(items) == set(expected)
    for key, (script_id, answer) in expected.items():
        item = items[key]
        assert item["demo"]["script"] == script_id
        assert item["answer"] == answer["answer"][item["workerLang"]]
        assert item["answerGloss"] == answer["answer"]["en"]
        assert item["gold"] == answer["expected"]


FOLLOW_UPS = {  # 16 Oct: the stored samples for every question of both demos' rounds
    "lifting-zone.q2.ta.demo.clean.r1": {"s3": "covered"},
    "lifting-zone.q3.ta.demo.clean.r1": {"s4": "contradicted"},
    "lifting-zone.q2.ta.demo.clean.r2": {"s3": "covered"},
    "lifting-zone.q3.ta.demo.clean.r2": {"s4": "covered"},
    "scaffold-harness.q2.hi.demo.clean.r1": {"s3": "contradicted"},
    "scaffold-harness.q2.hi.demo.clean.r2": {"s3": "covered"},
}


def test_the_six_follow_ups_are_voiced_by_sarvam_and_back_translated_by_gemini(doc):
    """Their text is the catalog's. Their clips were voiced on 16 Oct by a second vendor (Sarvam Bulbul, vendor_tts.py),
    so the Sample page has every answer with no Google account; the 17 Oct paid build (eval/RUN_PAID.md) added their
    Gemini back-translations, as it did for the breadth demos (tests/test_breadth.py) and the four demo suites
    (tests/test_domain_suites.py). No synthetic item is pending."""
    items = {item["id"]: item for item in doc["items"]}
    breadth = {i["id"] for i in doc["items"] if i["demo"] and i["demo"]["script"] in ("sg-hot-work", "chennai-trench")}
    suites = {i["id"] for i in doc["items"] if i["demo"] and i["demo"]["script"] in (
        "sg-hydrojet", "sg-steam-line", "chennai-press", "chennai-tower")}

    assert {item_id: items[item_id]["gold"] for item_id in FOLLOW_UPS} == FOLLOW_UPS
    for item_id in FOLLOW_UPS:
        item = items[item_id]
        assert item["answer"] and item["fidelity"] == "review" and item["heldOut"] is False, item_id
        assert item["pending"] == [] and item["backTranslation"], item_id
        assert item["voice"].startswith("sarvam/bulbul:") and item["source"] == "synthetic_tts", item_id
    assert len(breadth) == 8 and len(suites) == 16
    synthetic_pending = [i["id"] for i in doc["items"] if i["pending"] and i["source"] == "synthetic_tts"]
    assert synthetic_pending == []  # recorded items wait for a person's back-translation instead


def test_the_lead_demo_hard_case_is_in_the_set_with_its_catalog_gold(doc):
    lead = {i["demo"]["round"]: i for i in doc["items"]
            if i["demo"] and i["demo"]["script"] == "sg-lead" and i["questionId"] == "q1"}

    assert lead[0]["id"] == "lifting-zone.q1.ta.demo.clean.r1"
    assert lead[0]["taskId"] == "lifting-zone" and lead[0]["workerLang"] == "ta"
    assert lead[0]["gold"] == {"s1": "contradicted", "s2": "missed"}
    assert lead[1]["gold"] == {"s1": "covered", "s2": "covered"}


def test_only_demo_items_carry_demo_and_every_item_lists_its_pending_fields(doc):
    for item in doc["items"]:
        assert (item["demo"] is not None) == (item["pattern"] == "demo"), item["id"]
        assert set(item["pending"]) <= {"answer", "backTranslation", "audio"}, item["id"]


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


def test_pending_audio_marks_match_the_clips_on_disk(doc):
    """An item is pending 'audio' exactly when its clip is missing or says other words (clips.json)."""
    clips = load_clip_manifest()

    wrong = [item["id"] for item in doc["items"] if ("audio" in item["pending"]) == clip_is_current(item, clips)]

    assert wrong == []


def test_every_clip_on_disk_is_in_the_manifest_with_its_hash():
    clips = load_clip_manifest()
    on_disk = {path.stem: path for path in AUDIO_DIR.glob("*.wav")}

    assert set(on_disk) <= set(clips)
    assert all(clips[stem]["sha256"] == file_sha256(path) for stem, path in on_disk.items())


OLD_PANEL_R1 = "நான் அதை ஆஃப் பண்ணிட்டு திறப்பேன்."  # the 13 Oct clip's line ("switch it off"), before the breaker


def test_the_panel_round_1_clip_now_says_the_catalog_line_not_the_older_one(doc, catalog):
    """The 13 Oct clip said 'switch it off'; the catalog line names the breaker, and the paid render re-voiced it."""
    item = next(i for i in doc["items"] if i["id"] == "panel-isolation.q1.ta.demo.clean.r1")
    sg_panel = next(s for s in catalog["demoScripts"] if s["id"] == "sg-panel")
    clips = load_clip_manifest()

    assert item["answer"] == sg_panel["rounds"][0]["answer"]["ta"] != OLD_PANEL_R1
    assert clips[item["id"]]["text"] == item["answer"]
    assert clip_is_current(item, clips) and "audio" not in item["pending"]


def test_every_item_has_a_current_clip(doc, allow_missing_audio):
    """Completeness: needs the paid render (eval/RUN_PAID.md). --allow-missing-audio skips only this test."""
    clips = load_clip_manifest()
    pending = [item["id"] for item in doc["items"] if not clip_is_current(item, clips)]
    if pending and allow_missing_audio:
        pytest.skip(f"--allow-missing-audio: {len(pending)} of {len(doc['items'])} clips pending render "
                    f"(eval/RUN_PAID.md), e.g. {', '.join(pending[:3])}")

    assert pending == []


def test_question_texts_were_translated_from_the_current_catalog_english(doc, catalog):
    english = {(t["id"], q["id"]): q["text"] for t in catalog["tasks"] for q in t["referenceQuestions"]}

    for task_id, questions in doc["questions"].items():
        for question_id, langs in questions.items():
            for lang in langs:
                assert doc["questionSources"][task_id][question_id][lang] == english[(task_id, question_id)]


def test_every_catalog_question_is_translated_or_listed_as_pending(doc, catalog):
    have = {f"{t}.{q}.{lang}" for t, qs in doc["questions"].items() for q, langs in qs.items() for lang in langs}
    wanted = {f"{task['id']}.{q['id']}.{lang}" for task in catalog["tasks"]
              for lang in site_worker_langs(catalog, task) for q in task["referenceQuestions"]}

    assert have | set(doc["pendingQuestions"]) == wanted
    assert not have & set(doc["pendingQuestions"])


def test_contract_rejects_a_pending_answer_that_holds_text(doc, catalog):
    """On a fixture: an ordinary item made pending, with text left in it (the real set has no pending item)."""
    pending, broken = copy.deepcopy(doc), copy.deepcopy(doc)
    for d in (pending, broken):
        item = next(i for i in d["items"] if i["id"] == "trench-entry.q1.or.complete.clean")
        item.update(answer="", backTranslation="", pending=["answer", "backTranslation", "audio"])
    next(i for i in broken["items"] if i["id"] == "trench-entry.q1.or.complete.clean")["answer"] = "invented text"

    assert not [line for line in problems(pending, catalog) if line.startswith("trench-entry.q1.or.complete.clean")]
    assert any(line.startswith("trench-entry.q1.or.complete.clean: answer is pending but holds text")
               for line in problems(broken, catalog))


def test_contract_rejects_an_empty_answer_not_marked_pending(doc, catalog):
    broken = copy.deepcopy(doc)
    item = next(i for i in broken["items"] if i["pattern"] == "complete" and "answer" not in i["pending"])
    item["answer"] = ""

    assert any("answer is empty but not marked pending" in line for line in problems(broken, catalog))


def test_contract_rejects_two_demo_items_for_one_task_language_and_round(doc, catalog):
    broken = copy.deepcopy(doc)
    r1 = next(i for i in broken["items"] if i["id"] == "lifting-zone.q1.ta.demo.clean.r1")
    r2 = next(i for i in broken["items"] if i["id"] == "lifting-zone.q1.ta.demo.clean.r2")
    r2["demo"] = dict(r1["demo"])

    assert any("a second demo item" in line for line in problems(broken, catalog))


def test_contract_keys_demo_items_by_question_too(doc, catalog):
    """A round's own answer and its follow-ups share (taskId, workerLang, round); the question tells them apart, and
    two items for the same question of one round are refused."""
    broken = copy.deepcopy(doc)
    q3 = next(i for i in broken["items"] if i["id"] == "lifting-zone.q3.ta.demo.clean.r1")
    q3.update(questionId="q2", gold={"s3": "covered"})

    assert problems(doc, catalog) == []
    assert any("lifting-zone.q3.ta.demo.clean.r1: a second demo item" in line for line in problems(broken, catalog))


def test_contract_rejects_a_demo_item_for_a_question_its_round_does_not_script(doc, catalog):
    broken = copy.deepcopy(doc)
    panel = next(i for i in broken["items"] if i["id"] == "panel-isolation.q1.ta.demo.clean.r1")
    panel.update(questionId="q2", gold={"s3": "missed"})  # sg-panel scripts q1 only

    assert any("round 1 of sg-panel scripts no answer to q2" in line for line in problems(broken, catalog))


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


# v0.5: held-out tasks, and the panel items that tested for power before opening --------------------------------

HELD_OUT_PATTERNS = {"complete", "one_missing", "contradicted", "negation", "fluent_wrong", "vague"}


def test_held_out_items_are_exactly_the_items_on_the_held_out_tasks(doc):
    held = [item for item in doc["items"] if item["heldOut"] is True]

    assert {item["id"] for item in held} == {item["id"] for item in doc["items"] if item["taskId"] in HELD_OUT_TASKS}
    assert all(item["heldOut"] is False for item in doc["items"] if item not in held)
    assert len([item for item in held if item["source"] == "synthetic_tts"]) == 12  # plus any recorded copies
    assert {item["workerLang"] for item in held} == {"hi", "or", "bn", "ta", "my"}
    for task_id in HELD_OUT_TASKS:
        assert {item["pattern"] for item in held if item["taskId"] == task_id} == HELD_OUT_PATTERNS, task_id
    assert all(item["demo"] is None and item["fidelity"] == "review" for item in held)


NEVER_COVERED_EXAMPLES = re.compile(r"\b(ok|okay|yes|understood|careful)\b")  # the judge prompt's own list


def test_held_out_glosses_avoid_the_judge_prompts_never_covered_examples():
    """A held-out vague answer built from the prompt's examples ("yes", "I will be careful") would test recall."""
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    found = [entry["gloss"] for entry in spec["items"]
             if entry["heldOut"] and NEVER_COVERED_EXAMPLES.search(entry["gloss"].lower())]

    assert found == []


def test_held_out_tasks_are_catalog_tasks_with_no_demo_script_and_an_sop_only_step(catalog):
    tasks = task_map(catalog)
    scripted = {script["taskId"] for script in catalog["demoScripts"]}
    wanted = {"confined-space": ("confined", "chennai", "ta", "hi"), "fragile-roof": ("roof", "sg", "en", "bn")}

    assert set(HELD_OUT_TASKS) == set(wanted)
    for task_id, (icon, site, supervisor, worker) in wanted.items():
        task = tasks[task_id]
        assert task_id not in scripted
        assert (task["icon"], task["demoSite"], task["demoPair"]) == (
            icon, site, {"supervisorLang": supervisor, "workerLang": worker})
        assert set(task["title"]) == set(task["sampleInstruction"]) == {"en", "ta"}
        assert "\nHazards:" in task["sop"]["text"]
        assert 3 <= len(task["referenceSteps"]) <= 4 and 2 <= len(task["referenceQuestions"]) <= 3
        assert any(step["source"] == "sop" for step in task["referenceSteps"]), task_id
        assert "DRAFT" in task["designNote"]
        asked = {sid for q in task["referenceQuestions"] for sid in q["stepIds"]}
        assert asked == {step["id"] for step in task["referenceSteps"]}, task_id


def test_contract_rejects_a_held_out_flag_that_does_not_match_the_task(doc, catalog):
    in_set, held = copy.deepcopy(doc), copy.deepcopy(doc)
    next(i for i in in_set["items"] if i["taskId"] == "lifting-zone")["heldOut"] = True
    next(i for i in held["items"] if i["taskId"] == "fragile-roof")["heldOut"] = 1

    for broken in (in_set, held):
        assert any("heldOut must be true exactly" in line for line in problems(broken, catalog))


def test_contract_rejects_a_demo_script_on_a_held_out_task(doc, catalog):
    scripted = copy.deepcopy(catalog)
    scripted["demoScripts"].append({**scripted["demoScripts"][0], "id": "x", "taskId": "confined-space"})

    assert any("held-out task confined-space has a demo script" in line for line in problems(doc, scripted))


def test_a_missing_question_text_is_allowed_only_while_pending_and_never_with_a_current_clip(doc, catalog):
    """On a fixture: the question of one held-out item is taken out again, as it was before the paid render."""
    item_id = "confined-space.q2.hi.negation.clean"
    key = "confined-space.q2.hi"

    def without_question(listed: bool, clip_pending: bool) -> list[str]:
        d = copy.deepcopy(doc)
        del d["questions"]["confined-space"]["q2"]["hi"]
        d["pendingQuestions"] = [key] if listed else []
        item = next(i for i in d["items"] if i["id"] == item_id)
        item.update(answer="", backTranslation="", pending=["answer", "backTranslation", "audio"][:3 if clip_pending else 2])
        return [line for line in problems(d, catalog) if line.startswith(f"{item_id}:")]

    assert problems(doc, catalog) == []
    assert without_question(listed=True, clip_pending=True) == []
    assert any("no worker-language question text" in line for line in without_question(False, True))
    assert any("its question is pending, so its clip must be pending too" in line
               for line in without_question(True, False))


PANEL_FIXES = {  # id: (gold, the answer was reworded to the SOP order)
    "panel-isolation.q1.ta.demo.clean.r2": ({"s1": "covered", "s2": "covered", "s3": "covered"}, True),
    "panel-isolation.q1.zh.complete.clean": ({"s1": "covered", "s2": "covered", "s3": "covered"}, True),
    "panel-isolation.q1.ta.code_switch.clean": ({"s1": "covered", "s2": "covered", "s3": "contradicted"}, False),
    "panel-isolation.q1.zh.one_missing.clean": ({"s1": "covered", "s2": "missed", "s3": "contradicted"}, False),
}


PRE_FIX_ANSWERS = {  # the four answers' worker-language text on 14 Oct, before the v0.5 gold fix
    "panel-isolation.q1.ta.demo.clean.r2": "முதல்ல பிரேக்கரை ஆஃப் பண்ணுவேன், அப்புறம் லாக் போட்டு டேக் மாட்டுவேன், டெஸ்டர் "
                                           "வச்சு கரண்ட் இல்லைன்னு செக் பண்ணிட்டுதான் பேனலைத் திறப்பேன்.",
    "panel-isolation.q1.zh.complete.clean": "先关掉breaker，然后挂上我的lock和tag，接着用tester测一下确认没电，最后才打开panel。",
    "panel-isolation.q1.ta.code_switch.clean": "முதல்ல breaker-ஐ ஆஃப் பண்ணிட்டு, என் lock மற்றும் tag போடுவேன், அப்புறம் "
                                               "current இல்லைன்னு tester வச்சு செக் பண்ணிட்டு panel-ஐ திறப்பேன்.",
    "panel-isolation.q1.zh.one_missing.clean": "我会关掉breaker，用tester测一下没电流，然后打开panel。",
}


def test_the_four_panel_answers_that_tested_before_opening_are_fixed(doc):
    """The SOP proves the panel dead after opening, before touching. 2 answers were reworded to that order and
    voiced again (a new text, and a current clip of it); 2 were kept in the wrong order (the same text and clip)
    with s3 gold contradicted."""
    items = {item["id"]: item for item in doc["items"]}
    clips = load_clip_manifest()

    for item_id, (gold, reworded) in PANEL_FIXES.items():
        item = items[item_id]
        assert item["gold"] == gold, item_id
        assert (item["answer"] != PRE_FIX_ANSWERS[item_id]) is reworded, item_id
        assert clips[item_id]["text"] == item["answer"] and clip_is_current(item, clips), item_id
        assert item["pending"] == [] and item["backTranslation"], item_id
        assert "v0.5 gold fix" in _spec_note(item_id)


def test_no_panel_answer_that_tests_before_opening_is_gold_covered_on_s3(doc, catalog):
    """A test for power before the panel is opened is the wrong order (catalog step s3 says "after opening"). The
    gloss is what the item was written to say; the back-translation is an independent reading of what was voiced."""
    s3 = next(s for s in task_map(catalog)["panel-isolation"]["referenceSteps"] if s["id"] == "s3")
    assert s3["text"].startswith("After opening")
    for item in doc["items"]:
        for field in ("answerGloss", "backTranslation"):
            text = item[field].lower()
            if item["taskId"] == "panel-isolation" and "tester" in text and "open" in text:
                if text.index("tester") < text.index("open"):
                    assert item["gold"]["s3"] == "contradicted", (item["id"], field)


def _spec_note(item_id: str) -> str:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    return next(entry["note"] for entry in spec["items"] if build_testset.item_id(entry) == item_id)
