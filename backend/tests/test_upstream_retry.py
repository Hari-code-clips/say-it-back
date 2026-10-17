"""A Gemini 429/5xx is retried with backoff, SIB_RETRY_ATTEMPTS in all (3 since v0.5.1, the first
call included), then the API answers 503 upstream_busy. Timeouts: test_call_timeout.py.

This drives the real google-genai client and ADK's Gemini model over a mock HTTP transport, so the
retry plumbing (HttpRetryOptions from backends.retry_options) is exercised, not assumed.
"""

from __future__ import annotations

import json

import httpx
import pytest
from google import genai
from google.adk.models import Gemini
from google.genai import types

from sayitback import backends, phases
from sayitback.errors import UpstreamBusy, UpstreamError
from sayitback.models import Sop
from sayitback.runtime import Runtime

OK_BODY = {
    "candidates": [
        {
            "content": {
                "role": "model",
                "parts": [{"text": json.dumps({"explanation": "Do it safely."})}],
            },
            "finishReason": "STOP",
        }
    ],
    "modelVersion": "gemini-3.8-flash",
}
BUSY = {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}}
CANCELLED = {
    "error": {"code": 499, "message": "The operation was cancelled.", "status": "CANCELLED"}
}


def runtime_over(statuses: list[int], settings) -> tuple[Runtime, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status = queue.pop(0) if queue else 200
        body = OK_BODY if status == 200 else CANCELLED if status == 499 else BUSY
        return httpx.Response(status, json=body)

    s = settings.with_overrides(retry_backoff_s=0.01)
    client = genai.Client(
        api_key="test-key-not-real",
        http_options=types.HttpOptions(
            retry_options=backends.retry_options(s),
            httpx_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ),
    )
    rt = Runtime(s, Gemini(model=s.flash_model, client=client), lambda cb: None, lambda: None)
    return rt, seen


async def explain(rt):
    return await phases.explain(rt, steps=[], ratings={}, supervisor_lang="en", sop_title="SOP")


async def test_one_503_is_retried_and_the_call_succeeds(settings):
    rt, seen = runtime_over([503], settings)
    text, _ = await explain(rt)
    assert text == "Do it safely."
    assert len(seen) == 2


async def test_three_503s_surface_as_upstream_busy_after_exactly_two_retries(settings):
    rt, seen = runtime_over([503, 503, 503, 503], settings)
    with pytest.raises(UpstreamBusy) as err:
        await explain(rt)
    assert (err.value.status, err.value.code) == (503, "upstream_busy")
    assert len(seen) == 3  # the first call plus two retries, never more


async def test_a_429_is_retried_too(settings):
    rt, seen = runtime_over([429, 429, 429], settings)
    with pytest.raises(UpstreamBusy):
        await explain(rt)
    assert len(seen) == 3


async def test_a_400_is_not_retried_and_is_a_502(settings):
    rt, seen = runtime_over([400], settings)
    with pytest.raises(UpstreamError):
        await explain(rt)
    assert len(seen) == 1


def test_the_production_flash_model_carries_the_retry_options(settings):
    flash = backends.make_flash(settings)
    assert flash.retry_options == backends.retry_options(settings)


async def test_extract_uses_the_same_path(settings):
    rt, seen = runtime_over([503], settings)
    sop = Sop(id="S", version="v1", title="t", text="1. x")
    with pytest.raises(UpstreamError):  # the canned body is not an ExtractOut
        await phases.extract_steps(rt, instruction="do x", supervisor_lang="en", sop=sop)
    assert len(seen) == 2


@pytest.mark.parametrize("status", [499, 408])
async def test_a_cancelled_or_timed_out_request_is_retried_and_the_answer_used(settings, status):
    """Agent Platform answers 499 CANCELLED under load (seen in the paid eval), and 408 for a
    request it gave up on: both are transient, like a 503."""
    rt, seen = runtime_over([status], settings)
    text, _ = await explain(rt)
    assert text == "Do it safely." and len(seen) == 2


@pytest.mark.parametrize("status", [499, 408])
async def test_three_cancellations_are_upstream_busy(settings, status):
    rt, seen = runtime_over([status] * 4, settings)
    with pytest.raises(UpstreamBusy) as err:
        await explain(rt)
    assert (err.value.status, err.value.code) == (503, "upstream_busy")
    assert len(seen) == 3


def test_the_retried_statuses():
    assert set(backends.RETRY_STATUS) == {408, 429, 499, 500, 502, 503, 504}
    assert set(backends.retry_options(backends.Settings()).http_status_codes) == set(
        backends.RETRY_STATUS
    )
