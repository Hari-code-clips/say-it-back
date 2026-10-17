"""The permit-to-work stub: `uvicorn ptw_stub.app:app --port 8090`.

- POST /webhook: Say It Back's signed decision record (API.md v0.4, "Webhooks"). The signature is
  checked first (300 s window); then a Go releases a permit and a No-go holds one. v0.5.2: a
  record with `permit` is filed under that permit ref, one worker slot each; the permit is
  released only when every slot holds a Go (a crewSize that differs is 409 crew_mismatch).
- GET /api/permits: the permits as JSON, newest first (`?ref=` narrows it to one permit ref).
- GET /api/permits/{id}: one permit's status, for a site's systems to poll (ETag, 304).
- GET /: the permit board, server-rendered HTML.

Pilot (Say It Back docs/EPERMIT_ADAPTER.md): a post's `Idempotency-Key` is kept with the permit it
filed; the same key again is 409 `duplicate` with that permit, changing nothing, and a key reused
for another briefing is 422 `idempotency_key_reused`. A key that is not the one the signed record
names (`sib-<briefingId>-<first 16 hex of recordHash>`) is 422 `idempotency_key_mismatch`, so a
replayed body cannot take another delivery's key (security fixes B). The supervisor's reason is
never stored, so no route can show it.

Settings, environment only: SIB_WEBHOOK_SECRET (the same secret as the backend's; without it every
post is refused, unless PTW_ALLOW_UNSIGNED=true for a local try), PTW_STORE (`memory`, the default,
or `firestore`), PTW_STORE_FILE (with `memory`, an optional JSON file the permits are also written
to). The secret is never logged or shown.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from ptw_stub import board, signing
from ptw_stub.permits import (
    DELIVERY_KEY,
    BadRecord,
    CrewMismatch,
    Duplicate,
    KeyMismatch,
    KeyReused,
    PermitBook,
    PermitStore,
    now_iso,
    parse_record,
)

log = logging.getLogger("ptw_stub")
MAX_BODY_BYTES = 64 * 1024  # a decision record is a few KB
TIMESTAMP_HEADER = "x-sib-timestamp"
SIGNATURE_HEADER = "x-sib-signature"
KEY_HEADER = "idempotency-key"
NO_STORE = {"Cache-Control": "no-store"}
BOARD_CSP = (
    f"default-src 'none'; style-src 'sha256-{board.STYLE_SHA256}'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)
STORES = ("memory", "firestore")
REFUSALS = {
    "unsigned": "The post carries no X-SIB-Timestamp and X-SIB-Signature.",
    "bad_timestamp": "X-SIB-Timestamp is not Unix seconds.",
    "stale": "X-SIB-Timestamp is more than 300 s away from now.",
    "bad_signature": "X-SIB-Signature does not match the body.",
}


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status)


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _book_from_env(store_file: Path | None) -> PermitStore:
    """PTW_STORE: `memory` (with PTW_STORE_FILE, if set) or `firestore`. Anything else stops the
    service at start-up."""
    kind = os.environ.get("PTW_STORE", "").strip().lower() or "memory"
    if kind not in STORES:
        raise ValueError(f"PTW_STORE must be one of {', '.join(STORES)}")
    if kind == "firestore":
        from ptw_stub.firestore_book import FirestorePermitBook

        return FirestorePermitBook.from_env()
    if store_file is None and os.environ.get("PTW_STORE_FILE", "").strip():
        store_file = Path(os.environ["PTW_STORE_FILE"].strip())
    return PermitBook(store_file)


def create_app(
    *,
    secret: str | None = None,
    store_file: Path | None = None,
    allow_unsigned: bool | None = None,
    clock: Callable[[], float] = time.time,
    book: PermitStore | None = None,
) -> FastAPI:
    """`book` replaces the store PTW_STORE picks (tests pass one over a fake Firestore)."""
    secret = os.environ.get("SIB_WEBHOOK_SECRET", "").strip() if secret is None else secret
    unsigned_ok = _flag("PTW_ALLOW_UNSIGNED") if allow_unsigned is None else allow_unsigned
    book = book or _book_from_env(store_file)
    app = FastAPI(title="Permit-to-work stub", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.book = book

    @app.post("/webhook")
    async def webhook(request: Request) -> JSONResponse:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return _error(413, "payload_too_large", "A decision record is at most 64 KB.")
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_BODY_BYTES:
                return _error(413, "payload_too_large", "A decision record is at most 64 KB.")
        if secret:
            reason = signing.problem(
                secret,
                request.headers.get(TIMESTAMP_HEADER),
                request.headers.get(SIGNATURE_HEADER),
                body,
                clock(),
            )
            if reason:
                log.warning("webhook refused: %s", reason)
                return _error(401, reason, REFUSALS[reason])
        elif not unsigned_ok:
            return _error(503, "not_configured", "SIB_WEBHOOK_SECRET is not set on this service.")
        try:
            record = parse_record(body)
        except BadRecord as exc:
            return _error(422, "bad_record", str(exc))
        key = request.headers.get(KEY_HEADER)
        if key is not None and not DELIVERY_KEY.fullmatch(key):
            return _error(422, "bad_idempotency_key", "Idempotency-Key: 8-128 of A-Za-z0-9._:-")
        try:
            permit, created = await book.record(record, now_iso(), key=key)
        except CrewMismatch as exc:  # v0.5.2: the permit stays as it was
            return _error(409, "crew_mismatch", str(exc))
        except Duplicate as dup:  # a retried delivery: answered, nothing changes
            log.info("duplicate delivery for %s", dup.permit.briefing_id)
            error = {"code": "duplicate", "message": str(dup)}
            return JSONResponse({"error": error, "permit": dup.permit.wire()}, 409)
        except KeyReused as exc:
            return _error(422, "idempotency_key_reused", str(exc))
        except KeyMismatch as exc:  # the key is not the signed record's own: nothing changes
            return _error(422, "idempotency_key_mismatch", str(exc))
        log.info("permit %s %s for %s", permit.id, permit.status, permit.briefing_id)
        return JSONResponse({"permit": permit.wire(), "created": created}, 201 if created else 200)

    @app.get("/api/permits")
    async def permits(ref: str | None = None) -> JSONResponse:
        """Newest first; `?ref=` (case-insensitive) narrows it to that permit ref's permit."""
        listed = [p.wire() for p in await book.newest_first()]
        if ref is not None:
            listed = [p for p in listed if (p["ref"] or "").upper() == ref.strip().upper()]
        return JSONResponse({"permits": listed}, headers=NO_STORE)

    @app.get("/api/permits/{permit_id}")
    async def permit_status(permit_id: str, request: Request) -> Response:
        """One permit, for a site's systems to poll: an ETag, and 304 when it has not changed."""
        found = next((p for p in await book.newest_first() if p.id == permit_id), None)
        if found is None:
            return _error(404, "not_found", "No such permit.")
        body = json.dumps({"permit": found.wire()}, ensure_ascii=False, separators=(",", ":"))
        etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'
        headers = {**NO_STORE, "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(body, media_type="application/json", headers=headers)

    @app.get("/", response_class=HTMLResponse)
    async def permit_board() -> HTMLResponse:
        headers = {"Content-Security-Policy": BOARD_CSP, "Cache-Control": "no-store"}
        page = board.render(await book.newest_first(), store=book.name)
        return HTMLResponse(page, headers=headers)

    @app.get("/healthz")
    async def health() -> dict[str, Any]:
        permits = len(await book.newest_first())
        return {"ok": True, "signed": bool(secret), "store": book.name, "permits": permits}

    @app.middleware("http")
    async def harden(request: Request, call_next):  # noqa: ANN001, ANN202
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    return app


app = create_app()
