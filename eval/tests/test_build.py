"""The build's ledger, pending marks, render selection and client switch. No network and no Gemini call.

FakeCalls answers translate and back-translate batches from their prompts and records every batch, so a
test can say exactly which rows a rebuild would send to Gemini.
"""

import copy
import json

import pytest

import build_testset as bt
import config
import gemini_client
import items_io
from catalog_io import load_catalog
from config import SPEC_PATH
from items_io import file_sha256
from testset_text import TRANSLATE_SCHEMA


class FakeCalls:
    def __init__(self) -> None:
        self.batches: list[dict] = []

    def text_json(self, purpose, system, prompt, schema, validate):
        payload = json.loads(prompt.split("\n", 1)[1])
        if schema is TRANSLATE_SCHEMA:
            self.batches.append({"kind": "translate", "purpose": purpose,
                                 "ids": [a["id"] for a in payload["answers"]],
                                 "keys": [q["key"] for q in payload["questions"]]})
            response = {"answers": [{"id": a["id"], "text": f"T[{a['draft']}]"} for a in payload["answers"]],
                        "questions": [{"key": q["key"], "text": f"Q[{q['draft']}]"} for q in payload["questions"]]}
        else:
            self.batches.append({"kind": "back", "purpose": purpose, "ids": [row["id"] for row in payload]})
            response = {"items": [{"id": row["id"], "en": f"B[{row['text']}]"} for row in payload]}
        validate(response)
        return response

    def of(self, kind: str) -> list[dict]:
        return [batch for batch in self.batches if batch["kind"] == kind]


@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog() -> dict:
    return load_catalog()


def _first_build(spec: dict, catalog: dict) -> tuple[dict, list[dict]]:
    """A build from nothing with the fake: every row translated once. Returns (items doc, records)."""
    records = bt.resolve_records(spec, catalog)
    texts = bt.build_texts(FakeCalls(), records, catalog, bt.Ledger(None))
    return bt.build_doc(spec, records, texts, {}, None), records


def _rebuild(spec: dict, catalog: dict, ledger_doc: dict) -> tuple[FakeCalls, bt.Texts]:
    calls = FakeCalls()
    texts = bt.build_texts(calls, bt.resolve_records(spec, catalog), catalog, bt.Ledger(ledger_doc))
    return calls, texts


def test_a_rebuild_with_nothing_changed_makes_no_call(spec, catalog):
    doc, _ = _first_build(spec, catalog)

    calls, texts = _rebuild(spec, catalog, doc)

    assert calls.batches == []
    assert {i["id"]: i["answer"] for i in doc["items"]} == {
        rec_id: texts.answers.get(rec_id, "") for rec_id in (i["id"] for i in doc["items"])}


def test_reordering_the_catalog_translates_nothing_again(spec, catalog):
    doc, _ = _first_build(spec, catalog)
    reordered = copy.deepcopy(catalog)
    reordered["tasks"].reverse()

    calls, _ = _rebuild(spec, reordered, doc)

    assert calls.batches == []


def test_a_new_catalog_question_is_the_only_row_translated(spec, catalog):
    doc, _ = _first_build(spec, catalog)
    grown = copy.deepcopy(catalog)
    task = next(t for t in grown["tasks"] if t["id"] == "lifting-zone")
    task["referenceQuestions"].append({"id": "q9", "text": "What will you do with the tag line?", "stepIds": ["s4"]})

    calls, texts = _rebuild(spec, grown, doc)

    sg_langs = next(s for s in grown["sites"] if s["id"] == "sg")["workerLanguages"]
    assert sorted(b["purpose"].split(":")[0] for b in calls.of("translate")) == sorted(
        f"translate {lang}" for lang in sg_langs)
    assert all(b["keys"] == ["lifting-zone.q9"] and b["ids"] == [] for b in calls.of("translate"))
    assert calls.of("back") == []
    assert texts.questions[("lifting-zone.q9", "ta")] == "Q[What will you do with the tag line?]"


def test_a_changed_english_question_is_translated_again(spec, catalog):
    doc, _ = _first_build(spec, catalog)
    edited = copy.deepcopy(catalog)
    task = next(t for t in edited["tasks"] if t["id"] == "hot-work")
    task["referenceQuestions"][1]["text"] = "What will you do once the cutting is done?"

    calls, texts = _rebuild(spec, edited, doc)

    assert {key for b in calls.of("translate") for key in b["keys"]} == {"hot-work.q2"}
    assert texts.sources[("hot-work.q2", "bn")] == "What will you do once the cutting is done?"


def test_a_changed_gloss_retranslates_that_item_alone_and_redoes_its_back_translation(spec, catalog):
    doc, _ = _first_build(spec, catalog)
    edited = copy.deepcopy(spec)
    entry = next(e for e in edited["items"] if e["pattern"] == "complete" and e["workerLang"] == "zh")
    entry["gloss"] = entry["gloss"] + " Then I'll tell the supervisor."
    changed = bt.item_id(entry)

    calls, texts = _rebuild(edited, catalog, doc)

    assert [b["ids"] for b in calls.of("translate")] == [[changed]]
    assert [b["keys"] for b in calls.of("translate")] == [[]]
    assert [b["ids"] for b in calls.of("back")] == [[changed]]
    unchanged = {i["id"]: i["answer"] for i in doc["items"] if i["id"] != changed and i["answer"]}
    assert all(texts.answers[k] == v for k, v in unchanged.items())


def test_a_changed_demo_line_keeps_its_text_from_the_catalog_and_redoes_only_the_back_translation(spec, catalog):
    doc, _ = _first_build(spec, catalog)
    edited = copy.deepcopy(catalog)
    script = next(s for s in edited["demoScripts"] if s["id"] == "sg-lead")
    script["rounds"][0]["answer"]["ta"] = "லோடுக்கு அடியில போவேன்."

    calls, texts = _rebuild(spec, edited, doc)

    assert calls.of("translate") == []
    assert [b["ids"] for b in calls.of("back")] == [["lifting-zone.q1.ta.demo.clean.r1"]]
    assert texts.answers["lifting-zone.q1.ta.demo.clean.r1"] == "லோடுக்கு அடியில போவேன்."


SIX_FOLLOW_UPS = [  # 16 Oct: the demo rounds' answers to their further questions, in spec order
    "lifting-zone.q2.ta.demo.clean.r1", "lifting-zone.q3.ta.demo.clean.r1",
    "lifting-zone.q2.ta.demo.clean.r2", "lifting-zone.q3.ta.demo.clean.r2",
    "scaffold-harness.q2.hi.demo.clean.r1", "scaffold-harness.q2.hi.demo.clean.r2",
]
EIGHT_BREADTH = [  # 16 Oct breadth (build-notes/34-breadth.md): hot work in Bengali, trench entry in Odia, in spec order
    "hot-work.q1.bn.demo.clean.r1", "hot-work.q2.bn.demo.clean.r1", "hot-work.q1.bn.demo.clean.r2",
    "hot-work.q2.bn.demo.clean.r2", "trench-entry.q1.or.demo.clean.r1", "trench-entry.q2.or.demo.clean.r1",
    "trench-entry.q1.or.demo.clean.r2", "trench-entry.q2.or.demo.clean.r2",
]
SIXTEEN_SUITES = [  # 17 Oct demo suites (build-notes/37-domain-suites.md), in spec order
    f"{task}.{qid}.{lang}.demo.clean.{variant}"
    for task, lang in (("hydro-jetting", "bn"), ("steam-line-break", "ta"), ("press-lockout", "hi"), ("telecom-tower", "te"))
    for variant in ("r1", "r2") for qid in ("q1", "q2")
]


def test_a_follow_up_takes_its_text_gloss_and_gold_from_its_rounds_catalog_answer(spec, catalog):
    records = {rec["id"]: rec for rec in bt.resolve_records(spec, catalog)}
    follow_up = next(s for s in catalog["demoScripts"] if s["id"] == "sg-lead")["rounds"][0]["followUps"][1]

    rec = records["lifting-zone.q3.ta.demo.clean.r1"]

    assert (rec["text"], rec["gloss"], rec["gold"]) == (follow_up["answer"]["ta"], follow_up["answer"]["en"],
                                                        follow_up["expected"])
    assert rec["demo"] == {"script": "sg-lead", "round": 0} and rec["needsTranslation"] is False
    assert records["lifting-zone.q1.ta.demo.clean.r1"]["text"].startswith("லோடுக்கு அடியில நின்னு")  # its own answer


@pytest.mark.parametrize("change", [{"gold": {"s4": "covered"}}, {"questionId": "q9"}])
def test_a_follow_up_whose_gold_or_question_differs_from_the_catalog_is_refused(spec, catalog, change):
    edited = copy.deepcopy(spec)
    entry = next(e for e in edited["items"] if bt.item_id(e) == "lifting-zone.q3.ta.demo.clean.r1")
    entry.update(change)

    with pytest.raises(ValueError, match="gold differs|does not match the item"):
        bt.resolve_records(edited, catalog)


def test_the_plan_back_translates_the_six_follow_ups_and_voices_nothing(spec, catalog, tmp_path, monkeypatch):
    """--plan with no cache at all (as on a fresh clone): every clip is current (the six follow-ups voiced by Sarvam on
    16 Oct), so only their back-translations wait for Gemini. Since the breadth push (same day) the eight new demo
    answers wait for their back-translation too, and for their Sarvam clips until they are rendered. Since the four
    demo suites (17 Oct) sixteen more do, and the question texts no item needs yet (the new tasks in their sites' other
    languages, and Telugu, an eval language since then, on every Chennai task) wait for one translate batch per language;
    the eight the new items need are hand-written (spec.json questionFixes)."""
    monkeypatch.setattr(gemini_client, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(gemini_client, "CALL_LOG_PATH", tmp_path / "calls.log")
    records = bt.resolve_records(spec, catalog)
    calls = gemini_client.GeminiCalls(offline=True)
    previous = bt.previous_doc()
    texts = bt.build_texts(calls, records, catalog, bt.Ledger(previous))
    manifest = items_io.load_clip_manifest()

    plan = bt.call_plan(calls, records, texts, manifest)

    pending_langs = {key.rsplit(".", 1)[1] for key in previous["pendingQuestions"]}
    assert (plan["translate"], set(plan["translateLanguages"])) == (len(pending_langs), pending_langs)
    assert pending_langs <= {"ta", "bn", "zh", "my", "hi", "or", "te"}
    # The build back-translates synthetic answers only; a recorded answer's waits for a person (record_clips.py).
    back_rows = sum("backTranslation" in item["pending"] for item in previous["items"] if item["source"] == "synthetic_tts")
    assert (plan["backTranslate"], plan["backRows"]) == (-(-back_rows // config.BACK_BATCH), back_rows)
    assert not {f"{t}.{q}.{lang}" for t, q, lang in (
        ("hydro-jetting", "q1", "bn"), ("steam-line-break", "q2", "ta"), ("press-lockout", "q1", "hi"),
        ("telecom-tower", "q2", "te"))} & set(previous["pendingQuestions"])
    unrendered = [item_id for item_id in EIGHT_BREADTH + SIXTEEN_SUITES if item_id not in manifest]
    assert plan["ttsIds"] == [] and plan["vendorIds"] == unrendered and plan["localRenders"] == 0
    assert ({rec["id"] for rec in records if bt.rec_voice(rec) and bt.rec_voice(rec).startswith("sarvam/")}
            == set(SIX_FOLLOW_UPS + EIGHT_BREADTH + SIXTEEN_SUITES))
    assert not (tmp_path / "calls.log").exists()


def test_an_offline_build_with_an_empty_cache_makes_no_call_and_marks_misses_pending(spec, catalog, tmp_path,
                                                                                     monkeypatch):
    monkeypatch.setattr(gemini_client, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(gemini_client, "CALL_LOG_PATH", tmp_path / "calls.log")
    records = bt.resolve_records(spec, catalog)

    texts = bt.build_texts(gemini_client.GeminiCalls(offline=True), records, catalog, bt.Ledger(None))
    doc = bt.build_doc(spec, records, texts, {}, None)  # the Burmese hand fix waits for its translation

    assert not (tmp_path / "calls.log").exists()
    assert texts.missed_languages
    for item, rec in zip(doc["items"], records):
        if rec["needsTranslation"]:
            assert item["answer"] == "" and item["pending"] == ["answer", "backTranslation", "audio"], item["id"]
        elif rec["pattern"] == "demo":
            assert item["answer"] == rec["text"] and "answer" not in item["pending"], item["id"]


def test_clips_to_render_leaves_current_clips_alone_and_picks_missing_or_stale_ones(spec, catalog, tmp_path,
                                                                                    monkeypatch):
    monkeypatch.setattr(items_io, "TESTSET_DIR", tmp_path)
    (tmp_path / "audio").mkdir()
    records = bt.resolve_records(spec, catalog)[:4]
    texts = {rec["id"]: rec["text"] or f"text {n}" for n, rec in enumerate(records)}
    current, stale, missing, no_text = records
    clips = {}
    for rec in (current, stale):
        path = tmp_path / "audio" / f"{rec['id']}.wav"
        path.write_bytes(b"RIFF" + rec["id"].encode())
        clips[rec["id"]] = {"text": texts[rec["id"]], "voice": bt.voice_for(rec["id"]), "sha256": file_sha256(path)}
    clips[stale["id"]]["text"] = "an older line"
    del texts[no_text["id"]]

    chosen = [rec["id"] for rec in bt.clips_to_render(records, texts, clips)]

    assert chosen == [stale["id"], missing["id"]]
    assert [rec["id"] for rec in bt.clips_to_render(records, texts, clips, only=missing["id"])] == [missing["id"]]


def test_a_clip_whose_file_changed_is_not_current(tmp_path, monkeypatch):
    monkeypatch.setattr(items_io, "TESTSET_DIR", tmp_path)
    (tmp_path / "audio").mkdir()
    item = {"id": "x", "audio": "audio/x.wav", "answer": "words", "voice": "Kore", "source": "synthetic_tts"}
    (tmp_path / "audio" / "x.wav").write_bytes(b"RIFF1")
    clips = {"x": {"text": "words", "voice": "Kore", "sha256": file_sha256(tmp_path / "audio" / "x.wav")}}

    assert items_io.clip_is_current(item, clips)
    (tmp_path / "audio" / "x.wav").write_bytes(b"RIFF2")
    assert not items_io.clip_is_current(item, clips)
    assert not items_io.clip_is_current({**item, "voice": "Puck"}, clips)


def test_build_clients_follow_the_backend_switch_including_the_tts_fallback():
    platform = {"GOOGLE_GENAI_USE_ENTERPRISE": "true", "GOOGLE_CLOUD_PROJECT": "demo-project",
                "GOOGLE_CLOUD_LOCATION": "global"}

    assert gemini_client.client_kwargs("flash", platform) == {
        "enterprise": True, "location": "global", "project": "demo-project"}
    assert gemini_client.client_kwargs("tts", platform)["enterprise"] is True
    assert gemini_client.client_kwargs("tts", {**platform, "SIB_TTS_BACKEND": "developer-api"}) == {
        "enterprise": False}
    assert gemini_client.client_kwargs("flash", {**platform, "SIB_TTS_BACKEND": "developer-api"})["enterprise"]
    assert gemini_client.client_kwargs("flash", {}) == {"enterprise": False}


def test_a_fresh_call_bypasses_a_cached_result_and_replaces_it(tmp_path, monkeypatch):
    """--rerender: a clip that failed its spot-check must get a new TTS call, not the cached audio again."""
    monkeypatch.setattr(gemini_client, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(gemini_client, "CALL_LOG_PATH", tmp_path / "calls.log")
    calls = gemini_client.GeminiCalls()
    material = {"kind": "test", "text": "words"}

    def cached(value: int, fresh: bool = False) -> dict:
        return calls._cached("tts x", "m", material, lambda: {"v": value}, lambda r: None, fresh=fresh)

    assert [cached(1), cached(2), cached(3, fresh=True), cached(4)] == [{"v": 1}, {"v": 1}, {"v": 3}, {"v": 3}]
    assert len((tmp_path / "calls.log").read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.parametrize("argv", [["--rerender", "no.such.item", "--offline"],
                                  ["--rerender", "panel-isolation.q1.ta.demo.clean.r1", "--offline"]])
def test_rerender_refuses_an_unknown_id_or_an_offline_run_before_any_stage(argv, monkeypatch, capsys):
    def no_texts(*args, **kwargs):
        raise AssertionError("the text stage must not start")

    monkeypatch.setattr(bt, "build_texts", no_texts)

    assert bt.main(argv) == 1
    assert "--rerender needs an exact item id" in capsys.readouterr().err


def test_held_out_comes_from_the_spec_and_must_match_the_held_out_tasks(spec, catalog):
    doc, _ = _first_build(spec, catalog)
    assert {i["id"] for i in doc["items"] if i["heldOut"] is True} == {
        i["id"] for i in doc["items"] if i["taskId"] in config.HELD_OUT_TASKS}

    for change in ({"heldOut": True}, {"heldOut": None}):
        edited = copy.deepcopy(spec)
        entry = next(e for e in edited["items"] if e["taskId"] == "lifting-zone")
        entry.update(change)
        with pytest.raises(ValueError, match="heldOut must be true exactly"):
            bt.resolve_records(edited, catalog)
    unflagged = copy.deepcopy(spec)
    del next(e for e in unflagged["items"] if e["taskId"] == "fragile-roof")["heldOut"]
    with pytest.raises(ValueError, match="heldOut must be true exactly"):
        bt.resolve_records(unflagged, catalog)


def test_a_new_held_out_item_is_translated_with_its_language_batch_and_nothing_else_is(spec, catalog):
    doc, _ = _first_build(spec, catalog)
    grown = copy.deepcopy(spec)
    grown["items"].append({"taskId": "fragile-roof", "questionId": "q3", "workerLang": "ta", "pattern": "vague",
                           "noise": "clean", "heldOut": True, "gloss": "Fine, fine.", "gold": {"s4": "missed"}})

    calls, texts = _rebuild(grown, catalog, doc)

    assert [(b["purpose"].split(":")[0], b["ids"], b["keys"]) for b in calls.of("translate")] == [
        ("translate ta", ["fragile-roof.q3.ta.vague.clean"], [])]
    assert [b["ids"] for b in calls.of("back")] == [["fragile-roof.q3.ta.vague.clean"]]


def test_every_spot_check_id_is_an_item_and_one_is_a_held_out_negation(spec, catalog):
    records = {rec["id"]: rec for rec in bt.resolve_records(spec, catalog)}

    assert set(bt.SPOTCHECK_IDS) <= set(records)
    assert any(records[i]["heldOut"] and records[i]["pattern"] == "negation" for i in bt.SPOTCHECK_IDS)


def test_the_call_budget_is_70_unless_the_environment_raises_it(monkeypatch):
    monkeypatch.delenv("SIB_EVAL_CALL_BUDGET", raising=False)
    assert config._call_budget() == 70
    monkeypatch.setenv("SIB_EVAL_CALL_BUDGET", "120")
    assert config._call_budget() == 120
    monkeypatch.setenv("SIB_EVAL_CALL_BUDGET", "lots")
    with pytest.raises(ValueError):
        config._call_budget()
