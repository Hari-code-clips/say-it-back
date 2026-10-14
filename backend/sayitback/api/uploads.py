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


async def read_wav(upload: UploadFile, s: Settings, name: str) -> tuple[bytes, WavInfo]:
    """Read at most the per-file limit, then require a 16-bit PCM WAV within the clip length.
    `name` is the form field's name, which the caller chose: an error quotes only a bit of it."""
    data = await upload.read(s.max_audio_bytes + 1)
    shown = quote(name, s.max_echo_chars)
    if len(data) > s.max_audio_bytes:
        raise PayloadTooLarge(f"{shown} is larger than {s.max_audio_bytes // (1024 * 1024)} MB.")
    try:
        info = parse_wav(data)
    except WavError as exc:
        raise UnsupportedMedia(f"{shown}: {exc}") from None
    if info.duration_s > s.max_clip_seconds:
        raise Unprocessable(
            f"{shown} is longer than {s.max_clip_seconds:g} s.", code="audio_too_long"
        )
    return data, info


def parse_meta(raw: Any) -> CheckMeta:
    if raw is None or isinstance(raw, FormFile):
        return CheckMeta()
    try:
        return CheckMeta.model_validate(json.loads(raw))
    except (ValueError, TypeError):
        raise Unprocessable('meta must be JSON like {"mode": "live" | "turn"}.') from None


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
