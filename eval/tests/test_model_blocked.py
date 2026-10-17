"""A reply that Agent Platform blocked (no text, prompt_feedback.block_reason) is ModelBlocked, never
json.loads(None); the spot-check records it as a non-match and goes on (15 Oct 2026: one Odia clip)."""

from types import SimpleNamespace

import pytest

import build_testset
import gemini_client
from gemini_client import ModelBlocked, _text_or_blocked


def blocked_reply():
    return SimpleNamespace(text=None, prompt_feedback=SimpleNamespace(block_reason=SimpleNamespace(value="SAFETY")))


def test_a_blocked_reply_names_its_reason():
    with pytest.raises(ModelBlocked, match="SAFETY"):
        _text_or_blocked(blocked_reply())


def test_a_reply_with_text_is_returned():
    assert _text_or_blocked(SimpleNamespace(text='{"a": 1}', prompt_feedback=None)) == '{"a": 1}'


def test_the_spot_check_records_a_blocked_clip_and_goes_on(tmp_path, monkeypatch):
    items = []
    for item_id in build_testset.SPOTCHECK_IDS:
        wav = tmp_path / f"{item_id}.wav"
        wav.write_bytes(b"RIFF")
        items.append({"id": item_id, "answer": "abc", "pending": [], "_wav": wav})
    monkeypatch.setattr(build_testset, "audio_path", lambda item: item["_wav"])
    monkeypatch.setattr(build_testset, "SPOTCHECK_PATH", tmp_path / "spotcheck.json")
    first = build_testset.SPOTCHECK_IDS[0]

    class Calls:
        def audio_json(self, *, purpose, **_):
            if first in purpose:
                raise ModelBlocked("the model returned no text: SAFETY")
            return {"transcript": "abc", "language": "ta"}

    rows = build_testset.spot_check(Calls(), {"items": items})
    by_id = {r["id"]: r for r in rows}
    assert by_id[first]["match"] is False and "SAFETY" in by_id[first]["blocked"]
    assert all(r["match"] for r in rows if r["id"] != first)
    assert len(rows) == len(build_testset.SPOTCHECK_IDS)


def test_the_client_never_parses_none():
    calls = gemini_client.GeminiCalls(client=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: blocked_reply())))
    with pytest.raises(ModelBlocked):
        calls._audio_json_call(b"RIFF", "system", "prompt", {"type": "object"})


def test_a_blocked_reply_is_retried_once_and_a_second_answer_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini_client, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(gemini_client, "_record_call", lambda *a, **k: None)
    replies = iter([blocked_reply(), SimpleNamespace(text='{"transcript": "abc", "language": "ta"}', prompt_feedback=None)])
    calls = gemini_client.GeminiCalls(client=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: next(replies))))
    got = calls.audio_json(purpose="spot-check x", wav=b"RIFF", system="s", prompt="p", schema={"type": "object"},
                           validate=lambda d: None)
    assert got == {"transcript": "abc", "language": "ta"}


def test_two_blocked_replies_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini_client, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(gemini_client, "_record_call", lambda *a, **k: None)
    calls = gemini_client.GeminiCalls(client=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: blocked_reply())))
    with pytest.raises(ModelBlocked):
        calls.audio_json(purpose="spot-check x", wav=b"RIFF", system="s", prompt="p", schema={"type": "object"},
                         validate=lambda d: None)
