"""The briefing state machine (API.md, "State machine"). Pure functions; each wrong-state path
raises InvalidState, which the API renders as 409 {"error": {"code": "invalid_state"}}.

    draft -> steps_proposed -> steps_confirmed -> briefing -> judged
    -> (briefing -> judged)* -> decided
"""

from __future__ import annotations

from typing import Literal

from sayitback.errors import InvalidState, NotFound, Unprocessable
from sayitback.models import Briefing, Decision, DecisionBody, Round, now_iso
from sayitback.settings import Settings
from sayitback.validators import clean_text

RoundKind = Literal["initial", "reexplain"]
EDITABLE = ("draft", "steps_proposed")
EARLY_NO_GO = ("steps_confirmed", "briefing")


def require_editable(b: Briefing, what: str) -> None:
    """Extract and instruction edits: only in draft or steps_proposed."""
    if b.status not in EDITABLE:
        raise InvalidState(
            f"{what} is only allowed before the steps are confirmed (now {b.status})."
        )


def require_confirmable(b: Briefing) -> None:
    """Confirm steps: in steps_proposed or steps_confirmed, and only before round 1 exists."""
    if b.status not in ("steps_proposed", "steps_confirmed") or b.rounds:
        raise InvalidState(f"Steps can only be confirmed before the first round (now {b.status}).")


def next_round(b: Briefing, max_rounds: int) -> tuple[RoundKind, int]:
    """Which round may be created now: round 1 after confirm, or a re-explain once judged."""
    if b.status == "steps_confirmed" and not b.rounds:
        return "initial", 1
    if b.status != "judged":
        raise InvalidState(f"A round cannot be created while the briefing is {b.status}.")
    if not b.open_step_ids():
        raise InvalidState("Every step is covered; there is nothing to re-explain.")
    if len(b.rounds) >= max_rounds:
        raise InvalidState(f"At most {max_rounds} rounds are allowed. Verify by demonstration.")
    return "reexplain", len(b.rounds) + 1


def require_unjudged_round(b: Briefing, n: int) -> Round:
    """Live session and check: the round must exist and still be unjudged."""
    found = b.round_n(n)
    if found is None:
        raise NotFound(f"Round {n} does not exist.", code="round_not_found")
    if b.status != "briefing" or found.judged_at is not None:
        raise InvalidState(f"Round {n} is already judged or the briefing is {b.status}.")
    return found


def decide(b: Briefing, body: DecisionBody, s: Settings) -> Decision:
    """Decision: Go or No-go in judged; an explicit No-go also in steps_confirmed or briefing.

    Go while any step is not covered needs a reason of 5+ characters (422 reason_required).
    """
    allowed = b.status == "judged" or (b.status in EARLY_NO_GO and body.value == "no_go")
    if not allowed:
        raise InvalidState(f"A {body.value.replace('_', '-')} cannot be recorded while {b.status}.")
    reason = clean_text(body.reason, field="reason", limit=s.decision_reason_max_chars)
    open_ids = b.open_step_ids()
    if body.value == "go" and open_ids and len(reason) < s.decision_reason_min_chars:
        raise Unprocessable(
            f"Go with open steps needs a reason of {s.decision_reason_min_chars}+ characters.",
            code="reason_required",
        )
    by = clean_text(body.by, field="by", limit=s.decision_by_max_chars)
    return Decision(
        value=body.value, reason=reason or None, by=by or None, open_step_ids=open_ids, at=now_iso()
    )
