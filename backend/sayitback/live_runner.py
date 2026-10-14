"""ADK side of the Live relay: the briefer's session, its RunConfig and its state.

The briefer's state holds the worker-language script and nothing else: no step, essential,
hazard or rating ever reaches the model. `open_adk_session` is the default LiveOpener; tests
pass their own.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps import App
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from sayitback import catalog
from sayitback.adk_common import INPUT_KEY
from sayitback.agents.briefer_live.agent import NAME, build_agent
from sayitback.check_state import sentences_of
from sayitback.models import Script
from sayitback.observability import build_plugins
from sayitback.runtime import Runtime
from sayitback.settings import Settings

USER_ID = "sayitback"


class LiveHandle(Protocol):
    def events(self, queue: LiveRequestQueue, config: RunConfig) -> AsyncIterator[Event]: ...

    async def close(self) -> None: ...


LiveOpener = Callable[[Runtime, dict[str, Any], Callable[[], None]], Awaitable[LiveHandle]]


def briefer_state(script: Script, worker_lang: str) -> dict[str, Any]:
    """Script text only. Question step ids and the step map are deliberately left out."""
    return {
        "lang_name": catalog.lang_name(worker_lang),
        "instruction": " ".join(sentences_of(script.instruction)),
        "questions": [{"id": q.id, "text": q.text} for q in script.questions],
        "closing": script.closing,
    }


def run_config(settings: Settings, *, manual: bool) -> RunConfig:
    """BIDI audio out in the SIB_LIVE_VOICE voice, both transcriptions on, nothing saved.

    Manual turn-taking disables automatic activity detection: the relay marks the answer window
    with activity start and end, so the model cannot reply mid-answer.
    """
    voice = types.PrebuiltVoiceConfig(voice_name=settings.live_voice)
    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=voice)
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        save_live_blob=False,
        realtime_input_config=(
            types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            )
            if manual
            else None
        ),
    )


class AdkHandle:
    """One in-memory ADK session and Runner for one socket."""

    def __init__(self, runner: Runner, session_id: str) -> None:
        self._runner = runner
        self._session_id = session_id

    def events(self, queue: LiveRequestQueue, config: RunConfig) -> AsyncIterator[Event]:
        return self._runner.run_live(
            user_id=USER_ID,
            session_id=self._session_id,
            live_request_queue=queue,
            run_config=config,
        )

    async def close(self) -> None:
        await self._runner.close()


async def open_adk_session(
    rt: Runtime, state: dict[str, Any], on_connected: Callable[[], None]
) -> LiveHandle:
    """Build the briefer agent (Live model, `on_connected` fires at setup complete) in a Runner."""
    plugins, _audit = build_plugins(rt.settings, NAME, live=True)
    app = App(name=NAME, root_agent=build_agent(rt, on_connected), plugins=plugins)
    sessions = InMemorySessionService()
    session_id = uuid.uuid4().hex
    await sessions.create_session(
        app_name=NAME, user_id=USER_ID, session_id=session_id, state={INPUT_KEY: state}
    )
    return AdkHandle(Runner(app=app, session_service=sessions), session_id)
