"""Gemini backend selection: the same code runs on the Developer API and on Agent Platform.

Backend per model kind comes from settings (env):
  GOOGLE_GENAI_USE_ENTERPRISE (legacy GOOGLE_GENAI_USE_VERTEXAI)  global switch
  SIB_LIVE_BACKEND / SIB_TTS_BACKEND                               per-kind override
  GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION / SIB_LIVE_LOCATION project and locations
  SIB_TTS_LOCATION                                                 TTS only (v0.5); empty = cloud

`client_kwargs` returns the exact `google.genai.Client(**kwargs)` arguments, which ADK's
`Gemini(client_kwargs=...)` forwards. Developer API keys are read by the SDK from GOOGLE_API_KEY;
they never pass through this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal, override

from google import genai
from google.adk.models import Gemini
from google.adk.models.base_llm import BaseLlm
from google.adk.models.base_llm_connection import BaseLlmConnection
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import Field

from sayitback import loop_clients
from sayitback.refusal import refusal_reason
from sayitback.settings import Settings

log = logging.getLogger("sayitback.run")

Kind = Literal["flash", "live", "tts"]
DEVELOPER_API = "developer-api"
AGENT_PLATFORM = "agent-platform"
# Transient: 408 request timeout, 429 quota, 499 CANCELLED (Agent Platform under load), and 5xx
RETRY_STATUS = [408, 429, 499, 500, 502, 503, 504]


def backend_for(kind: Kind, s: Settings) -> str:
    override = {"live": s.live_backend, "tts": s.tts_backend}.get(kind, "")
    if override:
        return override
    return AGENT_PLATFORM if s.agent_platform else DEVELOPER_API


def client_kwargs(kind: Kind, s: Settings) -> dict[str, Any]:
    """Arguments for `google.genai.Client`, explicit so env switches never flip a kind."""
    if backend_for(kind, s) == DEVELOPER_API:
        return {"enterprise": False}
    locations = {"live": s.live_location, "tts": s.tts_location_id}
    kwargs: dict[str, Any] = {
        "enterprise": True,
        "location": locations.get(kind, s.cloud_location),
    }
    if s.cloud_project:
        kwargs["project"] = s.cloud_project
    return kwargs


def backends(s: Settings) -> dict[str, str]:
    """For /api/health: the backend each model kind uses."""
    return {kind: backend_for(kind, s) for kind in ("flash", "live", "tts")}  # type: ignore[misc]


def retry_options(s: Settings) -> types.HttpRetryOptions:
    """SIB_RETRY_ATTEMPTS attempts in all (the first call included) on RETRY_STATUS and, from
    google-genai's own predicate, httpx timeouts and connect errors: so an attempt that
    `call_http_options` cut off is retried too. Exponential backoff from SIB_RETRY_BACKOFF_S, with
    google-genai's default jitter (up to 1 s). A retry costs tokens but no daily-cap units: the cap
    counts requests (daily_cap.py)."""
    return types.HttpRetryOptions(
        attempts=s.retry_attempts,
        initial_delay=s.retry_backoff_s,
        max_delay=s.retry_backoff_s * 4,
        http_status_codes=RETRY_STATUS,
    )


def call_http_options(s: Settings) -> types.HttpOptions:
    """The per-attempt cut-off for one Flash or Flash-Lite generate call: SIB_CALL_TIMEOUT_S, or the
    phase timeout if that is shorter, in the milliseconds HttpOptions wants. It goes in each
    agent's request config (adk_common), so the client's retry options still apply: one retry
    policy, never two."""
    return types.HttpOptions(timeout=round(min(s.call_timeout_s, s.phase_timeout_s) * 1000))


class RefusalRetry:
    """Mixin for a BaseLlm (before it in the bases): a model whose reply the safety filter blocked
    asks again (v0.5.1), as Agent Platform's prompt-level block is not deterministic. Up to
    `refusal_attempts` calls in all (SIB_REFUSAL_RETRIES + 1: refusal_retry), each with its own
    HTTP retries and per-attempt cut-off,
    waiting like those retries do (exponential from `refusal_backoff_s`, plus jitter) and inside
    the phase timeout. A reply still blocked on the last attempt is passed on as it is, for
    adk_common.record_refusal. A streamed call is never repeated. A retry costs tokens but no
    daily-cap units. The class using it declares the two fields (pydantic takes no fields from a
    mixin), as FlashGemini does."""

    refusal_attempts: int
    refusal_backoff_s: float

    def _refusal_wait(self, attempt: int) -> float:
        base = self.refusal_backoff_s
        return min(base * 2 ** (attempt - 1), base * 4) + random.uniform(0, base)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncIterator[LlmResponse]:
        attempts = 1 if stream else max(1, self.refusal_attempts)
        for attempt in range(1, attempts + 1):
            generate = super().generate_content_async  # type: ignore[misc]
            replies = [r async for r in generate(llm_request, stream)]
            reason = refusal_reason(replies[-1]) if replies else None
            if reason is None or attempt == attempts:
                for reply in replies:
                    yield reply
                return
            log.warning(
                "the model's filter blocked the reply (%s); asking again, attempt %d of %d",
                reason,
                attempt + 1,
                attempts,
            )
            await asyncio.sleep(self._refusal_wait(attempt))


class FlashGemini(RefusalRetry, Gemini):
    """ADK's Gemini with the refusal retry: every Flash and Flash-Lite agent's model. Its client
    for a loop is closed in that loop when the loop shuts down (loop_clients).

    17 Oct: when the model is out of capacity (Agent Platform's shared pool answers 429
    RESOURCE_EXHAUSTED on every one of its HTTP retries), the same request goes once to
    `fallback_model`, with its own retries, if one is set. Only a 429 before any reply falls back:
    any other error, or a stream that has already yielded, is raised as before. The reply's
    `model_version` names the model that answered, so the round's `modelIds` and the audit line
    record the fallback (observability.AuditPlugin)."""

    refusal_attempts: int = Field(default=1, exclude=True)
    refusal_backoff_s: float = Field(default=0.0, exclude=True)
    fallback_model: str = Field(default="", exclude=True)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncIterator[LlmResponse]:
        answered = False
        try:
            async for reply in super().generate_content_async(llm_request, stream):
                answered = True
                yield reply
            return
        except genai_errors.APIError as exc:
            if (
                answered
                or exc.code != 429
                or not self.fallback_model
                or llm_request.model == self.fallback_model
            ):
                raise
            log.warning(
                "%s is out of capacity (429 on every retry); asking %s instead",
                llm_request.model,
                self.fallback_model,
            )
        llm_request.model = self.fallback_model
        async for reply in super().generate_content_async(llm_request, stream):
            yield reply

    @property
    def api_client(self) -> genai.Client:
        client = Gemini.api_client.__get__(self, type(self))  # ADK's own per-loop client
        loop_clients.track(client)
        return client


def refusal_retry(s: Settings) -> dict[str, Any]:
    """The refusal retry's settings: SIB_REFUSAL_RETRIES calls after the first (0 = none), with the
    HTTP retries' backoff."""
    return {"refusal_attempts": s.refusal_retries + 1, "refusal_backoff_s": s.retry_backoff_s}


def make_flash(s: Settings, model: str | None = None) -> FlashGemini:
    """A Flash-kind model: SIB_FLASH_MODEL, or `model` (judge B's SIB_JUDGE_B_MODEL), on the same
    backend, with the same HTTP retry, and asked again when the safety filter blocks a reply.
    Only SIB_FLASH_MODEL gets SIB_FLASH_FALLBACK_MODEL: judge B keeps its own model, so a fallback
    never puts both judges on one model by itself."""
    name = model or s.flash_model
    return FlashGemini(
        model=name,
        client_kwargs=client_kwargs("flash", s),
        retry_options=retry_options(s),
        fallback_model=s.flash_fallback_model if name == s.flash_model else "",
        **refusal_retry(s),
    )


class LiveGemini(Gemini):
    """`Gemini` that reports when the Live session is open (setup complete).

    ADK's run_live yields nothing until the model speaks, so the relay needs this signal to send
    `ready`. A connect that fails (for example a rejected config) raises before it fires.
    """

    on_connected: Callable[[], None] | None = Field(default=None, exclude=True)

    @override
    @contextlib.asynccontextmanager
    async def connect(self, llm_request: LlmRequest) -> AsyncIterator[BaseLlmConnection]:
        async with super().connect(llm_request) as connection:
            if self.on_connected is not None:
                self.on_connected()
            yield connection


def make_live(s: Settings, on_connected: Callable[[], None] | None = None) -> LiveGemini:
    return LiveGemini(
        model=s.live_model, client_kwargs=client_kwargs("live", s), on_connected=on_connected
    )


def make_genai_client(kind: Kind, s: Settings) -> genai.Client:
    """A plain google-genai client (TTS needs no agent)."""
    return genai.Client(
        http_options=types.HttpOptions(retry_options=retry_options(s)), **client_kwargs(kind, s)
    )


def thinking_config(level: str) -> types.ThinkingConfig:
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel(level.upper()))


__all__ = [
    "AGENT_PLATFORM",
    "DEVELOPER_API",
    "BaseLlm",
    "FlashGemini",
    "Kind",
    "LiveGemini",
    "RefusalRetry",
    "backend_for",
    "backends",
    "call_http_options",
    "client_kwargs",
    "make_flash",
    "make_genai_client",
    "make_live",
    "refusal_retry",
    "retry_options",
    "thinking_config",
]
