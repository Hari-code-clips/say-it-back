"""Gemini backend selection: the same code runs on the Developer API and on Agent Platform.

Backend per model kind comes from settings (env):
  GOOGLE_GENAI_USE_ENTERPRISE (legacy GOOGLE_GENAI_USE_VERTEXAI)  global switch
  SIB_LIVE_BACKEND / SIB_TTS_BACKEND                               per-kind override
  GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION / SIB_LIVE_LOCATION project and locations

`client_kwargs` returns the exact `google.genai.Client(**kwargs)` arguments, which ADK's
`Gemini(client_kwargs=...)` forwards. Developer API keys are read by the SDK from GOOGLE_API_KEY;
they never pass through this module.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal, override

from google import genai
from google.adk.models import Gemini
from google.adk.models.base_llm import BaseLlm
from google.adk.models.base_llm_connection import BaseLlmConnection
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from pydantic import Field

from sayitback.settings import Settings

Kind = Literal["flash", "live", "tts"]
DEVELOPER_API = "developer-api"
AGENT_PLATFORM = "agent-platform"
RETRY_STATUS = [429, 500, 502, 503, 504]


def backend_for(kind: Kind, s: Settings) -> str:
    override = {"live": s.live_backend, "tts": s.tts_backend}.get(kind, "")
    if override:
        return override
    return AGENT_PLATFORM if s.agent_platform else DEVELOPER_API


def client_kwargs(kind: Kind, s: Settings) -> dict[str, Any]:
    """Arguments for `google.genai.Client`, explicit so env switches never flip a kind."""
    if backend_for(kind, s) == DEVELOPER_API:
        return {"enterprise": False}
    kwargs: dict[str, Any] = {
        "enterprise": True,
        "location": s.live_location if kind == "live" else s.cloud_location,
    }
    if s.cloud_project:
        kwargs["project"] = s.cloud_project
    return kwargs


def backends(s: Settings) -> dict[str, str]:
    """For /api/health: the backend each model kind uses."""
    return {kind: backend_for(kind, s) for kind in ("flash", "live", "tts")}  # type: ignore[misc]


def retry_options(s: Settings) -> types.HttpRetryOptions:
    """One retry with backoff on 429 and 5xx (attempts counts the first call)."""
    return types.HttpRetryOptions(
        attempts=s.retry_attempts,
        initial_delay=s.retry_backoff_s,
        max_delay=s.retry_backoff_s * 4,
        http_status_codes=RETRY_STATUS,
    )


def make_flash(s: Settings) -> Gemini:
    return Gemini(
        model=s.flash_model, client_kwargs=client_kwargs("flash", s), retry_options=retry_options(s)
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
    "Kind",
    "LiveGemini",
    "backend_for",
    "backends",
    "client_kwargs",
    "make_flash",
    "make_genai_client",
    "make_live",
    "retry_options",
    "thinking_config",
]
