"""The worker's consent before any answer is recorded (privacy, 16 Oct; API.md Deviations).

On the worker's own screen, before the first answer of a round, the worker chooses "I agree" or
"Not now" in their language: their voice is used only to check this briefing and is not kept
(audio is dropped after judging unless SIB_KEEP_AUDIO). The choice is stored on the round
(`round.consent`) and appended to the record chain as a `consent` event, in one atomic update.

What it gates:
- A declined round takes no audio at all: its check (13) and its Live ticket (11) are 409
  `consent_declined`. A decline is never a verdict or a failure: the round stays unjudged, and the
  supervisor briefs in person (or the worker agrees later; the latest choice stands until the round
  is judged).
- With SIB_REQUIRE_CONSENT (true in the environment), a round with no recorded choice is checked
  only when `meta.sampleAnswers` lists every question of the round, and gets a Live ticket only
  when the request declares a samples-only session (`{"samplesOnly": true}`); otherwise 409
  `consent_required`. That is the evaluator's path, on which the web shows no consent step: stored
  synthetic sample answers record no human voice (security fixes B, M3 and M4).

Consent is a choice the client records. The server cannot tell a stored sample from a person's
voice on the wire, so these rules make the record consistent for an honest client: a round with no
recorded choice can only ever be judged as all samples.
"""

from __future__ import annotations

from sayitback import chain, state_machine
from sayitback.errors import InvalidState
from sayitback.models import Briefing, Round, RoundConsent, now_iso
from sayitback.repo import Repo

NOT_AGREED = "The worker has not agreed to be recorded for this round yet. Ask them first."


def refuse_declined(rnd: Round) -> None:
    """Nothing of a declined round is heard or checked: 409 consent_declined."""
    if rnd.consent is not None and not rnd.consent.given:
        raise InvalidState(
            "The worker chose not to be recorded for this round. Brief them in person.",
            code="consent_declined",
        )


def samples_only(rnd: Round, samples: list[str] | None) -> bool:
    """Every question of the round is answered by a stored sample (`meta.sampleAnswers`)."""
    listed = set(samples or [])
    questions = rnd.script.questions
    return bool(questions) and all(q.id in listed for q in questions)


def require_for_check(rnd: Round, samples: list[str] | None, required: bool) -> None:
    """Endpoint 13: a declined round is refused; with `required`, a round with no recorded choice
    is checked only as all samples, whatever clips are sent."""
    refuse_declined(rnd)
    if required and rnd.consent is None and not samples_only(rnd, samples):
        raise InvalidState(NOT_AGREED, code="consent_required")


def require_for_live(rnd: Round, declared_samples_only: bool, required: bool) -> None:
    """Endpoint 11: a declined round is refused; with `required`, a round with no recorded choice
    gets a ticket only for a session the request declares samples-only."""
    refuse_declined(rnd)
    if required and rnd.consent is None and not declared_samples_only:
        raise InvalidState(NOT_AGREED, code="consent_required")


def record(b: Briefing, n: int, given: bool) -> Round:
    """The atomic change: store the worker's choice for round n and append its chain event. The
    round must exist, be approved and unjudged (409 otherwise). The same choice again is a no-op."""
    rnd = state_machine.require_approved_round(b, n)
    if rnd.consent is not None and rnd.consent.given is given:
        return rnd
    rnd.consent = RoundConsent(given=given, at=now_iso())
    chain.append(b, "consent", chain.consent(rnd), at=rnd.consent.at)
    return rnd


async def record_for(repo: Repo, briefing_id: str, n: int, given: bool, owner: str) -> Round:
    """Endpoint `POST /api/briefings/{id}/rounds/{n}/consent` for the briefing's owner."""
    stored = await repo.mutate(briefing_id, owner, lambda b: _ignore(record(b, n, given)))
    return stored.rounds[n - 1]


def _ignore(_: object) -> None:
    return None
