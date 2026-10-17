"""Permits: one per decided briefing. Go releases a permit, No-go holds it.

The decision is the supervisor's (Say It Back never approves work); the permit only follows it,
and carries what was still open when it was made. A briefing's decision is final, so a second post
for the same briefing (a retry) returns the permit it already has.

API v0.5.2, permit-to-work grouping: a post whose record names a `permit` ({ref, crewSize, slot})
is filed under that permit's ref (matched case-insensitively, kept as first typed), one entry per
worker slot holding that slot's latest decision. A later decision for the same slot replaces it (a
re-brief); an older one arriving late, or a repeat of the same briefing, changes nothing. The
permit is released only when every slot 1..crewSize holds a Go, otherwise held, with `verified`
and `waiting`. A post whose crewSize differs from the permit's is refused (CrewMismatch) and
changes nothing. No worker is ever named: the slot number is the only per-worker field.

Where permits live (PTW_STORE): `memory` (the default) keeps them in this process, and in a JSON
file too when PTW_STORE_FILE names one (written atomically after each new permit); `firestore`
keeps them in Firestore (firestore_book.py), so every instance, and a new one, shows the same board.

Pilot (Say It Back docs/EPERMIT_ADAPTER.md): a post may carry an `Idempotency-Key`. The book keeps
each key it took with the briefing and permit it filed, in the same write as the permit, so a
retried delivery is answered as a duplicate (Duplicate, 409) and changes nothing, and a key reused
for another briefing is refused (KeyReused, 422). Security fixes B: the key must be the one its own
signed record names, `sib-<briefingId>-<first 16 hex of recordHash>` (KeyMismatch, 422), so a
replayed body cannot take a key that a later briefing's delivery will need.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

BRIEFING_ID = re.compile(r"^b_[a-z2-7]{12}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
SHORT = 80
TEXT = 300
DEMO_LABEL = "Demo: synthetic sample answers"
REF = re.compile(r"^[A-Za-z0-9._/-]{1,32}$")
MAX_CREW = 6
DELIVERY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")  # Idempotency-Key
MAX_KEYS = 10_000  # the memory book forgets the oldest keys past this


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)


class StepIn(_In):
    id: str = Field(max_length=16)
    text: str = Field(default="", max_length=TEXT)


class DecisionIn(_In):
    value: Literal["go", "no_go"]
    by: str | None = Field(default=None, max_length=SHORT)
    open_step_ids: list[str] = Field(default=[], alias="openStepIds", max_length=6)
    open_hazard_ids: list[str] = Field(default=[], alias="openHazardIds", max_length=10)
    # 2026-10-17: a Go after the worker declined the AI check: the supervisor checked them in
    # person. A JSON boolean only; a record from an older backend has none (false).
    in_person: bool = Field(default=False, alias="inPerson", strict=True)


class SampleIn(_In):
    round: int
    question_id: str = Field(alias="questionId", max_length=16)


class PermitIn(_In):
    """The record's `permit`: {ref, crewSize, slot}, and nothing else (no name, no ID)."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    ref: str = Field(pattern=REF.pattern)
    crew_size: int = Field(alias="crewSize", ge=1, le=MAX_CREW, strict=True)
    slot: int = Field(ge=1, le=MAX_CREW, strict=True)

    @field_validator("ref", mode="before")
    @classmethod
    def _trimmed(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _slot_on_the_permit(self) -> PermitIn:
        if self.slot > self.crew_size:
            raise ValueError("slot must be between 1 and crewSize")
        return self

    @property
    def key(self) -> str:
        return self.ref.upper()


class DecisionRecord(_In):
    """The fields of Say It Back's JSON record that a permit needs."""

    event: Literal["briefing_decided"]
    briefing_id: str = Field(alias="briefingId", pattern=BRIEFING_ID.pattern)
    site_id: str = Field(alias="siteId", max_length=SHORT)
    task_id: str = Field(alias="taskId", max_length=SHORT)
    steps: list[StepIn] = Field(default=[], max_length=6)
    decision: DecisionIn
    decided_at: str = Field(default="", alias="decidedAt", max_length=SHORT)
    record_hash: str = Field(alias="recordHash", pattern=HASH.pattern)
    sample_answers: list[SampleIn] = Field(default=[], alias="sampleAnswers", max_length=12)
    permit: PermitIn | None = None  # v0.5.2


class SlotDecision(BaseModel):
    """One worker slot of a grouped permit: that slot's latest decision."""

    slot: int
    briefing_id: str
    decision: Literal["go", "no_go"]
    decided_by: str | None = None  # kept in the stub's own record, never shown or served
    decided_at: str = ""
    record_hash: str
    open_steps: list[dict[str, str]] = []
    open_hazards: list[str] = []
    sample_answers: list[dict[str, Any]] = []
    received_at: str
    in_person: bool = False  # 2026-10-17: checked in person, no AI check (the reason stays out)

    @property
    def go_with_open_steps(self) -> bool:
        """A Go the supervisor gave with steps still open (with a reason, kept in the record)."""
        return self.decision == "go" and bool(self.open_steps)

    def wire(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "decision": self.decision,
            "briefingId": self.briefing_id,
            "recordHash": self.record_hash,
            "decidedAt": self.decided_at,
            "openSteps": self.open_steps,
            "openHazards": self.open_hazards,
            "goWithOpenSteps": self.go_with_open_steps,
            "inPerson": self.in_person,
        }


class Permit(BaseModel):
    id: str  # PTW-<n>
    status: Literal["released", "held"]
    briefing_id: str
    site_id: str
    task_id: str
    decision: Literal["go", "no_go"]
    decided_by: str | None = None  # kept in the stub's own record, never shown or served
    decided_at: str = ""
    open_steps: list[dict[str, Any]] = []  # a grouped permit's carry the worker's `slot` too
    open_hazards: list[str] = []
    record_hash: str
    received_at: str
    sample_answers: list[dict[str, Any]] = []  # [{round, questionId}]: answers that were samples
    # 2026-10-17: checked in person (no AI check); for a grouped permit, some worker on it was
    in_person: bool = False
    # v0.5.2, a grouped permit: the site's permit number as first typed, the crew, the slots
    ref: str | None = None
    crew_size: int | None = None
    slots: list[SlotDecision] = []

    @model_validator(mode="after")
    def _derived_from_slots(self) -> Permit:
        """A grouped permit's status, decision, open steps, hazards and sample answers are its
        slots', recomputed whenever it is read: a permit stored by older code shows by today's
        rules, with no migration, in either store."""
        if self.grouped:
            _aggregate(self)
        return self

    @property
    def demo(self) -> bool:
        """Some answers were stored synthetic samples, not the worker's own: a demo permit."""
        return bool(self.sample_answers)

    @property
    def grouped(self) -> bool:
        return self.ref is not None

    def slot(self, n: int) -> SlotDecision | None:
        return next((s for s in self.slots if s.slot == n), None)

    @property
    def verified(self) -> int:
        """Slots whose latest decision is Go."""
        return sum(1 for s in self.slots if s.decision == "go")

    @property
    def waiting(self) -> list[int]:
        """Slots 1..crewSize with no decision yet, or a No-go."""
        held = [n for n in range(1, (self.crew_size or 0) + 1) if not self._go(n)]
        return held

    def _go(self, n: int) -> bool:
        entry = self.slot(n)
        return entry is not None and entry.decision == "go"

    def wire(self) -> dict[str, Any]:
        """The public form: what /api/permits serves. The decider's name stays in the record."""
        return {
            "id": self.id,
            "status": self.status,
            "briefingId": self.briefing_id,
            "siteId": self.site_id,
            "taskId": self.task_id,
            "decision": self.decision,
            "decidedAt": self.decided_at,
            "openSteps": self.open_steps,
            "openHazards": self.open_hazards,
            "recordHash": self.record_hash,
            "receivedAt": self.received_at,
            "demo": DEMO_LABEL if self.demo else None,
            "sampleAnswers": self.sample_answers,
            "inPerson": self.in_person,
            "ref": self.ref,
            "crewSize": self.crew_size,
            "verified": self.verified if self.grouped else None,
            "waiting": self.waiting,
            "slots": [s.wire() for s in sorted(self.slots, key=lambda s: s.slot)],
        }


class BadRecord(ValueError):
    """The body is not a Say It Back decision record."""


class CrewMismatch(ValueError):
    """A post's crewSize differs from its permit's: refused, nothing changes (409)."""


class Duplicate(Exception):  # noqa: N818 - it is an answer, not an error
    """The post's Idempotency-Key was already taken for this briefing: nothing changes (409
    `duplicate`), and the permit it filed is returned."""

    def __init__(self, permit: Permit) -> None:
        super().__init__("This delivery was already received.")
        self.permit = permit


class KeyReused(ValueError):
    """The post's Idempotency-Key was taken for another briefing: refused (422)."""


class KeyMismatch(ValueError):
    """The post's Idempotency-Key is not the one its own record names: refused (422), nothing
    changes."""


def record_key(record: DecisionRecord) -> str:
    """The Idempotency-Key Say It Back sends with this record (its webhook.idempotency_key): both
    parts are inside the signed body."""
    return f"sib-{record.briefing_id}-{record.record_hash[:16]}"


def check_key(record: DecisionRecord, key: str | None) -> None:
    """Raise KeyMismatch when a post carries a key that is not its own record's."""
    if key and key != record_key(record):
        raise KeyMismatch(
            "Idempotency-Key must be sib-<briefingId>-<first 16 hex of recordHash> of this record."
        )


def parse_record(body: bytes) -> DecisionRecord:
    try:
        return DecisionRecord.model_validate(json.loads(body))
    except (ValueError, ValidationError):  # a JSON error is a ValueError too
        raise BadRecord("Not a briefing_decided record.") from None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_permit(record: DecisionRecord, number: int, received_at: str | None = None) -> Permit:
    """Permit PTW-<number> for this decision: released for a Go, held for a No-go."""
    texts = {s.id: s.text for s in record.steps}
    d = record.decision
    return Permit(
        id=f"PTW-{number}",
        status="released" if d.value == "go" else "held",
        briefing_id=record.briefing_id,
        site_id=record.site_id,
        task_id=record.task_id,
        decision=d.value,
        decided_by=d.by,
        decided_at=record.decided_at,
        open_steps=[{"id": sid, "text": texts.get(sid, "")} for sid in d.open_step_ids],
        open_hazards=list(d.open_hazard_ids),
        record_hash=record.record_hash,
        received_at=received_at or now_iso(),
        sample_answers=[
            {"round": a.round, "questionId": a.question_id} for a in record.sample_answers
        ],
        in_person=d.in_person,
    )


def _slot_decision(record: DecisionRecord, received_at: str) -> SlotDecision:
    texts = {s.id: s.text for s in record.steps}
    d = record.decision
    assert record.permit is not None
    return SlotDecision(
        slot=record.permit.slot,
        briefing_id=record.briefing_id,
        decision=d.value,
        decided_by=d.by,
        decided_at=record.decided_at,
        record_hash=record.record_hash,
        open_steps=[{"id": sid, "text": texts.get(sid, "")} for sid in d.open_step_ids],
        open_hazards=list(d.open_hazard_ids),
        sample_answers=[
            {"round": a.round, "questionId": a.question_id} for a in record.sample_answers
        ],
        received_at=received_at,
        in_person=d.in_person,
    )


def _aggregate(permit: Permit) -> None:
    """A grouped permit's own fields that follow from its slots: released only when every slot
    holds a Go. What was open is every slot's, a Go given with steps open as much as a No-go,
    labelled by worker: each step with its `slot`, each hazard as "<id> (worker <slot>)"."""
    released = not permit.waiting
    permit.status = "released" if released else "held"
    permit.decision = "go" if released else "no_go"
    ordered = sorted(permit.slots, key=lambda s: s.slot)
    permit.open_steps = [{"slot": e.slot, **step} for e in ordered for step in e.open_steps]
    permit.open_hazards = [f"{h} (worker {e.slot})" for e in ordered for h in e.open_hazards]
    permit.sample_answers = [a for e in ordered for a in e.sample_answers]
    permit.in_person = any(e.in_person for e in ordered)


def _settle(permit: Permit, record: DecisionRecord, latest: SlotDecision) -> None:
    """After a post: the briefing, site, task, hash and times are the latest post's, and the rest
    follows from the slots (_aggregate)."""
    permit.briefing_id, permit.site_id, permit.task_id = (
        latest.briefing_id,
        record.site_id,
        record.task_id,
    )
    permit.decided_by, permit.decided_at = latest.decided_by, latest.decided_at
    permit.record_hash, permit.received_at = latest.record_hash, latest.received_at
    _aggregate(permit)


def new_group(record: DecisionRecord, number: int, received_at: str | None = None) -> Permit:
    """Permit PTW-<number> for a permit ref's first post."""
    assert record.permit is not None
    entry = _slot_decision(record, received_at or now_iso())
    permit = Permit(
        id=f"PTW-{number}",
        status="held",
        briefing_id=record.briefing_id,
        site_id=record.site_id,
        task_id=record.task_id,
        decision=record.decision.value,
        record_hash=record.record_hash,
        received_at=entry.received_at,
        ref=record.permit.ref,
        crew_size=record.permit.crew_size,
        slots=[entry],
    )
    _settle(permit, record, entry)
    return permit


def file_into(permit: Permit, record: DecisionRecord, received_at: str | None = None) -> bool:
    """File a post into its grouped permit; True when the permit changed. Raises CrewMismatch,
    changing nothing, when the crew size differs."""
    assert record.permit is not None
    if permit.crew_size != record.permit.crew_size:
        raise CrewMismatch(
            f"Permit {permit.ref} covers {permit.crew_size} worker(s), not "
            f"{record.permit.crew_size}."
        )
    current = permit.slot(record.permit.slot)
    if current is not None and (
        current.briefing_id == record.briefing_id or record.decided_at < current.decided_at
    ):
        return False  # a repeat of this slot's decision, or an older one arriving late
    entry = _slot_decision(record, received_at or now_iso())
    permit.slots = [s for s in permit.slots if s.slot != entry.slot] + [entry]
    _settle(permit, record, entry)
    return True


class PermitStore(Protocol):
    """What the app needs from wherever permits live."""

    name: str

    async def record(
        self, record: DecisionRecord, received_at: str | None = None, key: str | None = None
    ) -> tuple[Permit, bool]: ...

    async def newest_first(self) -> list[Permit]: ...


class PermitBook:
    """PTW_STORE=memory: this process's permits, also in PTW_STORE_FILE when set."""

    name = "memory"

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._keys: dict[str, dict[str, str]] = {}  # Idempotency-Key -> {briefingId, permit}
        self._permits: list[Permit] = self._load()

    def _load(self) -> list[Permit]:
        if self._path is None or not self._path.is_file():
            return []
        stored = json.loads(self._path.read_text(encoding="utf-8"))
        self._keys = dict(stored.get("deliveries", {}))
        return [Permit.model_validate(r) for r in stored.get("permits", [])]

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rows = [p.model_dump(mode="json") for p in self._permits]
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"permits": rows, "deliveries": self._keys}, handle, ensure_ascii=False)
        Path(tmp).replace(self._path)

    def _seen(self, key: str | None, record: DecisionRecord) -> None:
        """Raise Duplicate (or KeyReused) when this delivery's key was already taken."""
        taken = self._keys.get(key) if key else None
        if taken is None:
            return
        if taken["briefingId"] != record.briefing_id:
            raise KeyReused("This Idempotency-Key was used for another briefing.")
        raise Duplicate(next(p for p in self._permits if p.id == taken["permit"]))

    def _take(self, key: str | None, record: DecisionRecord, permit: Permit) -> None:
        if not key:
            return
        self._keys[key] = {"briefingId": record.briefing_id, "permit": permit.id}
        while len(self._keys) > MAX_KEYS:
            self._keys.pop(next(iter(self._keys)))
        self._save()

    async def record(
        self, record: DecisionRecord, received_at: str | None = None, key: str | None = None
    ) -> tuple[Permit, bool]:
        """The permit for this decision, and whether it is new. Raises KeyMismatch when `key` (the
        post's Idempotency-Key) is not the record's own, and Duplicate when it was already taken,
        changing nothing."""
        check_key(record, key)
        with self._lock:
            self._seen(key, record)
            permit, created = self._filed(record, received_at)
            self._take(key, record, permit)
            return permit, created

    def _filed(self, record: DecisionRecord, received_at: str | None) -> tuple[Permit, bool]:
        if record.permit is not None:
            return self._file(record, received_at)
        for permit in self._permits:
            if not permit.grouped and permit.briefing_id == record.briefing_id:
                return permit, False
        permit = new_permit(record, len(self._permits) + 1, received_at)
        self._permits.append(permit)
        self._save()
        return permit, True

    def _file(self, record: DecisionRecord, received_at: str | None) -> tuple[Permit, bool]:
        assert record.permit is not None
        key = record.permit.key
        group = next((p for p in self._permits if p.ref and p.ref.upper() == key), None)
        if group is None:
            group = new_group(record, len(self._permits) + 1, received_at)
            self._permits.append(group)
            self._save()
            return group, True
        if file_into(group, record, received_at):  # CrewMismatch leaves it as it was
            self._save()
        return group, False

    async def newest_first(self) -> list[Permit]:
        with self._lock:
            return list(reversed(self._permits))
