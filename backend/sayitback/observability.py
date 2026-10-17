"""ADK plugins and telemetry: the audit plugin (always on), BigQuery analytics, Cloud Trace.

Nothing here records content. The audit plugin keeps only model ids, timings, call counts and token
counts: one `usage` line per model call, and one `audit` line per run. It also notes which replies
were cut off at the output ceiling (SIB_MAX_OUTPUT_TOKENS), which adk_run.run_phase refuses. The
BigQuery plugin gets a content formatter that drops transcripts, audio and prompt text, and its
STATE_DELTA rows (which would carry them) are denied. Cloud Trace spans are exported with ADK's
message-content capture switched off. An unhandled error goes to Cloud Error Reporting as one JSON
line on stderr with its stack frames and exception type, never its message (report_error).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

from sayitback import __version__
from sayitback.settings import ConfigError, Settings

log = logging.getLogger("sayitback.audit")
REDACTED = "[redacted]"
# Rows that can carry content outside the formatter: STATE_DELTA holds transcripts and ratings, and
# error rows hold str(exception), which a pydantic error fills with the model output it rejected.
# NODE_OUTPUT is every Workflow node's whole output (the transcripts, the ratings): denied, not left
# to the formatter alone.
BQ_DENIED_EVENTS = [
    "STATE_DELTA",
    "LLM_ERROR",
    "AGENT_ERROR",
    "INVOCATION_ERROR",
    "TOOL_ERROR",
    "NODE_ERROR",
    "NODE_OUTPUT",
]
CAPTURE_SPAN_CONTENT_ENV = "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"


def configure_logging() -> None:
    """Show our INFO lines (the audit log) and keep httpx from logging request URLs: a Chat
    webhook URL carries a key and a secret. uvicorn's traceback of an error that escaped the app
    becomes an Error Reporting line instead (ServerTracebackFilter)."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("sayitback").setLevel(logging.INFO)
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    server = logging.getLogger(SERVER_LOGGER)
    if not any(isinstance(f, ServerTracebackFilter) for f in server.filters):
        server.addFilter(ServerTracebackFilter())


# Cloud Error Reporting ---------------------------------------------------------------------------

ERROR_EVENT_TYPE = (
    "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent"
)
SERVER_LOGGER = "uvicorn.error"  # where uvicorn logs an error that escaped the app, message and all
_REPORTED = "_sib_error_reported"


def error_trace(exc: BaseException) -> str:
    """The stack trace in the layout of traceback.format_exc(), which Error Reporting parses for
    Python: the frames (file, line, function, source line), then the exception's type alone. No
    message, its own or a cause's: a message can carry what the request held (a validation error
    echoes its input, a KeyError its key), and a cause is often the error that was being handled."""
    kind = type(exc)
    name = kind.__qualname__
    if kind.__module__ not in ("builtins", "__main__"):
        name = f"{kind.__module__}.{name}"
    frames = traceback.format_list(traceback.extract_tb(exc.__traceback__))
    return "Traceback (most recent call last):\n" + "".join(frames) + name


def error_report(exc: BaseException) -> dict[str, Any]:
    """The Error Reporting entry for an unhandled error. Cloud Run's logging agent reads a JSON line
    on stderr as a structured entry: `severity` becomes the entry's severity, the rest its
    jsonPayload. The service and version are the Cloud Run service and revision, so an error group
    names the revision to roll back from."""
    return {
        "severity": "ERROR",
        "@type": ERROR_EVENT_TYPE,
        "message": error_trace(exc),
        "serviceContext": {
            "service": os.environ.get("K_SERVICE") or "say-it-back-api",
            "version": os.environ.get("K_REVISION") or __version__,
        },
    }


def report_error(exc: BaseException) -> None:
    """Write the error's report to stderr as one line, and mark the exception reported, so the
    server's own traceback of it (with its message) is dropped rather than logged twice."""
    setattr(exc, _REPORTED, True)  # every exception has a __dict__, __slots__ or not
    sys.stderr.write(json.dumps(error_report(exc), sort_keys=True) + "\n")
    sys.stderr.flush()


class ServerTracebackFilter(logging.Filter):
    """On uvicorn's error logger. Starlette re-raises every error its 500 handler answered, and
    uvicorn then logs the full traceback, message included, as plain lines. Such a record is
    dropped: reported once already (main.py's handler), or reported here in the same format when
    the app never saw it (a WebSocket route, the lifespan)."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if exc is None:
            return True
        if not getattr(exc, _REPORTED, False):
            report_error(exc)
        return False


@dataclass(frozen=True)
class AuditSummary:
    phase: str
    calls: Mapping[str, int]
    latency_ms: Mapping[str, float]
    model_ids: Mapping[str, str]
    errors: int
    total_ms: float
    cut_off: tuple[str, ...] = ()  # agents whose reply hit the output ceiling (finish MAX_TOKENS)


class AuditPlugin(BasePlugin):
    """Per-run audit: model id, latency, call count and token usage per agent, and the replies cut
    off at the output ceiling. Never touches content."""

    def __init__(self, phase: str, *, live_model: str | None = None) -> None:
        super().__init__(name="sib_audit")
        self.phase = phase
        self.live_model = live_model  # set for the Live relay: one call per session
        self._t0 = time.perf_counter()
        self._started: dict[str, float] = {}
        self._requested: dict[str, str] = {}
        self._calls: Counter[str] = Counter()
        self._latency: defaultdict[str, float] = defaultdict(float)
        self._models: dict[str, str] = {}
        self._errors = 0
        self._cut_off: list[str] = []

    async def before_model_callback(self, *, callback_context: Any, llm_request: Any) -> None:
        if self.live_model:
            return None
        agent = callback_context.agent_name
        self._started[agent] = time.perf_counter()
        self._requested[agent] = str(getattr(llm_request, "model", "") or "")
        return None

    async def after_model_callback(self, *, callback_context: Any, llm_response: Any) -> None:
        agent = callback_context.agent_name
        if self.live_model or getattr(llm_response, "partial", False):
            return None
        started = self._started.pop(agent, None)
        self._calls[agent] += 1
        if started is not None:
            self._latency[agent] += (time.perf_counter() - started) * 1000
        self._models[agent] = str(
            getattr(llm_response, "model_version", None) or self._requested.get(agent, "")
        )
        record = usage_record(self.phase, agent, self._models[agent], llm_response)
        log.info("usage %s", json.dumps(record, sort_keys=True))
        if getattr(llm_response, "finish_reason", None) == types.FinishReason.MAX_TOKENS:
            self._cut_off.append(agent)
        return None

    async def on_model_error_callback(
        self, *, callback_context: Any, llm_request: Any, error: Exception
    ) -> None:
        self._errors += 1
        return None

    async def before_run_callback(self, *, invocation_context: Any) -> None:
        if self.live_model:
            self._calls[self.phase] = 1
            self._models[self.phase] = self.live_model
        return None

    async def after_run_callback(self, *, invocation_context: Any) -> None:
        log.info("audit %s", json.dumps(audit_record(self.summary()), sort_keys=True))

    def summary(self) -> AuditSummary:
        total_ms = round((time.perf_counter() - self._t0) * 1000, 1)
        latency = {k: round(v, 1) for k, v in self._latency.items()}
        if self.live_model:  # a Live session is one long call
            latency[self.phase] = total_ms
        return AuditSummary(
            phase=self.phase,
            calls=dict(self._calls),
            latency_ms=latency,
            model_ids=dict(self._models),
            errors=self._errors,
            total_ms=total_ms,
            cut_off=tuple(self._cut_off),
        )


def _count(usage: Any, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def usage_record(phase: str, agent: str, model: str, response: Any) -> dict[str, Any]:
    """The `usage` log line for one model call: who called which model, how many tokens it used,
    and why it stopped. Counts only: a value that is not an int is dropped, so nothing the model
    said or was sent can ride along. `output` excludes thinking, which is billed as output too."""
    usage = getattr(response, "usage_metadata", None)
    reason = getattr(response, "finish_reason", None)
    return {
        "event": "usage",
        "phase": phase,
        "agent": agent,
        "model": model,
        "prompt_tokens": _count(usage, "prompt_token_count"),
        "output_tokens": _count(usage, "candidates_token_count"),
        "thinking_tokens": _count(usage, "thoughts_token_count"),
        "total_tokens": _count(usage, "total_token_count"),
        "finish_reason": reason.name if isinstance(reason, types.FinishReason) else None,
    }


def audit_record(s: AuditSummary) -> dict[str, Any]:
    """The audit log line: ids, timings and counts only."""
    return {
        "event": "audit",
        "phase": s.phase,
        "calls": dict(s.calls),
        "latency_ms": dict(s.latency_ms),
        "models": dict(s.model_ids),
        "errors": s.errors,
        "total_ms": s.total_ms,
    }


# BigQuery Agent Analytics ----------------------------------------------------------------------


def redact_content(content: Any, event_type: str) -> Any:
    """BigQueryLoggerConfig.content_formatter: drop transcripts, audio and prompt text.

    Only token counts survive. The plugin treats this as a redaction boundary: whatever it
    returns replaces the logged content, and a failure never falls back to the original.
    """
    try:
        if isinstance(content, Mapping):
            usage = content.get("usage")
            kept = (
                {k: v for k, v in usage.items() if isinstance(v, int | float)}
                if isinstance(usage, Mapping)
                else {}
            )
            return {"redacted": True, **({"usage": kept} if kept else {})}
    except Exception:  # noqa: BLE001 - fail closed
        return REDACTED
    return REDACTED


def make_bq_plugin(settings: Settings) -> BasePlugin | None:
    """Google's BigQuery Agent Analytics plugin, or None when it is off or not installed."""
    if not settings.bq_dataset:
        return None
    project, _, dataset = settings.bq_dataset.partition(".")
    if not project or not dataset:
        raise ConfigError("SIB_BQ_DATASET must look like project.dataset")
    try:  # optional extra: sayitback[bigquery]
        from google.adk.plugins.bigquery_agent_analytics_plugin import (
            BigQueryAgentAnalyticsPlugin,
            BigQueryLoggerConfig,
        )
    except ImportError:
        log.error("SIB_BQ_DATASET is set but the 'bigquery' extra is not installed; skipping")
        return None
    config = BigQueryLoggerConfig(
        content_formatter=redact_content,
        event_denylist=BQ_DENIED_EVENTS,
        log_multi_modal_content=False,
        log_session_metadata=False,  # otherwise every row carries the session state: transcripts
    )
    return BigQueryAgentAnalyticsPlugin(
        project_id=project, dataset_id=dataset, config=config, location=settings.bq_location
    )


def build_plugins(
    settings: Settings, phase: str, *, live: bool = False
) -> tuple[list[BasePlugin], AuditPlugin]:
    """A fresh audit plugin for this run, plus BigQuery analytics when SIB_BQ_DATASET is set."""
    audit = AuditPlugin(phase, live_model=settings.live_model if live else None)
    plugins: list[BasePlugin] = [audit]
    try:
        bq = make_bq_plugin(settings)
    except ConfigError:
        raise
    except Exception:  # noqa: BLE001 - analytics must never break a briefing
        log.exception("could not create the BigQuery analytics plugin; skipping")
        bq = None
    if bq is not None:
        plugins.append(bq)
    return plugins, audit


# Cloud Trace -----------------------------------------------------------------------------------


def _load_trace_api() -> tuple[Any, Any, Any, Any]:
    import google.auth
    from google.adk.telemetry.google_cloud import get_gcp_exporters, get_gcp_resource
    from google.adk.telemetry.setup import maybe_set_otel_providers

    return google.auth.default, get_gcp_exporters, get_gcp_resource, maybe_set_otel_providers


def setup_cloud_trace() -> bool:
    """Wire ADK's OpenTelemetry to Cloud Trace (SIB_TRACE_TO_CLOUD). Returns whether it did."""
    os.environ.setdefault(CAPTURE_SPAN_CONTENT_ENV, "false")  # no prompts or transcripts in spans
    try:
        auth_default, get_exporters, get_resource, set_providers = _load_trace_api()
        credentials, project_id = auth_default()
        hooks = get_exporters(enable_cloud_tracing=True, google_auth=(credentials, project_id))
        set_providers([hooks], otel_resource=get_resource(project_id))
    except Exception:  # noqa: BLE001 - tracing must never stop the service
        log.exception("Cloud Trace export could not be set up; continuing without it")
        return False
    return True
