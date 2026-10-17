"""The report's real-voice split by noise (recordedNoise), the --source run and its honest headline. Fixture rows and
a fixture test set only: no backend, no Gemini, and the real reports/ is never written."""

import json

import pytest
from test_report import meta
from test_run_eval import _fake, _wav

import augment_recorded as ar
import items_io
import run_eval
from items_io import file_sha256, load_items
from metrics import Row
from report import build_report, render_markdown


def row(item_id: str, gold: str, pred: str, source: str = "recorded", noise: str = "clean") -> Row:
    return Row(item_id=item_id, task_id="lifting-zone", worker_lang="ta", pattern="negation", noise=noise,
               step_id="s1", gold=gold, pred=pred, any_covered=pred == "covered", source=source)


def report_for(rows: list[Row], **meta_extra) -> dict:
    items = [{"id": r.item_id, "taskId": r.task_id, "workerLang": r.worker_lang, "pattern": r.pattern,
              "noise": r.noise, "source": r.source} for r in rows]
    return build_report(rows, items, {**meta(), **meta_extra})


ROWS = [row("syn", "missed", "missed", source="synthetic_tts"),
        row("a.rec.V01", "missed", "missed"), row("b.rec.V01", "covered", "covered"),
        row("a.rec.V01.site-hammer.snr0", "missed", "covered", noise="site-hammer.snr0"),
        row("a.rec.V01.site-drone.snr0", "missed", "missed", noise="site-drone.snr0"),
        row("b.rec.V01.site-drone.snr10", "covered", "unclear", noise="site-drone.snr10")]


def test_the_report_splits_the_recorded_items_by_noise_and_keeps_by_source():
    report = report_for(ROWS)

    split = report["recordedNoise"]
    assert (split["clean"]["nItems"], split["clean"]["unsafeErrors"]) == (2, 0)
    assert (split["siteNoise"]["nItems"], split["siteNoise"]["unsafeErrors"]) == (3, 1)
    assert set(split["bySnr"]) == {"snr10", "snr5", "snr0"}
    assert (split["bySnr"]["snr0"]["nItems"], split["bySnr"]["snr0"]["unsafeErrors"]) == (2, 1)
    assert split["bySnr"]["snr5"]["nItems"] == 0
    assert list(split["byNoise"]) == ["site-drone.snr0", "site-drone.snr10", "site-hammer.snr0"]
    assert split["byNoise"]["site-hammer.snr0"]["unsafeErrors"] == 1
    assert (report["bySource"]["recorded"]["nItems"], report["bySource"]["synthetic_tts"]["nItems"]) == (5, 1)
    assert report["selection"] is None


def test_the_headline_and_markdown_count_a_noisy_copy_as_a_copy_never_as_a_recording():
    report = report_for(ROWS)
    markdown = render_markdown(report, ROWS, meta())

    assert "and 5 consented recordings (3 of them with synthetic site noise)" in report["headline"]
    assert "## Real voices by noise" in markdown
    assert "| As recorded (quiet room) | 2 | 2 |" in markdown and "| All site noise | 3 | 3 |" in markdown
    assert "| Site noise at 0 dB SNR | 2 | 2 | 50.0% | 1 of 2 |" in markdown
    assert "| site-hammer.snr0 | 1 | 1 |" in markdown and "Site noise at 5 dB" not in markdown
    assert "not a field trial" in markdown and "The answers are synthetic." in markdown


def test_a_run_with_no_recording_has_no_real_voice_table_and_the_same_headline():
    rows = [row("syn", "missed", "missed", source="synthetic_tts")]
    report = report_for(rows)

    assert "## Real voices by noise" not in render_markdown(report, rows, meta())
    assert report["recordedNoise"]["clean"]["nItems"] == report["recordedNoise"]["siteNoise"]["nItems"] == 0
    assert "answers in synthetic Gemini TTS voices (gemini-3.8-flash-tts), judged" in report["headline"]


def test_a_whole_source_run_names_the_subset_and_a_partial_one_stays_incomplete():
    rows = ROWS[1:]
    whole = report_for(rows, complete=False, selection={"source": "recorded", "nItems": 5, "complete": True})
    partial = report_for(rows, complete=False, selection={"source": "recorded", "nItems": 9, "complete": False})
    markdown = render_markdown(whole, rows, meta())

    assert whole["headline"].startswith("Recorded human voices only (5 of the 46 items in the set): ")
    assert "5 answers from consented human recordings (3 of them with synthetic site noise)" in whole["headline"]
    assert "(recorded human voices only, not the whole set)" in markdown and "not for quoting" not in markdown
    assert "The answers are synthetic." not in markdown and "Recorded human voices only:" in markdown
    assert partial["headline"].startswith("Incomplete run (5 of 46 items, not for quoting): ")


@pytest.fixture
def with_recordings(tmp_path, monkeypatch) -> dict:
    """The real synthetic set plus one consented recording and two site-noise copies, every clip a stand-in."""
    doc = load_items()
    doc["items"] = [i for i in doc["items"] if i["source"] != "recorded"]  # the real V01 clips are not this test's
    for dotted in doc["pendingQuestions"]:
        task_id, question_id, lang = dotted.split(".")
        doc["questions"].setdefault(task_id, {}).setdefault(question_id, {})[lang] = f"stand-in {dotted}"
    doc["pendingQuestions"] = []
    source = next(i for i in doc["items"] if i["pattern"] == "negation" and i["workerLang"] == "ta")
    rec = {**source, "id": f"{source['id']}.rec.V01", "source": "recorded", "fidelity": "review",
           "audio": f"audio/recorded/{source['id']}.rec.V01.wav", "voice": "V01", "demo": None, "consent": True,
           "recordedFrom": source["id"], "pending": []}
    doc["items"] += [rec, ar.copy_item(rec, "site-hammer", "snr0"), ar.copy_item(rec, "site-babble", "snr5")]
    (tmp_path / "audio" / "recorded").mkdir(parents=True)
    clips = {}
    for n, item in enumerate(doc["items"], start=1):
        (tmp_path / item["audio"]).write_bytes(_wav(n))
        clips[item["id"]] = {"text": item["answer"], "voice": item["voice"], "model": "gemini-3.8-flash-tts",
                             "sha256": file_sha256(tmp_path / item["audio"])}
    monkeypatch.setattr(items_io, "TESTSET_DIR", tmp_path)
    monkeypatch.setattr(run_eval, "load_items", lambda: doc)
    monkeypatch.setattr(run_eval, "load_clip_manifest", lambda: clips)
    monkeypatch.setattr(run_eval, "REPORTS_DIR", tmp_path / "reports")  # never the real eval/reports
    return doc


def test_source_recorded_runs_only_the_real_voices_into_their_own_folder(with_recordings, tmp_path, capsys):
    assert items_io.problems(with_recordings, run_eval.load_catalog()) == []
    asked: list[str] = []
    fake = _fake(lambda clip, sid: "missed")

    def check(**kwargs):
        asked.append(kwargs["worker_lang"])
        return fake(**kwargs)

    code = run_eval.main(["--source", "recorded"], run_check=check)

    report = json.loads((tmp_path / "reports" / "recorded" / "latest.json").read_text(encoding="utf-8"))
    assert code == 0 and len(asked) == 3 and not (tmp_path / "reports" / "latest.json").exists()
    assert report["nItems"] == 3 and {i["source"] for i in report["items"]} == {"recorded"}
    assert report["selection"] == {"source": "recorded", "nItems": 3, "complete": True}
    assert report["complete"] is False and report["headline"].startswith("Recorded human voices only (3 of the ")
    assert report["recordedNoise"]["siteNoise"]["nItems"] == 2
    assert "real voices: 0 false passes" in capsys.readouterr().out


def test_select_items_filters_by_source():
    assert run_eval.select_items([{"workerLang": "ta", "source": "recorded", "id": "r"},
                                  {"workerLang": "ta", "source": "synthetic_tts", "id": "s"}],
                                 None, None, source="recorded") == [{"workerLang": "ta", "source": "recorded", "id": "r"}]
