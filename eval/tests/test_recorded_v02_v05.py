"""17-18 Oct: four more consented speakers, re-voicing the recording sheets (recording-sheets/ in the build folder).
V02 Tamil, recorded with rain and other noise behind (10 of the sheet's 11 lines: line 7 changed meaning and was left
out); V03 Odia (6), V04 Hindi (9) and V05 Bengali (10), phone voice notes in quieter rooms. Each clip was cut from the
speaker's takes at the pauses and checked by transcribing it; spoken line numbers ("the fourth one"), false starts and
an abandoned take were left out, and in two Odia lines long silent gaps were shortened to 0.5 s, no word removed.

A recording made where real noise was present carries `ambient`, a note of that noise. It stays noise "clean" (no
synthetic noise mixed in), gets no site-noise copy, and the report counts it on its own row, never as a quiet room."""

import copy
import wave

import pytest

import augment_recorded
from catalog_io import load_catalog
from config import TESTSET_DIR
from items_io import load_items, problems
from metrics import Row
from report import recorded_noise

SPEAKERS = {"V02": ("ta", 10), "V03": ("or", 6), "V04": ("hi", 9), "V05": ("bn", 10)}


@pytest.fixture(scope="module")
def catalog() -> dict:
    return load_catalog()


def test_the_new_recordings_are_consented_copies_of_existing_items_with_their_gold():
    doc = load_items()
    items = {item["id"]: item for item in doc["items"]}
    for code, (lang, count) in SPEAKERS.items():
        recorded = [item for item in doc["items"] if item["source"] == "recorded" and item["voice"] == code]
        assert len(recorded) == count, code
        for item in recorded:
            source = items[item["recordedFrom"]]
            assert item["id"] == f"{source['id']}.rec.{code}" and source["source"] == "synthetic_tts", item["id"]
            assert item["workerLang"] == lang and item["gold"] == source["gold"] and item["consent"] is True
            assert item["noise"] == "clean" and item["fidelity"] == "review" and item["answer"], item["id"]
            with wave.open(str(TESTSET_DIR / item["audio"]), "rb") as clip:
                assert (clip.getframerate(), clip.getnchannels(), clip.getsampwidth()) == (16000, 1, 2), item["id"]
                assert 1.5 <= clip.getnframes() / 16000 <= 30, item["id"]


def test_only_the_rain_recording_carries_an_ambient_note():
    doc = load_items()
    ambient = {item["voice"] for item in doc["items"] if item.get("ambient")}
    assert ambient == {"V02"}
    assert all(item.get("ambient") for item in doc["items"] if item["source"] == "recorded" and item["voice"] == "V02")


def test_the_contract_keeps_ambient_on_as_recorded_clips_only(catalog):
    doc = load_items()
    rain = next(item for item in doc["items"] if item.get("ambient"))

    synthetic = copy.deepcopy(doc)
    next(i for i in synthetic["items"] if i["source"] == "synthetic_tts")["ambient"] = "traffic"
    assert any("only a recording has an ambient note" in line for line in problems(synthetic, catalog))

    empty = copy.deepcopy(doc)
    next(i for i in empty["items"] if i["id"] == rain["id"])["ambient"] = "  "
    assert any("ambient is a non-empty note" in line for line in problems(empty, catalog))

    copied = copy.deepcopy(doc)
    copied["items"].append({**rain, "id": f"{rain['id']}.drone.snr10", "noise": "drone.snr10", "augmentedFrom": rain["id"],
                            "audio": f"audio/recorded/{rain['id']}.drone.snr10.wav"})
    lines = problems(copied, catalog)
    assert any("site noise is added only to a quiet-room recording" in line for line in lines)


def test_no_site_noise_copy_is_made_of_a_recording_with_real_noise():
    doc = load_items()
    chosen = {item["id"] for item in augment_recorded.recordings(doc)}
    assert not any(item.get("ambient") and item["id"] in chosen for item in doc["items"])
    assert any(item["voice"] == "V01" for item in augment_recorded.recordings(doc))


def _row(item_id: str, noise: str = "clean") -> Row:
    return Row(item_id=item_id, task_id="lifting-zone", worker_lang="ta", pattern="complete", noise=noise, step_id="s1",
               gold="covered", pred="covered", any_covered=True, source="recorded")


def test_the_report_counts_real_noise_on_its_own_row_and_never_as_a_quiet_room():
    items = [{"id": "a.rec.V01"}, {"id": "b.rec.V02", "ambient": "rain"}]
    split = recorded_noise([_row("a.rec.V01"), _row("b.rec.V02")], items)
    assert (split["clean"]["nItems"], split["ambient"]["nItems"]) == (1, 1)
    assert recorded_noise([_row("b.rec.V02")])["clean"]["nItems"] == 1  # no items: no ambient split, as before 17 Oct
