"""Audit plugin, BigQuery analytics wiring with its redacting formatter, and Cloud Trace wiring.

BigQuery and Cloud Trace need optional extras and cloud credentials, so they are verified here as
wiring only (the right classes, arguments and redaction); they have not run against Google.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import types as pytypes
from types import SimpleNamespace

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from sayitback import observability as obs
from sayitback.settings import ConfigError, Settings

SECRET_TEXT = "TRANSCRIPT-OF-THE-WORKER-ANSWER"
PROMPT_TEXT = "SYSTEM-PROMPT-WITH-STEP-TEXT"


class TestAuditPlugin:
    def ctx(self, name):
        return SimpleNamespace(agent_name=name)

    async def run_call(
        self, plugin, agent="judge_a", model="gemini-3.8-flash", version=None, partial=False
    ):
        await plugin.before_model_callback(
            callback_context=self.ctx(agent),
            llm_request=SimpleNamespace(model=model, contents=[SECRET_TEXT]),
        )
        await plugin.after_model_callback(
            callback_context=self.ctx(agent),
            llm_response=SimpleNamespace(
                model_version=version, partial=partial, content=SECRET_TEXT
            ),
        )

    async def test_it_counts_calls_and_times_them_per_agent(self):
        plugin = obs.AuditPlugin("check_answer")
        await self.run_call(plugin, "blind_transcriber", version="gemini-3.8-flash-001")
        await self.run_call(plugin, "judge_a", version=None)
        await self.run_call(plugin, "judge_a", version=None)
        s = plugin.summary()
        assert s.calls == {"blind_transcriber": 1, "judge_a": 2}
        assert s.model_ids == {
            "blind_transcriber": "gemini-3.8-flash-001",
            "judge_a": "gemini-3.8-flash",
        }  # falls back to the requested id
        assert set(s.latency_ms) == {"blind_transcriber", "judge_a"} and s.total_ms >= 0

    async def test_partial_streaming_chunks_are_not_counted(self):
        plugin = obs.AuditPlugin("x")
        await self.run_call(plugin, partial=True)
        assert plugin.summary().calls == {}

    async def test_errors_are_counted(self):
        plugin = obs.AuditPlugin("x")
        await plugin.on_model_error_callback(
            callback_context=self.ctx("a"), llm_request=None, error=RuntimeError("x")
        )
        assert plugin.summary().errors == 1

    async def test_the_log_line_has_phase_model_latency_and_count_but_no_content(self, caplog):
        plugin = obs.AuditPlugin("check_answer")
        await self.run_call(plugin, "judge_a")
        with caplog.at_level(logging.INFO, logger="sayitback.audit"):
            await plugin.after_run_callback(invocation_context=None)
        line = next(
            r.getMessage()
            for r in caplog.records
            if r.name == "sayitback.audit" and r.getMessage().startswith("audit ")
        )  # the run's one audit line; each model call also logs a `usage` line (test_usage_log.py)
        record = json.loads(line.removeprefix("audit "))
        assert record["event"] == "audit" and record["phase"] == "check_answer"
        assert record["calls"] == {"judge_a": 1} and "judge_a" in record["latency_ms"]
        assert record["models"] == {"judge_a": "gemini-3.8-flash"}
        assert SECRET_TEXT not in line

    async def test_a_live_session_is_one_call_with_the_live_model(self):
        plugin = obs.AuditPlugin("briefer_live", live_model="gemini-3.8-live")
        await plugin.before_run_callback(invocation_context=None)
        await self.run_call(
            plugin, "briefer_live"
        )  # per-chunk model callbacks are ignored in live mode
        s = plugin.summary()
        assert s.calls == {"briefer_live": 1} and s.model_ids == {"briefer_live": "gemini-3.8-live"}
        assert "briefer_live" in s.latency_ms

    def test_the_audit_plugin_is_always_on(self):
        plugins, audit = obs.build_plugins(Settings(), "check_answer")
        assert plugins == [audit]


class TestContentFormatter:
    def test_prompt_text_audio_and_transcripts_are_dropped(self):
        request = LlmRequest(
            model="gemini-3.8-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(text=SECRET_TEXT),
                        types.Part.from_bytes(data=b"AUDIOBYTES", mime_type="audio/wav"),
                    ],
                )
            ],
        )
        request.config.system_instruction = PROMPT_TEXT
        content = types.Content(
            role="user",
            parts=[
                types.Part(text=SECRET_TEXT),
                types.Part.from_bytes(data=b"AUDIOBYTES", mime_type="audio/wav"),
            ],
        )
        cases = [
            request,
            content,
            SECRET_TEXT,
            [SECRET_TEXT, PROMPT_TEXT],
            {"response": SECRET_TEXT, "usage": {"prompt": 10, "completion": 5, "total": 15}},
            {"nested": {"text": SECRET_TEXT}},
            {"error_traceback": f"boom {SECRET_TEXT}"},
            None,
        ]
        for case in cases:
            out = json.dumps(obs.redact_content(case, "LLM_REQUEST"), default=str)
            for banned in (SECRET_TEXT, PROMPT_TEXT, "AUDIOBYTES"):
                assert banned not in out

    def test_token_counts_survive_for_analytics(self):
        out = obs.redact_content(
            {"response": SECRET_TEXT, "usage": {"prompt": 10, "completion": 5, "weird": "text"}},
            "LLM_RESPONSE",
        )
        assert out == {"redacted": True, "usage": {"prompt": 10, "completion": 5}}

    def test_it_never_raises(self):
        class Hostile(dict):
            def get(self, *a):
                raise RuntimeError("hostile")

        assert obs.redact_content(Hostile(), "X") == obs.REDACTED

    def test_the_result_types_are_ones_the_plugin_accepts(self):
        for case in ({"a": 1}, "x", [1], None, object()):
            assert isinstance(obs.redact_content(case, "E"), str | dict | list | type(None))


@pytest.fixture
def fake_bq(monkeypatch):
    """Stand in for google.adk.plugins.bigquery_agent_analytics_plugin (needs the bigquery extra)."""
    created = []

    class Config:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Plugin:
        name = "bigquery_agent_analytics"

        def __init__(self, **kwargs):
            created.append(kwargs)

    module = pytypes.ModuleType("google.adk.plugins.bigquery_agent_analytics_plugin")
    module.BigQueryAgentAnalyticsPlugin, module.BigQueryLoggerConfig = Plugin, Config
    monkeypatch.setitem(sys.modules, "google.adk.plugins.bigquery_agent_analytics_plugin", module)
    return created


class TestBigQueryPlugin:
    def test_off_by_default(self):
        assert obs.make_bq_plugin(Settings()) is None

    def test_sib_bq_dataset_adds_the_adk_plugin_with_the_redacting_formatter(self, fake_bq):
        settings = Settings(bq_dataset="my-proj.say_it_back", bq_location="asia-south1")
        plugins, audit = obs.build_plugins(settings, "check_answer")
        assert len(plugins) == 2 and plugins[0] is audit
        (kwargs,) = fake_bq
        assert (kwargs["project_id"], kwargs["dataset_id"], kwargs["location"]) == (
            "my-proj",
            "say_it_back",
            "asia-south1",
        )
        config = kwargs["config"]
        assert config.content_formatter is obs.redact_content
        assert "STATE_DELTA" in config.event_denylist  # state carries transcripts and ratings
        assert config.log_multi_modal_content is False

    def test_a_malformed_dataset_is_a_config_error(self):
        with pytest.raises(ConfigError, match="project.dataset"):
            obs.make_bq_plugin(Settings(bq_dataset="just-a-name"))

    def test_without_the_extra_the_service_still_runs(self, caplog):
        with caplog.at_level(logging.ERROR, logger="sayitback.audit"):
            plugins, audit = obs.build_plugins(Settings(bq_dataset="p.d"), "x")
        assert plugins == [audit]
        assert "bigquery' extra is not installed" in caplog.text

    def test_a_plugin_that_fails_to_build_never_breaks_a_briefing(self, monkeypatch):
        monkeypatch.setattr(
            obs, "make_bq_plugin", lambda s: (_ for _ in ()).throw(RuntimeError("no creds"))
        )
        plugins, audit = obs.build_plugins(Settings(bq_dataset="p.d"), "x")
        assert plugins == [audit]


class TestCloudTrace:
    def test_sib_trace_to_cloud_wires_adk_otel_to_cloud_trace(self, monkeypatch):
        calls = {}
        creds = object()
        monkeypatch.setattr(
            obs,
            "_load_trace_api",
            lambda: (
                lambda: (creds, "my-proj"),
                lambda **kw: calls.setdefault("exporters", kw) and "hooks",
                lambda project: f"resource:{project}",
                lambda hooks, otel_resource: calls.update(providers=(hooks, otel_resource)),
            ),
        )
        monkeypatch.delenv(obs.CAPTURE_SPAN_CONTENT_ENV, raising=False)
        assert obs.setup_cloud_trace() is True
        assert calls["exporters"] == {
            "enable_cloud_tracing": True,
            "google_auth": (creds, "my-proj"),
        }
        assert calls["providers"] == (["hooks"], "resource:my-proj")
        assert (
            os.environ[obs.CAPTURE_SPAN_CONTENT_ENV] == "false"
        )  # no prompts or transcripts in spans
        monkeypatch.delenv(obs.CAPTURE_SPAN_CONTENT_ENV)

    def test_an_explicit_capture_setting_is_respected(self, monkeypatch):
        monkeypatch.setenv(obs.CAPTURE_SPAN_CONTENT_ENV, "true")
        monkeypatch.setattr(
            obs, "_load_trace_api", lambda: (_ for _ in ()).throw(ImportError("extra missing"))
        )
        assert obs.setup_cloud_trace() is False
        assert os.environ[obs.CAPTURE_SPAN_CONTENT_ENV] == "true"

    def test_a_failure_to_set_up_never_stops_the_service(self, monkeypatch, caplog):
        monkeypatch.setattr(
            obs, "_load_trace_api", lambda: (_ for _ in ()).throw(RuntimeError("no adc"))
        )
        monkeypatch.delenv(obs.CAPTURE_SPAN_CONTENT_ENV, raising=False)
        assert obs.setup_cloud_trace() is False
        monkeypatch.delenv(obs.CAPTURE_SPAN_CONTENT_ENV, raising=False)

    def test_the_real_adk_entry_points_exist_with_the_signatures_we_call(self):
        auth_default, get_exporters, get_resource, set_providers = obs._load_trace_api()
        import inspect

        assert "enable_cloud_tracing" in inspect.signature(get_exporters).parameters
        assert "google_auth" in inspect.signature(get_exporters).parameters
        assert "otel_resource" in inspect.signature(set_providers).parameters
        assert callable(get_resource) and callable(auth_default)


class TestBigQueryPrivacyAgainstTheRealConfigClass:
    """The extra is not installed here, so the real BigQueryLoggerConfig cannot be imported. Its
    source can be read, so the argument names we pass are checked against the installed ADK."""

    @staticmethod
    def real_config_fields() -> dict[str, object]:
        import ast
        from pathlib import Path

        import google.adk.plugins as plugins

        source = Path(plugins.__file__).parent / "bigquery_agent_analytics_plugin.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        cls = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BigQueryLoggerConfig"
        )
        return {
            n.target.id: (ast.unparse(n.value) if n.value else None)
            for n in cls.body
            if isinstance(n, ast.AnnAssign)
        }

    def test_every_argument_we_pass_exists_in_the_installed_adk(self, fake_bq):
        obs.make_bq_plugin(Settings(bq_dataset="p.d"))
        passed = set(vars(fake_bq[0]["config"]))
        assert passed <= set(self.real_config_fields()), passed - set(self.real_config_fields())

    def test_session_state_is_not_logged_because_it_holds_the_transcripts(self, fake_bq):
        obs.make_bq_plugin(Settings(bq_dataset="p.d"))
        config = fake_bq[0]["config"]
        assert config.log_session_metadata is False
        assert (
            self.real_config_fields()["log_session_metadata"] == "True"
        )  # ADK's default is to log it

    def test_rows_that_can_echo_content_are_denied(self, fake_bq):
        obs.make_bq_plugin(Settings(bq_dataset="p.d"))
        denied = set(fake_bq[0]["config"].event_denylist)
        assert {
            "STATE_DELTA",
            "LLM_ERROR",
            "AGENT_ERROR",
            "INVOCATION_ERROR",
            "TOOL_ERROR",
            "NODE_ERROR",
        } <= denied
