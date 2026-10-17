"""The second TTS vendor (vendor_tts.py, 16 Oct): Sarvam-voiced clips, routed by spec.json's `voice`. No network: every
call goes to a fake `post`."""

import base64
import io
import json
import shutil
import urllib.error
import wave

import pytest

import build_testset as bt
import gemini_client
import vendor_tts
from config import SAMPLE_RATE

VOICE = "sarvam/bulbul:v4-flash/gokul_ta_narration"
KEY = "sk_test_never_printed"


def _wav(seconds: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"\x01\x00" * int(SAMPLE_RATE * seconds))
    return buf.getvalue()


class FakePost:
    def __init__(self, fail: int | None = None) -> None:
        self.calls: list[tuple[dict, dict]] = []
        self._fail = fail

    def __call__(self, url, headers, body, timeout):
        self.calls.append((headers, body))
        if self._fail is not None:
            raise urllib.error.HTTPError(url, self._fail, "no", {}, None)
        return json.dumps({"request_id": "r", "audios": [base64.b64encode(_wav()).decode()]}).encode()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(vendor_tts, "VENDOR_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(vendor_tts, "VENDOR_CALL_LOG_PATH", tmp_path / "vendor.log")
    monkeypatch.setenv("SARVAM_API_KEY", KEY)
    monkeypatch.delenv("SIB_VENDOR_CALL_BUDGET", raising=False)
    return tmp_path


def test_parse_voice_reads_model_and_speaker_and_refuses_a_gemini_name():
    assert vendor_tts.parse_voice(VOICE) == ("bulbul:v4-flash", "gokul_ta_narration")
    for voice in ("Kore", "sarvam/bulbul/gokul", "sarvam/bulbul:v4-flash/Gokul", None, ""):
        assert vendor_tts.parse_voice(voice) is None, voice


def test_a_call_sends_the_key_as_a_header_asks_for_16k_wav_and_logs_the_call_without_the_key(isolated):
    post = FakePost()
    wav = vendor_tts.VendorCalls(post=post).tts_wav("tts x", "வணக்கம்", "ta", VOICE)

    assert gemini_client.is_wav(wav)
    headers, body = post.calls[0]
    assert headers["api-subscription-key"] == KEY
    assert body == {"text": "வணக்கம்", "language_code": "ta-IN", "speaker": "gokul_ta_narration",
                    "model": "bulbul:v4-flash", "speech_sample_rate": 16000, "output_audio_codec": "wav"}
    log = (isolated / "vendor.log").read_text(encoding="utf-8")
    assert "sarvam\tbulbul:v4-flash" in log and "7 chars" in log and KEY not in log


def test_a_cached_clip_makes_no_call_and_fresh_makes_one(isolated):
    post = FakePost()
    calls = vendor_tts.VendorCalls(post=post)
    first = calls.tts_wav("tts x", "வணக்கம்", "ta", VOICE)
    assert calls.tts_wav("tts x", "வணக்கம்", "ta", VOICE) == first and len(post.calls) == 1
    calls.tts_wav("tts x", "வணக்கம்", "ta", VOICE, fresh=True)
    assert len(post.calls) == 2


def test_offline_never_calls_and_raises_the_build_s_offline_miss(isolated):
    post = FakePost()
    with pytest.raises(gemini_client.OfflineMiss):
        vendor_tts.VendorCalls(offline=True, post=post).tts_wav("tts x", "வணக்கம்", "ta", VOICE)
    assert post.calls == [] and not (isolated / "vendor.log").exists()


def test_no_key_refuses_before_any_call(isolated, monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY")
    post = FakePost()
    with pytest.raises(RuntimeError, match="SARVAM_API_KEY is not set"):
        vendor_tts.VendorCalls(post=post).tts_wav("tts x", "வணக்கம்", "ta", VOICE)
    assert post.calls == []


def test_the_budget_stops_the_build_before_the_call_that_would_pass_it(isolated, monkeypatch):
    monkeypatch.setenv("SIB_VENDOR_CALL_BUDGET", "1")
    post = FakePost()
    calls = vendor_tts.VendorCalls(post=post)
    calls.tts_wav("tts a", "ஒன்று", "ta", VOICE)
    with pytest.raises(vendor_tts.VendorBudgetExceeded):
        calls.tts_wav("tts b", "இரண்டு", "ta", VOICE)
    assert len(post.calls) == 1


def test_an_http_error_is_reported_by_status_only_and_a_busy_reply_is_retried_once(isolated, monkeypatch):
    monkeypatch.setattr(vendor_tts, "RETRY_WAIT_S", 0)
    post = FakePost(fail=503)
    with pytest.raises(RuntimeError, match="HTTP 503") as err:
        vendor_tts.VendorCalls(post=post).tts_wav("tts x", "வணக்கம்", "ta", VOICE)
    assert len(post.calls) == 2 and KEY not in str(err.value)


def test_a_language_sarvam_does_not_speak_is_refused():
    with pytest.raises(ValueError, match="does not speak zh"):
        vendor_tts.VendorCalls(post=FakePost()).tts_wav("tts x", "你好", "zh", VOICE)


def _entry(**over) -> dict:
    entry = {"taskId": "lifting-zone", "questionId": "q1", "workerLang": "ta", "pattern": "complete", "noise": "clean",
             "heldOut": False, "gloss": "I stay outside.", "gold": {"s1": "covered", "s2": "covered"}}
    return {**entry, **over}


def test_a_spec_voice_overrides_the_gemini_rotation_and_must_be_a_vendor_voice_for_a_language_it_speaks():
    tasks = {"lifting-zone": {}}
    rec = bt._resolve(_entry(voice=VOICE), tasks, {})
    assert bt.rec_voice(rec) == VOICE
    assert bt.rec_voice(bt._resolve(_entry(), tasks, {})) in bt.TTS_VOICES
    for bad in (_entry(voice="Kore"), _entry(voice=VOICE, workerLang="zh")):
        with pytest.raises(ValueError, match="voice must be sarvam"):
            bt._resolve(bad, tasks, {})


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg (render_item converts to 16 kHz)")
def test_render_item_routes_a_vendor_voice_to_the_vendor_and_records_it_in_the_manifest(isolated, monkeypatch):
    monkeypatch.setattr(bt, "AUDIO_DIR", isolated / "audio")
    monkeypatch.setattr(bt, "WORK_DIR", isolated / "work")
    (isolated / "audio").mkdir()
    rec = bt._resolve(_entry(voice=VOICE), {"lifting-zone": {}}, {})

    class NoGemini:
        def __getattr__(self, name):
            raise AssertionError(f"Gemini was called: {name}")

    entry = bt.render_item(NoGemini(), rec, "வணக்கம்", vendor=vendor_tts.VendorCalls(post=FakePost()))

    assert (entry["voice"], entry["model"], entry["render"], entry["backend"]) == (VOICE, "bulbul:v4-flash", "sarvam", "sarvam")
    with wave.open(str(isolated / "audio" / f"{rec['id']}.wav")) as w:
        assert (w.getframerate(), w.getnchannels()) == (SAMPLE_RATE, 1)
