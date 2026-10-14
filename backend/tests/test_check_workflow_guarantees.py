"""What the move from SequentialAgent and ParallelAgent to a `Workflow` must not change: no ADK
deprecation warning, the per-phase timeout, the plugins (audit, BigQuery), what reaches the logs and
what the real google-genai client puts on the wire.
"""

from __future__ import annotations

import asyncio
import json
import logging
import warnings
from pathlib import Path

import google.adk.plugins as adk_plugins
import httpx
import pytest
from google import genai
from google.adk.models import Gemini
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

from sayitback import backends, demo
from sayitback import observability as obs
from sayitback.agents.check_answer.agent import build_agent
from sayitback.errors import UpstreamBusy, UpstreamError
from sayitback.runtime import Runtime
from tests.check_support import check, scenario
from tests.fakes import fake_runtime


def deprecations(caught: list[warnings.WarningMessage]) -> list[str]:
    return [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]


class TestNoDeprecatedAdkClass:
    async def test_building_and_running_the_check_raises_no_deprecation_warning(self, settings):
        rt, _ = fake_runtime(scenario(), settings)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")  # not even pyproject's filters may hide one
            build_agent(rt)
            build_agent(rt, passes=1)
            result = await check(rt)
        assert result.next_action == "reexplain"
        assert deprecations(caught) == []

    def test_the_same_recording_does_catch_the_old_classes(self):
        """A guard that cannot fail proves nothing: ADK 2.11 still warns for these two."""
        from google.adk.agents import ParallelAgent, SequentialAgent

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            SequentialAgent(name="old", sub_agents=[ParallelAgent(name="inner")])
        found = deprecations(caught)
        assert sorted(m.split(" is deprecated")[0] for m in found) == [
            "ParallelAgent",
            "SequentialAgent",
        ]
        assert all("in favor of Workflow" in m for m in found)


class TestTimeoutsPluginsAndLogs:
    async def test_a_slow_model_stops_at_the_phase_timeout_and_leaves_no_task_behind(
        self, settings
    ):
        rt, llm = fake_runtime(scenario(), settings.with_overrides(phase_timeout_s=0.3))
        llm.delay = 5.0
        with pytest.raises(UpstreamBusy):
            await check(rt)
        await asyncio.sleep(0)
        assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []

    async def test_plugins_from_build_plugins_see_every_model_call_and_node_output(
        self, settings, monkeypatch
    ):
        class Recorder(BasePlugin):
            def __init__(self):
                super().__init__(name="recorder")
                self.models, self.runs, self.node_outputs = [], [], []

            async def before_run_callback(self, *, invocation_context):
                self.runs.append("before")

            async def after_run_callback(self, *, invocation_context):
                self.runs.append("after")

            async def before_model_callback(self, *, callback_context, llm_request):
                self.models.append(callback_context.agent_name)

            async def on_event_callback(self, *, invocation_context, event):
                if event.output is not None:
                    self.node_outputs.append(event.node_info.path)

        recorder = Recorder()
        monkeypatch.setattr(obs, "make_bq_plugin", lambda s: recorder)  # the BigQuery slot
        rt, _ = fake_runtime(scenario(), settings.with_overrides(bq_dataset="proj.dataset"))
        result = await check(rt)
        assert sorted(recorder.models) == ["blind_transcriber", "judge_a", "judge_b"]
        assert recorder.runs == ["before", "after"]
        assert "check_answer@1/blind_transcriber@1" in recorder.node_outputs
        assert result.model_ids["judge_a"] == "fake-flash-001"  # and the audit plugin ran too

    def test_node_outputs_are_denied_in_bigquery_because_they_carry_the_transcript(self):
        source = Path(adk_plugins.__file__).parent / "bigquery_agent_analytics_plugin.py"
        assert '"NODE_OUTPUT"' in source.read_text(encoding="utf-8")  # ADK 2.x logs them
        assert "NODE_OUTPUT" in obs.BQ_DENIED_EVENTS

    @pytest.mark.parametrize(
        "reply",
        [
            "SECRETWORDS this is not json",
            json.dumps({"transcripts": [{"question_id": 7, "original": ["SECRETWORDS"]}]}),
            json.dumps({"transcripts": "SECRETWORDS"}),
        ],
    )
    async def test_a_malformed_model_reply_is_never_echoed_into_the_logs(
        self, settings, caplog, reply
    ):
        """ADK's Workflow logs a failed node with the exception text; pydantic would echo the reply."""
        rt, llm = fake_runtime(scenario(), settings)
        llm.handler = lambda seen: reply
        with caplog.at_level(logging.DEBUG), pytest.raises(UpstreamError):
            await check(rt)
        assert caplog.records  # ADK did log the failure, messages and tracebacks included
        assert "SECRETWORDS" not in caplog.text


def wire_runtime(settings, bodies: list[dict]) -> Runtime:
    """The real ADK Gemini model and google-genai client over a mock transport: no network. The
    reply is chosen from the request's response schema; `bodies` collects what was sent."""
    sc = scenario()
    replies = {
        "TranscribeOut": {"transcripts": sc.transcripts},
        "JudgeOut": {"ratings": sc.judge_a},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        text = json.dumps(replies[schema_title(body)], ensure_ascii=False)
        reply = {"role": "model", "parts": [{"text": text}]}
        return httpx.Response(
            200,
            json={"candidates": [{"content": reply, "finishReason": "STOP"}], "modelVersion": "m"},
        )

    client = genai.Client(
        api_key="test-key-not-real",
        http_options=types.HttpOptions(
            retry_options=backends.retry_options(settings),
            httpx_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ),
    )
    return Runtime(
        settings, Gemini(model=settings.flash_model, client=client), lambda cb: None, lambda: None
    )


def schema_title(body: dict) -> str:
    return body["generationConfig"]["responseSchema"]["title"]


def audio_count(body: dict) -> int:
    return sum(
        "inlineData" in p or "inline_data" in p for c in body["contents"] for p in c["parts"]
    )


class TestOnTheWire:
    async def test_the_clip_is_in_the_transcriber_and_judge_a_requests_once_and_never_in_judge_bs(
        self, settings
    ):
        bodies: list[dict] = []
        result = await check(wire_runtime(settings, bodies))
        assert result.next_action == "reexplain" and len(bodies) == 3
        by_schema = {}
        for body in bodies:
            by_schema.setdefault(body["generationConfig"]["responseSchema"]["title"], []).append(
                body
            )
        (transcriber,), judges = by_schema["TranscribeOut"], by_schema["JudgeOut"]
        assert audio_count(transcriber) == 1
        assert sorted(audio_count(j) for j in judges) == [0, 1]  # judge B, then judge A
        assert all(set(b["generationConfig"]) >= {"thinkingConfig"} for b in bodies)

    async def test_nothing_about_the_steps_leaves_the_process_in_the_transcribers_request(
        self, settings
    ):
        bodies: list[dict] = []
        await check(wire_runtime(settings, bodies))
        transcriber = next(b for b in bodies if schema_title(b) == "TranscribeOut")
        sent = json.dumps(transcriber, ensure_ascii=False)
        steps = demo.steps()
        hidden = [*(s["text"] for s in steps), *(e for s in steps for e in s["essential"])]
        assert [h for h in hidden if h in sent] == []
