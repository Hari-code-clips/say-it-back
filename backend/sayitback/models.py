"""Wire models: the Pydantic twins of the TypeScript types in docs/API.md.

Python attributes are snake_case; the wire (and the stored JSON) is camelCase. Every model also
accepts snake_case, so `Step(**catalog_reference_step)` and `Step.model_validate(wire)` both work.
"""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

Verdict = Literal["covered", "missed", "contradicted", "unclear"]
StepSource = Literal["instruction", "sop", "both"]
Status = Literal["draft", "steps_proposed", "steps_confirmed", "briefing", "judged", "decided"]
NextAction = Literal["decide", "reexplain"]
Mode = Literal["live", "turn"]
HazardKind = Literal["voice", "tap"]
DeliveryIssue = Literal[
    "not_spoken", "wrong_script", "low_similarity", "negation_changed", "number_changed",
    "reply_too_long", "reply_not_neutral",
]  # fmt: skip
ChainEventType = Literal[
    "created", "instruction_edited", "steps_proposed", "steps_confirmed", "round_created",
    "script_approved", "round_judged", "hazard_raised", "hazard_acknowledged", "decided",
    "consent",  # privacy (16 Oct): the worker gave or declined consent for a round (consent.py)
]  # fmt: skip

PERMIT_REF_PATTERN = r"^[A-Za-z0-9._/-]{1,32}$"
MAX_CREW = 6

# Severity for "a judge that rates a step twice is held to its worst" (guards.normalise_pass).
# Rule 1, which combines the two judges, no longer uses it (v0.5.3).
SEVERITY: dict[str, int] = {"covered": 0, "unclear": 1, "missed": 2, "contradicted": 3}


class Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    def wire(self) -> dict[str, Any]:
        """camelCase JSON with absent optionals omitted, as the API returns and the store keeps."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class PermitLink(Wire):
    """v0.5.2: the permit-to-work a briefing checks and which worker on it this is ("worker 2 of
    3"). The slot number is the only per-worker field: never a name, an ID or a nationality
    (Rule 6), so the block takes no other key. Immutable once the briefing is created."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    ref: str = Field(pattern=PERMIT_REF_PATTERN)  # as typed on the permit, trimmed
    crew_size: StrictInt = Field(ge=1, le=MAX_CREW)
    slot: StrictInt = Field(ge=1, le=MAX_CREW)

    @field_validator("ref", mode="before")
    @classmethod
    def _trimmed(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _slot_on_the_permit(self) -> PermitLink:
        if self.slot > self.crew_size:
            raise ValueError("slot must be between 1 and crewSize")
        return self

    @property
    def key(self) -> str:
        """What permits match on: the ref, upper-cased."""
        return self.ref.upper()


class Step(Wire):
    id: str
    text: str
    hazard: str = ""
    essential: list[str] = []
    source: StepSource = "instruction"
    sop_quote: str | None = None
    speakable: bool = True


class Conflict(Wire):
    step_id: str | None = None
    message: str


class Question(Wire):
    id: str
    text: str
    back_translation: str = ""
    step_ids: list[str] = []


class Script(Wire):
    instruction: str
    instruction_back_translation: str = ""
    questions: list[Question]
    step_map: dict[str, list[int]] = {}
    closing: str


class Transcript(Wire):
    question_id: str
    original: str = ""
    detected_lang: str = "none"
    translation: str = ""
    flags: list[str] = []


class Rating(Wire):
    step_id: str
    verdict: Verdict
    quote: str | None = None
    quote_translation: str | None = None
    reason: str = ""
    confidence: float | None = None
    flags: list[str] = []


class DeliveryCheck(Wire):
    """Live mode: what Live said for one segment against the approved script (API.md v0.4)."""

    segment: str
    similarity: float
    script_ok: bool
    ok: bool = False  # a record from before v0.4 has no verdict: it is not vouched for
    issues: list[DeliveryIssue] = []
    said: str | None = None


class LiveRecord(Wire):
    model: str
    started_at: str
    ended_at: str | None = None
    delivered: dict[str, str] = {}
    heard: dict[str, str] = {}


class RoundConsent(Wire):
    """Privacy (16 Oct): the worker's own choice before any answer of the round is recorded.
    `given` false is a decline: no answer of the round may be checked (consent.py). It is never a
    verdict about the worker."""

    given: bool
    at: str


class Round(Wire):
    n: int
    kind: Literal["initial", "reexplain"]
    step_ids: list[str]
    supervisor_note: str | None = None
    script: Script
    mode: Mode | None = None
    transcripts: list[Transcript] = []
    pass_a: list[Rating] = []
    pass_b: list[Rating] = []
    ratings: list[Rating] = []
    delivery: list[DeliveryCheck] = []
    live: LiveRecord | None = None
    next_action: NextAction = "reexplain"
    model_ids: dict[str, str] = {}
    timings_ms: dict[str, float] = {}
    created_at: str
    approved_at: str | None = None  # v0.4: the supervisor approved the script (endpoint 23)
    approved_by: str | None = None
    sample_answers: list[str] | None = None  # v0.4: question ids answered by a stored sample
    judged_at: str | None = None
    consent: RoundConsent | None = None  # privacy (16 Oct): absent until the worker chooses


class HazardAck(Wire):
    note: str
    by: str | None = None
    at: str


class Hazard(Wire):
    """v0.4: a worker's report of a problem. It blocks Go until the supervisor acknowledges it."""

    id: str
    round: int | None = None
    kind: HazardKind
    original: str = ""
    translation: str = ""
    detected_lang: str = "none"
    raised_at: str
    ack: HazardAck | None = None


class ChainEvent(Wire):
    """v0.4: one link of the record's hash chain (chain.py)."""

    seq: int
    type: ChainEventType
    at: str
    data: dict[str, Any] = {}
    prev_hash: str
    hash: str


class Sop(Wire):
    id: str
    version: str
    title: str
    text: str


SOP_ID_PATTERN = r"^[A-Za-z0-9._-]{1,40}$"


class SopRef(Wire):
    """library (2026-10-16): an approved version of a site's SOP library (sop_library.py) that a
    briefing starts from. Immutable once the briefing is created; bound in its `created` event."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    sop_id: str = Field(pattern=SOP_ID_PATTERN)
    version: StrictInt = Field(ge=1, le=9999)


class Decision(Wire):
    value: Literal["go", "no_go"]
    reason: str | None = None
    by: str | None = None
    open_step_ids: list[str]
    open_hazard_ids: list[str] = []  # v0.4; a decision from before v0.4 has none
    at: str
    # 2026-10-17: a Go after the worker declined the AI check (state_machine.in_person_round): the
    # supervisor checked them in person. True only then; absent (None) on every other decision.
    in_person: bool | None = None


class Briefing(Wire):
    id: str
    site_id: str
    task_id: str
    sop: Sop
    supervisor_lang: str
    worker_lang: str
    instruction: str
    permit: PermitLink | None = None  # v0.5.2, immutable
    sop_ref: SopRef | None = None  # library (2026-10-16), immutable
    status: Status = "draft"
    steps: list[Step] = []
    steps_version: int = 0
    conflicts: list[Conflict] = []
    rounds: list[Round] = []
    latest_verdicts: dict[str, Verdict] = {}
    decision: Decision | None = None
    hazards: list[Hazard] = []
    events: list[ChainEvent] = []  # v0.4: append-only, written only by chain.append
    record_hash: str = ""  # the last event's hash
    prompt_version: str
    created_at: str
    updated_at: str

    def open_step_ids(self) -> list[str]:
        """Steps not yet covered: the scope of a re-explain round."""
        return [s.id for s in self.steps if self.latest_verdicts.get(s.id) != "covered"]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sample_covered_step_ids(self) -> list[str]:
        """v0.4 review: steps whose latest `covered` rating came only from stored synthetic sample
        answers (endpoint 24), not from the worker. Derived on every read, never stored, and never
        taken from a request. A decision treats them as open."""
        return sample_covered(self)

    def decision_open_step_ids(self) -> list[str]:
        """What a decision counts as open: not covered, or covered only by a sample answer."""
        sampled = set(self.sample_covered_step_ids)
        open_ids = set(self.open_step_ids())
        return [s.id for s in self.steps if s.id in open_ids or s.id in sampled]

    def wire(self) -> dict[str, Any]:
        """As Wire.wire, with `permit` always present: null when the briefing has none."""
        return {**super().wire(), "permit": self.permit.wire() if self.permit else None}

    def stored(self) -> dict[str, Any]:
        """The record as the store keeps it: the wire form without the derived fields."""
        return self.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude={"sample_covered_step_ids"}
        )

    def open_hazard_ids(self) -> list[str]:
        return [h.id for h in self.hazards if h.ack is None]

    def hazard(self, hazard_id: str) -> Hazard | None:
        return next((h for h in self.hazards if h.id == hazard_id), None)

    def round_n(self, n: int) -> Round | None:
        return self.rounds[n - 1] if 1 <= n <= len(self.rounds) else None


def sample_covered(b: Briefing) -> list[str]:
    """Steps whose latest rating is `covered` and whose cover came only from sample answers.

    In the round that last rated the step: if every question asking about it (`stepIds`) was
    answered by a sample, the cover is the sample's. If a worker's own answer asked about it too,
    the step is still the sample's unless the rating's quote is in one of the worker's own
    transcripts: an answer that said nothing cannot lend its question to a sample's words."""
    from sayitback.guards import GuardConfig, transcripts_with_quote  # guards imports models

    latest: dict[str, tuple[Round, Rating]] = {}
    for rnd in b.rounds:
        for r in rnd.ratings:
            latest[r.step_id] = (rnd, r)
    found = []
    for step in b.steps:
        rnd, rating = latest.get(step.id, (None, None))
        if rnd is None or rating is None or rating.verdict != "covered":
            continue
        samples = set(rnd.sample_answers or [])
        if not samples:
            continue
        asking = [q.id for q in rnd.script.questions if step.id in q.step_ids]
        own = [t for t in rnd.transcripts if t.question_id in set(asking) - samples]
        if not own or not transcripts_with_quote(rating.quote, own, GuardConfig()):
            found.append(step.id)
    return found


class BriefingSummary(Wire):
    id: str
    site_id: str
    task_id: str
    task_title: str
    supervisor_lang: str
    worker_lang: str
    status: Status
    rounds: int
    decision: Decision | None = None
    created_at: str
    permit: PermitLink | None = None  # v0.5.2

    def wire(self) -> dict[str, Any]:
        return {**super().wire(), "permit": self.permit.wire() if self.permit else None}


class CheckResult(Wire):
    """What `pipeline.run_check` returns (API.md, "Check workflow")."""

    transcripts: list[Transcript]
    pass_a: list[Rating]
    pass_b: list[Rating]
    ratings: list[Rating]
    next_action: NextAction
    model_ids: dict[str, str] = {}
    timings_ms: dict[str, float] = {}


# Request bodies --------------------------------------------------------------------------------


class SopInput(Wire):
    title: str
    text: str


class CreateBriefing(Wire):
    site_id: str
    task_id: str
    supervisor_lang: str
    worker_lang: str
    instruction: str
    sop: SopInput | None = None
    permit: PermitLink | None = None  # v0.5.2
    sop_ref: SopRef | None = None  # library (2026-10-16): an approved library version


class PatchBriefing(Wire):
    instruction: str


class PutSteps(Wire):
    steps: list[Step]


class CreateRound(Wire):
    step_ids: list[str] | None = None
    supervisor_note: str | None = None


class DecisionBody(Wire):
    value: Literal["go", "no_go"]
    reason: str | None = None
    by: str | None = None


class TtsBody(Wire):
    """Endpoint 12: a line of round `n`'s script, which the caller's own briefing holds."""

    briefing_id: str
    n: int
    text: str


class CheckMeta(Wire):
    mode: Mode = "turn"
    sample_answers: list[str] | None = None  # v0.4: question ids answered by a stored sample


class ApproveBody(Wire):
    """Endpoint 23: the supervisor has read the script and its back-translation."""

    by: str | None = None


class HazardAckBody(Wire):
    """Endpoint 22: what the supervisor did about the hazard."""

    note: str = ""
    by: str | None = None


class ConsentBody(Wire):
    """Privacy (16 Oct): the worker's choice for round n, "I agree" (true) or "Not now" (false).
    Strict: "true", 1 or a missing value is 422, never read as a yes."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    given: StrictBool


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_briefing_id() -> str:
    """ "b_" plus 12 lowercase base32 characters (60 random bits)."""
    return "b_" + base64.b32encode(secrets.token_bytes(8)).decode().lower()[:12]
