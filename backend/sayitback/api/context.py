"""The application context: everything a request handler needs, built once per app."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request, WebSocket

from sayitback.caller import Caller
from sayitback.daily_cap import Clock, DailyCap, utc_now
from sayitback.errors import DeviceRequired, UpstreamBusy
from sayitback.evalset import EvalData
from sayitback.live_relay import RelayDeps
from sayitback.live_runner import LiveOpener, open_adk_session
from sayitback.ratelimit import RateLimiter
from sayitback.repo import Repo
from sayitback.rounds import Rounds
from sayitback.runtime import Runtime
from sayitback.service import Briefings
from sayitback.settings import Settings
from sayitback.store import Store, make_store
from sayitback.tts import Tts
from sayitback.webhook import WebhookSender


@dataclass
class AppContext:
    settings: Settings
    rt: Runtime
    repo: Repo
    briefings: Briefings
    rounds: Rounds
    tts: Tts
    webhook: WebhookSender
    limiter: RateLimiter
    cap: DailyCap
    relay: RelayDeps
    evals: EvalData


def build_context(
    settings: Settings,
    *,
    runtime: Runtime | None = None,
    store: Store | None = None,
    webhook_transport: httpx.AsyncBaseTransport | None = None,
    live_opener: LiveOpener | None = None,
    clock: Clock | None = None,
) -> AppContext:
    rt = runtime or Runtime.from_settings(settings)
    repo = Repo(store or make_store(settings))
    cap = DailyCap(
        repo.store, settings.daily_gemini_calls, clock or utc_now, settings.daily_calls_per_ip
    )
    return AppContext(
        settings=settings,
        rt=rt,
        repo=repo,
        briefings=Briefings(rt, repo, cap),
        rounds=Rounds(rt, repo, cap),
        tts=Tts(rt),
        webhook=WebhookSender(settings.webhook_url, settings.webhook_timeout_s, webhook_transport),
        limiter=RateLimiter(settings.rate_limit_per_min),
        cap=cap,
        relay=RelayDeps(rt, repo, live_opener or open_adk_session),
        evals=EvalData(settings.eval_dir),
    )


def ctx_of(request: Request) -> AppContext:
    return request.app.state.ctx


def ctx_of_ws(ws: WebSocket) -> AppContext:
    return ws.app.state.ctx


def caller_of(request: Request) -> Caller:
    """Who sent the request: the device key's owner hash and the client address, left in the
    request's state by `api.device.DeviceMiddleware`, which refuses a request without a key."""
    caller = getattr(request.state, "caller", None)
    if caller is None:  # a route the middleware leaves open asked for a caller: refuse, never guess
        raise DeviceRequired("This request needs a device key.")
    return caller


CallerDep = Annotated[Caller, Depends(caller_of)]


def rate_limited(request: Request) -> None:
    """Dependency for the Gemini-backed endpoints and the free writes: a per-address limit
    (SIB_RATE_LIMIT_PER_MIN). It runs before the handler, so a refused client never reaches the
    daily cap (daily_cap.py)."""
    ctx_of(request).limiter.check(caller_of(request).address)


async def within_budget[T](request: Request, work: Awaitable[T]) -> T:
    """Bound a whole /api call that may chain model phases, so the client gets a JSON 503
    instead of Firebase Hosting's 504 at 60 s."""
    try:
        async with asyncio.timeout(ctx_of(request).settings.request_timeout_s):
            return await work
    except TimeoutError:
        raise UpstreamBusy("The request took too long. Try again in a moment.") from None
