"""POST /admin/outbox/retry (SIB_OUTBOX): one retry pass over the deliveries that are due.

Cloud Run gives an instance CPU only while it serves a request, so the retries run inside this
one, and Cloud Scheduler calls it every minute or two (docs/EPERMIT_ADAPTER.md, "Runbook"). It
sits outside /api because a machine calls it: `Authorization: Bearer <SIB_OUTBOX_TOKEN>` instead
of a device key, compared in constant time, never logged. Without SIB_OUTBOX or the token it
answers 404, as if it did not exist.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sayitback.api.context import ctx_of

RETRY_PATH = "/admin/outbox/retry"
router = APIRouter()


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status)


@router.post(RETRY_PATH, include_in_schema=False)
async def retry_due(request: Request) -> JSONResponse:
    """`{checked, delivered, pending, failed}`: the briefings this pass looked at, by status."""
    ctx = ctx_of(request)
    token = ctx.settings.outbox_token
    if ctx.outbox is None or not token:
        return _error(404, "not_found", "Not found.")
    given = request.headers.get("authorization", "").encode("utf-8", "replace")
    if not hmac.compare_digest(given, f"Bearer {token}".encode()):
        return _error(401, "unauthorized", "Send SIB_OUTBOX_TOKEN as a bearer token.")
    return JSONResponse(await ctx.outbox.retry_due(), headers={"Cache-Control": "no-store"})
