"""Site noise for real recordings (16 Oct): four procedural profiles, mixed at an SNR measured over the speech.

Each profile is made here from a seeded stdlib generator (random.Random, whose random() sequence Python keeps stable
for a given seed), so it is licence-clean, needs no download and holds no one's voice, and a seed always gives the
same samples:
- site-drone: steady machinery hum and generator drone, an engine's low harmonics over broadband rumble;
- site-hammer: hammering and riveting, short decaying knocks with a metal ring, at random intervals;
- site-beeper: a reversing beeper, a square-ish tone near 1 kHz, about half a second on and half off;
- site-babble: distant crowd or radio babble, speech-band noise modulated at the pace of syllables and phrases.
Each profile returns float samples at 16 kHz with an RMS of 1. A faint broadband floor sits under the impulsive
ones, as on any site, so the noise is never exactly silent while someone speaks.

mix_over_speech sets the noise level against the frames that hold speech (speech_mask), so a recording's leading
and trailing room tone and its pauses do not dilute the speech level, then adds the noise through
audio_tools.mix_at_snr, which scales the mix down as a whole when a peak would pass PEAK_LIMIT (the SNR is kept and
nothing clips).
"""

from __future__ import annotations

import hashlib
import math
import random
from array import array
from collections.abc import Callable, Sequence

from audio_tools import mean_square, mix_at_snr
from config import SAMPLE_RATE

SNR_LEVELS = {"snr10": 10.0, "snr5": 5.0, "snr0": 0.0}  # speech power over noise power, over the speech frames
FRAME = SAMPLE_RATE // 50  # 20 ms
SPEECH_RANGE_DB = 30.0  # a frame is speech when it is within this of the loud frames
LOUD_PERCENTILE = 0.95  # "the loud frames": robust to one knock on the desk
FLOOR = 0.03  # the broadband floor under the impulsive profiles, as a share of their RMS (about -30 dB)
TWO_PI = 2 * math.pi


def seed_for(text: str) -> int:
    """A stable seed from an id (the SHA-256 of its text)."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _white(rng: random.Random, n: int) -> list[float]:
    return [2 * rng.random() - 1 for _ in range(n)]


def _lowpass(x: Sequence[float], hz: float) -> list[float]:
    """One-pole low-pass filter."""
    a = 1 - math.exp(-TWO_PI * hz / SAMPLE_RATE)
    y, out = 0.0, []
    for v in x:
        y += a * (v - y)
        out.append(y)
    return out


def _highpass(x: Sequence[float], hz: float) -> list[float]:
    return [v - low for v, low in zip(x, _lowpass(x, hz))]


def _unit(x: Sequence[float]) -> list[float]:
    rms = math.sqrt(mean_square(x)) if len(x) else 0.0
    return [v / rms for v in x] if rms else list(x)


def _with_floor(x: list[float], rng: random.Random) -> list[float]:
    floor = _unit(_lowpass(_white(rng, len(x)), 3000.0))
    return _unit([v + FLOOR * f for v, f in zip(_unit(x), floor)])


def drone(n: int, rng: random.Random) -> list[float]:
    """Steady machinery hum and generator drone: ten harmonics of a 45-75 Hz engine tone, slowly wavering, over
    low broadband rumble (white noise through two 250 Hz low-pass stages), about equal in power."""
    f0 = rng.uniform(45.0, 75.0)
    parts = [(TWO_PI * k * f0 / SAMPLE_RATE, 1.0 / k, rng.uniform(0, TWO_PI)) for k in range(1, 11)]
    wobble, wobble_phase = TWO_PI * rng.uniform(0.2, 0.6) / SAMPLE_RATE, rng.uniform(0, TWO_PI)
    hum = [(1 + 0.15 * math.sin(wobble * i + wobble_phase)) * sum(a * math.sin(w * i + p) for w, a, p in parts)
           for i in range(n)]
    rumble = _lowpass(_lowpass(_white(rng, n), 250.0), 250.0)
    return _unit([h + r for h, r in zip(_unit(hum), _unit(rumble))])


def hammer(n: int, rng: random.Random) -> list[float]:
    """Hammering and riveting: knocks 0.12-0.7 s apart (the short gaps are riveting bursts), each a burst of
    noise decaying in 4-15 ms and a 0.9-3.5 kHz metal ring decaying in 30-120 ms."""
    out = [0.0] * n
    start = int(rng.uniform(0.0, 0.1) * SAMPLE_RATE)
    while start < n:
        ring, knock_tau, ring_tau = rng.uniform(900, 3500), rng.uniform(0.004, 0.015), rng.uniform(0.03, 0.12)
        amp = rng.uniform(0.5, 1.0)
        for j in range(min(n - start, int(5 * ring_tau * SAMPLE_RATE))):
            t = j / SAMPLE_RATE
            out[start + j] += amp * ((2 * rng.random() - 1) * math.exp(-t / knock_tau)
                                     + 0.6 * math.sin(TWO_PI * ring * t) * math.exp(-t / ring_tau))
        start += int(rng.uniform(0.12, 0.7) * SAMPLE_RATE)
    return _with_floor(out, rng)


def beeper(n: int, rng: random.Random) -> list[float]:
    """A reversing beeper: a 950-1250 Hz tone with its third harmonic (a piezo is not a pure tone), on for half of
    a 0.9-1.1 s period, with 5 ms ramps so the gating does not click."""
    hz, period = rng.uniform(950.0, 1250.0), rng.uniform(0.9, 1.1)
    offset, on, ramp = rng.uniform(0, period), period / 2, 0.005
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        phase = (t + offset) % period
        gate = 0.0 if phase >= on else min(1.0, phase / ramp, (on - phase) / ramp)
        out.append(gate * (math.sin(TWO_PI * hz * t) + math.sin(3 * TWO_PI * hz * t) / 3))
    return _with_floor(out, rng)


def babble(n: int, rng: random.Random, talkers: int = 4) -> list[float]:
    """Distant crowd or radio babble: per talker, noise in the speech band (250 Hz to 2.2 kHz) gated by a 3-6 Hz
    syllable rhythm and a 0.2-0.6 Hz phrase rhythm; the talkers summed and dulled by distance (1.8 kHz low-pass)."""
    out = [0.0] * n
    for _ in range(talkers):
        voice = _lowpass(_lowpass(_highpass(_white(rng, n), 250.0), 2200.0), 2200.0)
        syllable, syllable_phase = TWO_PI * rng.uniform(3.0, 6.0) / SAMPLE_RATE, rng.uniform(0, TWO_PI)
        phrase, phrase_phase = TWO_PI * rng.uniform(0.2, 0.6) / SAMPLE_RATE, rng.uniform(0, TWO_PI)
        for i in range(n):
            envelope = max(0.0, math.sin(syllable * i + syllable_phase)) * (0.55 + 0.45 * math.sin(phrase * i + phrase_phase))
            out[i] += envelope * voice[i]
    return _unit(_lowpass(out, 1800.0))


PROFILES: dict[str, Callable[[int, random.Random], list[float]]] = {
    "site-drone": drone, "site-hammer": hammer, "site-beeper": beeper, "site-babble": babble,
}
NOISE_NAMES = tuple(f"{profile}.{snr}" for profile in PROFILES for snr in SNR_LEVELS)  # an item's `noise`


def make(profile: str, n: int, seed: int) -> list[float]:
    """n samples of a profile; the same seed always gives the same samples."""
    return PROFILES[profile](n, random.Random(seed))


def speech_mask(samples: Sequence[int]) -> list[bool]:
    """Per sample, whether its 20 ms frame holds speech: within SPEECH_RANGE_DB of the loud frames (the 95th
    percentile frame power), so room tone and pauses are left out of the speech level."""
    powers = [mean_square(samples[i:i + FRAME]) for i in range(0, len(samples), FRAME)]
    if not powers or max(powers) == 0.0:
        raise ValueError("the recording is silent")
    loud = sorted(powers)[int(LOUD_PERCENTILE * (len(powers) - 1))] or max(powers)
    floor = loud * 10 ** (-SPEECH_RANGE_DB / 10)
    mask: list[bool] = []
    for n, power in enumerate(powers):
        mask.extend([power >= floor] * min(FRAME, len(samples) - n * FRAME))
    return mask


def mix_over_speech(speech: array, noise: Sequence[float], snr_db: float) -> array:
    """speech + noise at snr_db measured over the speech frames, as 16-bit samples that never clip."""
    return mix_at_snr(speech, noise, snr_db, active=speech_mask(speech))
