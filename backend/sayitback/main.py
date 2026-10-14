"""The FastAPI app: `uvicorn sayitback.main:app --port 8080`.

All 20 endpoints of API.md, camelCase on the wire, errors as {"error": {"code", "message"}}.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from sayitback import __version__
from sayitback.api import briefings, evaluation, live, misc
from sayitback.api.context import AppContext, build_context
from sayitback.api.device import DOCS_URL, OPENAPI_URL, DeviceMiddleware, open_paths
from sayitback.api.limits import BodyLimitMiddleware, limits_for
from sayitback.caller import DEVICE_HEADER
from sayitback.daily_cap import Clock
from sayitback.errors import ApiError, RateLimited, safe_describe
from sayitback.live_runner import LiveOpener
from sayitback.observability import configure_logging, setup_cloud_trace
from sayitback.runtime import Runtime
from sayitback.settings import Settings
from sayitback.store import Store

log = logging.getLogger("sayitback")
HTTP_CODES = {
    404: "not_found",
    405: "method_not_allowed",
    400: "bad_request",
    413: "payload_too_large",
}


def _error(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status, headers=headers)


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        headers = None
        if isinstance(exc, RateLimited) and exc.retry_after:
            headers = {"Retry-After": str(exc.retry_after)}
        return _error(exc.status, exc.code, exc.message, headers)

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names only: never echo the submitted values back.
        where = ", ".join(
            sorted(
                {".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]) for e in exc.errors()}
            )
        )
        return _error(422, "validation_error", f"Invalid request: {where}.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODES.get(exc.status_code, "http_error")
        return _error(
            exc.status_code, code, str(exc.detail) if exc.status_code != 404 else "Not found."
        )

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error: %s", safe_describe(exc))
        return _error(500, "internal_error", "Something went wrong.")


def create_app(
    settings: Settings | None = None,
    *,
    runtime: Runtime | None = None,
    store: Store | None = None,
    webhook_transport: httpx.AsyncBaseTransport | None = None,
    live_opener: LiveOpener | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build the app. Tests pass fakes for the model layer, store, webhook transport and Live, and
    a clock for the daily Gemini cap's UTC day."""
    configure_logging()
    settings = settings or Settings.from_env()
    ctx: AppContext = build_context(
        settings,
        runtime=runtime,
        store=store,
        webhook_transport=webhook_transport,
        live_opener=live_opener,
        clock=clock,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.trace_to_cloud:
            setup_cloud_trace()
        yield

    app = FastAPI(
        title="Say It Back",
        version=__version__,
        lifespan=lifespan,
        docs_url=DOCS_URL if settings.api_docs else None,  # off unless SIB_API_DOCS=true
        openapi_url=OPENAPI_URL if settings.api_docs else None,
        redoc_url=None,
    )
    app.state.ctx = ctx
    _install_http(app, settings)
    _install_error_handlers(app)
    for router in (misc.router, briefings.router, evaluation.router, live.router):
        app.include_router(router)
    return app


def _install_http(app: FastAPI, settings: Settings) -> None:
    """Body limits (innermost), the device key, CORS for the web origins, no-store plus nosniff on
    API responses. The key check sits inside CORS, so its 401 carries the CORS headers a
    cross-origin browser needs to read it, and outside the body limit, so a request without a key
    is refused before any of its body is read."""
    app.add_middleware(BodyLimitMiddleware, limits=limits_for(settings))
    app.add_middleware(
        DeviceMiddleware, hops=settings.trusted_proxy_hops, open_paths=open_paths(settings)
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", DEVICE_HEADER],
        expose_headers=["Retry-After"],  # a cross-origin page may read none of it otherwise
        max_age=settings.cors_max_age_s,
    )

    @app.middleware("http")
    async def harden(request: Request, call_next):  # noqa: ANN001, ANN202
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


app = create_app()
