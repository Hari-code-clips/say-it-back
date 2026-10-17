"""The record chain (API.md v0.4, "Record chain"): a hash-chained, tamper-evident briefing record.

Every state change appends one `ChainEvent` inside the same `repo.mutate` atomic update as the
change it records, and nothing else writes `events` (repo.py refuses a change that rewrites an
earlier one). Each event's hash covers the previous event's hash and the event itself:

    hash = sha256_hex(prevHash + "\\n" + canonical({seq, type, at, data}))

`canonical` is JSON with sorted keys, no whitespace and UTF-8 characters unescaped. Content is
bound by digest, `sha256_hex(canonical(<wire form>))` (a string's wire form is its JSON string), so
an event carries ids, verdicts and digests, never a transcript, an answer, audio or a device key.

`verify` recomputes every link and re-derives each bound digest from the record as it is stored
now. An edit to the stored record (a rating, a step, the decision, an event) is detected at the
`seq` of the event that binds it. Someone who can rewrite the whole store can rebuild the chain:
that is why the decision's `recordHash` also goes to every webhook, outside the store.

A briefing made before v0.4 has no events. It never starts a chain part-way through its life (its
earlier changes are unrecorded), so it keeps verifying as `no_chain`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Any

from sayitback.models import (
    Briefing,
    ChainEvent,
    ChainEventType,
    Decision,
    Hazard,
    Round,
    now_iso,
)

GENESIS = "0" * 64
INSTRUCTION_EVENTS = ("created", "instruction_edited")
STEPS_EVENTS = ("steps_proposed", "steps_confirmed")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(value: Any) -> str:
    """The digest that binds a piece of content: sha256_hex(canonical(<wire form>))."""
    return sha256_hex(canonical(value))


def event_body(event: ChainEvent) -> dict[str, Any]:
    """The event without `hash` and `prevHash`: what its hash covers."""
    return {"seq": event.seq, "type": event.type, "at": event.at, "data": event.data}


def link_hash(prev_hash: str, body: dict[str, Any]) -> str:
    return sha256_hex(prev_hash + "\n" + canonical(body))


def append(
    b: Briefing, kind: ChainEventType, data: dict[str, Any], at: str | None = None
) -> ChainEvent | None:
    """Append one event and move `recordHash` to it. Call it inside the change it records."""
    if not b.events and kind != "created":
        return None  # a record from before v0.4: no chain can vouch for its past
    prev = b.events[-1].hash if b.events else GENESIS
    body = {"seq": len(b.events) + 1, "type": kind, "at": at or now_iso(), "data": data}
    event = ChainEvent(**body, prev_hash=prev, hash=link_hash(prev, body))
    b.events.append(event)
    b.record_hash = event.hash
    return event


# What each event binds -------------------------------------------------------------------------


def steps_sha(b: Briefing) -> str:
    return digest([s.wire() for s in b.steps])


def script_sha(r: Round) -> str:
    return digest(r.script.wire())


def ratings_sha(r: Round) -> str:
    return digest([x.wire() for x in r.ratings])


def evidence_sha(r: Round) -> str:
    """What the judgement rests on besides the ratings: transcripts, both passes, the delivery
    check, the next action and the sample answers."""
    return digest(
        {
            "transcripts": [t.wire() for t in r.transcripts],
            "passA": [x.wire() for x in r.pass_a],
            "passB": [x.wire() for x in r.pass_b],
            "delivery": [d.wire() for d in r.delivery],
            "nextAction": r.next_action,
            "sampleAnswers": list(r.sample_answers or []),
        }
    )


def live_sha(r: Round) -> str | None:
    """What Live said and heard (round.live), as the check read it, or None without a session."""
    return digest(r.live.wire()) if r.live is not None else None


def derived_verdicts(b: Briefing) -> dict[str, str]:
    """latestVerdicts as the rounds' ratings make it: each step's verdict from the last round that
    rated it."""
    verdicts: dict[str, str] = {}
    for rnd in b.rounds:
        verdicts.update({x.step_id: x.verdict for x in rnd.ratings})
    return verdicts


def report_sha(h: Hazard) -> str:
    return digest({"original": h.original, "translation": h.translation, "lang": h.detected_lang})


CREATED_KEYS = ("siteId", "taskId", "supervisorLang", "workerLang", "permit", "sopRef")
SOP_KEYS = ("sopId", "sopVersion", "sopSha256")


def created(b: Briefing) -> dict[str, Any]:
    """v0.5.2: with `permit` ({ref, crewSize, slot}) only when the briefing has one, so a record
    made without one keeps the v0.4 event shape and verifies as before."""
    data = {
        "instructionSha256": digest(b.instruction),
        "siteId": b.site_id,
        "taskId": b.task_id,
        "supervisorLang": b.supervisor_lang,
        "workerLang": b.worker_lang,
        "sopId": b.sop.id,
        "sopVersion": b.sop.version,
        "sopSha256": digest(b.sop.wire()),
    }
    if b.permit is not None:
        data["permit"] = b.permit.wire()
    if b.sop_ref is not None:  # library (2026-10-16): only when present, as for permit
        data["sopRef"] = b.sop_ref.wire()
    return data


def instruction_edited(b: Briefing) -> dict[str, Any]:
    return {"instructionSha256": digest(b.instruction)}


def steps_proposed(b: Briefing) -> dict[str, Any]:
    return {"stepIds": [s.id for s in b.steps], "stepsSha256": steps_sha(b)}


def steps_confirmed(b: Briefing) -> dict[str, Any]:
    return {
        "stepsVersion": b.steps_version,
        "stepIds": [s.id for s in b.steps],
        "stepsSha256": steps_sha(b),
    }


def round_created(r: Round) -> dict[str, Any]:
    return {"n": r.n, "kind": r.kind, "stepIds": list(r.step_ids), "scriptSha256": script_sha(r)}


def script_approved(r: Round) -> dict[str, Any]:
    return {"n": r.n, "scriptSha256": script_sha(r), "by": r.approved_by}


def round_judged(r: Round) -> dict[str, Any]:
    return {
        "n": r.n,
        "mode": r.mode,
        "verdicts": {x.step_id: x.verdict for x in r.ratings},
        "ratingsSha256": ratings_sha(r),
        "deliveryOk": all(d.ok for d in r.delivery),
        "sampleAnswers": list(r.sample_answers or []),
        "evidenceSha256": evidence_sha(r),
        "liveSha256": live_sha(r),
    }


def consent(r: Round) -> dict[str, Any]:
    """Privacy (16 Oct): the worker's choice for round n. A record with no consent event (made
    before it, or a stored-sample round that never asked) binds nothing and verifies as before."""
    assert r.consent is not None
    return {"n": r.n, "given": r.consent.given}


def hazard_raised(h: Hazard) -> dict[str, Any]:
    return {"hazardId": h.id, "kind": h.kind, "round": h.round, "reportSha256": report_sha(h)}


def hazard_acknowledged(h: Hazard) -> dict[str, Any]:
    assert h.ack is not None
    return {
        "hazardId": h.id,
        "kind": h.kind,
        "noteSha256": digest(h.ack.note),
        "by": h.ack.by,
    }


def decided(d: Decision) -> dict[str, Any]:
    """2026-10-17: with `inPerson: true` only for a Go after an in-person check, so every other
    decision keeps the v0.4 event shape and verifies as before (as `permit` in `created`)."""
    data = {
        "value": d.value,
        "openStepIds": list(d.open_step_ids),
        "openHazardIds": list(d.open_hazard_ids),
        "reasonSha256": digest(d.reason) if d.reason else None,
        "by": d.by,
    }
    if d.in_person:
        data["inPerson"] = True
    return data


# Verify ----------------------------------------------------------------------------------------

Check = Callable[[], str | None]  # None when the content still matches, else the reason


def _differs(stored: dict[str, Any], expected: dict[str, Any], keys: Iterable[str]) -> bool:
    return any(stored.get(k) != expected.get(k) for k in keys)


def _latest(events: list[ChainEvent], match: Callable[[ChainEvent], bool]) -> int | None:
    found = [i for i, e in enumerate(events) if match(e)]
    return found[-1] if found else None


def _round_of(b: Briefing, data: dict[str, Any]) -> Round | None:
    n = data.get("n")
    return b.round_n(n) if isinstance(n, int) and not isinstance(n, bool) else None


def _bindings(b: Briefing) -> tuple[dict[int, Check], list[str]]:
    """Which event binds which content (the latest of its kind does), and the content that no
    event records at all."""
    events = b.events
    checks: dict[int, Check] = {}
    unrecorded: list[str] = []

    def bind(index: int | None, check: Check, missing: str | None = None) -> None:
        if index is None:
            if missing:
                unrecorded.append(missing)
            return
        earlier = checks.get(index)
        checks[index] = (lambda: earlier() or check()) if earlier else check

    first = events[0] if events else None
    if first is not None and first.type == "created":
        stored, now = first.data, created(b)

        def created_check() -> str | None:
            if _differs(stored, now, SOP_KEYS):
                return "sop_mismatch"
            return "created_mismatch" if _differs(stored, now, CREATED_KEYS) else None

        bind(0, created_check)

    i = _latest(events, lambda e: e.type in INSTRUCTION_EVENTS)
    bind(
        i,
        lambda: (
            "instruction_mismatch"
            if events[i].data.get("instructionSha256") != digest(b.instruction)
            else None
        ),
        "instruction_unrecorded",
    )

    j = _latest(events, lambda e: e.type in STEPS_EVENTS)
    keys = ("stepsSha256", "stepIds", "stepsVersion")

    def steps_check() -> str | None:
        assert j is not None
        e = events[j]
        expected = steps_confirmed(b) if e.type == "steps_confirmed" else steps_proposed(b)
        return "steps_mismatch" if _differs(e.data, expected, keys) else None

    bind(j, steps_check, "steps_unrecorded" if b.steps else None)

    for r in b.rounds:
        _bind_round(events, r, bind)
    for index, e in enumerate(events):  # an event about a round the record no longer has
        if e.type in ("round_created", "script_approved", "round_judged", "consent") and (
            _round_of(b, e.data) is None
        ):
            bind(index, lambda: "round_missing")

    for h in b.hazards:
        _bind_hazard(events, h, bind)
    for index, e in enumerate(events):
        if e.type.startswith("hazard_") and b.hazard(str(e.data.get("hazardId"))) is None:
            bind(index, lambda: "hazard_missing")

    last_judged = _latest(events, lambda e: e.type == "round_judged")
    bind(
        last_judged,
        lambda: "verdicts_mismatch" if b.latest_verdicts != derived_verdicts(b) else None,
        "verdicts_unrecorded" if b.latest_verdicts else None,
    )

    k = _latest(events, lambda e: e.type == "decided")

    def decision_check() -> str | None:
        assert k is not None
        if b.decision is None or b.status != "decided":
            return "decision_mismatch"
        keys = ("value", "openStepIds", "openHazardIds", "reasonSha256", "by", "inPerson")
        return "decision_mismatch" if _differs(events[k].data, decided(b.decision), keys) else None

    bind(k, decision_check, "decision_unrecorded" if b.decision is not None else None)
    return checks, unrecorded


def _bind_round(events: list[ChainEvent], r: Round, bind: Any) -> None:
    def about(kind: str) -> int | None:
        return _latest(events, lambda e: e.type == kind and e.data.get("n") == r.n)

    c = about("round_created")
    bind(
        c,
        lambda: (
            "script_mismatch"
            if _differs(events[c].data, round_created(r), ("kind", "stepIds", "scriptSha256"))
            else None
        ),
        f"round_{r.n}_unrecorded",
    )
    a = about("script_approved")

    def approval_check() -> str | None:
        assert a is not None
        if r.approved_at is None or events[a].data.get("scriptSha256") != script_sha(r):
            return "script_mismatch"
        return "approval_mismatch" if events[a].data.get("by") != r.approved_by else None

    bind(a, approval_check, f"approval_{r.n}_unrecorded" if r.approved_at else None)
    j = about("round_judged")
    keys = ("mode", "verdicts", "ratingsSha256", "deliveryOk", "sampleAnswers")

    def judged_check() -> str | None:
        assert j is not None
        if r.judged_at is None or _differs(events[j].data, round_judged(r), keys):
            return "ratings_mismatch"
        data = events[j].data
        if "evidenceSha256" in data and data["evidenceSha256"] != evidence_sha(r):
            return "evidence_mismatch"
        if "liveSha256" in data and data["liveSha256"] != live_sha(r):
            return "live_mismatch"
        return None

    bind(j, judged_check, f"judgement_{r.n}_unrecorded" if r.judged_at else None)
    k = about("consent")  # privacy (16 Oct): the latest consent event binds the round's consent
    bind(
        k,
        lambda: (
            "consent_mismatch"
            if r.consent is None or events[k].data.get("given") is not r.consent.given
            else None
        ),
        f"consent_{r.n}_unrecorded" if r.consent is not None else None,
    )


def _bind_hazard(events: list[ChainEvent], h: Hazard, bind: Any) -> None:
    def about(kind: str) -> int | None:
        return _latest(events, lambda e: e.type == kind and e.data.get("hazardId") == h.id)

    raised = about("hazard_raised")
    bind(
        raised,
        lambda: (
            "hazard_mismatch"
            if _differs(events[raised].data, hazard_raised(h), ("kind", "round", "reportSha256"))
            else None
        ),
        f"hazard_{h.id}_unrecorded",
    )
    acked = about("hazard_acknowledged")
    bind(
        acked,
        lambda: (
            "hazard_mismatch"
            if h.ack is None
            or _differs(events[acked].data, hazard_acknowledged(h), ("kind", "noteSha256", "by"))
            else None
        ),
        f"hazard_{h.id}_ack_unrecorded" if h.ack is not None else None,
    )


def verify(b: Briefing) -> dict[str, Any]:
    """Endpoint 25: `{ok, events, recordHash, brokenAt?, reason?}`. `brokenAt` is the `seq` of the
    first event whose link, hash or bound content no longer matches the stored record."""
    events = b.events

    def broken(seq: int, reason: str) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "events": len(events), "recordHash": b.record_hash}
        return {**out, "brokenAt": seq, "reason": reason}

    if not events:
        return {"ok": False, "events": 0, "recordHash": b.record_hash, "reason": "no_chain"}
    checks, unrecorded = _bindings(b)
    prev = GENESIS
    for index, event in enumerate(events):
        seq = index + 1
        if event.seq != seq:
            return broken(seq, "seq_mismatch")
        if event.prev_hash != prev:
            return broken(seq, "prev_hash_mismatch")
        if link_hash(prev, event_body(event)) != event.hash:
            return broken(seq, "hash_mismatch")
        check = checks.get(index)
        problem = check() if check else None
        if problem:
            return broken(seq, problem)
        prev = event.hash
    if b.record_hash != prev:
        return broken(len(events), "record_hash_mismatch")
    if unrecorded:  # content that no event records: an edit made after the last event
        return broken(len(events), "unrecorded_change")
    return {"ok": True, "events": len(events), "recordHash": prev}
