"""augment_recorded.py and record_clips.py --forget on a fixture test set in a temp folder. The real testset/ is never
read or written: every call passes testset_dir."""

import copy
import json
import wave
from pathlib import Path

import pytest
from test_record_clips import TRENCH, fixture_doc
from test_site_noise import speech_like

import augment_recorded as ar
import record_clips as rc
from audio_tools import read_samples, write_samples
from catalog_io import load_catalog
from items_io import problems
from site_noise import NOISE_NAMES


def recording(source: dict, speaker: str) -> dict:
    """What record_clips.py saves for a kept word-for-word take (test_record_clips pins the same dict)."""
    rec_id = rc.recorded_id(source["id"], speaker)
    return {**{k: source[k] for k in ("taskId", "questionId", "workerLang", "pattern")}, "id": rec_id,
            "noise": "clean", "source": "recorded", "answer": source["answer"], "answerGloss": source["answerGloss"],
            "backTranslation": source["backTranslation"], "fidelity": "review", "gold": dict(source["gold"]),
            "audio": f"audio/recorded/{rec_id}.wav", "voice": speaker, "demo": None, "heldOut": source["heldOut"],
            "consent": True, "recordedFrom": source["id"], "pending": []}


@pytest.fixture
def testset(tmp_path: Path) -> Path:
    doc = fixture_doc()
    trench = next(item for item in doc["items"] if item["id"] == TRENCH)
    speech, _ = speech_like(bursts=(0.4, 0.3), gap=0.2, lead=0.2)
    for speaker in ("V01", "V02"):
        item = recording(trench, speaker)
        doc["items"].append(item)
        write_samples(tmp_path / item["audio"], speech)
    rc.write_doc(doc, tmp_path)
    return tmp_path


def load(testset: Path) -> dict:
    return json.loads((testset / "items.json").read_text(encoding="utf-8"))


def mine(doc: dict, prefix: str) -> list[str]:
    return [line for line in problems(doc, load_catalog()) if line.startswith(prefix)]


V01 = f"{TRENCH}.rec.V01"


def test_a_dry_run_lists_twelve_copies_per_recording_and_writes_nothing(testset, capsys):
    before = (testset / "items.json").read_bytes()
    files = sorted((testset / "audio" / "recorded").iterdir())

    code = ar.main(["--dry-run"], testset_dir=testset)

    out = capsys.readouterr().out
    assert code == 0 and "dry run: 24 site-noise copies to write (24 new); nothing written" in out
    assert f"new    {V01}.site-hammer.snr5" in out
    assert (testset / "items.json").read_bytes() == before
    assert sorted((testset / "audio" / "recorded").iterdir()) == files


def test_each_copy_keeps_the_recordings_gold_texts_and_consent_points_back_and_passes_the_contract(testset):
    before = load(testset)
    old_text = (testset / "items.json").read_text(encoding="utf-8")

    code = ar.main(["--speaker", "V01"], testset_dir=testset)

    doc = load(testset)
    copies = [item for item in doc["items"] if item.get("augmentedFrom") == V01]
    rec = next(item for item in doc["items"] if item["id"] == V01)
    assert code == 0 and sorted(item["noise"] for item in copies) == sorted(NOISE_NAMES)
    for item in copies:
        assert item["id"] == f"{V01}.{item['noise']}" and item["audio"] == f"audio/recorded/{item['id']}.wav"
        assert {k: v for k, v in item.items() if k not in ("id", "noise", "audio", "augmentedFrom")} == {
            k: v for k, v in rec.items() if k not in ("id", "noise", "audio")}
        assert (item["source"], item["consent"], item["recordedFrom"]) == ("recorded", True, TRENCH)
        with wave.open(str(testset / item["audio"]), "rb") as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert len(read_samples(testset / item["audio"])) == len(read_samples(testset / rec["audio"]))
    assert mine(doc, V01) == []
    assert [i for i in doc["items"] if i["source"] == "synthetic_tts"] == [
        i for i in before["items"] if i["source"] == "synthetic_tts"]  # synthetic items untouched
    assert not [i for i in doc["items"] if i.get("augmentedFrom", "").endswith("V02")]
    assert doc["items"][:len(before["items"])] == before["items"]  # appended, nothing reordered
    assert (testset / "items.json").read_text(encoding="utf-8").startswith(old_text[:old_text.rindex("\n  ]\n}")])


def test_a_rerun_writes_nothing_new_and_a_lost_clip_comes_back_byte_for_byte(testset, capsys):
    ar.main([], testset_dir=testset)
    lost = testset / f"audio/recorded/{V01}.site-babble.snr0.wav"
    first, items_before = lost.read_bytes(), (testset / "items.json").read_bytes()

    ar.main([], testset_dir=testset)
    assert "wrote 0 site-noise copies (none)" in capsys.readouterr().out
    lost.unlink()
    ar.main([], testset_dir=testset)

    assert "wrote 1 site-noise copies (1 clip)" in capsys.readouterr().out
    assert lost.read_bytes() == first and (testset / "items.json").read_bytes() == items_before


def test_a_transcript_typed_later_makes_the_copies_stale_until_the_tool_runs_again(testset, capsys):
    ar.main(["--speaker", "V01"], testset_dir=testset)
    doc = load(testset)
    next(item for item in doc["items"] if item["id"] == V01).update(answer="typed later", fidelity="ok")
    rc.write_doc(doc, testset)
    assert len(mine(load(testset), f"{V01}.site-")) == 12

    ar.main(["--speaker", "V01"], testset_dir=testset)

    assert "(12 update)" in capsys.readouterr().out
    assert mine(load(testset), V01) == []
    assert all(item["answer"] == "typed later" for item in load(testset)["items"] if item.get("augmentedFrom") == V01)


def test_filters_choose_the_speaker_profile_and_snr(testset):
    ar.main(["--speaker", "V02", "--profile", "site-hammer", "--snr", "snr0"], testset_dir=testset)

    assert [i["id"] for i in load(testset)["items"] if "augmentedFrom" in i] == [f"{TRENCH}.rec.V02.site-hammer.snr0"]


def test_a_name_is_refused_and_a_set_with_no_recording_has_nothing_to_do(testset, tmp_path, capsys):
    assert ar.main(["--speaker", "Hari"], testset_dir=testset) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    rc.write_doc(fixture_doc(), empty)

    assert ar.main([], testset_dir=empty) == 1
    assert "never a name" in capsys.readouterr().out


def test_a_recording_whose_clip_is_missing_is_skipped_and_said(testset, capsys):
    (testset / f"audio/recorded/{V01}.wav").unlink()

    code = ar.main([], testset_dir=testset)

    assert code == 1 and f"skipped {V01}: its clip is missing" in capsys.readouterr().out
    assert not [i for i in load(testset)["items"] if i.get("augmentedFrom") == V01]


def test_forget_deletes_the_speakers_copies_and_stray_clips_and_nothing_of_anyone_else(testset):
    ar.main([], testset_dir=testset)
    stray = testset / f"audio/recorded/{V01}.site-drone.snr7.wav"  # a clip a stopped run left with no item
    stray.write_bytes(b"x")
    said: list[str] = []

    code = rc.main(["--forget", "V01"], io=rc.Io(ask=lambda _: "", say=said.append), testset_dir=testset)

    left = load(testset)["items"]
    assert code == 0 and "Deleted 13 items of V01" in said[0]
    assert not [i for i in left if i["voice"] == "V01" or i.get("augmentedFrom") == V01]
    assert len([i for i in left if i.get("augmentedFrom") == f"{TRENCH}.rec.V02"]) == 12
    assert not [p for p in (testset / "audio" / "recorded").iterdir() if ".rec.V01" in p.name]
    assert len(list((testset / "audio" / "recorded").iterdir())) == 13  # V02's recording and its 12 copies
    assert TRENCH in [i["id"] for i in left]


def test_the_contract_refuses_a_broken_copy(testset):
    ar.main(["--speaker", "V01"], testset_dir=testset)
    doc = load(testset)
    copy_id = f"{V01}.site-hammer.snr5"
    for change, message in (({"noise": "snr5"}, "noise snr5"),
                            ({"noise": "site-hammer.snr0"}, "<recording id>.<noise>"),
                            ({"augmentedFrom": TRENCH}, "must name a clean recorded item"),
                            ({"gold": {"s1": "missed", "s2": "covered"}}, "keeps"),
                            ({"consent": False}, "needs consent: true")):
        broken = copy.deepcopy(doc)
        next(i for i in broken["items"] if i["id"] == copy_id).update(change)
        assert any(message in line for line in mine(broken, copy_id)), change
    noisy_recording = copy.deepcopy(doc)
    next(i for i in noisy_recording["items"] if i["id"] == V01)["noise"] = "snr10"
    assert any("a recording is noise clean" in line for line in mine(noisy_recording, V01 + ":"))
    synthetic_copy = copy.deepcopy(doc)
    next(i for i in synthetic_copy["items"] if i["id"] == TRENCH)["augmentedFrom"] = V01
    assert any("only a recorded item" in line for line in mine(synthetic_copy, TRENCH + ":"))
