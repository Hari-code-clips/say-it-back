"""Mixing, level and format checks for the synthetic clips."""

import array
import io
import math
import wave

import pytest

from audio_tools import PEAK_LIMIT, mean_square, mix_at_snr, pcm_to_wav, scale_to_dbfs
from config import AUDIO_DIR, SAMPLE_RATE


def tone(n: int, amplitude: float) -> array.array:
    return array.array("h", (round(amplitude * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)) for i in range(n)))


def noise(n: int, amplitude: float) -> array.array:
    """Deterministic pseudo-noise (a linear congruential generator), so the test is repeatable."""
    state = 12345
    values = array.array("h")
    for _ in range(n):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        values.append(round((state / 0x7FFFFFFF * 2 - 1) * amplitude))
    return values


def measured_snr_db(clean: array.array, mixed: array.array) -> float:
    residual = array.array("h", (m - c for m, c in zip(mixed, clean)))
    return 10 * math.log10(mean_square(clean) / mean_square(residual))


def test_mix_hits_the_requested_snr_over_the_clip():
    speech = tone(SAMPLE_RATE, 6000)
    bed = noise(SAMPLE_RATE, 8000)

    mixed = mix_at_snr(speech, bed, snr_db=5.0)

    assert measured_snr_db(speech, mixed) == pytest.approx(5.0, abs=0.1)


def test_mix_keeps_peaks_under_the_limit_and_the_clip_length():
    speech = tone(SAMPLE_RATE, 30000)
    bed = noise(SAMPLE_RATE, 30000)

    mixed = mix_at_snr(speech, bed, snr_db=5.0)

    assert len(mixed) == len(speech)
    assert max(abs(x) for x in mixed) <= PEAK_LIMIT


def test_scale_to_dbfs_sets_the_rms_level():
    quiet = scale_to_dbfs(noise(SAMPLE_RATE, 1000), -50.0)

    level_dbfs = 10 * math.log10(mean_square(quiet) / 32768 ** 2)

    assert level_dbfs == pytest.approx(-50.0, abs=0.2)


def test_pcm_to_wav_wraps_raw_pcm_at_the_rate_in_the_mime_type():
    raw = tone(100, 1000).tobytes()

    wav_bytes = pcm_to_wav(raw, "audio/L16;codec=pcm;rate=24000")

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) == (24000, 1, 2, 100)


def test_pcm_to_wav_leaves_an_existing_wav_unchanged():
    wav_bytes = pcm_to_wav(tone(100, 1000).tobytes(), "audio/L16;codec=pcm;rate=16000")

    assert pcm_to_wav(wav_bytes, "audio/wav") == wav_bytes


def test_every_built_clip_is_16khz_mono_16bit():
    clips = sorted(AUDIO_DIR.glob("*.wav"))
    if not clips:
        pytest.skip("audio not built yet; run build_testset.py")

    for path in clips:
        with wave.open(str(path), "rb") as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2), path.name
