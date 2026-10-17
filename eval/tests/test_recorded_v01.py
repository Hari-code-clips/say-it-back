"""17 Oct: Sam's consented recordings (speaker V01), one take cut into the recording sheet's 11 lines. Each is a
recorded copy of an existing synthetic item with that item's gold; its answer is Sarvam STT's transcript of the
clip (the lines were said in the speaker's own words), and its back-translation waits for a person."""

import wave

from config import TESTSET_DIR
from items_io import load_items
from sayitback.catalog import unicode_ranges
from sayitback.guards import script_shares


def test_the_eleven_v01_recordings_are_consented_tamil_copies_of_existing_items_with_their_gold():
    doc = load_items()
    items = {item["id"]: item for item in doc["items"]}
    recorded = [item for item in doc["items"] if item["source"] == "recorded" and item["voice"] == "V01"]

    assert len(recorded) == 11
    for item in recorded:
        source = items[item["recordedFrom"]]
        assert item["id"] == f"{source['id']}.rec.V01" and source["source"] == "synthetic_tts", item["id"]
        assert item["gold"] == source["gold"] and item["consent"] is True, item["id"]
        same = ("taskId", "questionId", "workerLang", "pattern", "heldOut", "answerGloss")
        assert {k: item[k] for k in same} == {k: source[k] for k in same}, item["id"]
        assert item["fidelity"] == "review" and item["pending"] == ["backTranslation"] and item["demo"] is None
        share, latin, _ = script_shares(item["answer"], unicode_ranges("ta"))
        assert share >= 0.9 and latin == 0.0, item["id"]  # the transcript is in Tamil script, as the worker said it
        with wave.open(str(TESTSET_DIR / item["audio"]), "rb") as clip:
            assert (clip.getframerate(), clip.getnchannels(), clip.getsampwidth()) == (16000, 1, 2), item["id"]
            assert clip.getnframes() / 16000 >= 1.5, item["id"]
