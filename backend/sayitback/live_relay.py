"""Endpoint 20: relay one Live briefing between the browser and the ADK briefer agent.

browser <-> this relay <-> Runner.run_live (gemini-3.8-live). The relay validates every frame,
forwards only enumerated cues (each once) and audio inside answer windows, attributes Live's speech
to the script's segments, and writes `round.live` when the socket closes. Never logs a ticket.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai import types

from sayitback import live_session, state_machine
from sayitback.errors import ApiError, safe_describe
from sayitback.live_frames import (
    CLOSE_CODES,
    AnswerEnd,
    AnswerStart,
    BadFrame,
    Command,
    Cue,
    Stop,
    parse_command,
    parse_start,
)
from sayitback.live_idle import IdleClock, OpenSockets
from sayitback.live_order import SessionOrder
from sayitback.live_runner import (
    LiveHandle,
    LiveOpener,
    briefer_state,
    open_adk_session,
    run_config,
)
from sayitback.live_transcripts import LiveTranscripts
from sayitback.models import Briefing, Round, now_iso
from sayitback.ratelimit import client_ip
from sayitback.repo import Repo
from sayitback.runtime import Runtime
from sayitback.store.base import round_key

log = logging.getLogger("sayitback.live")
NORMAL_CLOSE = 1000
POLICY_CLOSE = 1008
PCM_BYTES_PER_S = 32000  # 16 kHz, 16-bit, mono
PLAYBACK_BYTES_PER_S = 48000  # the model's audio: 24 kHz, 16-bit, mono


@dataclass(frozen=True)
class RelayDeps:
    rt: Runtime
    repo: Repo
    opener: LiveOpener = field(default=open_adk_session)
    sockets: OpenSockets = field(default_factory=OpenSockets)  # open sockets per client address


def origin_allowed(origin: str | None, allowed: tuple[str, ...]) -> bool:
    return bool(origin) and origin.rstrip("/") in allowed  # type: ignore[union-attr]


class LiveRelay:
    def __init__(self, ws: WebSocket, deps: RelayDeps, briefing_id: str, n: int) -> None:
        self.ws, self.deps, self.briefing_id, self.n = ws, deps, briefing_id, n
        self.s = deps.rt.settings
        self.tx = LiveTranscripts()
        self.owner = uuid.uuid4().hex  # this socket's holder of the round's lease
        self.briefing_owner = ""  # whom the ticket was issued to: the owner of the briefing
        self.address = client_ip(ws, self.s.trusted_proxy_hops)
        self.question_ids: list[str] = []
        self.queue: LiveRequestQueue | None = None
        self.handle: LiveHandle | None = None
        self.events_task: asyncio.Task[None] | None = None
        self.manual = True
        self.order = SessionOrder()
        self.ready_sent = False
        self.started_at = ""
        self.lock_held = False
        self.closing = False
        self.idle = IdleClock(self.s.ws_idle_s, self.s.ws_first_cue_s)
        self.error_sent = False
        self.close_code = NORMAL_CLOSE
        self._send_lock = asyncio.Lock()

    # Entry point ------------------------------------------------------------------------------

    async def run(self) -> None:
        if not origin_allowed(self.ws.headers.get("origin"), self.s.allowed_origins):
            await self.ws.close(code=POLICY_CLOSE)  # refused at the handshake (HTTP 403)
            return
        if not self.deps.sockets.admit(self.address, self.s.max_sockets_per_ip):
            await self._refuse_socket()  # before any ticket is read or Live is opened
            return
        try:
            await self.ws.accept()
            ctx = await self._handshake()
            if ctx is not None:
                await self._serve(*ctx)
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001 - always close cleanly and persist what was said
            log.warning("live relay failed: %s", safe_describe(exc))
            await self._fail("upstream_busy", "The live voice service failed. Use turn mode.")
        finally:
            await self._finalize()

    async def _refuse_socket(self) -> None:
        """This address already holds its limit of sockets: accept only to say why, then close."""
        await self.ws.accept()
        await self._fail("limit", "Too many live sockets are open from this address.")
        await _quiet(self.ws.close(code=self.close_code), "close the socket")

    # Handshake: first frame, ticket, state, lease ---------------------------------------------

    async def _handshake(self) -> tuple[Briefing, Round] | None:
        try:
            message = await asyncio.wait_for(self.ws.receive(), self.s.ws_first_message_s)
        except TimeoutError:
            return await self._reject("bad_message", "No start frame arrived in time.")
        if message.get("type") == "websocket.disconnect":
            return None
        try:
            ticket = parse_start(message.get("text") or "", self.s.ws_max_text_bytes)
        except BadFrame as bad:
            return await self._reject(bad.code, bad.message)
        record = await live_session.redeem_ticket(self.deps.repo.store, ticket)
        del ticket
        owner = live_session.ticket_owner(record, self.briefing_id, self.n)
        if owner is None:
            return await self._reject("bad_ticket", "The ticket is not valid.")
        self.briefing_owner = owner  # the relay reads and writes the briefing as its owner
        return await self._claim_round()

    async def _claim_round(self) -> tuple[Briefing, Round] | None:
        try:
            briefing = await self.deps.repo.get(self.briefing_id, self.briefing_owner)
            rnd = state_machine.require_approved_round(briefing, self.n)  # as the ticket was
        except ApiError as err:
            return await self._reject("invalid_state", err.message)
        ttl = self.s.ws_max_session_s + self.s.live_lock_extra_s
        held = await self.deps.repo.store.acquire_live(
            round_key(self.briefing_id, self.n), self.owner, datetime.now(UTC), ttl
        )
        if not held:
            return await self._reject("invalid_state", "This round already has a live session.")
        self.lock_held = True
        return briefing, rnd

    async def _reject(self, code: str, message: str) -> None:
        await self._fail(code, message)

    # Serving: open the model session, then pump both directions -------------------------------

    async def _serve(self, briefing: Briefing, rnd: Round) -> None:
        self.question_ids = [q.id for q in rnd.script.questions]
        if not await self._open(briefer_state(rnd.script, briefing.worker_lang)):
            return
        self.started_at = now_iso()
        self.idle.start()
        browser = asyncio.create_task(self._browser_loop())
        assert self.events_task is not None
        done, _ = await asyncio.wait(
            {browser, self.events_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if browser not in done:  # the model side ended first
            if not self.closing:
                await self._fail("upstream_busy", "The live session ended. Use turn mode.")
            browser.cancel()
        await asyncio.gather(browser, return_exceptions=True)

    async def _open(self, state: dict[str, Any]) -> bool:
        """Connect in the configured turn-taking mode; if Live rejects manual, retry in auto."""
        modes = ["manual", "auto"] if self.s.live_turn_taking == "manual" else ["auto"]
        for attempt, mode in enumerate(modes):
            if attempt:
                await asyncio.sleep(self.s.retry_backoff_s)
            connected = asyncio.Event()
            handle = await self.deps.opener(self.deps.rt, state, connected.set)
            queue = LiveRequestQueue()
            task = asyncio.create_task(self._pump_events(handle, queue, mode == "manual"))
            if await self._connected(task, connected):
                self.handle, self.queue, self.events_task, self.manual = (
                    handle,
                    queue,
                    task,
                    mode == "manual",
                )
                self.ready_sent = True
                await self._send({"type": "ready", "model": self.s.live_model, "turnTaking": mode})
                return True
            log.warning("live connect failed in %s mode", mode)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await _quiet(handle.close(), "close the ADK runner")
        await self._fail("upstream_busy", "The live voice service is unavailable. Use turn mode.")
        return False

    async def _connected(self, task: asyncio.Task[None], connected: asyncio.Event) -> bool:
        waiter = asyncio.ensure_future(connected.wait())
        await asyncio.wait(
            {task, waiter},
            timeout=self.s.live_connect_timeout_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
        waiter.cancel()
        return connected.is_set()

    async def _pump_events(self, handle: LiveHandle, queue: LiveRequestQueue, manual: bool) -> None:
        try:
            async for event in handle.events(queue, run_config(self.s, manual=manual)):
                await self._on_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported to the browser by _serve
            log.warning("live model stream ended: %s", safe_describe(exc))

    # Model -> browser -------------------------------------------------------------------------

    async def _on_event(self, event: Any) -> None:
        self.idle.touch()
        for part in event.content.parts if event.content and event.content.parts else []:
            blob = part.inline_data
            if blob and blob.data and (blob.mime_type or "").startswith("audio/"):
                # Live sends audio ahead of real time; the browser plays it back to back
                self.idle.speak(len(blob.data) / PLAYBACK_BYTES_PER_S)
                await self._send_bytes(blob.data)
        if event.output_transcription and event.output_transcription.text is not None:
            await self._model_caption(event.output_transcription)
        heard = event.input_transcription
        if heard and heard.finished and heard.text:
            text = self.tx.worker_final(heard.text)
            if text:
                await self._send({"type": "caption", "role": "worker", "text": text, "final": True})
        if event.interrupted:
            self.idle.hush()  # the browser drops what it had queued
            await self._send({"type": "interrupted"})
        if event.turn_complete:
            self.order.turn_complete()
            await self._send({"type": "turn_complete"})

    async def _model_caption(self, transcription: Any) -> None:
        final = bool(transcription.finished)
        text = (
            self.tx.model_final(transcription.text)
            if final
            else self.tx.model_partial(transcription.text)
        )
        if text:
            await self._send({"type": "caption", "role": "model", "text": text, "final": final})

    # Browser -> model -------------------------------------------------------------------------

    async def _browser_loop(self) -> None:
        try:
            async with asyncio.timeout(self.s.ws_max_session_s):
                while await self._next_frame():
                    pass
        except TimeoutError:
            await self._fail("limit", "The live session time limit was reached.")

    async def _next_frame(self) -> bool:
        message = await self.idle.receive(self.ws.receive)
        if message is None:
            await self._fail("limit", self.idle.expiry())
            return False
        if message.get("type") == "websocket.disconnect":
            return False
        try:
            if message.get("bytes") is not None:
                if self._on_audio(message["bytes"]):
                    self.idle.touch()  # only audio that reached the model; a dropped frame is not
                return True
            command = parse_command(
                message.get("text") or "", self.question_ids, self.s.ws_max_text_bytes
            )
            keep_going = self._on_command(command)
            self.idle.touch()  # a frame the relay accepted
            return keep_going
        except BadFrame as bad:
            await self._fail(bad.code, bad.message)
            return False

    def _on_audio(self, data: bytes) -> bool:
        """Forward mic audio to Live. False if the relay dropped it (outside an answer window)."""
        if len(data) > self.s.ws_max_binary_bytes or len(data) % 2:
            raise BadFrame("Audio frames are at most 8 KB of 16-bit samples.")
        if self.order.window is None:
            return False  # dropped, never forwarded
        self.order.window_bytes += len(data)
        if self.order.window_bytes > self.s.ws_max_window_s * PCM_BYTES_PER_S:
            raise BadFrame("The answer window is longer than allowed.", code="limit")
        assert self.queue is not None
        blob = types.Blob(data=data, mime_type=f"audio/pcm;rate={self.s.live_input_rate}")
        self.queue.send_realtime(blob)
        return True

    def _on_command(self, command: Command) -> bool:
        assert self.queue is not None
        if isinstance(command, Stop):
            return False
        if isinstance(command, Cue):
            self._cue(command)
        elif isinstance(command, AnswerStart):
            self._answer_start(command)
        elif isinstance(command, AnswerEnd):
            self._answer_end(command)
        return True

    def _cue(self, cue: Cue) -> None:
        assert self.queue is not None
        self.order.cue(cue)  # refuses a bad or repeated cue before anything is touched or sent
        self.idle.cue_seen()
        self.tx.start_cue(cue.segment)
        self.queue.send_content(types.Content(role="user", parts=[types.Part(text=cue.text)]))

    def _answer_start(self, cmd: AnswerStart) -> None:
        assert self.queue is not None
        self.order.open_window(cmd.qid)
        self.tx.open_window(cmd.qid)
        if self.manual:
            self.queue.send_activity_start()

    def _answer_end(self, cmd: AnswerEnd) -> None:
        assert self.queue is not None
        self.order.close_window(cmd.qid)
        self.tx.close_window(cmd.qid)
        if self.manual:
            self.queue.send_activity_end()
        else:
            self.queue.send_audio_stream_end()

    # Sending and closing ----------------------------------------------------------------------

    async def _send(self, frame: dict[str, Any]) -> None:
        async with self._send_lock:
            await _quiet(self.ws.send_text(json.dumps(frame, ensure_ascii=False)))

    async def _send_bytes(self, data: bytes) -> None:
        async with self._send_lock:
            await _quiet(self.ws.send_bytes(data))

    async def _fail(self, code: str, message: str) -> None:
        """Send one error frame, then the socket closes (API.md: error, then close)."""
        if self.error_sent:
            return
        self.error_sent = True
        self.close_code = CLOSE_CODES[code]
        await self._send({"type": "error", "code": code, "message": message})

    async def _finalize(self) -> None:
        self.closing = True
        self.deps.sockets.release(self.address)  # first: a client seeing the close may reconnect
        if self.queue is not None:
            self.queue.close()
        if self.events_task is not None:
            await asyncio.wait({self.events_task}, timeout=self.s.live_drain_s)
            if not self.events_task.done():
                self.events_task.cancel()
            await asyncio.gather(self.events_task, return_exceptions=True)
        # round.live first: a check posted right after `stop` waits for it. Closing the ADK
        # runner flushes plugins and can take seconds, so it comes last.
        if self.ready_sent:
            await _quiet(self._persist(), "persist round.live")
        if self.lock_held:
            release = self.deps.repo.store.release_live(
                round_key(self.briefing_id, self.n), self.owner
            )
            await _quiet(release, "release the live lease")
        await _quiet(self.ws.close(code=self.close_code), "close the socket")
        if self.handle is not None:
            await _quiet(self.handle.close(), "close the ADK runner")

    async def _persist(self) -> None:
        """Write round.live (what Live said and heard, per segment) through the store."""

        def change(b: Briefing) -> None:
            self.tx.record_into(b, self.n, model=self.s.live_model, started_at=self.started_at)

        await self.deps.repo.mutate(self.briefing_id, self.briefing_owner, change)


async def _quiet(awaitable: Awaitable[Any], what: str = "send") -> None:
    """Await a step; a failure must not mask the session's own outcome, but it is logged."""
    try:
        await awaitable
    except Exception as exc:  # noqa: BLE001
        level = logging.DEBUG if what == "send" else logging.WARNING  # a dropped frame is routine
        log.log(level, "live relay could not %s: %s", what, safe_describe(exc))
