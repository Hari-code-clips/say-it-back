"""Run one ADK phase: a Runner and App built for this request, over an in-memory session.

ADK sessions are deliberately in-memory so audio never lands in a persistent session. The
briefing state lives in the store. A 429, a 5xx or an attempt cut off at SIB_CALL_TIMEOUT_S is
retried inside the model call, up to SIB_RETRY_ATTEMPTS in all (backends.retry_options), and the
phase timeout bounds the lot; what still fails maps to 503 upstream_busy or 502 upstream_error. A
reply that hit the output ceiling (SIB_MAX_OUTPUT_TOKENS) is a 502 too, whatever else ADK made of
it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import BaseNode
from google.genai import types

from sayitback.adk_common import INPUT_KEY
from sayitback.errors import (
    CUT_OFF_MESSAGE,
    ApiError,
    UpstreamError,
    as_upstream_error,
    safe_describe,
)
from sayitback.observability import AuditPlugin, AuditSummary, build_plugins
from sayitback.runtime import Runtime

log = logging.getLogger("sayitback.run")
USER_ID = "sayitback"
RUN_TEXT = "Run the task described in your instructions."


@dataclass(frozen=True)
class PhaseRun:
    state: dict[str, Any]
    audit: AuditSummary


def user_message(parts: list[types.Part] | None = None) -> types.Content:
    """The run's user message. Gemini 3.8 wants a non-empty text part in the final user turn."""
    return types.Content(role="user", parts=[*(parts or []), types.Part(text=RUN_TEXT)])


def _cut_off(app_name: str, agents: Sequence[str]) -> UpstreamError:
    """A reply that hit the output ceiling stopped mid-answer, or (a thinking model) before it
    wrote any: it is never used. The log names the agents and nothing the model wrote."""
    log.warning("phase %s: reply cut off at the output ceiling (%s)", app_name, ", ".join(agents))
    return UpstreamError(CUT_OFF_MESSAGE)


def _failure(app_name: str, audit: AuditPlugin, exc: Exception) -> ApiError:
    """The API error for an exception raised while a phase ran. A cut-off reply is the likelier
    cause when there is one: ADK then fails to parse the half-written JSON."""
    if cut := audit.summary().cut_off:
        return _cut_off(app_name, cut)
    log.warning("phase %s failed: %s", app_name, safe_describe(exc))
    return as_upstream_error(exc)


async def run_phase(
    rt: Runtime,
    root_agent: BaseNode,
    *,
    app_name: str,
    phase_input: dict[str, Any],
    parts: list[types.Part] | None = None,
) -> PhaseRun:
    """Run `root_agent` (an agent, or a Workflow graph) once and return the final session state
    plus the audit summary."""
    plugins, audit = build_plugins(rt.settings, app_name)
    app = App(name=app_name, root_agent=root_agent, plugins=plugins)
    sessions = InMemorySessionService()
    runner = Runner(app=app, session_service=sessions)
    session_id = uuid.uuid4().hex
    try:
        await sessions.create_session(
            app_name=app_name,
            user_id=USER_ID,
            session_id=session_id,
            state={INPUT_KEY: phase_input},
        )
        async with asyncio.timeout(rt.settings.phase_timeout_s):
            async for _event in runner.run_async(
                user_id=USER_ID, session_id=session_id, new_message=user_message(parts)
            ):
                pass
        final = await sessions.get_session(
            app_name=app_name, user_id=USER_ID, session_id=session_id
        )
    except ApiError:
        raise
    except Exception as exc:
        raise _failure(app_name, audit, exc) from None
    finally:
        await runner.close()
    summary = audit.summary()
    if summary.cut_off:  # ADK may have parsed what it got, or made nothing of it: either way, no
        raise _cut_off(app_name, summary.cut_off)
    if final is None:
        raise UpstreamError("The session ended without a result.")
    return PhaseRun(state=dict(final.state), audit=summary)
