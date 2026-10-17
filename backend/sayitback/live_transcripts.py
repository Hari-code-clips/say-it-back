"""What Live said and heard, per segment, and the de-duplicated captions for the browser.

ADK sends output transcription as partial chunks plus one final aggregate (and input
transcription as one final text on Gemini 3.x). Captions carry the cumulative text of the current
utterance, so a client can replace its interim line and commit it on `final`.

Segments (API.md): the latest cue names where Live's speech goes ("instruction", a question id,
"closing"). Speech after an answer window goes to "<qid>.reply" (the neutral thanks), kept apart
so the question text stays comparable with the script. Heard speech goes to the latest window.
"""

from __future__ import annotations

from sayitback.delivery import REPLY_SUFFIX
from sayitback.models import Briefing, LiveRecord, now_iso


def _join(old: str, new: str) -> str:
    return f"{old} {new}".strip() if old else new.strip()


def _appended(earlier: dict[str, str], now: dict[str, str]) -> dict[str, str]:
    """A later session's speech for a segment follows the earlier session's, never replaces it:
    the worker heard both, so the delivery check must see both."""
    merged = dict(earlier)
    for segment, text in now.items():
        merged[segment] = _join(merged.get(segment, ""), text)
    return merged


class LiveTranscripts:
    def __init__(self) -> None:
        self.delivered: dict[str, str] = {}
        self.heard: dict[str, str] = {}
        self.segment = ""
        self.last_window: str | None = None
        self._interim = {"model": "", "worker": ""}

    def start_cue(self, segment: str) -> None:
        self.segment = segment

    def open_window(self, qid: str) -> None:
        self.last_window = qid
        self.segment = f"{qid}{REPLY_SUFFIX}"

    def close_window(self, qid: str) -> None:
        self.segment = f"{qid}{REPLY_SUFFIX}"

    def model_partial(self, chunk: str) -> str:
        """Cumulative text of the model utterance so far."""
        self._interim["model"] += chunk
        return self._interim["model"]

    def model_final(self, text: str) -> str:
        full = (text or self._interim["model"]).strip()
        self._interim["model"] = ""
        if full and self.segment:
            self.delivered[self.segment] = _join(self.delivered.get(self.segment, ""), full)
        return full

    def worker_final(self, text: str) -> str:
        full = text.strip()
        if full and self.last_window:
            self.heard[self.last_window] = _join(self.heard.get(self.last_window, ""), full)
        return full

    def record_into(self, b: Briefing, n: int, *, model: str, started_at: str) -> None:
        """Merge this session's speech into round n's `live` record after earlier sessions' (a
        segment both spoke holds both, with a space between).

        A round judged, or a briefing decided, while the socket was open is final: nothing is
        written then.
        """
        rnd = b.round_n(n)
        if rnd is None or rnd.judged_at is not None or b.status != "briefing":
            return
        live = rnd.live or LiveRecord(model=model, started_at=started_at)
        live.ended_at = now_iso()
        live.delivered = _appended(live.delivered, self.delivered)
        live.heard = _appended(live.heard, self.heard)
        rnd.live = live
