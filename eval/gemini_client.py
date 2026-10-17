"""Gemini access for the testset build: cached, logged, budget-capped.

A cache hit makes no call. Every real call is appended to CALL_LOG_PATH before it is made.
On a 429 or 503 the call waits once and retries once; a second one raises, so the build stops and reports.
Flash and TTS each get a client from the backend's backend switch (client_kwargs below), so Agent
Platform and the SIB_TTS_BACKEND override behave as they do in the service. A Developer API key is read
from the environment by the SDK and is never printed or logged.
"""

import base64
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

from config import (
    CACHE_DIR,
    CALL_LOG_PATH,
    FLASH_MODEL,
    GEMINI_CALL_BUDGET,
    HTTP_TIMEOUT_MS,
    RETRY_429_WAIT_S,
    TTS_MODEL,
    TTS_STYLE,
)
from audio_tools import pcm_to_wav


RETRYABLE_CODES = (429, 503)  # rate limit or overload: wait once, retry once, then stop and report


class BudgetExceeded(RuntimeError):
    pass


class OfflineMiss(RuntimeError):
    """A cache miss in an offline run. Raised before any request is made."""


def logged_call_count() -> int:
    if not CALL_LOG_PATH.exists():
        return 0
    return sum(1 for line in CALL_LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip())


def is_wav(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _digest(material: dict) -> str:
    raw = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_cache(material: dict) -> dict | None:
    path = CACHE_DIR / f"{_digest(material)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["response"]


class GeminiCalls:
    """One instance per build. Methods return cached or fresh results; they never return unvalidated data."""

    def __init__(self, client: Any = None, offline: bool = False) -> None:
        self._clients: dict[str, Any] = {"flash": client, "tts": client} if client is not None else {}
        self._offline = offline

    def _sdk(self, kind: str = "flash") -> Any:
        if kind not in self._clients:
            from google import genai  # lazy: the SDK is only needed when a call is actually made
            from google.genai import types

            # One HTTP attempt per logged call: retries are handled here, where they are counted.
            options = types.HttpOptions(timeout=HTTP_TIMEOUT_MS,
                                        retry_options=types.HttpRetryOptions(attempts=1))
            self._clients[kind] = genai.Client(http_options=options, **client_kwargs(kind))
        return self._clients[kind]

    def is_cached(self, material: dict) -> bool:
        return (CACHE_DIR / f"{_digest(material)}.json").exists()

    def is_cached_tts(self, text: str, voice: str) -> bool:
        render, key = self.tts_source(text, voice)
        return (CACHE_DIR / f"{key}.json").exists()

    def tts_source(self, text: str, voice: str, fresh: bool = False) -> tuple[str, str]:
        """(render, cache key) that tts_wav would use: the Interactions-era entry if cached, else generate_content."""
        earlier = {"kind": "tts", "model": TTS_MODEL, "voice": voice, "style": TTS_STYLE, "text": text}
        if not fresh and self.is_cached(earlier):
            return "interactions", _digest(earlier)
        return "generate_content", _digest(tts_material(text, voice))

    def text_json(self, purpose: str, system: str, prompt: str, schema: dict,
                  validate: Callable[[dict], None]) -> dict:
        material = {"kind": "text_json", "model": FLASH_MODEL, "system": system,
                    "prompt": prompt, "schema": schema}
        return self._cached(purpose, FLASH_MODEL, material,
                            lambda: self._text_json_call(system, prompt, schema), validate)

    def audio_json(self, purpose: str, wav: bytes, system: str, prompt: str, schema: dict,
                   validate: Callable[[dict], None]) -> dict:
        material = {"kind": "audio_json", "model": FLASH_MODEL, "system": system,
                    "prompt": prompt, "schema": schema, "audioSha256": hashlib.sha256(wav).hexdigest()}
        return self._cached(purpose, FLASH_MODEL, material,
                            lambda: self._audio_json_call(wav, system, prompt, schema), validate)

    def tts_wav(self, purpose: str, text: str, voice: str, fresh: bool = False) -> bytes:
        """fresh: make a new call even when a clip for this text and voice is cached (--rerender)."""
        # Clips rendered before the switch (interactions API, 10 of them) keep their original cache key.
        earlier = None if fresh else _read_cache(
            {"kind": "tts", "model": TTS_MODEL, "voice": voice, "style": TTS_STYLE, "text": text})
        if earlier is not None:
            return base64.b64decode(earlier["audioB64"])
        material = tts_material(text, voice)
        response = self._cached(purpose, TTS_MODEL, material,
                                lambda: self._tts_generate_call(text, voice),
                                lambda r: _require(is_wav(base64.b64decode(r["audioB64"])), "TTS output is not WAV"),
                                fresh=fresh)
        return base64.b64decode(response["audioB64"])

    def _cached(self, purpose: str, model: str, material: dict, call: Callable[[], dict],
                validate: Callable[[dict], None], fresh: bool = False) -> dict:
        key = _digest(material)
        path = CACHE_DIR / f"{key}.json"
        if path.exists() and not fresh:
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        if self._offline:
            raise OfflineMiss(f"offline run has no cached result for: {purpose}; nothing was called")
        response = self._call_with_retry(purpose, model, key, call)
        validate(response)  # raises before anything is cached, so bad output is never reused
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"purpose": purpose, "model": model, "response": response},
                                   ensure_ascii=False), encoding="utf-8")
        return response

    def _call_with_retry(self, purpose: str, model: str, key: str, call: Callable[[], dict]) -> dict:
        for attempt in (1, 2):
            _record_call(purpose, model, key, attempt)
            try:
                return call()
            except ModelBlocked:
                # The prompt-level safety block is not deterministic: the same clip and request passed and
                # failed from one call to the next on 15 Oct 2026. One retry, then the caller decides.
                if attempt == 1:
                    continue
                raise
            except Exception as exc:  # noqa: BLE001 - only overload errors are retried; everything else re-raises
                if getattr(exc, "code", None) in RETRYABLE_CODES and attempt == 1:
                    time.sleep(RETRY_429_WAIT_S)
                    continue
                raise
        raise RuntimeError("unreachable")

    def _text_json_call(self, system: str, prompt: str, schema: dict) -> dict:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        )
        resp = self._sdk().models.generate_content(model=FLASH_MODEL, contents=prompt, config=config)
        return json.loads(_text_or_blocked(resp))

    def _audio_json_call(self, wav: bytes, system: str, prompt: str, schema: dict) -> dict:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        )
        parts = [types.Part.from_bytes(data=wav, mime_type="audio/wav"), prompt]
        resp = self._sdk().models.generate_content(model=FLASH_MODEL, contents=parts, config=config)
        return json.loads(_text_or_blocked(resp))

    def _tts_generate_call(self, text: str, voice: str) -> dict:
        # generate_content with audio output: the path that honours HttpOptions (timeout, one attempt).
        from google.genai import types

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
        )
        prompt = f"Say this in a {TTS_STYLE}: {text}" if TTS_STYLE else text  # a style prefix can be spoken aloud
        resp = self._sdk("tts").models.generate_content(model=TTS_MODEL, contents=prompt, config=config)
        inline = resp.candidates[0].content.parts[0].inline_data
        if inline is None or not inline.data:
            raise RuntimeError("TTS returned no audio")
        pcm = inline.data if isinstance(inline.data, bytes) else base64.b64decode(inline.data)
        wav = pcm_to_wav(pcm, inline.mime_type or "")
        return {"audioB64": base64.b64encode(wav).decode("ascii"), "mimeType": "audio/wav"}


def tts_material(text: str, voice: str) -> dict:
    return {"kind": "tts_generate", "model": TTS_MODEL, "voice": voice, "style": TTS_STYLE, "text": text}


def client_kwargs(kind: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    """google.genai.Client arguments for 'flash' or 'tts', from the backend's own switch (sayitback.backends).

    So the build follows the same environment as the service: GOOGLE_GENAI_USE_ENTERPRISE=true with
    GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION for Agent Platform, and SIB_TTS_BACKEND=developer-api to
    send only the voice calls to the Developer API (GOOGLE_API_KEY). Makes no call.
    """
    from sayitback.backends import client_kwargs as backend_kwargs  # lazy: only a real call needs it
    from sayitback.settings import Settings

    return backend_kwargs(kind, Settings.from_env(env))  # type: ignore[arg-type]


def backend_name(kind: str, env: dict[str, str] | None = None) -> str:
    """'agent-platform' or 'developer-api' for that model kind, as the service would choose it."""
    from sayitback.backends import backend_for
    from sayitback.settings import Settings

    return backend_for(kind, Settings.from_env(env))  # type: ignore[arg-type]


class ModelBlocked(RuntimeError):
    """The model returned no text because Agent Platform blocked the request (prompt_feedback.block_reason),
    as it did for one synthetic Odia clip on 15 Oct 2026 even with every adjustable safety setting off."""


def _text_or_blocked(resp: Any) -> str:
    """The reply's text, or ModelBlocked naming the block reason (never json.loads(None))."""
    if resp.text:
        return resp.text
    feedback = getattr(resp, "prompt_feedback", None)
    reason = getattr(getattr(feedback, "block_reason", None), "value", None) or "no text in the reply"
    raise ModelBlocked(f"the model returned no text: {reason}")


def _record_call(purpose: str, model: str, key: str, attempt: int) -> None:
    used = logged_call_count()
    if used >= GEMINI_CALL_BUDGET:
        raise BudgetExceeded(f"Gemini call budget reached ({used}/{GEMINI_CALL_BUDGET}); not calling")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_purpose = purpose.replace("\t", " ").replace("\n", " ")
    with CALL_LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"{stamp}\t#{used + 1}\tattempt={attempt}\t{model}\t{key[:12]}\t{safe_purpose}\n")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)
