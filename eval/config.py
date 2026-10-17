"""Constants for the Say It Back eval harness. Model ids are overridable by env (SIB_*)."""

import os
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
TESTSET_DIR = EVAL_DIR / "testset"
AUDIO_DIR = TESTSET_DIR / "audio"
SPEC_PATH = TESTSET_DIR / "spec.json"
ITEMS_PATH = TESTSET_DIR / "items.json"
CLIPS_PATH = AUDIO_DIR / "clips.json"  # what each clip says: written when a clip is rendered
SPOTCHECK_PATH = TESTSET_DIR / "spotcheck.json"
CATALOG_PATH = EVAL_DIR.parent / "backend" / "sayitback" / "data" / "catalog.json"
CACHE_DIR = EVAL_DIR / ".cache" / "gemini"
WORK_DIR = EVAL_DIR / ".cache" / "work"
CALL_LOG_PATH = EVAL_DIR / "gemini_calls.log"
REPORTS_DIR = EVAL_DIR / "reports"

FLASH_MODEL = os.environ.get("SIB_FLASH_MODEL", "gemini-3.8-flash")
TTS_MODEL = os.environ.get("SIB_TTS_MODEL", "gemini-3.8-flash-tts")
TTS_VOICES = ("Kore", "Charon", "Puck", "Aoede", "Leda", "Orus")
# No style prefix (15 Oct 2026): on Agent Platform the TTS model sometimes read "Say this in a calm natural
# conversational pace" aloud as part of the clip. The text alone is what the app's turn mode sends too.
TTS_STYLE = ""


def _call_budget() -> int:
    raw = os.environ.get("SIB_EVAL_CALL_BUDGET", "").strip() or "70"
    if not raw.isdigit() or int(raw) < 1:
        raise ValueError("SIB_EVAL_CALL_BUDGET must be a positive whole number")
    return int(raw)


# Whole project: generation and spot checks, counted in CALL_LOG_PATH. 70 unless SIB_EVAL_CALL_BUDGET
# raises it for a paid run (RUN_PAID.md). run_eval.py's check calls go through the backend and are not counted.
GEMINI_CALL_BUDGET = _call_budget()
BACK_BATCH = 20  # rows per back-translation call
RETRY_429_WAIT_S = 30.0
HTTP_TIMEOUT_MS = 180_000  # the SDK has no timeout by default; a stalled connection would hang the build

SAMPLE_RATE = 16000
SNR_DB = {"snr10": 10.0, "snr5": 5.0}  # measured over the whole clip
SILENCE_DBFS = -50.0
SILENCE_SECONDS = 4.0
SPEECH_LOUDNESS_FILTER = "loudnorm=I=-20:TP=-2:LRA=11"

PATTERNS = (
    "complete", "one_missing", "two_missing", "contradicted", "vague", "echo", "fluent_wrong",
    "negation", "numbers", "code_switch", "wrong_language", "silence", "demo",
)
NOISES = ("clean", "snr10", "snr5")
# te since 17 Oct: the telecom-tower demo suite's items (build-notes/37-domain-suites.md)
WORKER_LANGS = ("ta", "bn", "zh", "my", "hi", "or", "te")
VERDICTS = ("covered", "missed", "contradicted", "unclear")
# Gold is unclear only on every step of a silence or wrong_language item, where the right response is to abstain (API.md).
GOLD_LABELS = VERDICTS
ABSTAIN_PATTERNS = ("silence", "wrong_language")
SOURCES = ("synthetic_tts", "recorded")
# An item lists here the fields that are not final yet: its worker-language text (a translation not made),
# its back-translation, or its clip (missing, or holding other words than the item's answer). [] = ready.
PENDING_FIELDS = ("answer", "backTranslation", "audio")
# v0.5: catalog tasks held out of everything the model is shown. They have no demo script, and no prompt example uses
# their words (backend tests/test_prompt_leak.py), so the eval items on them (heldOut: true) test judgement, not recall.
HELD_OUT_TASKS = ("confined-space", "fragile-roof")

PASS_EXACT_MIN = 0.80
PASS_UNSAFE_MAX = 0
PASS_CORRECT_MIN = 0.75  # v0.5: correctPassRate, so a checker that never says "covered" cannot meet the bar
