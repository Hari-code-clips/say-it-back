"""WAV parsing at the boundary, clip statistics and WAV writing."""

from __future__ import annotations

import struct

import pytest

from sayitback.wav import MAX_RATE, WavError, clip_stats, make_wav, parse_wav
from tests.fakes import silent_wav, tone_wav


def test_a_wav_we_wrote_parses_back():
    info = parse_wav(make_wav(b"\x01\x00" * 16000, 16000))
    assert (info.sample_rate, info.channels, info.frames) == (16000, 1, 16000)
    assert info.duration_s == pytest.approx(1.0)


def test_stereo_and_other_rates_are_read():
    info = parse_wav(make_wav(b"\x01\x00\x02\x00" * 24000, 24000, channels=2))
    assert (info.channels, info.frames, info.sample_rate) == (2, 24000, 24000)


def test_a_streamed_header_with_unknown_size_reads_to_the_end():
    good = bytearray(make_wav(b"\x01\x00" * 8000, 16000))
    struct.pack_into("<I", good, 40, 0xFFFFFFFF)  # data size unknown
    struct.pack_into("<I", good, 4, 0xFFFFFFFF)
    assert parse_wav(bytes(good)).frames == 8000


def test_a_data_size_larger_than_the_file_is_clamped():
    good = bytearray(make_wav(b"\x01\x00" * 100, 16000))
    struct.pack_into("<I", good, 40, 10_000_000)
    assert parse_wav(bytes(good)).frames == 100


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"RIFF" + b"\x00" * 40,
        b"not a wav file at all, just text" * 5,
        b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 40,
    ],
)
def test_garbage_is_rejected(data):
    with pytest.raises(WavError):
        parse_wav(data)


def test_non_pcm_and_non_16_bit_are_rejected():
    for tag, bits in ((3, 16), (1, 8), (1, 24)):
        bad = bytearray(make_wav(b"\x00\x00" * 100, 16000))
        struct.pack_into("<H", bad, 20, tag)
        struct.pack_into("<H", bad, 34, bits)
        with pytest.raises(WavError, match="16-bit PCM"):
            parse_wav(bytes(bad))


def test_unsupported_rates_and_channels_are_rejected():
    for rate in (4000, MAX_RATE + 1):
        with pytest.raises(WavError, match="Sample rate"):
            parse_wav(make_wav(b"\x00\x00" * 100, rate))
    with pytest.raises(WavError, match="mono or stereo"):
        parse_wav(make_wav(b"\x00\x00" * 120, 16000, channels=6))


def test_a_header_without_audio_is_rejected():
    with pytest.raises(WavError, match="no audio"):
        parse_wav(make_wav(b"", 16000))


def test_clip_stats_tell_speech_from_silence():
    tone, silence = clip_stats(tone_wav(1.5, amp=4000)), clip_stats(silent_wav(1.5))
    assert tone.duration_s == pytest.approx(1.5)
    assert tone.peak_rms == pytest.approx(4000 / 2**0.5, rel=0.05)
    assert silence.peak_rms == 0.0


def test_peak_rms_finds_a_short_burst_in_a_quiet_clip():
    quiet = b"\x00\x00" * 16000
    burst = b"".join(struct.pack("<h", 6000 if i % 2 else -6000) for i in range(1600))
    stats = clip_stats(make_wav(quiet + burst + quiet, 16000))
    assert stats.peak_rms > 5000
