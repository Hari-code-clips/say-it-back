"""17 Oct: Agent Platform's shared pool for gemini-3.8-flash answered 429 RESOURCE_EXHAUSTED for
minutes at a time while other Flash models had room, so a check failed as upstream_busy even with
5 attempts. SIB_FLASH_FALLBACK_MODEL sends that one request to a second model once the first has
answered 429 on every retry. Only a 429 falls back; judge B has no fallback; the reply's model
version is what the round records.

The real google-genai client and ADK's Gemini over a mock HTTP transport, as in
test_refusal_retry.py: the 429 body is the one Agent Platform sends.
"""

from __future__ import annotations

import json

import httpx
import pytest
from google import genai
from google.genai import types

from sayitback import backends, phases
from sayitback.errors import UpstreamBusy, UpstreamError
from sayitback.runtime import Runtime
from sayitback.settings import Settings

PRIMARY, FALLBACK = "gemini-3.8-flash", "gemini-3.7-flash"
EXHAUSTED = {
    "error": {
        "code": 429,
        "message": "Resource exhausted. Please try again later.",
        "status": "RESOURCE_EXHAUSTED",
    }
}
BAD_REQUEST = {"error": {"code": 400, "message": "Invalid argument.", "status": "INVALID_ARGUMENT"}}


def ok_body(model: str) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": json.dumps({"explanation": "Do it safely."})}],
                },
                "finishReason": "STOP",
            }
        ],
        "modelVersion": model,
    }


def model_of(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[-1].split(":", 1)[0]


def runtime(settings, answers: dict[str, tuple[int, dict]], **overrides):
    """A runtime whose Flash model is built like production's (make_flash), over a transport that
    answers each model with its fixed (status, body). Returns the requests' model names."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = model_of(request)
        seen.append(model)
        status, body = answers[model]
        return httpx.Response(status, json=body)

    s = settings.with_overrides(retry_backoff_s=0.01, flash_model=PRIMARY, **overrides)
    client = genai.Client(
        api_key="test-key-not-real",
        http_options=types.HttpOptions(
            retry_options=backends.retry_options(s),
            httpx_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ),
    )
    production = backends.make_flash(s)  # its fallback, on this client (TestTheWiring: make_flash)
    flash = backends.FlashGemini(
        model=production.model,
        client=client,
        fallback_model=production.fallback_model,
        **backends.refusal_retry(s),
    )
    return Runtime(s, flash, lambda cb: None, lambda: None), seen, s


async def explain(rt):
    return await phases.explain(rt, steps=[], ratings={}, supervisor_lang="en", sop_title="SOP")


class TestTheFallback:
    async def test_429_on_every_retry_goes_to_the_fallback(self, settings):
        rt, seen, s = runtime(
            settings,
            {PRIMARY: (429, EXHAUSTED), FALLBACK: (200, ok_body(FALLBACK))},
            flash_fallback_model=FALLBACK,
        )
        text, meta = await explain(rt)
        assert text == "Do it safely."
        assert seen == [PRIMARY] * s.retry_attempts + [FALLBACK]
        assert FALLBACK in meta.model_ids.values()  # the round records the model that answered

    async def test_without_a_fallback_it_is_still_upstream_busy(self, settings):
        rt, seen, s = runtime(settings, {PRIMARY: (429, EXHAUSTED)})
        with pytest.raises(UpstreamBusy):
            await explain(rt)
        assert seen == [PRIMARY] * s.retry_attempts

    async def test_a_busy_fallback_is_upstream_busy_after_its_own_retries(self, settings):
        rt, seen, s = runtime(
            settings,
            {PRIMARY: (429, EXHAUSTED), FALLBACK: (429, EXHAUSTED)},
            flash_fallback_model=FALLBACK,
        )
        with pytest.raises(UpstreamBusy):
            await explain(rt)
        assert seen == [PRIMARY] * s.retry_attempts + [FALLBACK] * s.retry_attempts

    async def test_any_other_error_never_falls_back(self, settings):
        rt, seen, _ = runtime(
            settings,
            {PRIMARY: (400, BAD_REQUEST), FALLBACK: (200, ok_body(FALLBACK))},
            flash_fallback_model=FALLBACK,
        )
        with pytest.raises(UpstreamError):
            await explain(rt)
        assert FALLBACK not in seen

    async def test_an_answer_from_the_first_model_is_kept(self, settings):
        rt, seen, _ = runtime(
            settings,
            {PRIMARY: (200, ok_body(PRIMARY)), FALLBACK: (200, ok_body(FALLBACK))},
            flash_fallback_model=FALLBACK,
        )
        _, meta = await explain(rt)
        assert seen == [PRIMARY]
        assert PRIMARY in meta.model_ids.values()


class TestTheWiring:
    def test_only_the_flash_model_gets_the_fallback(self):
        s = Settings(flash_model=PRIMARY, flash_fallback_model=FALLBACK)
        assert backends.make_flash(s).fallback_model == FALLBACK
        assert backends.make_flash(s, "gemini-3.1-flash-lite").fallback_model == ""  # judge B

    def test_the_setting_is_off_by_default_and_read_from_the_environment(self):
        assert Settings().flash_fallback_model == "" == Settings.from_env({}).flash_fallback_model
        env = {"SIB_FLASH_FALLBACK_MODEL": f" {FALLBACK} "}
        assert Settings.from_env(env).flash_fallback_model == FALLBACK
        assert backends.make_flash(Settings()).fallback_model == ""
