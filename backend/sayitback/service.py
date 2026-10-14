"""Briefing use cases: create, edit, extract, confirm, decide. Rounds and check: rounds.py.

Every one is for a caller (caller.py): it reads and writes only that caller's briefings, and a
call that needs the model reserves its share of the daily Gemini cap (daily_cap.py), against the
caller's address too, once the state checks have passed.

Model calls run outside the store's atomic update. Each update re-checks the state, so a request
that raced another one fails with 409 instead of overwriting it.
"""

from __future__ import annotations

from sayitback import phases, state_machine, validators
from sayitback.caller import Caller
from sayitback.daily_cap import EXTRACT_CALLS, DailyCap
from sayitback.errors import InvalidState
from sayitback.models import (
    Briefing,
    CreateBriefing,
    DecisionBody,
    Step,
    new_briefing_id,
    now_iso,
)
from sayitback.prompts import PROMPT_VERSION
from sayitback.repo import Repo
from sayitback.runtime import Runtime


class Briefings:
    def __init__(self, rt: Runtime, repo: Repo, cap: DailyCap) -> None:
        self.rt = rt
        self.repo = repo
        self.cap = cap

    async def create(self, body: CreateBriefing, caller: Caller) -> Briefing:
        s = self.rt.settings
        sop = validators.briefing_request(body, s)
        now = now_iso()
        briefing = Briefing(
            id=new_briefing_id(),
            site_id=body.site_id,
            task_id=body.task_id,
            sop=sop,
            supervisor_lang=body.supervisor_lang,
            worker_lang=body.worker_lang,
            instruction=validators.instruction(body.instruction, s),
            prompt_version=PROMPT_VERSION,
            created_at=now,
            updated_at=now,
        )
        return await self.repo.create(briefing, caller.owner)

    async def patch_instruction(self, briefing_id: str, text: str, caller: Caller) -> Briefing:
        value = validators.instruction(text, self.rt.settings)

        def change(b: Briefing) -> None:
            state_machine.require_editable(b, "Editing the instruction")
            b.instruction = value

        return await self.repo.mutate(briefing_id, caller.owner, change)

    async def extract(self, briefing_id: str, caller: Caller) -> Briefing:
        before = await self.repo.get(briefing_id, caller.owner)
        state_machine.require_editable(before, "Extracting steps")
        await self.cap.reserve(EXTRACT_CALLS, caller.address)
        steps, conflicts, _meta = await phases.extract_steps(
            self.rt,
            instruction=before.instruction,
            supervisor_lang=before.supervisor_lang,
            sop=before.sop,
        )

        def change(b: Briefing) -> None:
            state_machine.require_editable(b, "Extracting steps")
            if b.instruction != before.instruction:
                raise InvalidState("The instruction changed while the steps were extracted. Retry.")
            b.steps, b.conflicts, b.status = steps, conflicts, "steps_proposed"

        return await self.repo.mutate(briefing_id, caller.owner, change)

    async def confirm_steps(self, briefing_id: str, items: list[Step], caller: Caller) -> Briefing:
        steps = validators.steps(items, self.rt.settings)

        def change(b: Briefing) -> None:
            state_machine.require_confirmable(b)
            b.steps = steps
            b.steps_version += 1
            b.latest_verdicts = {}
            b.status = "steps_confirmed"

        return await self.repo.mutate(briefing_id, caller.owner, change)

    async def decide(self, briefing_id: str, body: DecisionBody, caller: Caller) -> Briefing:
        def change(b: Briefing) -> None:
            b.decision = state_machine.decide(b, body, self.rt.settings)
            b.status = "decided"

        return await self.repo.mutate(briefing_id, caller.owner, change)
