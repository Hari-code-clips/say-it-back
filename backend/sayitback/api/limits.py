"""Request body limits, enforced while the body streams.

FastAPI parses a multipart or JSON body before a handler runs, so a size check inside a handler
comes after the whole upload was received and spooled. This ASGI middleware checks the declared
Content-Length up front and counts bytes as they arrive (a chunked body has no length), refusing
with 413 as soon as the limit is crossed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sayitback.settings import Settings

WRITE_METHODS = {"POST", "PUT", "PATCH"}
TOO_LARGE = "The request body is too large."
FORM_OVERHEAD_BYTES = 64 * 1024
JSON_BODY_BYTES = 256 * 1024  # every other write: an instruction, a SOP, six steps, a decision
TRANSCRIBE = re.compile(r"/api/transcribe")
CHECK = re.compile(r"/api/briefings/[^/]+/rounds/[^/]+/check")
HAZARD = re.compile(r"/api/briefings/[^/]+/hazards")  # v0.4: a voice report, one clip
ANY = re.compile(r".*")


def limits_for(s: Settings) -> list[tuple[re.Pattern[str], int]]:
    """Longest-first: the audio routes get room for their files, everything else a small cap."""
    return [
        (TRANSCRIBE, s.max_audio_bytes + FORM_OVERHEAD_BYTES),
        (CHECK, s.max_audio_files * s.max_audio_bytes + FORM_OVERHEAD_BYTES),
        (HAZARD, s.max_audio_bytes + FORM_OVERHEAD_BYTES),
        (ANY, JSON_BODY_BYTES),
    ]


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limits: Sequence[tuple[re.Pattern[str], int]]) -> None:
        self.app = app
        self.limits = list(limits)

    def _limit(self, path: str) -> int | None:
        return next((n for pattern, n in self.limits if pattern.fullmatch(path)), None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limit(scope["path"]) if scope["type"] == "http" else None
        if limit is None or scope["method"] not in WRITE_METHODS:
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await _refuse()(scope, receive, send)
            return
        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # An HTTPException, because FastAPI turns any other error raised while it
                    # parses a body into a 400; the app's handler renders it as payload_too_large.
                    raise HTTPException(status_code=413, detail=TOO_LARGE)
            return message

        await self.app(scope, counted, send)


def _refuse() -> JSONResponse:
    body = {"error": {"code": "payload_too_large", "message": TOO_LARGE}}
    return JSONResponse(body, status_code=413)
