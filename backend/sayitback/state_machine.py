"""The briefing state machine (API.md, "State machine"). Pure functions; each wrong-state path
raises InvalidState, which the API renders as 409 {"error": {"code": "invalid_state"}}.

    draft -> steps_proposed -> steps_confirmed -> briefing -> judged
    -> (briefing -> judged)* -> decided

2026-10-17: briefing -> decided also by a Go, when the worker declined the latest round's recording
and the supervisor checked them in person (in_person_round).
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
HAZARD_STATES = ("steps_confirmed", "briefing", "judged")  # v0.4: raise (21) and acknowledge (22)


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


def require_round(b: Briefing, n: int) -> Round:
    found = b.round_n(n)
    if found is None:
        raise NotFound(f"Round {n} does not exist.", code="round_not_found")
    return found


def require_unjudged_round(b: Briefing, n: int) -> Round:
    """Approve, live session and check: the round must exist and still be unjudged."""
    found = require_round(b, n)
    if b.status != "briefing" or found.judged_at is not None:
        raise InvalidState(f"Round {n} is already judged or the briefing is {b.status}.")
    return found


def require_approved(rnd: Round) -> Round:
    """v0.4: nothing is spoken or judged before the supervisor approves the round's script."""
    if rnd.approved_at is None:
        raise InvalidState(
            f"Round {rnd.n}'s script is not approved yet. Approve it before the briefing.",
            code="script_not_approved",
        )
    return rnd


def require_approved_round(b: Briefing, n: int) -> Round:
    """Live ticket, live socket and check: an unjudged round whose script is approved."""
    return require_approved(require_unjudged_round(b, n))


def require_hazard_state(b: Briefing, what: str) -> None:
    """v0.4: a hazard is raised or acknowledged once the steps are confirmed, until the decision."""
    if b.status not in HAZARD_STATES:
        raise InvalidState(f"{what} is not possible while the briefing is {b.status}.")


def in_person_round(b: Briefing) -> Round | None:
    """2026-10-17: the latest round, while the briefing is in briefing and the worker's recorded
    choice for that round is a decline. Nothing of it is heard or checked (consent.py), so the
    supervisor briefs and checks the worker in person; a decline must never hold the permit."""
    latest = b.rounds[-1] if b.rounds else None
    if b.status != "briefing" or latest is None or latest.consent is None or latest.consent.given:
        return None
    return latest


def decide(b: Briefing, body: DecisionBody, s: Settings) -> Decision:
    """Decision: Go or No-go in judged; an explicit No-go also in steps_confirmed or briefing.

    Go while any step is not covered needs a reason of 5+ characters (422 reason_required). v0.4:
    Go while a hazard is unacknowledged is 409 hazard_open; a No-go lists them in openHazardIds.
    A step covered only by a stored sample answer (Briefing.sample_covered_step_ids) is open here.
    2026-10-17: a Go is also allowed in briefing after the worker declined the latest round (an
    in-person check, in_person_round). It always needs the reason, every step of that round's scope
    is open, and the decision carries in_person. No model call is made on this path.
    """
    in_person = in_person_round(b) if body.value == "go" else None
    early = b.status in EARLY_NO_GO and body.value == "no_go"
    if not (b.status == "judged" or early or in_person is not None):
        raise InvalidState(f"A {body.value.replace('_', '-')} cannot be recorded while {b.status}.")
    reason = clean_text(body.reason, field="reason", limit=s.decision_reason_max_chars)
    open_hazards = b.open_hazard_ids()
    if body.value == "go" and open_hazards:
        raise InvalidState(
            "Go is blocked until every hazard the worker reported is acknowledged.",
            code="hazard_open",
        )
    open_ids = b.decision_open_step_ids()  # a step covered only by a sample answer is open
    if in_person is not None:  # no model checked this round: every step it covers stays open
        scope = set(open_ids) | set(in_person.step_ids)
        open_ids = [step.id for step in b.steps if step.id in scope]
        if len(reason) < s.decision_reason_min_chars:
            raise Unprocessable(
                f"A Go after an in-person check needs a reason of {s.decision_reason_min_chars}+ "
                "characters: say what you checked.",
                code="reason_required",
            )
    if body.value == "go" and open_ids and len(reason) < s.decision_reason_min_chars:
        raise Unprocessable(
            f"Go with open steps needs a reason of {s.decision_reason_min_chars}+ characters.",
            code="reason_required",
        )
    by = clean_text(body.by, field="by", limit=s.decision_by_max_chars)
    return Decision(
        value=body.value,
        reason=reason or None,
        by=by or None,
        open_step_ids=open_ids,
        open_hazard_ids=open_hazards,
        at=now_iso(),
        in_person=True if in_person is not None else None,
    )
