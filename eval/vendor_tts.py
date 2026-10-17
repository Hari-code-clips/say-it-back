"""A second TTS vendor for the testset build (16 Oct 2026): Sarvam's Bulbul, for Indian worker languages.

Why: every other clip is Gemini TTS, judged by Gemini ("the same model family speaks and judges", reports/latest.md).
A clip voiced by another vendor is a small step away from that bias, and it needs no Google Cloud account.

A vendor voice is written `sarvam/<model>/<speaker>` in an item's spec.json `voice`, for example
`sarvam/bulbul:v4-flash/gokul_ta_narration`; build_testset.py keeps it and routes the clip here. Like
gemini_client.py: a cache hit makes no call, every real call is appended to VENDOR_CALL_LOG_PATH before it is made,
the whole project is capped at VENDOR_CALL_BUDGET calls (SIB_VENDOR_CALL_BUDGET), and an offline run never calls.
The key is read from SARVAM_API_KEY and is never printed, logged or cached.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable

from config import EVAL_DIR, SAMPLE_RATE

SARVAM_URL = "https://api.sarvam.ai/text-to-speech"
VOICE_PATTERN = re.compile(r"^sarvam/(bulbul:v[0-9][0-9a-z.-]*)/([a-z0-9_]+)$")
# Sarvam's codes for the worker languages it speaks. zh and my are not among them, so they stay on Gemini.
# te since 17 Oct (bulbul:v4-flash lists te-IN voices: kavitha, pooja, tarun; build-notes/37-domain-suites.md).
SARVAM_LANGS = {"ta": "ta-IN", "hi": "hi-IN", "bn": "bn-IN", "or": "od-IN", "te": "te-IN"}
VENDOR_CACHE_DIR = EVAL_DIR / ".cache" / "sarvam"
VENDOR_CALL_LOG_PATH = EVAL_DIR / "vendor_calls.log"
HTTP_TIMEOUT_S = 60
RETRY_WAIT_S = 10.0
RETRYABLE = (429, 500, 502, 503)

Post = Callable[[str, dict, dict, int], bytes]


class VendorBudgetExceeded(RuntimeError):
    pass


def _budget() -> int:
    raw = os.environ.get("SIB_VENDOR_CALL_BUDGET", "").strip() or "12"
    if not raw.isdigit() or int(raw) < 1:
        raise ValueError("SIB_VENDOR_CALL_BUDGET must be a positive whole number")
    return int(raw)


def parse_voice(voice: str | None) -> tuple[str, str] | None:
    """(model, speaker) of a vendor voice, or None for a Gemini voice name."""
    match = VOICE_PATTERN.match(voice or "")
    return (match.group(1), match.group(2)) if match else None


def is_vendor_voice(voice: str | None) -> bool:
    return parse_voice(voice) is not None


def logged_vendor_calls() -> int:
    if not VENDOR_CALL_LOG_PATH.exists():
        return 0
    return sum(1 for line in VENDOR_CALL_LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip())


def material(text: str, lang: str, voice: str) -> dict:
    return {"kind": "vendor_tts", "voice": voice, "lang": lang, "rate": SAMPLE_RATE, "text": text}


def cache_key(text: str, lang: str, voice: str) -> str:
    raw = json.dumps(material(text, lang, voice), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _urllib_post(url: str, headers: dict, body: dict, timeout: int) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - a fixed https URL
        return resp.read()


class VendorCalls:
    """One instance per build. `post` is injectable so the tests never reach the network."""

    def __init__(self, offline: bool = False, post: Post | None = None) -> None:
        self._offline = offline
        self._post = post or _urllib_post

    def is_cached(self, text: str, lang: str, voice: str) -> bool:
        return (VENDOR_CACHE_DIR / f"{cache_key(text, lang, voice)}.wav").exists()

    def tts_wav(self, purpose: str, text: str, lang: str, voice: str, fresh: bool = False) -> bytes:
        """A 16 kHz mono WAV of `text` in `lang`, spoken by the vendor voice. fresh: call even when cached."""
        from gemini_client import OfflineMiss, is_wav  # one exception type for every offline miss

        parsed = parse_voice(voice)
        if parsed is None:
            raise ValueError(f"{purpose}: not a vendor voice: {voice}")
        if lang not in SARVAM_LANGS:
            raise ValueError(f"{purpose}: Sarvam does not speak {lang}")
        key = cache_key(text, lang, voice)
        path = VENDOR_CACHE_DIR / f"{key}.wav"
        if path.exists() and not fresh:
            return path.read_bytes()
        if self._offline:
            raise OfflineMiss(f"offline run has no cached clip for: {purpose}; nothing was called")
        model, speaker = parsed
        body = {"text": text, "language_code": SARVAM_LANGS[lang], "speaker": speaker, "model": model,
                "speech_sample_rate": SAMPLE_RATE, "output_audio_codec": "wav"}
        wav = self._call(purpose, model, key, body)
        if not is_wav(wav):
            raise ValueError(f"{purpose}: the vendor reply is not a WAV")
        VENDOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav)
        return wav

    def _call(self, purpose: str, model: str, key: str, body: dict) -> bytes:
        api_key = os.environ.get("SARVAM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("SARVAM_API_KEY is not set; nothing was called")
        headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
        for attempt in (1, 2):
            _record(purpose, model, key, attempt, len(body["text"]))
            try:
                raw = self._post(SARVAM_URL, headers, body, HTTP_TIMEOUT_S)
                return base64.b64decode(json.loads(raw)["audios"][0])
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE and attempt == 1:
                    time.sleep(RETRY_WAIT_S)
                    continue
                raise RuntimeError(f"{purpose}: Sarvam answered HTTP {exc.code}") from None
        raise RuntimeError(f"{purpose}: no answer after a retry")  # unreachable: the loop returns or raises


def _record(purpose: str, model: str, key: str, attempt: int, chars: int) -> None:
    used, cap = logged_vendor_calls(), _budget()
    if used >= cap:
        raise VendorBudgetExceeded(f"vendor call budget reached ({used}/{cap}); not calling")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe = purpose.replace("\t", " ").replace("\n", " ")
    with VENDOR_CALL_LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"{stamp}\t#{used + 1}\tattempt={attempt}\tsarvam\t{model}\t{key[:12]}\t{chars} chars\t{safe}\n")
