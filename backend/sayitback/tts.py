"""Turn-mode voice: Gemini TTS through google-genai (no agent), cached by (model, voice, text).

`generate_content` with the AUDIO modality runs on both backends. The model returns raw 24 kHz
16-bit PCM, which is wrapped as WAV. It speaks only lines of a round's own script (`part_of_script`;
the API refuses anything else), so the language is the script's: the model detects it from the
text, and no language is sent. Like every Flash call, a call has an output ceiling
(SIB_MAX_OUTPUT_TOKENS), and a reply cut off at it is refused, never played or cached.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections import OrderedDict
from typing import Any

from google import genai
from google.genai import types

from sayitback.errors import CUT_OFF_MESSAGE, UpstreamError, as_upstream_error, safe_describe
from sayitback.models import Script
from sayitback.runtime import BeforeCall, Runtime
from sayitback.script_checks import clean
from sayitback.wav import make_wav

log = logging.getLogger("sayitback.tts")
DEFAULT_RATE = 24000
RATE = re.compile(r"rate=(\d+)")


def cache_key(model: str, voice: str, text: str) -> str:
    return hashlib.sha256(f"{model}\x00{voice}\x00{text}".encode()).hexdigest()


def part_of_script(script: Script, text: str) -> bool:
    """Whether `text` may be spoken for this round (API.md, endpoint 12): inside its instruction, or
    equal to one of its questions or its closing, with whitespace collapsed on both sides."""
    wanted = clean(text)
    whole = [clean(q.text) for q in script.questions] + [clean(script.closing)]
    return bool(wanted) and (wanted in clean(script.instruction) or wanted in whole)


def pcm_to_wav(data: bytes, mime_type: str | None) -> bytes:
    """The API sends PCM (audio/L16;codec=pcm;rate=24000). A ready-made WAV passes through."""
    if data[:4] == b"RIFF":
        return data
    match = RATE.search(mime_type or "")
    return make_wav(data, int(match.group(1)) if match else DEFAULT_RATE)


class Tts:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self._client: genai.Client | None = None
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._bytes = 0

    def _remember(self, key: str, wav: bytes) -> None:
        limit = self.rt.settings.tts_cache_max_bytes
        if len(wav) > limit:
            return
        self._bytes -= len(self._cache.pop(key, b""))  # a concurrent miss may insert the same key
        self._cache[key] = wav
        self._bytes += len(wav)
        while self._bytes > limit:
            _, dropped = self._cache.popitem(last=False)
            self._bytes -= len(dropped)

    def _config(self) -> types.GenerateContentConfig:
        voice = types.PrebuiltVoiceConfig(voice_name=self.rt.settings.tts_voice)
        return types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=voice)
            ),
            max_output_tokens=self.rt.settings.max_output_tokens,
        )

    async def speak(self, text: str, *, before_call: BeforeCall | None = None) -> bytes:
        """WAV (24 kHz mono 16-bit) for `text`. Raises 503 upstream_busy or 502 upstream_error (also
        for a reply cut off at the output ceiling, which is not cached).

        `before_call` is awaited on a cache miss, just before the model call (a cache hit makes no
        call and never awaits it); the HTTP API reserves the daily Gemini cap there."""
        s = self.rt.settings
        key = cache_key(s.tts_model, s.tts_voice, text)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if before_call is not None:
            await before_call()
        self._client = self._client or self.rt.tts_client_factory()
        try:
            async with asyncio.timeout(s.phase_timeout_s):
                response = await self._client.aio.models.generate_content(
                    model=s.tts_model, contents=text, config=self._config()
                )
        except Exception as exc:
            log.warning("tts failed: %s", safe_describe(exc))
            raise as_upstream_error(exc) from None
        wav = self._wav_from(response)
        self._remember(key, wav)
        return wav

    @staticmethod
    def _wav_from(response: Any) -> bytes:
        candidates = response.candidates or []
        if any(c.finish_reason == types.FinishReason.MAX_TOKENS for c in candidates):
            log.warning("tts reply cut off at the output ceiling")
            raise UpstreamError(CUT_OFF_MESSAGE)  # truncated audio: never played, never cached
        for candidate in candidates:
            for part in (candidate.content.parts if candidate.content else None) or []:
                blob = part.inline_data
                if blob and blob.data:
                    return pcm_to_wav(blob.data, blob.mime_type)
        raise UpstreamError("The voice service returned no audio.")
