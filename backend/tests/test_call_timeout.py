"""v0.5.1: shared-capacity tails. Every Flash and Flash-Lite call has a per-attempt cut-off
(SIB_CALL_TIMEOUT_S, 40 s), and a timed-out attempt is retried like a 429 or 5xx, up to
SIB_RETRY_ATTEMPTS (3, the first call included), with exponential backoff and jitter, all inside
the phase timeout. Live and TTS are unchanged.

Like test_upstream_retry.py, this drives the real google-genai client and ADK's Gemini model over
a mock HTTP transport. The transport behaves as a real one does when the server never answers: it
waits out the request's own read timeout, then raises httpx.ReadTimeout. With no timeout set it
just hangs.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from google import genai
from google.adk.models import Gemini
from google.genai import _api_client, types

from sayitback import backends, phases
from sayitback.agents.briefer_live.agent import build_agent as build_briefer
from sayitback.agents.check_answer.agent import build_agent as build_check
from sayitback.errors import UpstreamBusy, UpstreamError
from sayitback.runtime import Runtime
from sayitback.settings import ConfigError, Settings
from tests.helpers import graph_nodes

HANG = "hang"
CALL_TIMEOUT_S = 0.3
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
ERROR = {"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}}


class Server:
    """The mock Gemini endpoint: each request takes the next step of the plan (HANG or a status),
    then 200 once the plan is used up."""

    def __init__(self, plan: list[object]) -> None:
        self.plan = list(plan)
        self.requests: list[httpx.Request] = []
        self.read_timeouts: list[float | None] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        read = request.extensions.get("timeout", {}).get("read")
        self.read_timeouts.append(read)
        step = self.plan.pop(0) if self.plan else 200
        if step == HANG:
            await asyncio.sleep(30 if read is None else read)
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(step, json=OK_BODY if step == 200 else ERROR)  # type: ignore[arg-type]


def runtime_over(server: Server, settings, **overrides) -> Runtime:
    timing = {"retry_backoff_s": 0.01, "call_timeout_s": CALL_TIMEOUT_S, "phase_timeout_s": 8.0}
    s = settings.with_overrides(**{**timing, **overrides})
    client = genai.Client(
        api_key="test-key-not-real",
        http_options=types.HttpOptions(
            retry_options=backends.retry_options(s),
            httpx_async_client=httpx.AsyncClient(transport=httpx.MockTransport(server)),
        ),
    )
    return Runtime(s, Gemini(model=s.flash_model, client=client), lambda cb: None, lambda: None)


async def explain(rt):
    return await phases.explain(rt, steps=[], ratings={}, supervisor_lang="en", sop_title="SOP")


class TestThePerAttemptCutOff:
    async def test_a_hung_first_attempt_is_cut_and_the_second_answer_is_used(self, settings):
        server = Server([HANG])
        rt = runtime_over(server, settings)
        started = time.monotonic()
        text, _ = await explain(rt)
        assert text == "Do it safely."
        assert len(server.requests) == 2
        assert server.read_timeouts == [CALL_TIMEOUT_S, CALL_TIMEOUT_S]  # per attempt, not shared
        assert time.monotonic() - started < 5.0  # nowhere near the 30 s hang

    async def test_three_timeouts_are_the_existing_503_upstream_busy(self, settings):
        server = Server([HANG, HANG, HANG])
        rt = runtime_over(server, settings)
        with pytest.raises(UpstreamBusy) as err:
            await explain(rt)
        assert (err.value.status, err.value.code) == (503, "upstream_busy")
        assert len(server.requests) == 3  # SIB_RETRY_ATTEMPTS, the first call included

    async def test_a_timeout_then_a_503_then_an_answer(self, settings):
        server = Server([HANG, 503])
        text, _ = await explain(runtime_over(server, settings))
        assert text == "Do it safely." and len(server.requests) == 3

    async def test_a_400_is_not_retried(self, settings):
        server = Server([400])
        with pytest.raises(UpstreamError) as err:
            await explain(runtime_over(server, settings))
        assert (err.value.status, err.value.code) == (502, "upstream_error")
        assert len(server.requests) == 1

    async def test_the_phase_timeout_still_bounds_the_retries(self, settings):
        server = Server([HANG, HANG, HANG])
        rt = runtime_over(server, settings, call_timeout_s=1.0, phase_timeout_s=1.5)
        started = time.monotonic()
        with pytest.raises(UpstreamBusy):
            await explain(rt)
        assert time.monotonic() - started < 3.0
        assert len(server.requests) <= 2


class TestWhereTheCutOffApplies:
    def test_every_flash_agent_carries_the_per_attempt_timeout(self, fake_rt):
        rt, _ = fake_rt
        nodes = graph_nodes(build_check(rt))
        for name in ("blind_transcriber", "judge_a", "judge_b"):
            http = nodes[name].generate_content_config.http_options
            assert http is not None and http.timeout == 40_000, name  # ms
            assert http.retry_options is None  # the client's retry, so never twice

    def test_the_live_agent_has_none(self, fake_rt):
        rt, _ = fake_rt
        assert build_briefer(rt).generate_content_config is None

    def test_google_genai_uses_httpx_so_a_timeout_is_retried(self):
        """google-genai retries httpx timeouts, but switches to aiohttp when that is installed, and
        its retry predicate does not cover aiohttp's timeouts. If this fails, aiohttp has arrived
        as a dependency: per-attempt timeouts would then fail the call instead of retrying."""
        assert _api_client.has_aiohttp is False
        assert httpx.ReadTimeout.__mro__[1] is httpx.TimeoutException
        assert httpx.TimeoutException in _api_client._HTTPX_TRANSIENT_EXC


class TestTheSettings:
    def test_defaults_and_environment(self):
        assert (Settings().call_timeout_s, Settings().retry_attempts) == (40.0, 3)
        s = Settings.from_env({"SIB_CALL_TIMEOUT_S": "25", "SIB_RETRY_ATTEMPTS": "2"})
        assert (s.call_timeout_s, s.retry_attempts) == (25.0, 2)
        assert backends.retry_options(s).attempts == 2
        assert backends.call_http_options(s).timeout == 25_000

    def test_a_cut_off_longer_than_the_phase_is_the_phase_timeout(self):
        s = Settings.from_env({"SIB_CALL_TIMEOUT_S": "200"})
        assert backends.call_http_options(s).timeout == 110_000
        short_phase = Settings.from_env({"SIB_PHASE_TIMEOUT_S": "30"})
        assert backends.call_http_options(short_phase).timeout == 30_000

    @pytest.mark.parametrize(
        "env",
        [
            {"SIB_CALL_TIMEOUT_S": "0"},
            {"SIB_CALL_TIMEOUT_S": "-1"},
            {"SIB_CALL_TIMEOUT_S": "soon"},
            {"SIB_RETRY_ATTEMPTS": "0"},
            {"SIB_RETRY_ATTEMPTS": "6"},
            {"SIB_RETRY_ATTEMPTS": "2.5"},
        ],
    )
    def test_bad_values_fail_at_start_up(self, env):
        with pytest.raises(ConfigError, match=next(iter(env))):
            Settings.from_env(env)
