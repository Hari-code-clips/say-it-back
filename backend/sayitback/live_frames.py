"""Validation of the browser's WebSocket frames (API.md, "Live session protocol").

The browser may send only: a `start` frame with the ticket, enumerated cues, answer window
markers, `stop`, and PCM audio. Anything else is a `bad_message`. The text forwarded to the model
is built here from constants and a qid taken from the round's own question ids, never from the
browser's string, so no browser text can reach the briefer.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

READ_INSTRUCTION = "READ_INSTRUCTION"
ASK = "ASK"
CLOSE = "CLOSE"
INSTRUCTION_SEGMENT = "instruction"
CLOSING_SEGMENT = "closing"
TICKET_SHAPE = re.compile(r"[A-Za-z0-9_-]{16,128}")  # token_urlsafe(32) is 43 such characters
CUE_KEYS = {"type", "cue", "qid"}
WINDOW_KEYS = {"type", "qid"}

# error code -> WebSocket close code
CLOSE_CODES = {
    "bad_ticket": 4401,
    "bad_message": 4400,
    "invalid_state": 4409,
    "limit": 4429,
    "upstream_busy": 4503,
}


class BadFrame(Exception):
    def __init__(self, message: str, code: str = "bad_message") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Cue:
    text: str  # what the briefer receives: READ_INSTRUCTION, ASK q1 or CLOSE
    segment: str  # where Live's next speech is recorded
    qid: str | None = None


@dataclass(frozen=True)
class AnswerStart:
    qid: str


@dataclass(frozen=True)
class AnswerEnd:
    qid: str


@dataclass(frozen=True)
class Stop:
    pass


Command = Cue | AnswerStart | AnswerEnd | Stop


def _load(raw: str, max_bytes: int) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > max_bytes:
        raise BadFrame("The message is too large.")
    try:
        data = json.loads(raw)
    except ValueError:
        raise BadFrame("The message is not valid JSON.") from None
    if not isinstance(data, dict):
        raise BadFrame("The message must be a JSON object.")
    return data


def _qid(data: dict[str, Any], question_ids: Collection[str]) -> str:
    qid = data.get("qid")
    if not isinstance(qid, str) or qid not in question_ids:
        raise BadFrame("qid is not a question of this round.")
    return qid


def parse_start(raw: str, max_bytes: int) -> str:
    """The first frame: {"type": "start", "ticket": "..."}. Returns the ticket. Never echoes it."""
    data = _load(raw, max_bytes)
    ticket = data.get("ticket")
    if data.get("type") != "start" or not isinstance(ticket, str):
        raise BadFrame("Send {type: start, ticket} first.", code="bad_ticket")
    if not TICKET_SHAPE.fullmatch(ticket):
        raise BadFrame("The ticket is not valid.", code="bad_ticket")
    return ticket


def parse_command(raw: str, question_ids: Collection[str], max_bytes: int) -> Command:
    data = _load(raw, max_bytes)
    kind = data.get("type")
    if kind == "cue":
        return _parse_cue(data, question_ids)
    if kind in ("answer_start", "answer_end"):
        if set(data) - WINDOW_KEYS:
            raise BadFrame("Unexpected fields.")
        qid = _qid(data, question_ids)
        return AnswerStart(qid) if kind == "answer_start" else AnswerEnd(qid)
    if kind == "stop" and set(data) == {"type"}:
        return Stop()
    raise BadFrame("Unknown message type.")


def _parse_cue(data: dict[str, Any], question_ids: Collection[str]) -> Cue:
    if set(data) - CUE_KEYS:
        raise BadFrame("Unexpected fields.")
    cue = data.get("cue")
    if cue == READ_INSTRUCTION and "qid" not in data:
        return Cue(READ_INSTRUCTION, INSTRUCTION_SEGMENT)
    if cue == CLOSE and "qid" not in data:
        return Cue(CLOSE, CLOSING_SEGMENT)
    if cue == ASK:
        qid = _qid(data, question_ids)
        return Cue(f"{ASK} {qid}", qid, qid)
    raise BadFrame("Unknown cue.")
