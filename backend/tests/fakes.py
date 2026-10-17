"""Fakes for the model layer: no test touches the network.

FakeLlm stands in for Gemini Flash under ADK's real Runner. The Live fakes are in fake_live.py.
"""

from __future__ import annotations

import asyncio
import copy
import json
import math
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

from sayitback.backends import RefusalRetry, refusal_retry
from sayitback.llm_schemas import (
    BackOut,
    ExtractOut,
    HazardOut,
    JudgeOut,
    ReExplainOut,
    ScriptOut,
    SpokenText,
    TranscribeOut,
)
from sayitback.runtime import Runtime
from sayitback.settings import Settings
from sayitback.wav import make_wav
from tests.fake_live import FakeLiveLlm

# Audio -------------------------------------------------------------------------------------


def tone_wav(seconds: float = 2.0, rate: int = 16000, amp: int = 4000) -> bytes:
    n = int(seconds * rate)
    pcm = b"".join(
        struct.pack("<h", int(amp * math.sin(2 * math.pi * 220 * i / rate))) for i in range(n)
    )
    return make_wav(pcm, rate)


def silent_wav(seconds: float = 2.0, rate: int = 16000) -> bytes:
    return make_wav(b"\x00\x00" * int(seconds * rate), rate)


# Flash -------------------------------------------------------------------------------------


@dataclass
class Seen:
    schema: type | None
    system: str
    contents: list[types.Content]
    thinking_level: str | None
    temperature: float | None
    tools: Any
    max_output_tokens: int | None = None

    @property
    def has_audio(self) -> bool:
        return any(p.inline_data for c in self.contents for p in (c.parts or []))

    @property
    def text(self) -> str:
        return "\n".join(p.text or "" for c in self.contents for p in (c.parts or []))


def usage(prompt: int, output: int, thinking: int) -> types.GenerateContentResponseUsageMetadata:
    """What a real response reports; `output` excludes thinking, as the API's does."""
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt,
        candidates_token_count=output,
        thoughts_token_count=thinking,
        total_token_count=prompt + output + thinking,
    )


@dataclass
class Reply:
    """A canned model reply with the metadata a real response carries: why it stopped, and its
    usage. `payload` is a dict (sent as JSON), a str (sent as is) or None (no content at all, as
    when thinking used up the whole ceiling). `thought` makes the text thinking, not an answer.
    `blocked` is a prompt the API refused: no candidate at all, only `prompt_feedback`, as Agent
    Platform answers "prompt is blocked due to safety" whatever the safety settings."""

    payload: Any = None
    finish_reason: types.FinishReason = types.FinishReason.STOP
    usage: types.GenerateContentResponseUsageMetadata | None = field(
        default_factory=lambda: usage(100, 50, 20)
    )
    thought: bool = False
    blocked: types.BlockedReason | None = None

    def response(self, model_version: str = "fake-flash-001") -> types.GenerateContentResponse:
        if self.blocked is not None:
            feedback = types.GenerateContentResponsePromptFeedback(
                block_reason=self.blocked, block_reason_message="Prompt is blocked due to safety."
            )
            return types.GenerateContentResponse(
                prompt_feedback=feedback, usage_metadata=self.usage, model_version=model_version
            )
        content = None
        if self.payload is not None:
            text = self.payload
            if not isinstance(text, str):
                text = json.dumps(text, ensure_ascii=False)
            content = types.Content(
                role="model", parts=[types.Part(text=text, thought=self.thought or None)]
            )
        candidate = types.Candidate(content=content, finish_reason=self.finish_reason)
        return types.GenerateContentResponse(
            candidates=[candidate], usage_metadata=self.usage, model_version=model_version
        )


class _FakeFlash(BaseLlm):
    model: str = "fake-flash"
    handler: Any = Field(default=None, exclude=True)
    seen: list[Any] = Field(default_factory=list, exclude=True)
    delay: float = Field(default=0.0, exclude=True)  # simulated model latency
    version: str = Field(default="fake-flash-001", exclude=True)  # the id the "API" returns

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncIterator[LlmResponse]:
        cfg = llm_request.config
        level = cfg.thinking_config.thinking_level if cfg.thinking_config else None
        seen = Seen(
            schema=cfg.response_schema,
            system=str(cfg.system_instruction or ""),
            contents=copy.deepcopy(llm_request.contents),
            thinking_level=getattr(level, "value", level),
            temperature=cfg.temperature,
            tools=cfg.tools,
            max_output_tokens=cfg.max_output_tokens,
        )
        self.seen.append(seen)
        payload = self.handler(seen)
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(payload, Exception):
            raise payload
        reply = payload if isinstance(payload, Reply) else Reply(payload)
        yield LlmResponse.create(reply.response(self.version))  # as ADK's Gemini model converts


class FakeLlm(RefusalRetry, _FakeFlash):
    """The Flash fake with production's refusal retry (backends.RefusalRetry): a blocked reply is
    asked for again, `refusal_attempts` calls in all (1, unless fake_runtime sets it)."""

    refusal_attempts: int = Field(default=1, exclude=True)
    refusal_backoff_s: float = Field(default=0.0, exclude=True)


def rating(step_id: str, verdict: str, quote: str = "", confidence: float = 0.9) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "verdict": verdict,
        "quote": quote,
        "quote_translation": quote and "translation",
        "reason": f"{verdict} reason",
        "confidence": confidence,
    }


def transcript(qid: str, original: str, lang: str = "ta", flags: list[str] | None = None) -> dict:
    return {
        "question_id": qid,
        "original": original,
        "detected_lang": lang,
        "translation": "translated",
        "flags": flags or [],
    }


@dataclass
class Scenario:
    """Canned model outputs for the whole workflow. Override a field to steer a test."""

    extract: dict[str, Any] = field(default_factory=lambda: PANEL_EXTRACT)
    script: dict[str, Any] = field(default_factory=lambda: PANEL_SCRIPT)
    back: dict[str, Any] = field(default_factory=lambda: PANEL_BACK)
    explanation: str = "Switch it off, lock it, and test it dead."
    transcripts: list[dict] = field(default_factory=list)
    judge_a: list[dict] = field(default_factory=list)
    judge_b: list[dict] | None = None  # None: same as judge A
    transcription_text: str = "Isolate the breaker."
    hazard: dict[str, Any] = field(default_factory=lambda: dict(HAZARD_REPORT))
    script_drafts: list[dict[str, Any]] = field(default_factory=list)  # write_script's next
    # replies, used up in turn; once they are gone (or if there are none) the reply is `script`

    def handler(self, seen: Seen) -> Any:
        schema = seen.schema
        if schema is ExtractOut:
            return self.extract
        if schema is ScriptOut:
            return self.script_drafts.pop(0) if self.script_drafts else self.script
        if schema is BackOut:
            return self.back
        if schema is ReExplainOut:
            return {"explanation": self.explanation}
        if schema is SpokenText:
            return {"text": self.transcription_text}
        if schema is HazardOut:
            return self.hazard
        if schema is TranscribeOut:
            return {"transcripts": self.transcripts}
        if schema is JudgeOut:
            b = self.judge_a if self.judge_b is None else self.judge_b
            return {"ratings": self.judge_a if seen.has_audio else b}
        raise AssertionError(f"unexpected schema {schema}")


HAZARD_REPORT = {
    "original": "கிரேன் கயிறு அறுந்து போயிருக்கு",
    "detected_lang": "ta",
    "translation": "The crane sling is torn.",
}

PANEL_EXTRACT = {
    "steps": [
        {"text": "Switch off the supply at the breaker", "hazard": "Electric shock",
         "essential": ["switch off at the breaker"], "source": "instruction", "sop_quote": "",
         "speakable": True},
        {"text": "Lock and tag the breaker", "hazard": "Someone switches it back on",
         "essential": ["put a lock on the breaker"], "source": "both",
         "sop_quote": "Fit your personal lock and a danger tag to the breaker", "speakable": True},
        {"text": "Test that it is dead before touching", "hazard": "Back-feed",
         "essential": ["test with a tester before touching"], "source": "sop",
         "sop_quote": "Before touching any conductor, test it dead with an approved voltage tester.",
         "speakable": True},
    ],
    "conflicts": [{"step_number": 3, "message": "The SOP also asks to prove the tester."}],
}  # fmt: skip

PANEL_SCRIPT = {
    "sentences": ["பிரேக்கரை ஆஃப் செய்யுங்கள்.", "பிரேக்கரில் லாக் போடுங்கள்.", "டெஸ்டர் வைத்து செக் செய்யுங்கள்."],
    "step_map": [
        {"step_id": "s1", "sentence_indices": [0]},
        {"step_id": "s2", "sentence_indices": [1]},
        {"step_id": "s3", "sentence_indices": [2]},
    ],
    "questions": [
        {"text": "பேனலைத் திறப்பதற்கு முன் என்ன செய்வீர்கள்?", "step_ids": ["s1", "s2", "s3"]},
        {"text": "கரண்ட் இல்லை என்று எப்படி தெரியும்?", "step_ids": ["s3"]},
    ],
    "closing": "நன்றி. மேற்பார்வையாளருக்காகக் காத்திருங்கள்.",
}  # fmt: skip


def panel_script(**changes: Any) -> dict[str, Any]:
    """PANEL_SCRIPT (3 steps, one sentence each, 2 questions) with `changes` applied."""
    return copy.deepcopy(PANEL_SCRIPT) | changes


PANEL_BACK = {
    "sentences": ["Switch the breaker off.", "Put a lock on the breaker.", "Check with the tester."],
    "questions": [
        {"id": "q1", "text": "What will you do before you open the panel?"},
        {"id": "q2", "text": "How will you know there is no current?"},
    ],
}  # fmt: skip


def fake_runtime(
    scenario: Scenario | None = None,
    settings: Settings | None = None,
    live: BaseLlm | None = None,
    tts_client: Any = None,
    live_made: list[Any] | None = None,
    judge_b: BaseLlm | None = None,
) -> tuple[Runtime, FakeLlm]:
    """`live_made` collects every FakeLiveLlm the runtime builds (one per Live socket). `judge_b`
    is judge B's own model (SIB_JUDGE_B_MODEL); without it judge B runs on the Flash fake."""
    scenario = scenario or Scenario()
    settings = settings or Settings()
    llm = FakeLlm(handler=scenario.handler, **refusal_retry(settings))

    def live_factory(on_connected: Any) -> BaseLlm:
        model = live or FakeLiveLlm(on_connected=on_connected)
        if live_made is not None:
            live_made.append(model)
        return model

    rt = Runtime(
        settings=settings,
        flash=llm,
        live_factory=live_factory,
        tts_client_factory=lambda: tts_client,
        judge_b_llm=judge_b,
    )
    return rt, llm


# TTS ---------------------------------------------------------------------------------------


class FakeTtsClient:
    """google-genai client stand-in: aio.models.generate_content returns 24 kHz PCM."""

    def __init__(
        self,
        pcm: bytes = b"\x01\x00" * 2400,
        mime: str = "audio/L16;codec=pcm;rate=24000",
        finish_reason: types.FinishReason | None = None,
    ):
        self.calls: list[dict[str, Any]] = []
        self._pcm, self._mime = pcm, mime
        self.finish_reason = finish_reason  # MAX_TOKENS: the reply was cut off at the ceiling
        self.aio = self
        self.models = self

    async def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.calls.append({"model": model, "text": contents, "config": config})
        blob = types.Blob(data=self._pcm, mime_type=self._mime)
        part = types.Part(inline_data=blob)
        content = types.Content(role="model", parts=[part])
        candidate = types.Candidate(content=content, finish_reason=self.finish_reason)
        return types.GenerateContentResponse(candidates=[candidate])
