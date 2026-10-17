"""Multipart audio uploads: size limits and WAV parsing at the boundary."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request, UploadFile
from starlette.datastructures import UploadFile as FormFile

from sayitback.errors import PayloadTooLarge, Unprocessable, UnsupportedMedia, quote
from sayitback.models import CheckMeta
from sayitback.settings import Settings
from sayitback.wav import WavError, WavInfo, parse_wav

META_FIELD = "meta"
MAX_PARSED_FILES = 64  # parsing bound; the real limit (3) is counted below, with a clean 422


async def read_wav(
    upload: UploadFile, s: Settings, name: str, max_seconds: float | None = None
) -> tuple[bytes, WavInfo]:
    """Read at most the per-file limit, then require a 16-bit PCM WAV within the clip length
    (`max_seconds`, default SIB's clip limit). `name` is the form field's name, which the caller
    chose: an error quotes only a bit of it."""
    limit_s = s.max_clip_seconds if max_seconds is None else max_seconds
    data = await upload.read(s.max_audio_bytes + 1)
    shown = quote(name, s.max_echo_chars)
    if len(data) > s.max_audio_bytes:
        raise PayloadTooLarge(f"{shown} is larger than {s.max_audio_bytes // (1024 * 1024)} MB.")
    try:
        info = parse_wav(data)
    except WavError as exc:
        raise UnsupportedMedia(f"{shown}: {exc}") from None
    if info.duration_s > limit_s:
        raise Unprocessable(f"{shown} is longer than {limit_s:g} s.", code="audio_too_long")
    return data, info


def parse_meta(raw: Any) -> CheckMeta:
    if raw is None or isinstance(raw, FormFile):
        return CheckMeta()
    try:
        return CheckMeta.model_validate(json.loads(raw))
    except (ValueError, TypeError):
        raise Unprocessable(
            'meta must be JSON like {"mode": "live" | "turn", "sampleAnswers": ["q1"]}.'
        ) from None


async def read_check_form(request: Request, s: Settings) -> tuple[dict[str, bytes], CheckMeta]:
    """One audio/wav file per question id (the field name), plus optional `meta`."""
    clips: dict[str, bytes] = {}
    meta = CheckMeta()
    async with request.form(max_files=MAX_PARSED_FILES, max_fields=4) as form:
        for name, value in form.multi_items():
            if name == META_FIELD:
                meta = parse_meta(value)
            elif isinstance(value, FormFile):
                if name in clips:
                    raise Unprocessable(f"Two files named {quote(name, s.max_echo_chars)}.")
                clips[name] = (await read_wav(value, s, name))[0]
            else:
                raise Unprocessable(f"Unexpected field {quote(name, s.max_echo_chars)}.")
    if not clips:
        raise Unprocessable("Send at least one audio/wav file named by question id.")
    if len(clips) > s.max_audio_files:
        raise Unprocessable(f"At most {s.max_audio_files} files per check.", code="too_many_files")
    return clips, meta


HAZARD_AUDIO = "audio"
HAZARD_ROUND = "round"
FORM_TYPES = ("multipart/form-data", "application/x-www-form-urlencoded")


async def read_hazard_form(request: Request, s: Settings) -> tuple[bytes | None, int | None]:
    """Endpoint 21: an optional `audio` file (a 16-bit PCM WAV of at most SIB's hazard length)
    and an optional `round` number. No body at all is a tap."""
    kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if kind and kind not in FORM_TYPES:
        raise UnsupportedMedia("Send multipart/form-data with an optional audio and round.")
    audio: bytes | None = None
    round_n: int | None = None
    async with request.form(max_files=2, max_fields=4) as form:
        for name, value in form.multi_items():
            if name == HAZARD_AUDIO and isinstance(value, FormFile):
                if audio is not None:
                    raise Unprocessable("Send at most one audio file.")
                audio = (await read_wav(value, s, name, s.max_hazard_seconds))[0]
            elif name == HAZARD_ROUND and not isinstance(value, FormFile):
                round_n = _round_number(value)
            else:
                raise Unprocessable(f"Unexpected field {quote(name, s.max_echo_chars)}.")
    return audio, round_n


def _round_number(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    if not text.isascii() or not text.isdigit() or len(text) > 3:
        raise Unprocessable("round must be a round number.")
    return int(text)
