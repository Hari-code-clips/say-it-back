"""record_clips.py on a fixture test set in a temp folder: a fake recorder writes the takes, a script answers the
prompts. No microphone, no ffmpeg run, and the real testset/ is never read or written."""

import array
import copy
import json
import math
import shutil
import time
from pathlib import Path

import pytest

import record_clips as rc
from audio_tools import read_samples, write_samples
from catalog_io import load_catalog
from config import SAMPLE_RATE
from items_io import problems

SPEECH, QUIET, SHORT = (1.5, 8000), (1.5, 20), (0.2, 8000)  # (seconds, amplitude)


def synthetic(item_id: str, task: str, qid: str, lang: str, pattern: str, gold: dict, **extra) -> dict:
    item = {"id": item_id, "taskId": task, "questionId": qid, "workerLang": lang, "pattern": pattern,
            "noise": "clean", "source": "synthetic_tts", "answer": f"text of {item_id}",
            "answerGloss": f"gloss of {item_id}", "backTranslation": f"back of {item_id}", "fidelity": "ok",
            "gold": gold, "audio": f"audio/{item_id}.wav", "voice": "Kore", "demo": None,
            "heldOut": task in ("confined-space", "fragile-roof"), "pending": []}
    return {**item, **extra}


def fixture_doc() -> dict:
    return {
        "version": "fixture",
        "questions": {"trench-entry": {"q1": {"or": "Q or"}}, "fragile-roof": {"q1": {"my": "Q my"}},
                      "lifting-zone": {"q1": {"ta": "Q ta", "zh": "Q zh"}}},
        "questionSources": {},
        "pendingQuestions": ["confined-space.q2.hi"],
        "items": [
            synthetic("trench-entry.q1.or.complete.clean", "trench-entry", "q1", "or", "complete",
                      {"s1": "covered", "s2": "covered"}),
            synthetic("fragile-roof.q1.my.negation.clean", "fragile-roof", "q1", "my", "negation", {"s1": "covered"}),
            synthetic("lifting-zone.q1.ta.demo.clean.r1", "lifting-zone", "q1", "ta", "demo",
                      {"s1": "contradicted", "s2": "missed"}, demo={"script": "sg-lead", "round": 0}),
            synthetic("lifting-zone.q1.zh.silence.clean", "lifting-zone", "q1", "zh", "silence",
                      {"s1": "unclear", "s2": "unclear"}, answer="", backTranslation="", voice=None),
            synthetic("lifting-zone.q1.ta.negation.clean", "lifting-zone", "q1", "ta", "negation",
                      {"s1": "covered", "s2": "contradicted"}, answer="", backTranslation="",
                      pending=["answer", "backTranslation", "audio"]),
            synthetic("confined-space.q2.hi.negation.clean", "confined-space", "q2", "hi", "negation",
                      {"s4": "covered"}),
        ],
    }


@pytest.fixture
def testset(tmp_path: Path) -> Path:
    (tmp_path / "items.json").write_text(json.dumps(fixture_doc(), ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp_path


class FakeRecorder:
    """Writes the next take (seconds, amplitude) as a 16 kHz tone, after the stop prompt is answered."""

    def __init__(self, takes: list[tuple[float, int]]) -> None:
        self.takes = list(takes)
        self.recorded: list[Path] = []
        self.played: list[Path] = []

    def record(self, dst: Path, max_seconds: float, wait_for_stop) -> None:
        assert max_seconds == 30
        wait_for_stop()
        seconds, amplitude = self.takes.pop(0)
        n = int(seconds * SAMPLE_RATE)
        write_samples(dst, array.array("h", (round(amplitude * math.sin(2 * math.pi * (220 + 50 * len(self.recorded))
                                                                         * i / SAMPLE_RATE)) for i in range(n))))
        self.recorded.append(dst)

    def play(self, path: Path) -> None:
        self.played.append(path)


class Script(rc.Io):
    def __init__(self, answers: list[str]) -> None:
        self.answers, self.out = list(answers), []
        super().__init__(ask=self._ask, say=self.out.append)

    def _ask(self, prompt: str) -> str:
        self.out.append(prompt)
        assert self.answers, f"no scripted answer for: {prompt}"
        return self.answers.pop(0)

    def text(self) -> str:
        return "\n".join(self.out)


def run(testset: Path, argv: list[str], answers: list[str], takes=(SPEECH,)) -> tuple[int, Script, FakeRecorder]:
    io, recorder = Script(answers), FakeRecorder(list(takes))
    code = rc.main(argv, recorder=recorder, io=io, testset_dir=testset, catalog=load_catalog())
    return code, io, recorder


def items(testset: Path) -> dict[str, dict]:
    return {item["id"]: item for item in json.loads((testset / "items.json").read_text(encoding="utf-8"))["items"]}


KEEP_VERBATIM = ["", "", "k", "y", "y"]  # record, stop, keep, same meaning, word for word
TRENCH = "trench-entry.q1.or.complete.clean"


def test_nothing_is_recorded_without_a_typed_yes(testset):
    before = (testset / "items.json").read_bytes()
    for reply in ("y", "ok", "", "no", "yes please"):
        code, io, recorder = run(testset, ["--speaker", "V01", "--item", TRENCH], [reply])

        assert code == 1 and recorder.recorded == []
        assert "public" in io.text() and "No name is stored" in io.text() and "V01" in io.text()
        assert "nothing was recorded" in io.text()
    assert (testset / "items.json").read_bytes() == before
    assert not (testset / "audio").exists()


def test_a_kept_take_becomes_a_recorded_item_with_the_source_gold_and_a_speaker_code(testset):
    code, io, recorder = run(testset, ["--speaker", "V01", "--item", TRENCH], ["yes", *KEEP_VERBATIM])

    saved = items(testset)[f"{TRENCH}.rec.V01"]
    source = items(testset)[TRENCH]
    assert code == 0
    assert saved == {
        "id": f"{TRENCH}.rec.V01", "taskId": "trench-entry", "questionId": "q1", "workerLang": "or",
        "pattern": "complete", "noise": "clean", "source": "recorded", "answer": source["answer"],
        "answerGloss": source["answerGloss"], "backTranslation": source["backTranslation"], "fidelity": "review",
        "gold": source["gold"], "audio": f"audio/recorded/{TRENCH}.rec.V01.wav", "voice": "V01", "demo": None,
        "heldOut": False, "consent": True, "recordedFrom": TRENCH, "pending": [],
    }
    assert (testset / saved["audio"]).is_file()
    assert source["answerGloss"] in io.text() and source["answer"] in io.text() and "Q or" in io.text()


def test_the_saved_item_passes_the_contract_and_a_broken_one_does_not(testset):
    run(testset, ["--speaker", "V01", "--item", TRENCH], ["yes", *KEEP_VERBATIM])
    doc = json.loads((testset / "items.json").read_text(encoding="utf-8"))
    rec_id = f"{TRENCH}.rec.V01"

    def mine(d: dict) -> list[str]:
        return [line for line in problems(d, load_catalog()) if line.startswith(rec_id)]

    assert mine(doc) == []
    for change, message in (({"consent": False}, "needs consent: true"),
                            ({"voice": "Hari"}, "never a name"),
                            ({"gold": {"s1": "missed", "s2": "covered"}}, "must match"),
                            ({"recordedFrom": "no.such.item"}, "recordedFrom must name a synthetic item"),
                            ({"audio": "audio/elsewhere.wav"}, "audio/recorded/"),
                            ({"pattern": "silence", "gold": {"s1": "unclear", "s2": "unclear"}}, "not recorded")):
        broken = copy.deepcopy(doc)
        next(i for i in broken["items"] if i["id"] == rec_id).update(change)
        assert any(message in line for line in mine(broken)), change


def test_a_pending_transcript_does_not_force_a_pending_clip_but_a_synthetic_answer_still_does(testset):
    run(testset, ["--speaker", "V01", "--item", TRENCH], ["yes", "", "", "k", "y", "n", ""])
    doc = json.loads((testset / "items.json").read_text(encoding="utf-8"))
    saved = items(testset)[f"{TRENCH}.rec.V01"]
    synthetic_item = next(i for i in doc["items"] if i["id"] == TRENCH)
    synthetic_item.update(answer="", backTranslation="", pending=["answer", "backTranslation"])

    assert saved["answer"] == "" and saved["pending"] == ["answer", "backTranslation"]
    found = problems(doc, load_catalog())
    assert not [line for line in found if line.startswith(f"{TRENCH}.rec.V01")]
    assert any(line.startswith(TRENCH + ":") and "clip pending too" in line for line in found)


def test_a_paraphrase_keeps_the_typed_transcript_and_leaves_the_back_translation_pending(testset):
    run(testset, ["--speaker", "V02", "--item", TRENCH], ["yes", "", "", "k", "y", "n", "  in my own words  "])

    saved = items(testset)[f"{TRENCH}.rec.V02"]
    assert (saved["answer"], saved["backTranslation"], saved["pending"]) == ("in my own words", "", ["backTranslation"])


def test_play_and_redo_keep_only_the_last_take(testset):
    code, io, recorder = run(testset, ["--speaker", "V01", "--item", TRENCH],
                             ["yes", "", "", "p", "r", "", "", "p", "k", "y", "y"], takes=[SPEECH, SPEECH])

    saved = items(testset)[f"{TRENCH}.rec.V01"]
    assert len(recorder.recorded) == 2 and len(recorder.played) == 2
    assert code == 0 and (testset / saved["audio"]).is_file()
    assert sorted(p.name for p in (testset / "audio" / "recorded").iterdir()) == [f"{TRENCH}.rec.V01.wav"]


def test_a_take_with_another_meaning_is_not_kept(testset):
    code, io, _ = run(testset, ["--speaker", "V01", "--item", TRENCH], ["yes", "", "", "k", "n", "s"])

    assert code == 1 and f"{TRENCH}.rec.V01" not in items(testset)
    assert "gold labels would not fit" in io.text()


@pytest.mark.parametrize("bad", [QUIET, SHORT])
def test_a_silent_or_too_short_take_is_refused_and_recorded_again(testset, bad):
    code, io, recorder = run(testset, ["--speaker", "V01", "--item", TRENCH], ["yes", "", "", *KEEP_VERBATIM],
                             takes=[bad, SPEECH])

    assert "Not usable" in io.text() and len(recorder.recorded) == 2
    assert code == 0 and f"{TRENCH}.rec.V01" in items(testset)


def test_quit_keeps_what_was_already_saved(testset):
    code, _, _ = run(testset, ["--speaker", "V01", "--lang", "or", "--lang", "my"],
                     ["yes", *KEEP_VERBATIM, "q"], takes=[SPEECH])

    saved = [i for i in items(testset) if ".rec." in i]
    assert code == 0 and saved == [f"{TRENCH}.rec.V01"]


def test_only_translated_non_demo_non_silence_items_are_offered_and_a_dry_run_writes_nothing(testset):
    before = (testset / "items.json").read_bytes()
    doc = fixture_doc()

    offered = [i["id"] for i in rc.recordable(doc, "V01")]
    code, io, recorder = run(testset, ["--speaker", "V01", "--dry-run"], [])

    assert offered == [TRENCH, "fragile-roof.q1.my.negation.clean"]  # no demo, silence, pending text or question
    assert [i["id"] for i in rc.recordable(doc, "V01", tasks=["fragile-roof"])] == ["fragile-roof.q1.my.negation.clean"]
    assert [i["id"] for i in rc.recordable(doc, "V01", langs=["or"], tasks=["fragile-roof"])] == []
    assert code == 0 and recorder.recorded == [] and "nothing recorded or written" in io.text()
    assert (testset / "items.json").read_bytes() == before


def test_an_item_already_recorded_by_that_speaker_is_not_offered_again(testset):
    run(testset, ["--speaker", "V01", "--item", TRENCH], ["yes", *KEEP_VERBATIM])
    doc = json.loads((testset / "items.json").read_text(encoding="utf-8"))

    assert TRENCH not in [i["id"] for i in rc.recordable(doc, "V01")]
    assert TRENCH in [i["id"] for i in rc.recordable(doc, "V02")]


@pytest.mark.parametrize("speaker", ["Hari", "v01", "V1", "V001", ""])
def test_the_speaker_must_be_a_code_never_a_name(testset, speaker):
    code, io, recorder = run(testset, ["--speaker", speaker, "--item", TRENCH], [])

    assert code == 2 and recorder.recorded == [] and "never a name" in io.text()


def test_forget_deletes_only_that_speakers_recordings(testset):
    run(testset, ["--speaker", "V01", "--item", TRENCH], ["yes", *KEEP_VERBATIM])
    run(testset, ["--speaker", "V02", "--item", TRENCH], ["yes", *KEEP_VERBATIM])

    code, io, _ = run(testset, ["--forget", "V01"], [])

    left = items(testset)
    assert code == 0 and f"{TRENCH}.rec.V01" not in left and f"{TRENCH}.rec.V02" in left
    assert sorted(p.name for p in (testset / "audio" / "recorded").iterdir()) == [f"{TRENCH}.rec.V02.wav"]
    assert TRENCH in left


class ToneRecorder(rc.FfmpegRecorder):
    """The real recorder with ffmpeg's tone generator, read in real time, in place of the microphone."""

    def input_args(self) -> list[str]:
        return ["-re", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_the_real_recorder_stops_on_enter_and_writes_a_usable_16khz_clip(tmp_path):
    dst = tmp_path / "take.wav"

    ToneRecorder().record(dst, rc.MAX_SECONDS, lambda: time.sleep(1.0))

    problems, info = rc.check_clip(dst)
    seconds = len(read_samples(dst)) / SAMPLE_RATE
    assert problems == [] and 0.6 <= seconds <= 3.0, info


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_the_real_recorder_stops_by_itself_at_the_limit(tmp_path):
    dst = tmp_path / "take.wav"

    ToneRecorder().record(dst, 1.0, lambda: time.sleep(2.0))  # Enter comes after ffmpeg has already stopped

    assert len(read_samples(dst)) / SAMPLE_RATE == pytest.approx(1.0, abs=0.1)


def test_the_ffmpeg_command_records_the_mac_microphone_as_16khz_mono_16bit_with_a_30s_cap(tmp_path):
    cmd = rc.FfmpegRecorder(":1").command(tmp_path / "x.wav", rc.MAX_SECONDS)

    assert cmd[:1] == ["ffmpeg"] and cmd[cmd.index("-f") + 1] == "avfoundation" and cmd[cmd.index("-i") + 1] == ":1"
    assert (cmd[cmd.index("-t") + 1], cmd[cmd.index("-ar") + 1], cmd[cmd.index("-ac") + 1],
            cmd[cmd.index("-c:a") + 1]) == ("30", "16000", "1", "pcm_s16le")
    assert cmd[-1] == str(tmp_path / "x.wav")
