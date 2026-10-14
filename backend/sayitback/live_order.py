"""The order a Live session's cues and answer windows may come in (API.md, "Live session protocol").

Pure state, no I/O: the relay asks before it forwards anything, and a refusal is a BadFrame
`invalid_state` that changes nothing, so a refused frame never reaches Live. Besides the ordering
rules, each cue (`READ_INSTRUCTION`, each `ASK <qid>`, `CLOSE`) and each question's answer window
can be used once per session. Without that, one ticket would buy model speech and input audio for
as long as the socket stayed open: a client could loop a cue, or ASK plus answer windows, until
the session limit.
"""

from __future__ import annotations

from sayitback.live_frames import BadFrame, Cue


class SessionOrder:
    """What one socket's session has done so far, and so what the browser may send next."""

    def __init__(self) -> None:
        self.window: str | None = None  # the qid whose answer window is open
        self.window_bytes = 0  # audio forwarded into it so far
        self._turn_done = True  # the model finished its latest turn
        self._last_cue: Cue | None = None
        self._cues: set[str] = set()  # cue texts already sent
        self._windows: set[str] = set()  # qids whose answer window was already opened

    def cue(self, cue: Cue) -> None:
        """A cue comes while no window is open, and the same cue only once."""
        if self.window is not None:
            raise _refused("Close the answer window before the next cue.")
        if cue.text in self._cues:
            raise _refused("Each cue can be sent once per session.")
        self._cues.add(cue.text)
        self._last_cue, self._turn_done = cue, False

    def open_window(self, qid: str) -> None:
        """A window opens for the question just asked once its turn is over, and only once."""
        asked = self._last_cue is not None and self._last_cue.qid == qid
        if self.window is not None or not asked or not self._turn_done:
            raise _refused("Open an answer window only after the question finished.")
        if qid in self._windows:
            raise _refused("Each answer window can be opened once per session.")
        self._windows.add(qid)
        self.window, self.window_bytes = qid, 0

    def close_window(self, qid: str) -> None:
        if self.window != qid:
            raise _refused("No such answer window is open.")
        self.window, self._turn_done = None, False

    def turn_complete(self) -> None:
        self._turn_done = True


def _refused(message: str) -> BadFrame:
    return BadFrame(message, code="invalid_state")
