"""The real ADK `Gemini` model and google-genai client over a mock HTTP transport: no network. The
reply body is what the REST API would send, so ADK converts it (finish reason, usage metadata)
exactly as it does in production."""

from __future__ import annotations

from typing import Any

import httpx
from google import genai
from google.adk.models import Gemini
from google.genai import types

from sayitback import backends
from sayitback.runtime import Runtime
from sayitback.settings import Settings

# Thinking used up the whole ceiling: what a cut-off reply costs, and carries, on the wire.
USAGE = {"promptTokenCount": 900, "thoughtsTokenCount": 8192, "totalTokenCount": 9092}


def wire_reply(
    parts: list[dict[str, Any]] | None, finish: str = "STOP", usage: dict[str, int] | None = None
) -> dict[str, Any]:
    """A generateContent response body. `parts` None: no `content` at all, as when the ceiling
    was reached while the model was still thinking."""
    candidate: dict[str, Any] = {"finishReason": finish}
    if parts is not None:
        candidate["content"] = {"role": "model", "parts": parts}
    return {
        "candidates": [candidate],
        "usageMetadata": usage or USAGE,
        "modelVersion": "gemini-3.8-flash-001",
    }


def runtime_returning(settings: Settings, body: dict[str, Any]) -> Runtime:
    """A Runtime whose Flash model answers every request with `body`."""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    client = genai.Client(
        api_key="test-key-not-real",
        http_options=types.HttpOptions(
            retry_options=backends.retry_options(settings),
            httpx_async_client=httpx.AsyncClient(transport=transport),
        ),
    )
    flash = Gemini(model=settings.flash_model, client=client)
    return Runtime(settings, flash, lambda cb: None, lambda: None)
