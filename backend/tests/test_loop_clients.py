"""v0.5.1: a check run in its own event loop leaves nothing behind (sayitback/loop_clients.py).

eval/ runs every check in a fresh `asyncio.run` over one cached Runtime. ADK keeps a google-genai
client per loop and drops a finished loop's client unclosed; google-genai's `__del__` then tried
to close it on the next loop: "Task exception was never retrieved ... Event loop is closed", and
unclosed sockets. This runs that pattern against a real HTTP server on loopback (real sockets: a
mock transport has none to leak), with a judge that answers, fails or is blocked, and checks that
no loop saw an unhandled exception and no exception was raised in a destructor.
"""

from __future__ import annotations

import asyncio
import gc
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from google.genai import types

from sayitback import backends, loop_clients
from sayitback.errors import UpstreamBusy
from sayitback.pipeline import run_check
from sayitback.runtime import Runtime
from tests.check_support import QUESTIONS, STEPS
from tests.fakes import tone_wav


def _reply(obj) -> bytes:
    text = json.dumps(obj)
    return json.dumps(
        {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}
            ],
            "modelVersion": "gemini-test",
        }
    ).encode()


TRANSCRIPT = _reply({"transcripts": [{"question_id": "q1", "original": "நான் அதை ஆஃப் பண்ணிட்டு திறப்பேன்.",
                                      "detected_lang": "ta", "translation": "t", "flags": []}]})  # fmt: skip
RATINGS = _reply({"ratings": [{"step_id": s.id, "verdict": "missed", "quote": "", "quote_translation": "",
                               "reason": "r", "confidence": 0.9} for s in STEPS]})  # fmt: skip
BLOCKED = json.dumps({"promptFeedback": {"blockReason": "SAFETY"}, "modelVersion": "m"}).encode()
FAILED = json.dumps({"error": {"code": 500, "message": "boom", "status": "INTERNAL"}}).encode()


@pytest.fixture
def server():
    """A Gemini stand-in on 127.0.0.1 with keep-alive connections. `mode` makes judge A answer,
    fail (500) or be blocked."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        mode = "ok"

        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"])).decode()
            status, body = 200, RATINGS
            if "blind transcriber" in raw:
                body = TRANSCRIPT
            elif "hear the clips" in raw and Handler.mode == "fail":
                status, body = 500, FAILED
            elif "hear the clips" in raw and Handler.mode == "blocked":
                body = BLOCKED
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/", Handler
    httpd.shutdown()
    httpd.server_close()


def runtime(base_url: str, settings) -> Runtime:
    def flash():
        http = types.HttpOptions(base_url=base_url, retry_options=backends.retry_options(settings))
        return backends.FlashGemini(
            model=settings.flash_model,
            client_kwargs={"api_key": "test-key-not-real", "http_options": http},
            **backends.refusal_retry(settings),
        )

    return Runtime(settings, flash(), lambda cb: None, lambda: None, judge_b_llm=flash())


@pytest.mark.parametrize("mode", ["ok", "fail", "blocked"])
def test_checks_in_fresh_loops_leave_no_unretrieved_exception(server, settings, mode):
    base_url, handler = server
    handler.mode = mode
    rt = runtime(base_url, settings.with_overrides(retry_attempts=1, retry_backoff_s=0.0))
    problems: list[str] = []
    unraisable: list[str] = []
    closed: list[bool] = []

    def on_error(loop, context):
        problems.append(f"{context.get('message')}: {context.get('exception')!r}")

    async def one_check():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(on_error)
        try:
            result = await run_check(steps=STEPS, questions=QUESTIONS, clips={"q1": tone_wav()},
                                     worker_lang="ta", supervisor_lang="en", runtime=rt)  # fmt: skip
            outcome = [r.verdict for r in result.ratings]
        except UpstreamBusy:
            outcome = "upstream_busy"
        return outcome, loop_clients.tracked(loop)

    previous_hook = sys.unraisablehook
    sys.unraisablehook = lambda u: unraisable.append(f"{u.exc_type.__name__}: {u.exc_value}")
    try:
        for _ in range(3):  # as eval/ does: one asyncio.run per check, one shared Runtime
            outcome, clients = asyncio.run(one_check())
            closed += [c._api_client._async_httpx_client.is_closed for c in clients]
            gc.collect()
    finally:
        sys.unraisablehook = previous_hook
    # a blocked judge B is an `unclear` pass: against judge A's "missed" it is a split (rule 1, v0.5.3)
    expected = {"fail": "upstream_busy", "blocked": ["unclear"] * 3}.get(mode, ["missed"] * 3)
    assert outcome == expected
    assert problems == []
    assert unraisable == []
    assert closed and all(closed)  # each loop closed its own clients before it ended


def test_tracking_outside_a_loop_does_nothing():
    loop_clients.track(object())  # no running loop: no registration, no error
