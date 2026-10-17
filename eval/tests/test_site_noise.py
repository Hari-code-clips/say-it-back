"""site_noise.py: four procedural site-noise profiles, deterministic per seed, mixed at an SNR measured over the speech.

The SNR is measured here independently of the module: against the test signal's own ground truth of where the speech
is (bursts aligned to 20 ms frames, with faint room tone between them), and with the speech's share of the mix found
by least squares, so a mix that measured over the whole clip, or clipped, or wrapped, would miss by more than 0.5 dB.
"""

import array
import math

import pytest

import site_noise as sn
from audio_tools import PEAK_LIMIT, mean_square
from config import SAMPLE_RATE


def speech_like(amplitude: int = 6000, bursts=(0.6, 0.8, 0.5), gap: float = 0.3,
                lead: float = 0.4) -> tuple[array.array, list[bool]]:
    """Voiced bursts (three partials at 233, 711 and 1187 Hz under a 4.3 Hz syllable envelope), with room tone about
    60 dB down between them, aligned to frames. Returns the samples and the ground truth of where speech is."""
    samples: list[int] = []
    truth: list[bool] = []
    state = 12345

    def room(seconds: float) -> None:
        nonlocal state
        for _ in range(round(seconds * SAMPLE_RATE / sn.FRAME) * sn.FRAME):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            samples.append(round((state / 0x7FFFFFFF * 2 - 1) * 5))
            truth.append(False)

    room(lead)
    for seconds in bursts:
        for i in range(round(seconds * SAMPLE_RATE / sn.FRAME) * sn.FRAME):
            t = i / SAMPLE_RATE
            voiced = (math.sin(2 * math.pi * 233 * t) + 0.5 * math.sin(2 * math.pi * 711 * t + 1)
                      + 0.25 * math.sin(2 * math.pi * 1187 * t + 2))
            samples.append(round(amplitude * (0.6 + 0.4 * math.sin(2 * math.pi * 4.3 * t)) * voiced / 1.75))
            truth.append(True)
        room(gap)
    return array.array("h", samples), truth


def snr_over(speech: array.array, mixed: array.array, truth: list[bool]) -> float:
    """The mix's SNR over the true speech samples: the speech's share by least squares, the rest is noise."""
    alpha = sum(m * s for m, s in zip(mixed, speech)) / sum(s * s for s in speech)
    voiced = [alpha * s for s, on in zip(speech, truth) if on]
    rest = [m - alpha * s for m, s, on in zip(mixed, speech, truth) if on]
    return 10 * math.log10(mean_square(voiced) / mean_square(rest))


SPEECH, TRUTH = speech_like()


@pytest.mark.parametrize("noise_name", sn.NOISE_NAMES)
def test_each_profile_at_each_snr_lands_within_half_a_db_measured_over_the_speech(noise_name):
    profile, snr = noise_name.split(".")
    noise = sn.make(profile, len(SPEECH), seed=7)

    mixed = sn.mix_over_speech(SPEECH, noise, sn.SNR_LEVELS[snr])

    assert len(mixed) == len(SPEECH) and max(abs(x) for x in mixed) <= PEAK_LIMIT
    assert snr_over(SPEECH, mixed, TRUTH) == pytest.approx(sn.SNR_LEVELS[snr], abs=0.5)


def test_the_speech_mask_finds_the_speech_and_leaves_out_room_tone_and_pauses():
    assert sn.speech_mask(SPEECH) == TRUTH
    assert sum(TRUTH) < 0.7 * len(TRUTH)  # the pauses are a real share: measured over the clip, the SNR would differ


def test_a_loud_recording_at_0_db_under_hammering_never_clips_and_keeps_its_snr():
    loud, truth = speech_like(amplitude=32000)

    mixed = sn.mix_over_speech(loud, sn.make("site-hammer", len(loud), seed=11), 0.0)

    assert max(abs(x) for x in mixed) <= PEAK_LIMIT
    assert snr_over(loud, mixed, truth) == pytest.approx(0.0, abs=0.5)


@pytest.mark.parametrize("profile", sn.PROFILES)
def test_a_profile_is_the_same_for_a_seed_differs_between_seeds_and_has_unit_rms(profile):
    first = sn.make(profile, SAMPLE_RATE, seed=3)

    assert first == sn.make(profile, SAMPLE_RATE, seed=3)
    assert first != sn.make(profile, SAMPLE_RATE, seed=4)
    assert math.sqrt(mean_square(first)) == pytest.approx(1.0, abs=1e-9)


def _frame_powers(x: list[float]) -> list[float]:
    return [mean_square(x[i:i + sn.FRAME]) for i in range(0, len(x), sn.FRAME)]


def test_each_profile_sounds_like_its_name():
    n = 3 * SAMPLE_RATE
    drone, hammer, beeper, babble = (sn.make(p, n, seed=5) for p in
                                     ("site-drone", "site-hammer", "site-beeper", "site-babble"))
    kurtosis = {name: sum(v ** 4 for v in x) / len(x) for name, x in
                (("drone", drone), ("hammer", hammer), ("beeper", beeper), ("babble", babble))}  # unit RMS

    low_share = mean_square(sn._lowpass(sn._lowpass(drone, 400.0), 400.0))
    beeper_frames = _frame_powers(beeper)
    gated = sum(p < 0.01 * max(beeper_frames) for p in beeper_frames) / len(beeper_frames)
    babble_frames = _frame_powers(babble)
    hammer_frames = _frame_powers(hammer)
    loud = [p > 0.1 * max(hammer_frames) for p in hammer_frames]
    knocks = sum(now and not before for before, now in zip([False, *loud], loud))

    assert low_share > 0.5  # a drone: most of its power is low
    assert kurtosis["hammer"] > 10 and kurtosis["hammer"] > 2 * max(kurtosis["drone"], kurtosis["babble"])  # knocks
    assert knocks >= 4  # at intervals of 0.12-0.7 s, a 3 s clip holds several knocks, not one
    assert 0.35 < gated < 0.65  # a beeper: about half on, half off
    assert max(babble_frames) > 4 * min(babble_frames)  # babble: modulated, not steady
    assert len(sn.NOISE_NAMES) == 12 and "site-hammer.snr5" in sn.NOISE_NAMES
    assert sn.SNR_LEVELS == {"snr10": 10.0, "snr5": 5.0, "snr0": 0.0}  # the levels the deck quotes


def test_the_seed_comes_from_the_id_and_is_stable():
    assert sn.seed_for("a.rec.V01.site-hammer") == sn.seed_for("a.rec.V01.site-hammer")
    assert sn.seed_for("a.rec.V01.site-hammer") != sn.seed_for("a.rec.V02.site-hammer")
    assert sn.seed_for("x") == int("2d711642", 16)  # SHA-256 of "x", first 8 hex digits: fixed across machines
