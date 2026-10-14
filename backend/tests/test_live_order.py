"""SessionOrder: the order a Live session's cues and answer windows may come in, and the rule that
each cue and each question's answer window is used once. The relay's own tests, with the fake Live
queue, are in test_live_relay_once.py."""

from __future__ import annotations

import pytest

from sayitback.live_frames import BadFrame, Cue
from sayitback.live_order import SessionOrder

READ = Cue("READ_INSTRUCTION", "instruction")
ASK1 = Cue("ASK q1", "q1", "q1")
ASK2 = Cue("ASK q2", "q2", "q2")
CLOSE = Cue("CLOSE", "closing")

START_ONLY_AFTER = "Open an answer window only after the question finished."
CLOSE_FIRST = "Close the answer window before the next cue."
NOT_OPEN = "No such answer window is open."


def ask(order: SessionOrder, cue: Cue) -> None:
    """A cue, then the model finishing its turn."""
    order.cue(cue)
    order.turn_complete()


def answer(order: SessionOrder, qid: str) -> None:
    """A whole answer window, then the model finishing its reply."""
    order.open_window(qid)
    order.close_window(qid)
    order.turn_complete()


def refusal(action) -> BadFrame:
    with pytest.raises(BadFrame) as err:
        action()
    assert err.value.code == "invalid_state"
    return err.value


class TestEachCueAndWindowOnce:
    def test_the_normal_briefing_is_allowed(self):
        order = SessionOrder()
        ask(order, READ)
        ask(order, ASK1)
        answer(order, "q1")
        ask(order, ASK2)
        answer(order, "q2")
        ask(order, CLOSE)

    @pytest.mark.parametrize("cue", [READ, ASK1, CLOSE], ids=lambda cue: cue.text)
    def test_a_cue_is_allowed_once(self, cue):
        order = SessionOrder()
        ask(order, cue)
        assert "once per session" in refusal(lambda: order.cue(cue)).message

    def test_a_cue_is_refused_when_repeated_later_too(self):
        order = SessionOrder()
        ask(order, ASK1)
        ask(order, ASK2)
        assert "once per session" in refusal(lambda: order.cue(ASK1)).message

    def test_a_window_is_allowed_once_per_question(self):
        order = SessionOrder()
        ask(order, ASK1)
        answer(order, "q1")
        assert "once per session" in refusal(lambda: order.open_window("q1")).message

    def test_a_refusal_changes_nothing(self):
        order = SessionOrder()
        ask(order, READ)
        refusal(lambda: order.cue(READ))
        ask(order, ASK1)  # what is still legal still works
        answer(order, "q1")
        refusal(lambda: order.open_window("q1"))
        ask(order, CLOSE)

    def test_each_window_counts_its_own_audio(self):
        order = SessionOrder()
        ask(order, ASK1)
        order.open_window("q1")
        order.window_bytes = 1_000
        order.close_window("q1")
        order.turn_complete()
        ask(order, ASK2)
        order.open_window("q2")
        assert order.window == "q2" and order.window_bytes == 0


def after_ask(order: SessionOrder) -> None:  # q1 asked, its turn finished
    ask(order, ASK1)


def while_asking(order: SessionOrder) -> None:  # q1 asked, still being spoken
    order.cue(ASK1)


def while_listening(order: SessionOrder) -> None:  # q1's window is open
    ask(order, ASK1)
    order.open_window("q1")


def while_replying(order: SessionOrder) -> None:  # q1's window closed, the reply still going
    while_listening(order)
    order.close_window("q1")


# id -> (state, the frame refused in it, the existing rule's message)
ORDERING = {
    "a window before anything was asked": (lambda o: None, lambda o: o.open_window("q1"), START_ONLY_AFTER),
    "a window for a question that was not just asked": (after_ask, lambda o: o.open_window("q2"), START_ONLY_AFTER),
    "a window while the question is still spoken": (while_asking, lambda o: o.open_window("q1"), START_ONLY_AFTER),
    "a window while the model is still replying": (while_replying, lambda o: o.open_window("q1"), START_ONLY_AFTER),
    "a window while one is open": (while_listening, lambda o: o.open_window("q1"), START_ONLY_AFTER),
    "a cue while a window is open": (while_listening, lambda o: o.cue(CLOSE), CLOSE_FIRST),
    "a repeated cue while a window is open": (while_listening, lambda o: o.cue(ASK1), CLOSE_FIRST),
    "an end with no window open": (after_ask, lambda o: o.close_window("q1"), NOT_OPEN),
    "an end for another question's window": (while_listening, lambda o: o.close_window("q2"), NOT_OPEN),
}  # fmt: skip


@pytest.mark.parametrize(("state", "frame", "message"), list(ORDERING.values()), ids=list(ORDERING))
def test_every_existing_ordering_rule_is_unchanged(state, frame, message):
    order = SessionOrder()
    state(order)
    assert refusal(lambda: frame(order)).message == message
