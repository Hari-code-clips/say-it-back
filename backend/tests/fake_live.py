"""Fakes for Gemini Live: a scripted connection, the briefer model, a runner handle, a socket.

FakeLiveLlm stands in for Gemini Live under ADK's real `Runner.run_live`: its connection records
everything the relay sends and replays scripted server messages. FakeRunnerHandle consumes the
real LiveRequestQueue, so `requests` is exactly what would have reached the model.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.models.base_llm_connection import BaseLlmConnection
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field
from starlette.datastructures import Address, Headers


def audio_response(n_bytes: int = 960) -> LlmResponse:
    blob = types.Blob(data=b"\x02\x00" * (n_bytes // 2), mime_type="audio/pcm;rate=24000")
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(inline_data=blob)]))


def out_text(text: str, finished: bool) -> LlmResponse:
    return LlmResponse(
        output_transcription=types.Transcription(text=text, finished=finished),
        partial=not finished,
    )


def in_text(text: str) -> LlmResponse:
    return LlmResponse(input_transcription=types.Transcription(text=text, finished=True))


TURN_COMPLETE = LlmResponse(turn_complete=True)
Reply = Callable[[str], list[LlmResponse]]


def default_reply(text: str) -> list[LlmResponse]:
    """What the fake briefer 'says' for a cue: audio, a partial and final caption, turn end."""
    spoken = f"said:{text}"
    return [audio_response(), out_text(spoken[:6], False), out_text(spoken, True), TURN_COMPLETE]


class FakeConnection(BaseLlmConnection):
    def __init__(self, reply: Reply, heard: str) -> None:
        self.sent_text: list[str] = []
        self.realtime: list[Any] = []
        self.closed = False
        self._reply, self._heard = reply, heard
        self._queue: asyncio.Queue[LlmResponse | None] = asyncio.Queue()

    async def send_history(self, history: list[types.Content]) -> None:
        pass

    async def send_content(self, content: types.Content) -> None:
        await self._send_content(content)

    async def _send_content(self, content: types.Content, *, partial: bool = False) -> None:
        text = "".join(p.text or "" for p in (content.parts or []))
        self.sent_text.append(text)
        for response in self._reply(text):
            self._queue.put_nowait(response)

    async def send_realtime(self, input: Any) -> None:
        self.realtime.append(input)
        if isinstance(input, types.ActivityEnd) or getattr(input, "audio_stream_end", False):
            for response in [in_text(self._heard), *self._reply("THANKS")]:
                self._queue.put_nowait(response)

    async def receive(self) -> AsyncIterator[LlmResponse]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item
            if item.turn_complete:
                return

    async def close(self) -> None:
        self.closed = True
        self._queue.put_nowait(None)


class FakeLiveLlm(BaseLlm):
    """Gemini Live stand-in under ADK's real Runner.run_live."""

    model: str = "fake-live"
    on_connected: Any = Field(default=None, exclude=True)
    reply: Any = Field(default=default_reply, exclude=True)
    heard: str = "heard-answer"
    reject_manual: bool = False
    requests: list[Any] = Field(default_factory=list, exclude=True)
    connections: list[Any] = Field(default_factory=list, exclude=True)

    async def generate_content_async(self, llm_request, stream=False):  # pragma: no cover
        raise NotImplementedError("the fake Live model only streams")
        yield

    @contextlib.asynccontextmanager
    async def connect(self, llm_request: LlmRequest) -> AsyncIterator[BaseLlmConnection]:
        self.requests.append(copy.deepcopy(llm_request))
        config = llm_request.live_connect_config
        detection = (
            config.realtime_input_config.automatic_activity_detection
            if (config.realtime_input_config)
            else None
        )
        if self.reject_manual and detection is not None and detection.disabled:
            raise ConnectionError("1007 invalid argument")
        connection = FakeConnection(self.reply, self.heard)
        self.connections.append(connection)
        if self.on_connected:
            self.on_connected()
        try:
            yield connection
        finally:
            await connection.close()


# A fake ADK runner for the relay's protocol tests --------------------------------------------


def to_event(response: LlmResponse) -> Event:
    return Event(
        invocation_id="i",
        author="briefer_live",
        content=response.content,
        output_transcription=response.output_transcription,
        input_transcription=response.input_transcription,
        turn_complete=response.turn_complete,
        interrupted=response.interrupted,
        partial=response.partial,
    )


class FakeRunnerHandle:
    """Consumes the LiveRequestQueue the way Runner.run_live does and replays scripted events.

    `requests` records everything the relay put on the queue, so a test can prove that a rejected
    frame never reached the model.
    """

    def __init__(self, on_connected: Callable[[], None], state: dict[str, Any], **options: Any):
        self.on_connected, self.state = on_connected, state
        self.reply: Reply = options.get("reply", default_reply)
        self.heard: str = options.get("heard", "heard-answer")
        self.fail_manual: bool = options.get("fail_manual", False)
        self.fail_always: bool = options.get("fail_always", False)
        self.crash_after_cues: int | None = options.get("crash_after_cues")
        self.delay: float = options.get("delay", 0.0)  # pause before each scripted event
        self.requests: list[Any] = []
        self.configs: list[Any] = []
        self.closed = False

    @property
    def texts(self) -> list[str]:
        return ["".join(p.text or "" for p in r.content.parts) for r in self.requests if r.content]

    async def events(self, queue: Any, config: Any) -> AsyncIterator[Event]:
        self.configs.append(config)
        manual = config.realtime_input_config is not None
        if self.fail_always or (manual and self.fail_manual):
            raise ConnectionError("1007 invalid argument")
        self.on_connected()
        while True:
            request = await queue.get()
            self.requests.append(request)
            if request.close:
                return
            if request.content:
                if self.crash_after_cues is not None and len(self.texts) > self.crash_after_cues:
                    raise RuntimeError("the live model stream broke")
                for response in self.reply("".join(p.text or "" for p in request.content.parts)):
                    if self.delay:
                        await asyncio.sleep(self.delay)
                    yield to_event(response)
            elif request.activity_end or request.audio_stream_end:
                for response in [in_text(self.heard), *self.reply("THANKS")]:
                    yield to_event(response)

    async def close(self) -> None:
        self.closed = True


def fake_opener(handles: list[FakeRunnerHandle], **options: Any) -> Any:
    async def opener(
        rt: Any, state: dict[str, Any], on_connected: Callable[[], None]
    ) -> FakeRunnerHandle:
        handle = FakeRunnerHandle(on_connected, state, **options)
        handles.append(handle)
        return handle

    return opener


class FakeWebSocket:
    """Just enough of Starlette's WebSocket for LiveRelay, driven by a list of incoming messages."""

    def __init__(
        self,
        messages: list[dict[str, Any]],
        origin: str | None = "http://localhost:5173",
        peer: str = "203.0.113.7",
        headers: dict[str, str] | None = None,
    ):
        self.headers = Headers({**({"origin": origin} if origin else {}), **(headers or {})})
        self.client = Address(peer, 50000)  # the socket peer
        self._incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for message in messages:
            self._incoming.put_nowait(message)
        self.sent: list[tuple[str, Any]] = []
        self.accepted = False
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def receive(self) -> dict[str, Any]:
        return await self._incoming.get()

    async def send_text(self, text: str) -> None:
        self.sent.append(("json", json.loads(text)))

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(("bin", data))

    async def close(self, code: int = 1000) -> None:
        self.close_code = code


def text_message(**frame: Any) -> dict[str, Any]:
    return {"type": "websocket.receive", "text": json.dumps(frame)}


DISCONNECT = {"type": "websocket.disconnect", "code": 1001}
