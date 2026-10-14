"""WAV parsing at the trust boundary, clip statistics for the guards, and WAV writing for TTS.

The parser is tolerant of streamed headers (a data size of 0 or 0xFFFFFFFF means "to the end")
and strict about the format: 16-bit PCM, 1 or 2 channels, 8 to 48 kHz.
"""

from __future__ import annotations

import math
import struct
import sys
from array import array
from dataclasses import dataclass

PCM_TAG = 1
EXTENSIBLE_TAG = 0xFFFE
MIN_RATE = 8000
MAX_RATE = 48000
STREAMING_SIZES = (0, 0xFFFFFFFF)
RMS_WINDOW_S = 0.1


class WavError(ValueError):
    """The bytes are not a WAV file this service accepts."""


@dataclass(frozen=True)
class WavInfo:
    sample_rate: int
    channels: int
    frames: int
    data_offset: int
    data_length: int

    @property
    def duration_s(self) -> float:
        return self.frames / self.sample_rate


@dataclass(frozen=True)
class ClipStats:
    duration_s: float
    peak_rms: float


def parse_wav(data: bytes) -> WavInfo:
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise WavError("Not a RIFF/WAVE file.")
    fmt: tuple[int, int, int, int] | None = None
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        body = pos + 8
        if chunk_id == b"fmt ":
            fmt = _read_fmt(data, body, size)
        elif chunk_id == b"data":
            if fmt is None:
                raise WavError("The data chunk comes before the fmt chunk.")
            return _build_info(fmt, body, size, len(data))
        pos = body + size + (size & 1)
    raise WavError("No data chunk.")


def _read_fmt(data: bytes, body: int, size: int) -> tuple[int, int, int, int]:
    if size < 16 or body + 16 > len(data):
        raise WavError("The fmt chunk is truncated.")
    tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", data, body)
    if tag == EXTENSIBLE_TAG and size >= 26 and body + 26 <= len(data):
        (tag,) = struct.unpack_from("<H", data, body + 24)
    if tag != PCM_TAG or bits != 16:
        raise WavError("Only 16-bit PCM WAV is accepted.")
    if channels not in (1, 2):
        raise WavError("Only mono or stereo WAV is accepted.")
    if not MIN_RATE <= rate <= MAX_RATE:
        raise WavError(f"Sample rate must be between {MIN_RATE} and {MAX_RATE} Hz.")
    return tag, channels, rate, bits


def _build_info(fmt: tuple[int, int, int, int], body: int, size: int, total: int) -> WavInfo:
    _, channels, rate, bits = fmt
    available = total - body
    length = available if size in STREAMING_SIZES or size > available else size
    frame_bytes = channels * bits // 8
    frames = length // frame_bytes
    if frames == 0:
        raise WavError("The WAV file holds no audio.")
    return WavInfo(rate, channels, frames, body, frames * frame_bytes)


def _first_channel(data: bytes, info: WavInfo) -> array:
    samples = array("h")
    samples.frombytes(data[info.data_offset : info.data_offset + info.data_length])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples[:: info.channels] if info.channels > 1 else samples


def clip_stats(data: bytes, info: WavInfo | None = None) -> ClipStats:
    """Duration and the RMS of the loudest 100 ms window (int16 units), for guard rule 5."""
    info = info or parse_wav(data)
    samples = _first_channel(data, info)
    window = max(1, int(info.sample_rate * RMS_WINDOW_S))
    peak = 0.0
    for start in range(0, len(samples), window):
        chunk = samples[start : start + window]
        peak = max(peak, math.sqrt(math.sumprod(chunk, chunk) / len(chunk)))
    return ClipStats(duration_s=info.duration_s, peak_rms=peak)


def make_wav(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    """Wrap raw 16-bit little-endian PCM in a 44-byte WAV header."""
    byte_rate = sample_rate * channels * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        PCM_TAG,
        channels,
        sample_rate,
        byte_rate,
        channels * 2,
        16,
        b"data",
        len(pcm),
    )
    return header + pcm
