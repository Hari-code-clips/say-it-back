"""Wire models: the Pydantic twins of the TypeScript types in docs/API.md.

Python attributes are snake_case; the wire (and the stored JSON) is camelCase. Every model also
accepts snake_case, so `Step(**catalog_reference_step)` and `Step.model_validate(wire)` both work.
"""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Verdict = Literal["covered", "missed", "contradicted", "unclear"]
StepSource = Literal["instruction", "sop", "both"]
Status = Literal["draft", "steps_proposed", "steps_confirmed", "briefing", "judged", "decided"]
NextAction = Literal["decide", "reexplain"]
Mode = Literal["live", "turn"]

# Severity for "the worse verdict wins" (guard rule 1).
SEVERITY: dict[str, int] = {"covered": 0, "unclear": 1, "missed": 2, "contradicted": 3}


class Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    def wire(self) -> dict[str, Any]:
        """camelCase JSON with absent optionals omitted, as the API returns and the store keeps."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


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
    segment: str
    similarity: float
    script_ok: bool


class LiveRecord(Wire):
    model: str
    started_at: str
    ended_at: str | None = None
    delivered: dict[str, str] = {}
    heard: dict[str, str] = {}


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
    judged_at: str | None = None


class Sop(Wire):
    id: str
    version: str
    title: str
    text: str


class Decision(Wire):
    value: Literal["go", "no_go"]
    reason: str | None = None
    by: str | None = None
    open_step_ids: list[str]
    at: str


class Briefing(Wire):
    id: str
    site_id: str
    task_id: str
    sop: Sop
    supervisor_lang: str
    worker_lang: str
    instruction: str
    status: Status = "draft"
    steps: list[Step] = []
    steps_version: int = 0
    conflicts: list[Conflict] = []
    rounds: list[Round] = []
    latest_verdicts: dict[str, Verdict] = {}
    decision: Decision | None = None
    prompt_version: str
    created_at: str
    updated_at: str

    def open_step_ids(self) -> list[str]:
        return [s.id for s in self.steps if self.latest_verdicts.get(s.id) != "covered"]

    def round_n(self, n: int) -> Round | None:
        return self.rounds[n - 1] if 1 <= n <= len(self.rounds) else None


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


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_briefing_id() -> str:
    """ "b_" plus 12 lowercase base32 characters (60 random bits)."""
    return "b_" + base64.b32encode(secrets.token_bytes(8)).decode().lower()[:12]
