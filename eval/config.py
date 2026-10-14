"""Constants for the Say It Back eval harness. Model ids are overridable by env (SIB_*)."""

import os
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
TESTSET_DIR = EVAL_DIR / "testset"
AUDIO_DIR = TESTSET_DIR / "audio"
SPEC_PATH = TESTSET_DIR / "spec.json"
ITEMS_PATH = TESTSET_DIR / "items.json"
SPOTCHECK_PATH = TESTSET_DIR / "spotcheck.json"
CATALOG_PATH = EVAL_DIR.parent / "backend" / "sayitback" / "data" / "catalog.json"
CACHE_DIR = EVAL_DIR / ".cache" / "gemini"
WORK_DIR = EVAL_DIR / ".cache" / "work"
CALL_LOG_PATH = EVAL_DIR / "gemini_calls.log"
REPORTS_DIR = EVAL_DIR / "reports"

FLASH_MODEL = os.environ.get("SIB_FLASH_MODEL", "gemini-3.8-flash")
TTS_MODEL = os.environ.get("SIB_TTS_MODEL", "gemini-3.8-flash-tts")
TTS_VOICES = ("Kore", "Charon", "Puck", "Aoede", "Leda", "Orus")
TTS_STYLE = "calm, natural conversational pace"

GEMINI_CALL_BUDGET = 70  # whole project: generation and spot checks, counted in CALL_LOG_PATH
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
WORKER_LANGS = ("ta", "bn", "zh", "my", "hi", "or")
VERDICTS = ("covered", "missed", "contradicted", "unclear")
# Gold is unclear only on every step of a silence or wrong_language item, where the right response is to abstain (API.md).
GOLD_LABELS = VERDICTS
ABSTAIN_PATTERNS = ("silence", "wrong_language")
SOURCES = ("synthetic_tts", "recorded")

PASS_EXACT_MIN = 0.80
PASS_UNSAFE_MAX = 0
