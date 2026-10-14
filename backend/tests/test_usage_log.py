"""One `usage` log line for every Flash model call: the model, the agent and the token counts the API
reported (prompt, output, thinking, total), and why the call stopped. Counts only, never content.
The next real run reads the cost per call from these lines instead of estimating it."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from sayitback import observability as obs
from sayitback import phases
from sayitback.llm_schemas import TranscribeOut
from tests.check_support import check
from tests.check_support import scenario as judged_scenario
from tests.fakes import (
    PANEL_SCRIPT,
    Reply,
    Scenario,
    fake_runtime,
    panel_script,
    rating,
    transcript,
    usage,
)
from tests.helpers import api_client, drive_to_round, make_app
from tests.wire_support import runtime_returning, wire_reply

MARKER = "WORDSTHEMODELWROTE"


def usage_lines(caplog) -> list[dict]:
    """The parsed `usage` lines, in the order they were logged."""
    return [
        json.loads(r.getMessage().removeprefix("usage "))
        for r in caplog.records
        if r.name == "sayitback.audit" and r.getMessage().startswith("usage ")
    ]


def counts(line: dict) -> tuple:
    return tuple(line[k] for k in ("prompt_tokens", "output_tokens", "thinking_tokens"))


class TestUsageRecord:
    def test_a_real_response_gives_the_four_counts_and_why_it_stopped(self):
        response = LlmResponse.create(Reply({"x": 1}, usage=usage(1830, 210, 412)).response())

        record = obs.usage_record("check_answer", "judge_a", "gemini-3.8-flash-001", response)

        assert (
            record
            == {
                "event": "usage",
                "phase": "check_answer",
                "agent": "judge_a",
                "model": "gemini-3.8-flash-001",
                "prompt_tokens": 1830,
                "output_tokens": 210,  # what the model wrote; its 412 thinking tokens are billed as output too
                "thinking_tokens": 412,
                "total_tokens": 2452,
                "finish_reason": "STOP",
            }
        )

    def test_a_response_that_reports_no_usage_logs_none_not_zero(self):
        record = obs.usage_record("p", "a", "m", LlmResponse(content=None))
        assert [record[k] for k in ("prompt_tokens", "output_tokens", "thinking_tokens")] == [
            None
        ] * 3
        assert record["total_tokens"] is None and record["finish_reason"] is None

    def test_only_integers_and_a_finish_reason_can_appear_in_a_count_field(self):
        hostile = SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=MARKER,
                candidates_token_count=True,
                thoughts_token_count=1.5,
                total_token_count=7,
            ),  # fmt: skip
            finish_reason=MARKER,
        )
        record = obs.usage_record("p", "a", "m", hostile)
        assert counts(record) == (None, None, None) and record["total_tokens"] == 7
        assert record["finish_reason"] is None and MARKER not in json.dumps(record)

    def test_the_record_carries_no_content_even_when_the_response_has_some(self):
        response = LlmResponse.create(Reply(f'{{"text": "{MARKER}"}}').response())
        assert MARKER not in json.dumps(obs.usage_record("p", "a", "m", response))


class TestTheAuditPluginLogsEachCall:
    @staticmethod
    async def call(plugin, agent, response):
        ctx = SimpleNamespace(agent_name=agent)
        request = SimpleNamespace(model="gemini-3.8-flash", contents=[MARKER])
        await plugin.before_model_callback(callback_context=ctx, llm_request=request)
        await plugin.after_model_callback(callback_context=ctx, llm_response=response)

    @staticmethod
    def response(u, *, partial=False, finish=types.FinishReason.STOP):
        return SimpleNamespace(
            model_version="gemini-3.8-flash-001", partial=partial, finish_reason=finish,
            usage_metadata=u, content=MARKER,
        )  # fmt: skip

    async def test_every_call_gets_its_own_line_even_from_the_same_agent(self, caplog):
        plugin = obs.AuditPlugin("write_script")
        with caplog.at_level(logging.INFO, logger="sayitback.audit"):
            await self.call(plugin, "write_script", self.response(usage(100, 10, 1)))
            await self.call(plugin, "write_script", self.response(usage(120, 12, 2)))
        lines = usage_lines(caplog)
        assert [(ln["agent"], ln["phase"], counts(ln)) for ln in lines] == [
            ("write_script", "write_script", (100, 10, 1)),
            ("write_script", "write_script", (120, 12, 2)),
        ]
        assert [r.levelno for r in caplog.records] == [logging.INFO, logging.INFO]
        assert MARKER not in caplog.text

    async def test_a_partial_chunk_and_a_live_session_log_nothing(self, caplog):
        with caplog.at_level(logging.INFO, logger="sayitback.audit"):
            await self.call(obs.AuditPlugin("x"), "a", self.response(usage(1, 1, 1), partial=True))
            live = obs.AuditPlugin("briefer_live", live_model="gemini-3.8-live")
            await self.call(live, "briefer_live", self.response(usage(1, 1, 1)))
        assert usage_lines(caplog) == []

    async def test_the_run_still_ends_with_its_one_audit_line(self, caplog):
        plugin = obs.AuditPlugin("judge")
        with caplog.at_level(logging.INFO, logger="sayitback.audit"):
            await self.call(plugin, "judge_a", self.response(usage(1, 2, 3)))
            await plugin.after_run_callback(invocation_context=None)
        audit = [r.getMessage() for r in caplog.records if r.getMessage().startswith("audit ")]
        assert len(audit) == 1 and json.loads(audit[0].removeprefix("audit "))["calls"] == {
            "judge_a": 1
        }


class TestEveryFlashCallThroughTheRunner:
    async def test_the_check_logs_one_line_per_node_with_that_nodes_own_counts(
        self, settings, caplog
    ):
        base = judged_scenario()
        rt, llm = fake_runtime(base, settings)

        def handler(seen):
            ok = base.handler(seen)
            if seen.schema is TranscribeOut:
                return Reply(ok, usage=usage(1000, 100, 10))
            return Reply(ok, usage=usage(2000, 200, 20) if seen.has_audio else usage(1500, 150, 15))

        llm.handler = handler
        with caplog.at_level(logging.INFO, logger="sayitback.audit"):
            await check(rt)

        by_agent = {ln["agent"]: ln for ln in usage_lines(caplog)}
        assert set(by_agent) == {"blind_transcriber", "judge_a", "judge_b"}
        assert {a: counts(ln) for a, ln in by_agent.items()} == {
            "blind_transcriber": (1000, 100, 10),
            "judge_a": (2000, 200, 20),
            "judge_b": (1500, 150, 15),
        }
        assert {ln["total_tokens"] for ln in by_agent.values()} == {1110, 2220, 1665}
        assert {(ln["phase"], ln["model"], ln["finish_reason"]) for ln in by_agent.values()} == {
            ("check_answer", "fake-flash-001", "STOP")
        }

    def test_a_briefing_logs_extract_script_and_back_translation_in_order(self, settings, caplog):
        app, *_ = make_app(settings)
        with caplog.at_level(logging.INFO, logger="sayitback.audit"):
            drive_to_round(api_client(app))
        assert [ln["agent"] for ln in usage_lines(caplog)] == [
            "extract_steps",
            "write_script",
            "back_translate",
        ]

    def test_a_script_retry_is_a_second_write_script_line(self, settings, caplog):
        scenario = Scenario(script_drafts=[panel_script(closing="x" * 161), PANEL_SCRIPT])
        app, *_ = make_app(settings, scenario)
        with caplog.at_level(logging.INFO, logger="sayitback.audit"):
            drive_to_round(api_client(app))
        agents = [ln["agent"] for ln in usage_lines(caplog)]
        assert agents == ["extract_steps", "write_script", "write_script", "back_translate"]

    async def test_nothing_the_model_was_sent_or_wrote_reaches_the_logs(self, settings, caplog):
        base = Scenario(
            transcripts=[transcript("q1", MARKER)],
            judge_a=[
                rating("s1", "covered", MARKER),
                rating("s2", "missed"),
                rating("s3", "missed"),
            ],
        )
        rt, _ = fake_runtime(base, settings)
        with caplog.at_level(logging.DEBUG):
            await check(rt)
            await phases.explain(
                rt, steps=[], ratings={}, supervisor_lang="en", sop_title=f"SOP {MARKER}"
            )
        assert len(usage_lines(caplog)) == 4 and caplog.records
        assert MARKER not in caplog.text


class TestOnTheWire:
    async def test_the_real_clients_usage_metadata_becomes_the_counts(self, settings, caplog):
        reply = [{"text": '{"explanation": "Do it safely."}'}]
        body = wire_reply(
            reply,
            usage={
                "promptTokenCount": 1200,
                "candidatesTokenCount": 85,
                "thoughtsTokenCount": 310,
                "totalTokenCount": 1595,
            },
        )
        rt = runtime_returning(settings, body)

        with caplog.at_level(logging.INFO, logger="sayitback.audit"):
            await phases.explain(rt, steps=[], ratings={}, supervisor_lang="en", sop_title="SOP")

        (line,) = usage_lines(caplog)
        assert line == {
            "event": "usage", "phase": "re_explain", "agent": "re_explain",
            "model": "gemini-3.8-flash-001", "prompt_tokens": 1200, "output_tokens": 85,
            "thinking_tokens": 310, "total_tokens": 1595, "finish_reason": "STOP",
        }  # fmt: skip
