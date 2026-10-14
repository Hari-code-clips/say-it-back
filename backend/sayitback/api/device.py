"""The device key check (API.md, "Callers and ownership"), as middleware so no route can forget it.

Every /api route needs a caller except health, and the API docs when SIB_API_DOCS turns them on (a
browser opens those without custom headers). The WebSocket is not HTTP: its ticket is its own
capability. The check runs before any body is read, so a request without a key costs nothing: no
upload is parsed and nothing is counted. It leaves the `Caller` (the key's SHA-256 and the client
address) in the request's state for `api.context.caller_of`.
"""

from __future__ import annotations

from collections.abc import Collection

from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sayitback.caller import DEVICE_HEADER, DEVICE_KEY, Caller, owner_hash
from sayitback.errors import DeviceRequired
from sayitback.ratelimit import client_ip
from sayitback.settings import Settings

API_PREFIX = "/api/"
HEALTH_PATH = "/api/health"
DOCS_URL = "/api/docs"
OPENAPI_URL = "/api/openapi.json"
MESSAGE = (
    "Send your device key in the X-SIB-Device header "
    "(22 to 64 characters of A-Z, a-z, 0-9, _ and -)."
)


def open_paths(s: Settings) -> tuple[str, ...]:
    """The routes that take no device key."""
    return (HEALTH_PATH, DOCS_URL, OPENAPI_URL) if s.api_docs else (HEALTH_PATH,)


class DeviceMiddleware:
    def __init__(self, app: ASGIApp, hops: int, open_paths: Collection[str]) -> None:
        self.app = app
        self.hops = hops
        self.open_paths = frozenset(open_paths)

    def _needs_key(self, scope: Scope) -> bool:
        if scope["type"] != "http" or scope["method"] == "OPTIONS":  # a preflight carries no key
            return False
        return scope["path"].startswith(API_PREFIX) and scope["path"] not in self.open_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._needs_key(scope):
            await self.app(scope, receive, send)
            return
        keys = Headers(scope=scope).getlist(DEVICE_HEADER)
        if len(keys) != 1 or not DEVICE_KEY.fullmatch(keys[0]):
            refusal = DeviceRequired(MESSAGE)
            await JSONResponse(refusal.body(), refusal.status)(scope, receive, send)
            return
        caller = Caller(owner_hash(keys[0]), client_ip(HTTPConnection(scope), self.hops))
        scope.setdefault("state", {})["caller"] = caller
        await self.app(scope, receive, send)
