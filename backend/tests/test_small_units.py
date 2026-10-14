"""TTS, rate limiter, delivery check, eval set and transcript bookkeeping."""

from __future__ import annotations

import json

import pytest

from sayitback import catalog
from sayitback.delivery import delivery_checks, segment_texts, similarity
from sayitback.errors import NotFound, RateLimited, UpstreamError
from sayitback.evalset import EvalData, agreement, is_unsafe, public_item
from sayitback.live_transcripts import LiveTranscripts
from sayitback.models import Question, Script
from sayitback.ratelimit import RateLimiter
from sayitback.tts import Tts, cache_key, pcm_to_wav
from sayitback.wav import parse_wav
from tests.fakes import FakeTtsClient, fake_runtime

# TTS -----------------------------------------------------------------------------------------


async def test_tts_returns_a_24_khz_mono_wav_from_the_models_pcm(settings):
    client = FakeTtsClient(pcm=b"\x01\x00" * 4800)
    rt, _ = fake_runtime(settings=settings, tts_client=client)
    wav = await Tts(rt).speak("வணக்கம்")
    info = parse_wav(wav)
    assert (info.sample_rate, info.channels, info.frames) == (24000, 1, 4800)
    call = client.calls[0]
    assert call["model"] == "gemini-3.8-flash-tts" and call["text"] == "வணக்கம்"
    assert list(call["config"].response_modalities) == ["AUDIO"]
    assert call["config"].speech_config.voice_config.prebuilt_voice_config.voice_name == "Kore"


async def test_tts_is_cached_by_model_voice_and_text(settings):
    client = FakeTtsClient()
    rt, _ = fake_runtime(settings=settings, tts_client=client)
    tts = Tts(rt)
    first, again = await tts.speak("same text"), await tts.speak("same text")
    await tts.speak("other text")
    assert first == again and len(client.calls) == 2
    assert cache_key("m", "v", "t") != cache_key("m", "v2", "t") != cache_key("m2", "v", "t")


async def test_tts_cache_evicts_the_oldest_when_full(settings):
    client = FakeTtsClient(pcm=b"\x01\x00" * 4000)
    rt, _ = fake_runtime(
        settings=settings.with_overrides(tts_cache_max_bytes=17000), tts_client=client
    )
    tts = Tts(rt)
    for text in ("a", "b", "c"):
        await tts.speak(text)
    await tts.speak("a")  # evicted by now: a fresh call
    assert len(client.calls) == 4


async def test_tts_without_audio_is_a_502(settings):
    client = FakeTtsClient()

    async def silent(**kwargs):
        from google.genai import types

        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(role="model", parts=[types.Part(text="no audio")])
                )
            ]
        )

    client.generate_content = silent
    rt, _ = fake_runtime(settings=settings, tts_client=client)
    with pytest.raises(UpstreamError):
        await Tts(rt).speak("x")


def test_a_ready_made_wav_passes_through_and_the_rate_is_read_from_the_mime_type():
    from sayitback.wav import make_wav

    ready = make_wav(b"\x00\x00" * 10, 24000)
    assert pcm_to_wav(ready, "audio/wav") == ready
    assert (
        parse_wav(pcm_to_wav(b"\x00\x00" * 100, "audio/L16;codec=pcm;rate=16000")).sample_rate
        == 16000
    )
    assert parse_wav(pcm_to_wav(b"\x00\x00" * 100, None)).sample_rate == 24000


# Rate limiter --------------------------------------------------------------------------------


def test_the_rate_limit_is_per_key_and_per_minute():
    now = [0.0]
    limiter = RateLimiter(3, clock=lambda: now[0])
    for _ in range(3):
        limiter.check("1.2.3.4")
    with pytest.raises(RateLimited) as err:
        limiter.check("1.2.3.4")
    assert err.value.status == 429 and err.value.retry_after == 60
    limiter.check("5.6.7.8")  # another client is unaffected
    now[0] = 61.0
    limiter.check("1.2.3.4")  # the window slid


# Delivery check ------------------------------------------------------------------------------

SCRIPT = Script(
    instruction="பிரேக்கரை ஆஃப் செய்யுங்கள்.\nலாக் போடுங்கள்.",
    questions=[Question(id="q1", text="பேனலைத் திறப்பதற்கு முன் என்ன செய்வீர்கள்?")],
    closing="நன்றி.",
)
TA = catalog.unicode_ranges("ta")


def test_a_faithful_read_out_scores_high_and_is_in_the_worker_script():
    delivered = {
        "instruction": "பிரேக்கரை ஆஃப் செய்யுங்கள் லாக் போடுங்கள்",
        "q1": SCRIPT.questions[0].text,
        "closing": "நன்றி",
    }
    checks = {c.segment: c for c in delivery_checks(SCRIPT, delivered, TA, min_script_share=0.7)}
    assert set(checks) == {"instruction", "q1", "closing"}
    assert checks["instruction"].similarity > 0.95 and checks["instruction"].script_ok
    assert checks["q1"].similarity == 1.0


def test_a_paraphrase_scores_lower_and_a_missing_segment_scores_zero():
    delivered = {"instruction": "பிரேக்கரை நிறுத்துங்கள் அவ்வளவுதான்"}
    checks = {c.segment: c for c in delivery_checks(SCRIPT, delivered, TA, min_script_share=0.7)}
    assert 0 < checks["instruction"].similarity < 0.8
    assert checks["q1"].similarity == 0.0 and checks["q1"].script_ok is False


def test_drifting_to_another_language_fails_the_script_check_even_if_it_is_fluent():
    delivered = {"instruction": "मैं पहले ब्रेकर बंद करूंगा", "q1": "Switch the breaker off first"}
    checks = {c.segment: c for c in delivery_checks(SCRIPT, delivered, TA, min_script_share=0.7)}
    assert not checks["instruction"].script_ok and not checks["q1"].script_ok


def test_segment_texts_and_similarity_basics():
    assert list(segment_texts(SCRIPT)) == ["instruction", "q1", "closing"]
    assert similarity("Hello, World!", "hello world") == 1.0
    assert similarity("", "x") == 0.0


# Live transcripts (segments and de-duplicated captions) --------------------------------------


def test_segments_follow_the_latest_cue_and_answer_windows():
    tx = LiveTranscripts()
    tx.start_cue("instruction")
    assert tx.model_partial("Hel") == "Hel" and tx.model_partial("lo") == "Hello"
    assert tx.model_final("Hello there") == "Hello there"
    tx.start_cue("q1")
    tx.model_final("Question one?")
    tx.open_window("q1")
    assert tx.segment == "q1.reply"
    tx.worker_final("my answer")
    tx.close_window("q1")
    tx.model_final("Thanks")
    tx.start_cue("closing")
    tx.model_final("Bye")
    assert tx.delivered == {
        "instruction": "Hello there",
        "q1": "Question one?",
        "q1.reply": "Thanks",
        "closing": "Bye",
    }
    assert tx.heard == {"q1": "my answer"}


def test_a_final_with_no_text_falls_back_to_the_interim_and_resets_it():
    tx = LiveTranscripts()
    tx.start_cue("instruction")
    tx.model_partial("partial only")
    assert tx.model_final("") == "partial only"
    assert tx.model_partial("next") == "next"


def test_several_utterances_in_one_segment_are_joined_and_unattributed_heard_is_dropped():
    tx = LiveTranscripts()
    tx.worker_final("nobody asked yet")
    tx.start_cue("q1")
    tx.model_final("one")
    tx.model_final("two")
    assert tx.delivered["q1"] == "one two" and tx.heard == {}


# Eval set ------------------------------------------------------------------------------------


@pytest.fixture
def eval_dir(tmp_path):
    from tests.fakes import tone_wav

    testset = tmp_path / "eval" / "testset"
    (testset / "audio").mkdir(parents=True)
    (testset / "audio" / "a.wav").write_bytes(tone_wav())
    items = {
        "version": "t",
        "questions": {"panel-isolation": {"q1": {"ta": "பேனலைத் திறப்பதற்கு முன் என்ன செய்வீர்கள்?"}}},
        "items": [{
            "id": "panel-isolation.q1.ta.one_missing.clean", "taskId": "panel-isolation", "questionId": "q1",
            "workerLang": "ta", "pattern": "one_missing", "noise": "clean", "source": "synthetic_tts",
            "answer": "secret answer", "answerGloss": "gloss", "gold": {"s1": "covered", "s2": "missed", "s3": "covered"},
            "audio": "audio/a.wav",
        }, {"id": "evil", "taskId": "panel-isolation", "questionId": "q1", "workerLang": "ta", "audio": "../../outside.wav"}],
    }  # fmt: skip
    (testset / "items.json").write_text(json.dumps(items), encoding="utf-8")
    (tmp_path / "outside.wav").write_bytes(b"x")
    (tmp_path / "eval" / "reports").mkdir()
    (tmp_path / "eval" / "reports" / "latest.json").write_text('{"nItems": 1}')
    return tmp_path / "eval"


def test_the_public_item_hides_the_answer_and_the_audio_path(eval_dir):
    item = EvalData(eval_dir).item("panel-isolation.q1.ta.one_missing.clean")
    pub = public_item(item)
    assert set(pub) == {
        "id",
        "taskId",
        "questionId",
        "workerLang",
        "pattern",
        "noise",
        "source",
        "answerGloss",
        "gold",
    }


def test_an_items_audio_cannot_escape_the_testset_folder(eval_dir):
    data = EvalData(eval_dir)
    assert data.audio_path(data.item("panel-isolation.q1.ta.one_missing.clean")).name == "a.wav"
    with pytest.raises(NotFound):
        data.audio_path(data.item("evil"))


def test_missing_eval_data_is_404_with_the_documented_codes(tmp_path):
    data = EvalData(tmp_path / "nothing")
    with pytest.raises(NotFound) as err:
        data.latest_report()
    assert err.value.code == "no_report"
    with pytest.raises(NotFound) as err:
        data.items_file()
    assert err.value.code == "no_testset"


def test_check_inputs_use_reference_steps_in_scope_and_the_worker_language_question(eval_dir):
    steps, questions = EvalData(eval_dir).check_inputs(
        EvalData(eval_dir).item("panel-isolation.q1.ta.one_missing.clean")
    )
    assert [s.id for s in steps] == ["s1", "s2", "s3"]
    assert (
        questions[0].text.startswith("பேனலை")
        and questions[0].back_translation == "What will you do before you open the panel?"
    )


def test_agreement_and_the_unsafe_flag():
    gold = {"s1": "covered", "s2": "missed", "s3": "contradicted"}
    assert agreement(gold, {"s1": "covered", "s2": "unclear", "s3": "contradicted"}) == {
        "s1": True,
        "s2": False,
        "s3": True,
    }
    assert is_unsafe(gold, {"s1": "covered", "s2": "covered", "s3": "missed"}) is True
    assert is_unsafe(gold, {"s1": "unclear", "s2": "unclear", "s3": "missed"}) is False
