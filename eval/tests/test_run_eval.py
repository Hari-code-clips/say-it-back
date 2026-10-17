"""Runner wiring with an injected fake run_check. No backend and no Gemini calls are made.

Most tests run the whole real item set over stand-in clips (one small unique WAV per item in a temp
folder, with a matching manifest), so the wiring is tested before the paid render. The stand-ins test
the runner, not the audio: the fake judge recognises each item by its clip's bytes.
"""

import io
import json
import wave
from collections.abc import Callable
from pathlib import Path

import pytest

import check_adapter
import items_io
import run_eval
from sayitback.errors import UpstreamError
from sayitback.settings import Settings
from catalog_io import load_catalog, question_by_id, task_map
from items_io import audio_path, build_check_payload, file_sha256, load_items
from metrics import GOLD_MISS
from report import METRIC_KEYS

Verdict = Callable[[bytes, str], str]


def _wav(n: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(n.to_bytes(2, "little", signed=True) * 160)
    return buffer.getvalue()


@pytest.fixture
def stand_in(tmp_path, monkeypatch) -> dict:
    """Every item gets a unique stand-in clip and a manifest entry that makes it current, and every question still
    pending translation gets a stand-in text (the held-out tasks' questions wait for the paid run too)."""
    doc = load_items()
    for dotted in doc["pendingQuestions"]:
        task_id, question_id, lang = dotted.split(".")
        doc["questions"].setdefault(task_id, {}).setdefault(question_id, {})[lang] = f"stand-in {dotted}"
    doc["pendingQuestions"] = []
    (tmp_path / "audio").mkdir()
    clips = {}
    for n, item in enumerate(doc["items"], start=1):
        path = tmp_path / item["audio"]
        path.parent.mkdir(parents=True, exist_ok=True)  # audio/recorded/ too, since Sam's V01 clips (17 Oct)
        path.write_bytes(_wav(n))
        clips[item["id"]] = {"text": item["answer"], "voice": item["voice"], "model": "gemini-3.8-flash-tts",
                             "sha256": file_sha256(path)}
    monkeypatch.setattr(items_io, "TESTSET_DIR", tmp_path)
    monkeypatch.setattr(run_eval, "load_items", lambda: doc)
    monkeypatch.setattr(run_eval, "load_clip_manifest", lambda: clips)
    return doc


def _fake(verdict: Verdict, extra: list[dict] | None = None) -> Callable[..., dict]:
    """A check that, like guard rule 6, rates a passed step with no question as unclear + not_asked."""

    def fake(*, steps: list[dict], questions: list[dict], clips: dict[str, bytes],
             worker_lang: str, supervisor_lang: str) -> dict:
        (clip,) = clips.values()
        asked = {step_id for question in questions for step_id in question["stepIds"]}
        ratings = [
            {"stepId": step["id"], "verdict": verdict(clip, step["id"]), "flags": [], "quote": "q", "reason": "r"}
            if step["id"] in asked else
            {"stepId": step["id"], "verdict": "unclear", "flags": ["not_asked"], "reason": "not asked"}
            for step in steps
        ]
        return {"ratings": ratings + list(extra or []), "passB": [],
                "modelIds": {"transcribe": "gemini-3.8-flash", "judge_a": "gemini-3.8-flash"}}

    return fake


def _gold_by_clip(items: list[dict]) -> dict[bytes, dict]:
    return {audio_path(item).read_bytes(): item["gold"] for item in items}


def _read(out: Path, name: str) -> str:
    return (out / name).read_text(encoding="utf-8")


def test_a_perfect_judge_passes_over_the_whole_set_and_writes_the_schema_keys(stand_in, tmp_path):
    gold = _gold_by_clip(stand_in["items"])
    out = tmp_path / "reports"

    code = run_eval.main([], run_check=_fake(lambda clip, sid: gold[clip][sid]), out_dir=out)

    report = json.loads(_read(out, "latest.json"))
    assert code == 0
    assert report["passBar"]["passed"] is True
    assert report["complete"] is True and report["nItems"] == report["testset"]["nItems"] == len(stand_in["items"])
    assert report["metrics"]["exactAccuracy"] == 1.0
    assert report["metrics"]["unsafeErrors"] == 0
    assert set(report["metrics"]) == set(METRIC_KEYS)
    assert {"generatedAt", "promptVersion", "models", "judgePasses", "nItems", "nStepRatings", "metrics",
            "passBar", "byLanguage", "byPattern", "items", "counts", "headline", "testset"} <= set(report)
    assert report["headline"].startswith(f"0 false passes in {report['metrics']['unsafeDenominator']} gold-miss")
    assert not any("not_asked" in flags for item in report["items"] for flags in item["flags"].values())
    assert _read(out, "latest.md").startswith("# Say It Back eval report")


def test_a_judge_that_covers_everything_fails_and_lists_each_unsafe_item(stand_in, tmp_path):
    code = run_eval.main(["--lang", "bn"], run_check=_fake(lambda clip, sid: "covered"), out_dir=tmp_path / "r")

    report = json.loads(_read(tmp_path / "r", "latest.json"))
    markdown = _read(tmp_path / "r", "latest.md")
    unsafe_ids = [item["id"] for item in report["items"] if item["unsafe"]]
    assert code == 0
    assert report["passBar"]["passed"] is False
    assert report["complete"] is False
    assert report["metrics"]["unsafeErrors"] == report["metrics"]["unsafeDenominator"] > 0
    assert unsafe_ids and all(item_id in markdown for item_id in unsafe_ids)
    assert "None." not in markdown.split("## Unsafe errors")[1].split("## ")[0]


def test_dry_run_plans_the_run_without_calling_the_check(tmp_path, capsys):
    def never_called(**kwargs: object) -> dict:
        raise AssertionError("dry run must not call the check")

    code = run_eval.main(["--dry-run", "--limit", "3"], run_check=never_called, out_dir=tmp_path)

    assert code == 0
    assert "none made" in capsys.readouterr().out
    assert not (tmp_path / "latest.json").exists()


def test_repeats_mark_an_item_unsafe_when_any_run_covers_a_gold_miss(stand_in, tmp_path):
    seen: dict[tuple[bytes, str], int] = {}

    def first_misses_then_covers(clip: bytes, step_id: str) -> str:
        seen[(clip, step_id)] = seen.get((clip, step_id), 0) + 1
        return "missed" if seen[(clip, step_id)] == 1 else "covered"

    code = run_eval.main(["--lang", "my", "--repeat", "2"], run_check=_fake(first_misses_then_covers),
                         out_dir=tmp_path / "r")

    report = json.loads(_read(tmp_path / "r", "latest.json"))
    my_items = [item for item in stand_in["items"] if item["workerLang"] == "my"]
    gold_misses = sum(label in GOLD_MISS for item in my_items for label in item["gold"].values())
    assert code == 0
    assert report["judgePasses"] == 1
    assert report["nStepRatings"] == sum(len(item["gold"]) for item in my_items)
    assert report["metrics"]["unsafeErrors"] == gold_misses
    assert report["passBar"]["passed"] is False


def test_a_gold_covered_step_covered_in_only_one_repeat_is_not_a_correct_pass(stand_in, tmp_path):
    """--repeat 2: the judge says covered first and unclear second on every gold-covered step. None of them is a
    correct pass, so the pass bar fails on correctPassRate even though no gold miss was passed."""
    gold = _gold_by_clip(stand_in["items"])
    seen: dict[tuple[bytes, str], int] = {}

    def wavering(clip: bytes, step_id: str) -> str:
        seen[(clip, step_id)] = seen.get((clip, step_id), 0) + 1
        if gold[clip][step_id] != "covered":
            return gold[clip][step_id]
        return "covered" if seen[(clip, step_id)] == 1 else "unclear"

    run_eval.main(["--lang", "zh", "--repeat", "2"], run_check=_fake(wavering), out_dir=tmp_path / "r")

    report = json.loads(_read(tmp_path / "r", "latest.json"))
    assert report["counts"]["goldCovered"] > 0
    assert report["counts"]["correctPasses"] == 0 and report["metrics"]["correctPassRate"] == 0.0
    assert report["metrics"]["unsafeErrors"] == 0 and report["passBar"]["passed"] is False


def test_every_payload_holds_exactly_its_questions_steps_and_that_one_question(stand_in):
    catalog = load_catalog()
    tasks = task_map(catalog)

    for item in stand_in["items"]:
        payload = build_check_payload(item, stand_in, catalog)
        wanted = question_by_id(tasks[item["taskId"]], item["questionId"])["stepIds"]
        assert [step["id"] for step in payload["steps"]] == wanted, item["id"]
        assert [q["id"] for q in payload["questions"]] == [item["questionId"]], item["id"]
        assert payload["questions"][0]["stepIds"] == wanted, item["id"]
        assert set(payload["clips"]) == {item["questionId"]}
        if item["taskId"] == "lifting-zone" and item["questionId"] != "q3":
            assert "s4" not in {step["id"] for step in payload["steps"]}, item["id"]


def test_a_rating_for_a_step_outside_the_question_changes_no_metric(stand_in, tmp_path):
    """If the check ever returned s4 (asked only by q3) as not_asked for another question, the lifting-zone numbers
    must not move. Since 16 Oct the Tamil set has lifting-zone q3 items too (the demo follow-ups), where s4 is the
    question's own step, so the stray rating is added only where s4 is outside the question."""
    gold = _gold_by_clip(stand_in["items"])
    judge = lambda clip, sid: gold[clip][sid]  # noqa: E731
    stray = {"stepId": "s4", "verdict": "unclear", "flags": ["not_asked"], "reason": "not asked"}
    plain_check, stray_check = _fake(judge), _fake(judge, extra=[stray])

    def with_stray(**kwargs) -> dict:
        outside = "s4" not in {step["id"] for step in kwargs["steps"]}
        return (stray_check if outside else plain_check)(**kwargs)

    run_eval.main(["--lang", "ta"], run_check=plain_check, out_dir=tmp_path / "plain")
    run_eval.main(["--lang", "ta"], run_check=with_stray, out_dir=tmp_path / "stray")

    plain = json.loads(_read(tmp_path / "plain", "latest.json"))
    stray_report = json.loads(_read(tmp_path / "stray", "latest.json"))
    for key in ("metrics", "counts", "nStepRatings", "items", "byPattern"):
        assert stray_report[key] == plain[key], key
    lifting = [item for item in stray_report["items"] if item["taskId"] == "lifting-zone"]
    assert not any("s4" in item["pred"] for item in lifting if "s4" not in item["gold"])
    assert any("s4" in item["gold"] for item in lifting)  # the q3 follow-ups are in the Tamil run


def test_out_writes_a_smoke_report_elsewhere(stand_in, tmp_path, monkeypatch):
    gold = _gold_by_clip(stand_in["items"])
    smoke, default = tmp_path / "smoke", tmp_path / "default-reports"
    monkeypatch.setattr(run_eval, "REPORTS_DIR", default)  # never the real eval/reports, even if --out broke

    code = run_eval.main(["--limit", "2", "--out", str(smoke)], run_check=_fake(lambda clip, sid: gold[clip][sid]))

    assert code == 0
    assert json.loads(_read(smoke, "latest.json"))["complete"] is False
    assert not default.exists()


STALE = ("lifting-zone.q1.ta.demo.clean.r1", "fragile-roof.q2.ta.contradicted.snr5")


def _make_stale(stand_in: dict) -> None:
    """Two stand-in clips now say other words than their items (as the stale clips did before the paid render)."""
    clips = run_eval.load_clip_manifest()
    for item_id in STALE:
        clips[item_id] = {**clips[item_id], "text": "an older line"}


def test_a_real_run_stops_when_a_selected_clip_is_not_current(stand_in, tmp_path, capsys):
    """On stand-in clips, so it runs whatever the state of the real render (every real clip is current now)."""
    _make_stale(stand_in)

    def never_called(**kwargs: object) -> dict:
        raise AssertionError("a run with stale or missing clips must not call the check")

    code = run_eval.main([], run_check=never_called, out_dir=tmp_path)

    err = capsys.readouterr().err
    assert code == 1
    assert "not current" in err and all(item_id in err for item_id in STALE)
    assert not (tmp_path / "latest.json").exists()


def _with_transcript(fake: Callable[..., dict], translation: Callable[[bytes], str]) -> Callable[..., dict]:
    """The fake check, plus the blind transcriber's transcript of the one question (as the backend returns it)."""

    def check(**kwargs: object) -> dict:
        result = fake(**kwargs)
        (question,) = kwargs["questions"]
        (clip,) = kwargs["clips"].values()
        result["transcripts"] = [{"questionId": question["id"], "original": f"ORIGINAL {translation(clip)}",
                                  "detectedLang": "ta", "translation": translation(clip), "flags": []}]
        return result

    return check


def test_v05_report_records_the_testset_hash_the_held_out_split_the_baseline_and_each_translation(stand_in, tmp_path):
    gold = _gold_by_clip(stand_in["items"])
    said = {audio_path(item).read_bytes(): f"answer of {item['id']}" for item in stand_in["items"]}
    out = tmp_path / "reports"

    code = run_eval.main([], run_check=_with_transcript(_fake(lambda clip, sid: gold[clip][sid]), said.get),
                         out_dir=out)

    report = json.loads(_read(out, "latest.json"))
    held = [item for item in stand_in["items"] if item["heldOut"]]
    assert code == 0
    assert report["testsetSha256"] == file_sha256(items_io.ITEMS_PATH)
    assert report["byHeldOut"]["heldOut"]["nItems"] == len(held)
    assert sum(i["source"] == "synthetic_tts" for i in held) == 12  # plus Sam's recorded copies (17 Oct)
    assert report["byHeldOut"]["inSet"]["nItems"] == len(stand_in["items"]) - len(held)
    assert report["byHeldOut"]["heldOut"]["exactAccuracy"] == 1.0
    assert report["modelOnly"]["nItems"] == sum(i["pattern"] not in ("silence", "wrong_language")
                                                for i in stand_in["items"])
    assert set(report["baseline"]) == {"keyword", "keywordNegation"}
    assert report["passBar"]["correctPassMin"] == 0.75 and report["metrics"]["correctPassRate"] == 1.0
    assert all(entry["translation"] == f"answer of {entry['id']}" for entry in report["items"])
    assert sum(entry["heldOut"] for entry in report["items"]) == len(held)
    assert all(entry["original"] == f"ORIGINAL answer of {entry['id']}" for entry in report["items"])  # v0.5.1


def test_each_report_item_keeps_the_first_runs_original_and_final_ratings(stand_in, tmp_path):
    """v0.5.1: the worker's own words and every gold step's guarded rating of run 1, so a stored result can be shown
    as it was judged. With --repeat 2 the first run decides them, even where the second run disagrees."""
    gold = _gold_by_clip(stand_in["items"])
    seen: dict[tuple[bytes, str], int] = {}

    def check(*, steps, questions, clips, worker_lang, supervisor_lang) -> dict:
        (clip,) = clips.values()
        ratings = []
        for step in steps:
            seen[(clip, step["id"])] = n = seen.get((clip, step["id"]), 0) + 1
            first = n == 1
            ratings.append({"stepId": step["id"], "verdict": gold[clip][step["id"]] if first else "unclear",
                            "quote": "said it" if first else "later", "quoteTranslation": "said it (en)" if first else None,
                            "reason": f"run {n}", "flags": [] if first else ["judge_disagree"]})
        return {"ratings": ratings + [{"stepId": "s9", "verdict": "covered", "quote": "stray"}], "passB": True,
                "modelIds": {}, "transcripts": [{"questionId": questions[0]["id"], "original": f"words {n}",
                                                 "translation": "t"}]}

    run_eval.main(["--lang", "ta", "--repeat", "2"], run_check=check, out_dir=tmp_path / "r")

    report = json.loads(_read(tmp_path / "r", "latest.json"))
    items = {item["id"]: item for item in stand_in["items"]}
    for entry in report["items"]:
        assert entry["original"] == "words 1", entry["id"]
        assert [r["stepId"] for r in entry["ratings"]] == list(items[entry["id"]]["gold"]), entry["id"]
        for rating in entry["ratings"]:
            assert rating == {"stepId": rating["stepId"], "verdict": items[entry["id"]]["gold"][rating["stepId"]],
                              "quote": "said it", "quoteTranslation": "said it (en)", "reason": "run 1"}
    assert "stray" not in _read(tmp_path / "r", "latest.json")


def test_the_baseline_reads_the_stored_translation(stand_in, tmp_path):
    """The lead hard case's translation passes a keyword check on s1; the negation variant catches it."""
    lead = next(i for i in stand_in["items"] if i["id"] == "lifting-zone.q1.ta.demo.clean.r1")
    gold = _gold_by_clip(stand_in["items"])
    out = tmp_path / "r"

    run_eval.main(["--lang", "ta"], run_check=_with_transcript(
        _fake(lambda clip, sid: gold[clip][sid]), lambda clip: lead["answerGloss"]), out_dir=out)

    report = json.loads(_read(out, "latest.json"))
    assert report["baseline"]["keyword"]["unsafeErrors"] > report["baseline"]["keywordNegation"]["unsafeErrors"] >= 0
    assert report["metrics"]["unsafeErrors"] == 0


def test_an_item_whose_question_is_not_translated_is_not_ready_even_with_a_current_clip(stand_in, tmp_path):
    item = next(i for i in stand_in["items"] if i["taskId"] == "fragile-roof")
    clips = run_eval.load_clip_manifest()
    assert items_io.item_is_ready(item, stand_in, clips)
    del stand_in["questions"]["fragile-roof"][item["questionId"]][item["workerLang"]]

    def never_called(**kwargs: object) -> dict:
        raise AssertionError("an item without its question must not be checked")

    assert items_io.clip_is_current(item, clips) and not items_io.item_is_ready(item, stand_in, clips)
    assert run_eval.main(["--lang", item["workerLang"]], run_check=never_called, out_dir=tmp_path) == 1


def test_dry_run_counts_the_held_out_items(capsys):
    assert run_eval.main(["--dry-run"]) == 0

    out = capsys.readouterr().out
    held = [item for item in load_items()["items"] if item["heldOut"]]  # recorded copies of held-out items count too
    per_task = {task: sum(i["taskId"] == task for i in held) for task in ("confined-space", "fragile-roof")}  # items
    expected = (f"held out: {len(held)} items, {sum(len(i['gold']) for i in held)} step ratings "
                f"(confined-space {per_task['confined-space']}, fragile-roof {per_task['fragile-roof']})")
    assert expected in out, out
    synthetic = [i for i in held if i["source"] == "synthetic_tts"]
    assert (len(synthetic), sum(len(i["gold"]) for i in synthetic)) == (12, 23)


def test_aggregate_carries_each_items_source_onto_its_rows():
    """v0.5.1: a recorded item's rows say recorded, so the report can split bySource. Fixture items only."""
    items = [{"id": "a", "taskId": "t", "workerLang": "ta", "pattern": "complete", "noise": "clean",
              "questionId": "q1", "gold": {"s1": "covered"}, "source": "synthetic_tts", "heldOut": False},
             {"id": "a.rec.V01", "taskId": "t", "workerLang": "ta", "pattern": "complete", "noise": "clean",
              "questionId": "q1", "gold": {"s1": "covered"}, "source": "recorded", "heldOut": False}]
    run = {"ratings": {"s1": {"verdict": "covered", "flags": [], "evidence": "q"}}, "passB": False, "modelIds": {},
           "transcripts": {}}

    rows, _ = run_eval.aggregate(items, {"a": [run], "a.rec.V01": [run]})

    assert [(row.item_id, row.source) for row in rows] == [("a", "synthetic_tts"), ("a.rec.V01", "recorded")]


def test_normalize_result_keeps_each_transcripts_translation_and_original_and_each_ratings_fields():
    result = {"ratings": [{"step_id": "s1", "verdict": "covered", "quote": "சொன்னது", "quote_translation": "said",
                           "reason": "stated", "confidence": 0.9, "flags": ["x"]},
                          {"stepId": "s2", "verdict": "missed", "quote": None, "quoteTranslation": "", "reason": ""}],
              "transcripts": [{"question_id": "q1", "original": "மூலம்", "translation": "the words"}]}

    out = check_adapter.normalize_result(result)

    assert out["transcripts"] == {"q1": "the words"} and out["originals"] == {"q1": "மூலம்"}
    assert out["ratings"]["s1"] == {"verdict": "covered", "flags": ["x"], "evidence": "சொன்னது", "quote": "சொன்னது",
                                    "quoteTranslation": "said", "reason": "stated"}
    assert out["ratings"]["s2"] == {"verdict": "missed", "flags": [], "evidence": "", "quote": None,
                                    "quoteTranslation": None, "reason": None}
    assert check_adapter.normalize_result({"ratings": []})["originals"] == {}


def test_ready_only_runs_the_current_clips_and_marks_the_report_incomplete(stand_in, tmp_path):
    """On stand-in clips with two made stale, so it runs whatever the state of the real render."""
    _make_stale(stand_in)
    ready = [item for item in stand_in["items"] if item["id"] not in STALE]
    gold = _gold_by_clip(ready)

    code = run_eval.main(["--ready-only"], run_check=_fake(lambda clip, sid: gold[clip][sid]), out_dir=tmp_path)

    report = json.loads(_read(tmp_path, "latest.json"))
    assert code == 0
    assert report["complete"] is False
    assert report["nItems"] == len(ready) == report["testset"]["nItems"] - len(STALE)
    assert not {entry["id"] for entry in report["items"]} & set(STALE)
    assert report["headline"].startswith("Incomplete run")
    assert "Incomplete run" in _read(tmp_path, "latest.md")


# v0.5.1: a run that survives failures (checkpoint, one retry, error items, settings) -----------------------------

class Counting:
    """Wraps a fake check: counts calls per clip and raises what `fail(clip, n)` returns (n = that clip's call)."""

    def __init__(self, fake: Callable[..., dict], fail: Callable[[bytes, int], BaseException | None]) -> None:
        self.fake, self.fail, self.calls = fake, fail, {}

    def __call__(self, **kwargs: object) -> dict:
        (clip,) = kwargs["clips"].values()
        self.calls[clip] = n = self.calls.get(clip, 0) + 1
        problem = self.fail(clip, n)
        if problem is not None:
            raise problem
        return self.fake(**kwargs)

    def total(self) -> int:
        return sum(self.calls.values())


@pytest.fixture
def no_wait(monkeypatch):
    monkeypatch.setattr(run_eval, "RETRY_WAIT_S", 0.0)


def _perfect(stand_in: dict) -> Callable[..., dict]:
    gold = _gold_by_clip(stand_in["items"])
    return _fake(lambda clip, sid: gold[clip][sid])


def _progress_lines(out: Path) -> list[dict]:
    path = out / "progress.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_a_crash_mid_run_keeps_every_finished_item_and_resume_runs_only_the_rest(stand_in, tmp_path, no_wait):
    clips = [audio_path(item).read_bytes() for item in stand_in["items"]]
    crash_on = clips[5]
    crashing = Counting(_perfect(stand_in), lambda clip, n: KeyboardInterrupt() if clip == crash_on else None)
    out = tmp_path / "r"

    with pytest.raises(KeyboardInterrupt):  # not an Exception: the run stops, as on Ctrl-C or a killed process
        run_eval.main([], run_check=crashing, out_dir=out)

    kept = _progress_lines(out)
    assert [line["itemId"] for line in kept] == [item["id"] for item in stand_in["items"][:5]]
    assert not (out / "latest.json").exists()
    finishing = Counting(_perfect(stand_in), lambda clip, n: None)
    assert run_eval.main(["--resume"], run_check=finishing, out_dir=out) == 0
    report = json.loads(_read(out, "latest.json"))
    assert finishing.total() == len(stand_in["items"]) - 5 and not any(c in finishing.calls for c in clips[:5])
    assert report["complete"] is True and report["nItems"] == len(stand_in["items"]) and report["errors"] == []
    assert report["metrics"]["exactAccuracy"] == 1.0
    assert not (out / "progress.jsonl").exists()  # all in the report: the next run starts clean


def test_a_check_that_fails_once_is_tried_again_and_the_run_stays_complete(stand_in, tmp_path, no_wait):
    first = audio_path(stand_in["items"][0]).read_bytes()
    flaky = Counting(_perfect(stand_in),
                     lambda clip, n: UpstreamError("499 CANCELLED") if clip == first and n == 1 else None)

    code = run_eval.main([], run_check=flaky, out_dir=tmp_path / "r")

    report = json.loads(_read(tmp_path / "r", "latest.json"))
    assert code == 0 and flaky.calls[first] == 2
    assert report["complete"] is True and report["errors"] == []


def test_an_item_that_fails_twice_is_an_error_and_the_report_cannot_be_quoted(stand_in, tmp_path, no_wait, capsys):
    bad_item = stand_in["items"][3]
    bad = audio_path(bad_item).read_bytes()
    failing = Counting(_perfect(stand_in), lambda clip, n: UpstreamError("499 CANCELLED") if clip == bad else None)
    out = tmp_path / "r"

    code = run_eval.main([], run_check=failing, out_dir=out)

    report = json.loads(_read(out, "latest.json"))
    assert code == 1 and failing.calls[bad] == 2
    assert report["errors"] == [{"id": bad_item["id"], "class": "UpstreamError", "message": "499 CANCELLED"}]
    assert report["complete"] is False and report["headline"].startswith("Incomplete run")
    assert bad_item["id"] not in {entry["id"] for entry in report["items"]}
    assert report["nItems"] == len(stand_in["items"]) - 1
    assert "## Errors" in _read(out, "latest.md") and "1 of" in capsys.readouterr().err
    assert [line for line in _progress_lines(out) if "error" in line] == [
        {"itemId": bad_item["id"], "settings": report["settings"],
         "error": {"class": "UpstreamError", "message": "499 CANCELLED"}}]

    retry = Counting(_perfect(stand_in), lambda clip, n: None)
    assert run_eval.main(["--resume"], run_check=retry, out_dir=out) == 0
    assert retry.total() == 1 and retry.calls == {bad: 1}  # only the errored item runs again
    again = json.loads(_read(out, "latest.json"))
    assert again["complete"] is True and again["errors"] == [] and not (out / "progress.jsonl").exists()


def test_every_item_failing_still_writes_an_incomplete_report(stand_in, tmp_path, no_wait):
    always = Counting(_perfect(stand_in), lambda clip, n: RuntimeError("boom"))

    code = run_eval.main(["--lang", "my"], run_check=always, out_dir=tmp_path / "r")

    report = json.loads(_read(tmp_path / "r", "latest.json"))
    assert code == 1 and report["nItems"] == 0 and report["complete"] is False
    assert len(report["errors"]) == sum(i["workerLang"] == "my" for i in stand_in["items"])


def test_resume_refuses_progress_written_under_other_settings(stand_in, tmp_path, no_wait, monkeypatch, capsys):
    out = tmp_path / "r"
    crash_on = audio_path(stand_in["items"][2]).read_bytes()
    with pytest.raises(KeyboardInterrupt):
        run_eval.main([], run_check=Counting(_perfect(stand_in),
                                             lambda clip, n: KeyboardInterrupt() if clip == crash_on else None),
                      out_dir=out)
    current = Settings.from_env().thinking["judge_a"]  # whatever the backend's default is today
    monkeypatch.setenv("SIB_THINKING_JUDGE_A", "high" if current != "high" else "low")

    def never(**kwargs: object) -> dict:
        raise AssertionError("a refused resume must not call the check")

    assert run_eval.main(["--resume"], run_check=never, out_dir=out) == 1
    assert "thinking.judge_a" in capsys.readouterr().err
    assert len(_progress_lines(out)) == 2  # the file is left as it was


def test_an_earlier_progress_file_is_never_overwritten_without_resume_or_restart(stand_in, tmp_path, no_wait, capsys):
    out = tmp_path / "r"
    crash_on = audio_path(stand_in["items"][2]).read_bytes()
    with pytest.raises(KeyboardInterrupt):
        run_eval.main([], run_check=Counting(_perfect(stand_in),
                                             lambda clip, n: KeyboardInterrupt() if clip == crash_on else None),
                      out_dir=out)
    fresh = Counting(_perfect(stand_in), lambda clip, n: None)

    assert run_eval.main([], run_check=fresh, out_dir=out) == 1 and fresh.total() == 0
    assert "--resume" in capsys.readouterr().err and len(_progress_lines(out)) == 2
    assert run_eval.main(["--restart"], run_check=fresh, out_dir=out) == 0
    assert fresh.total() == len(stand_in["items"])


def test_the_report_records_the_settings_including_the_judges_thinking_levels(stand_in, tmp_path, monkeypatch):
    monkeypatch.setenv("SIB_THINKING_BLIND_TRANSCRIBER", "low")  # set, so the test does not follow the defaults
    monkeypatch.setenv("SIB_THINKING_JUDGE_A", "high")
    monkeypatch.setenv("SIB_THINKING_JUDGE_B", "low")
    out = tmp_path / "r"

    run_eval.main(["--lang", "zh"], run_check=_perfect(stand_in), out_dir=out)

    settings = json.loads(_read(out, "latest.json"))["settings"]
    assert settings["thinking"] == {"blind_transcriber": "low", "judge_a": "high", "judge_b": "low"}
    assert settings["testsetSha256"] == file_sha256(items_io.ITEMS_PATH) and settings["repeat"] == 1
    assert {"promptVersion", "models", "judgePasses"} <= set(settings)
    assert "thinking blind_transcriber low, judge_a high, judge_b low" in _read(out, "latest.md")
