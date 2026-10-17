"""Briefing use cases: create, edit, extract, confirm, decide, hazards, verify. Rounds and check:
rounds.py.

Every one is for a caller (caller.py): it reads and writes only that caller's briefings, and a
call that needs the model reserves its share of the daily Gemini cap (daily_cap.py), against the
caller's address too, once the state checks have passed.

Model calls run outside the store's atomic update. Each update re-checks the state, so a request
that raced another one fails with 409 instead of overwriting it. Each update also appends the
event that records it to the briefing's hash chain (chain.py), in the same atomic step.
"""

from __future__ import annotations

import logging
from typing import Any

from sayitback import chain, phases, state_machine, validators
from sayitback.caller import Caller
from sayitback.daily_cap import EXTRACT_CALLS, HAZARD_CALLS, DailyCap
from sayitback.errors import InvalidState, NotFound, Unprocessable
from sayitback.models import (
    Briefing,
    Conflict,
    CreateBriefing,
    DecisionBody,
    Hazard,
    HazardAck,
    HazardAckBody,
    HazardKind,
    Step,
    new_briefing_id,
    now_iso,
)
from sayitback.prompts import PROMPT_VERSION
from sayitback.repo import Repo
from sayitback.runtime import Runtime
from sayitback.sop_library import SopLibrary

log = logging.getLogger("sayitback.service")


class Briefings:
    def __init__(self, rt: Runtime, repo: Repo, cap: DailyCap) -> None:
        self.rt = rt
        self.repo = repo
        self.cap = cap

    async def create(self, body: CreateBriefing, caller: Caller) -> Briefing:
        s = self.rt.settings
        sop = validators.briefing_request(body, s)
        if sop is None:  # library (2026-10-16): an approved version of the site's SOP library
            sop = await SopLibrary(self.repo.store, s).briefing_sop(caller, body)
        now = now_iso()
        briefing = Briefing(
            id=new_briefing_id(),
            site_id=body.site_id,
            task_id=body.task_id,
            sop=sop,
            supervisor_lang=body.supervisor_lang,
            worker_lang=body.worker_lang,
            instruction=validators.instruction(body.instruction, s),
            permit=body.permit,
            sop_ref=body.sop_ref,
            prompt_version=PROMPT_VERSION,
            created_at=now,
            updated_at=now,
        )
        chain.append(briefing, "created", chain.created(briefing), at=now)
        return await self.repo.create(briefing, caller.owner)

    async def patch_instruction(self, briefing_id: str, text: str, caller: Caller) -> Briefing:
        value = validators.instruction(text, self.rt.settings)

        def change(b: Briefing) -> None:
            state_machine.require_editable(b, "Editing the instruction")
            b.instruction = value
            chain.append(b, "instruction_edited", chain.instruction_edited(b))

        return await self.repo.mutate(briefing_id, caller.owner, change)

    async def extract(self, briefing_id: str, caller: Caller) -> Briefing:
        before = await self.repo.get(briefing_id, caller.owner)
        state_machine.require_editable(before, "Extracting steps")
        steps, conflicts = await self._proposed_steps(before, caller)

        def change(b: Briefing) -> None:
            state_machine.require_editable(b, "Extracting steps")
            if b.instruction != before.instruction:
                raise InvalidState("The instruction changed while the steps were extracted. Retry.")
            b.steps, b.conflicts, b.status = steps, conflicts, "steps_proposed"
            chain.append(b, "steps_proposed", chain.steps_proposed(b))

        return await self.repo.mutate(briefing_id, caller.owner, change)

    async def _proposed_steps(
        self, before: Briefing, caller: Caller
    ) -> tuple[list[Step], list[Conflict]]:
        """The extract call's steps, or (library, 2026-10-16) a `sopRef` version's approved steps:
        no model call and no reservation. The supervisor still confirms them (PUT /steps)."""
        if before.sop_ref is not None:
            library = SopLibrary(self.repo.store, self.rt.settings)
            return await library.approved_steps(caller, before.site_id, before.sop_ref), []
        await self.cap.reserve(EXTRACT_CALLS, caller.address)
        steps, conflicts, _meta = await phases.extract_steps(
            self.rt,
            instruction=before.instruction,
            supervisor_lang=before.supervisor_lang,
            sop=before.sop,
        )
        return steps, conflicts

    async def confirm_steps(self, briefing_id: str, items: list[Step], caller: Caller) -> Briefing:
        """Endpoint 9. On a `sopRef` briefing (security fixes A, H2) only the version's signed-off
        steps, unchanged and in order: the sign-off is what the briefing checks, not advice."""
        steps = validators.steps(items, self.rt.settings)
        before = await self.repo.get(briefing_id, caller.owner)
        signed: list[dict[str, Any]] | None = None  # every Step field, in order
        if before.sop_ref is not None:
            library = SopLibrary(self.repo.store, self.rt.settings)
            approved = await library.approved_steps(caller, before.site_id, before.sop_ref)
            signed = [s.model_dump() for s in approved]

        def change(b: Briefing) -> None:
            state_machine.require_confirmable(b)
            if signed is not None and [s.model_dump() for s in steps] != signed:
                raise InvalidState(
                    f"These steps are signed off in {b.sop.id} {b.sop.version}. To change them, a "
                    "safety officer signs off a new version, or start the briefing with Gemini's "
                    "steps.",
                    code="sop_steps_locked",
                )
            b.steps = steps
            b.steps_version += 1
            b.latest_verdicts = {}
            b.status = "steps_confirmed"
            chain.append(b, "steps_confirmed", chain.steps_confirmed(b))

        return await self.repo.mutate(briefing_id, caller.owner, change)

    async def decide(self, briefing_id: str, body: DecisionBody, caller: Caller) -> Briefing:
        def change(b: Briefing) -> None:
            b.decision = state_machine.decide(b, body, self.rt.settings)
            b.status = "decided"
            chain.append(b, "decided", chain.decided(b.decision), at=b.decision.at)

        return await self.repo.mutate(briefing_id, caller.owner, change)

    async def verify(self, briefing_id: str, caller: Caller) -> dict[str, Any]:
        """Endpoint 25: recompute the record chain against the record as stored now."""
        return chain.verify(await self.repo.get(briefing_id, caller.owner))

    # Hazards (API.md v0.4, endpoints 21 and 22) ------------------------------------------------

    async def precheck_hazard(self, briefing_id: str, caller: Caller) -> Briefing:
        """404, 409 and 422 `too_many_hazards` before any upload is read."""
        b = await self.repo.get(briefing_id, caller.owner)
        _hazard_allowed(b, self.rt.settings.max_hazards)
        return b

    async def raise_hazard(
        self, briefing_id: str, caller: Caller, *, audio: bytes | None, round_n: int | None
    ) -> Hazard:
        """Endpoint 21. With audio, one Flash call transcribes the report verbatim and translates
        it (the audio is then dropped unless SIB_KEEP_AUDIO); without, it is a free tap."""
        s = self.rt.settings
        before = await self.precheck_hazard(briefing_id, caller)
        _require_round_number(before, round_n)
        kind: HazardKind = "tap"
        original, lang, translation = "", "none", ""
        if audio is not None:
            kind = "voice"
            await self.cap.reserve(HAZARD_CALLS, caller.address)
            original, lang, translation = await phases.report_hazard(
                self.rt,
                audio,
                worker_lang=before.worker_lang,
                supervisor_lang=before.supervisor_lang,
            )
        raised: list[Hazard] = []

        def change(b: Briefing) -> None:
            _hazard_allowed(b, s.max_hazards)
            hazard = Hazard(
                id=f"h{len(b.hazards) + 1}",
                round=round_n,
                kind=kind,
                original=original,
                translation=translation,
                detected_lang=lang,
                raised_at=now_iso(),
            )
            b.hazards.append(hazard)
            chain.append(b, "hazard_raised", chain.hazard_raised(hazard), at=hazard.raised_at)
            raised.append(hazard)

        await self.repo.mutate(briefing_id, caller.owner, change)
        if audio is not None:
            self._keep_audio(briefing_id, raised[0].id, audio)
        return raised[0]

    async def acknowledge_hazard(
        self, briefing_id: str, hazard_id: str, body: HazardAckBody, caller: Caller
    ) -> Briefing:
        """Endpoint 22: the supervisor says what was done (5+ characters, else 422
        note_required)."""
        s = self.rt.settings
        note = validators.clean_text(body.note, field="note", limit=s.hazard_note_max_chars)
        if len(note) < s.hazard_note_min_chars:
            raise Unprocessable(
                f"Say what was done about the hazard, in {s.hazard_note_min_chars}+ characters.",
                code="note_required",
            )
        by = validators.clean_text(body.by, field="by", limit=s.decision_by_max_chars)

        def change(b: Briefing) -> None:
            state_machine.require_hazard_state(b, "Acknowledging a hazard")
            hazard = b.hazard(hazard_id)
            if hazard is None:
                raise NotFound("Hazard not found.", code="hazard_not_found")
            if hazard.ack is not None:
                raise InvalidState("This hazard is already acknowledged.")
            hazard.ack = HazardAck(note=note, by=by or None, at=now_iso())
            event = chain.hazard_acknowledged(hazard)
            chain.append(b, "hazard_acknowledged", event, at=hazard.ack.at)

        return await self.repo.mutate(briefing_id, caller.owner, change)

    def _keep_audio(self, briefing_id: str, hazard_id: str, audio: bytes) -> None:
        """SIB_KEEP_AUDIO=true (consented demos only): keep the report's clip. Otherwise it was only
        ever in memory for the one model call."""
        if not self.rt.settings.keep_audio:
            return
        folder = self.rt.settings.data_dir / "audio" / briefing_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"hazard-{hazard_id}.wav").write_bytes(audio)
        log.warning("kept a hazard report clip for %s (SIB_KEEP_AUDIO)", briefing_id)


def _hazard_allowed(b: Briefing, max_hazards: int) -> None:
    state_machine.require_hazard_state(b, "Reporting a hazard")
    if len(b.hazards) >= max_hazards:
        raise Unprocessable(
            f"At most {max_hazards} hazard reports per briefing. Stop the work and talk in person.",
            code="too_many_hazards",
        )


def _require_round_number(b: Briefing, n: int | None) -> None:
    if n is not None and b.round_n(n) is None:
        raise Unprocessable("round must be the number of one of this briefing's rounds.")
