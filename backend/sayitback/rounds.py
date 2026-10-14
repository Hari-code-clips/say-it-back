"""Rounds: create a round's script, run the check, hand out Live tickets.

Each is for a caller (caller.py), whose briefings only it can reach. Each of the three reserves its
share of the daily Gemini cap (daily_cap.py), against the caller's address too, after its
validation and state checks, just before its first model call. A round whose script needs a retry
reserves that one more call just before the retry runs (`phases.make_script`'s `before_retry`).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from functools import partial
from typing import Any

from sayitback import catalog, live_session, phases, state_machine, validators
from sayitback.caller import Caller
from sayitback.daily_cap import (
    LIVE_TICKET_CALLS,
    SCRIPT_RETRY_CALLS,
    DailyCap,
    check_calls,
    round_calls,
)
from sayitback.delivery import delivery_checks
from sayitback.errors import InvalidState, Unprocessable
from sayitback.models import (
    Briefing,
    CheckResult,
    CreateRound,
    DeliveryCheck,
    Mode,
    Rating,
    Round,
    Step,
    now_iso,
)
from sayitback.pipeline import run_check
from sayitback.repo import Repo
from sayitback.runtime import Runtime

log = logging.getLogger("sayitback.rounds")
QNUM = re.compile(r"^q(\d+)$")
LIVE_POLL_S = 0.25


def latest_ratings(b: Briefing) -> dict[str, Rating]:
    """The latest rating per step, from the most recent round that rated it."""
    found: dict[str, Rating] = {}
    for rnd in b.rounds:
        found.update({r.step_id: r for r in rnd.ratings})
    return found


def first_question_number(b: Briefing) -> int:
    numbers = [
        int(m.group(1)) for r in b.rounds for q in r.script.questions if (m := QNUM.match(q.id))
    ]
    return max(numbers, default=0) + 1


def scope_for(b: Briefing, kind: str, requested: list[str] | None) -> list[Step]:
    """Round 1 covers every step. A re-explain round covers the open steps, or a subset of them."""
    pool = b.steps if kind == "initial" else [s for s in b.steps if s.id in b.open_step_ids()]
    if not requested:
        return list(pool)
    wanted = list(dict.fromkeys(requested))
    allowed = {s.id for s in pool}
    if kind == "initial" and set(wanted) != allowed:
        raise Unprocessable("Round 1 covers all steps; omit stepIds.", code="invalid_step_ids")
    if not set(wanted) <= allowed:
        raise Unprocessable("stepIds must be open steps of this briefing.", code="invalid_step_ids")
    return [s for s in pool if s.id in wanted]


def append_round(
    created: Round, kind: str, steps_version: int, max_rounds: int
) -> Callable[[Briefing], None]:
    """The atomic step that stores a new round, re-checking what the slow model calls assumed."""

    def change(cur: Briefing) -> None:
        if state_machine.next_round(cur, max_rounds) != (kind, created.n):
            raise InvalidState("The briefing changed while the script was written. Retry.")
        if cur.steps_version != steps_version:
            raise InvalidState("The steps were edited while the script was written. Retry.")
        cur.rounds.append(created)
        cur.status = "briefing"

    return change


class Rounds:
    def __init__(self, rt: Runtime, repo: Repo, cap: DailyCap) -> None:
        self.rt = rt
        self.repo = repo
        self.cap = cap

    async def create(self, briefing_id: str, body: CreateRound, caller: Caller) -> Round:
        s = self.rt.settings
        b = await self.repo.get(briefing_id, caller.owner)
        kind, n = state_machine.next_round(b, s.max_rounds)
        scope = scope_for(b, kind, body.step_ids)
        note = validators.clean_text(
            body.supervisor_note, field="supervisorNote", limit=s.max_instruction_chars
        )
        await self.cap.reserve(round_calls(kind, note), caller.address)
        meta = phases.Meta()
        basis = await self._basis(b, kind, note, scope, meta)
        script, script_meta = await phases.make_script(
            self.rt,
            steps=scope,
            basis=basis,
            round_kind=kind,
            supervisor_lang=b.supervisor_lang,
            worker_lang=b.worker_lang,
            site_id=b.site_id,
            first_qnum=first_question_number(b),
            previous_questions=[q.text for r in b.rounds for q in r.script.questions],
            before_retry=partial(self.cap.reserve, SCRIPT_RETRY_CALLS, caller.address),
        )
        _merge(meta, script_meta)
        created = Round(
            n=n,
            kind=kind,
            step_ids=[st.id for st in scope],
            supervisor_note=note or None,
            script=script,
            model_ids=meta.model_ids,
            timings_ms=meta.timings_ms,
            created_at=now_iso(),
        )
        change = append_round(created, kind, b.steps_version, s.max_rounds)
        await self.repo.mutate(briefing_id, caller.owner, change)
        return created

    async def _basis(
        self, b: Briefing, kind: str, note: str, scope: list[Step], meta: phases.Meta
    ) -> str:
        """What the script is written from: the instruction, the supervisor's note, or (re-explain
        with no note) a fresh explanation of the open steps."""
        if kind == "initial":
            return b.instruction
        if note:
            return note
        explanation, explain_meta = await phases.explain(
            self.rt,
            steps=scope,
            ratings=latest_ratings(b),
            supervisor_lang=b.supervisor_lang,
            sop_title=b.sop.title,
        )
        _merge(meta, explain_meta)
        return explanation

    async def live_ticket(self, briefing_id: str, n: int, caller: Caller) -> dict[str, Any]:
        """Endpoint 11: a single-use WebSocket ticket for round `n`, issued to the briefing's owner
        (the WebSocket carries no device key: the ticket is its capability)."""
        s = self.rt.settings
        b = await self.repo.get(briefing_id, caller.owner)
        state_machine.require_unjudged_round(b, n)
        # The round's ticket allowance (429 `limit`) is a refusal too, so it is checked first and
        # costs nothing. If the daily cap then refuses, the ticket is never returned (it expires
        # unused) but it did use one of the round's two slots.
        ticket, expires = await live_session.issue_ticket(
            self.repo.store, s, briefing_id, n, owner=caller.owner
        )
        await self.cap.reserve(LIVE_TICKET_CALLS, caller.address)
        return {
            "wsUrl": live_session.ws_url(s, briefing_id, n),
            "ticket": ticket,
            "model": s.live_model,
            "expiresAt": expires,
        }

    async def precheck(self, briefing_id: str, n: int, caller: Caller) -> None:
        """The round exists and is unjudged (else 404 or 409), before any upload is read."""
        state_machine.require_unjudged_round(await self.repo.get(briefing_id, caller.owner), n)

    async def check(
        self, briefing_id: str, n: int, clips: dict[str, bytes], mode: Mode, caller: Caller
    ) -> Round:
        s = self.rt.settings
        b = await self.repo.get(briefing_id, caller.owner)
        rnd = state_machine.require_unjudged_round(b, n)
        live = rnd.live if mode == "live" else None
        if mode == "live" and live is None:
            rnd = await self._wait_for_live(briefing_id, n, caller.owner)
            live = rnd.live
        result = await run_check(
            steps=[st for st in b.steps if st.id in rnd.step_ids],
            questions=rnd.script.questions,
            clips=clips,
            worker_lang=b.worker_lang,
            supervisor_lang=b.supervisor_lang,
            script=rnd.script,
            live_input_transcripts=live.heard if live else None,
            runtime=self.rt,
            before_call=partial(self.cap.reserve, check_calls(s), caller.address),
        )
        delivery = (
            delivery_checks(
                rnd.script,
                live.delivered,
                catalog.unicode_ranges(b.worker_lang),
                min_script_share=s.delivery_min_script_share,
            )
            if live
            else []
        )
        self._keep_audio(briefing_id, n, clips)

        def change(cur: Briefing) -> None:
            record_check(cur, n, mode, result, delivery)

        return (await self.repo.mutate(briefing_id, caller.owner, change)).rounds[n - 1]

    async def _wait_for_live(self, briefing_id: str, n: int, owner: str) -> Round:
        """The browser may post the check the moment it sends `stop`, before the relay has written
        round.live. Wait a little for it; if it never comes, 409 `live_not_recorded`."""
        deadline = asyncio.get_running_loop().time() + self.rt.settings.live_record_wait_s
        while True:
            b = await self.repo.get(briefing_id, owner)
            rnd = state_machine.require_unjudged_round(b, n)
            if rnd.live is not None:
                return rnd
            if asyncio.get_running_loop().time() >= deadline:
                raise InvalidState(
                    "No live session was recorded for this round. Use turn mode.",
                    code="live_not_recorded",
                )
            await asyncio.sleep(LIVE_POLL_S)

    def _keep_audio(self, briefing_id: str, n: int, clips: dict[str, bytes]) -> None:
        """SIB_KEEP_AUDIO=true (consented demos only): write the clips under the data directory."""
        if not self.rt.settings.keep_audio:
            return
        folder = self.rt.settings.data_dir / "audio" / briefing_id
        folder.mkdir(parents=True, exist_ok=True)
        for qid, data in clips.items():
            (folder / f"r{n}-{qid}.wav").write_bytes(data)
        log.warning(
            "kept %d answer clips for %s round %d (SIB_KEEP_AUDIO)", len(clips), briefing_id, n
        )


def record_check(
    cur: Briefing, n: int, mode: Mode, result: CheckResult, delivery: list[DeliveryCheck]
) -> None:
    """Write a check's outcome into round `n` and move the briefing to `judged`."""
    state_machine.require_unjudged_round(cur, n)
    target = cur.rounds[n - 1]
    target.mode = mode
    target.transcripts, target.pass_a, target.pass_b = (
        result.transcripts,
        result.pass_a,
        result.pass_b,
    )
    target.ratings, target.delivery, target.next_action = (
        result.ratings,
        delivery,
        result.next_action,
    )
    target.model_ids = {**target.model_ids, **result.model_ids}
    target.timings_ms = {**target.timings_ms, **result.timings_ms}
    target.judged_at = now_iso()
    cur.latest_verdicts = {**cur.latest_verdicts, **{r.step_id: r.verdict for r in result.ratings}}
    cur.status = "judged"


def _merge(into: phases.Meta, other: phases.Meta) -> None:
    into.model_ids.update(other.model_ids)
    for key, ms in other.timings_ms.items():
        into.timings_ms[key] = round(into.timings_ms.get(key, 0.0) + ms, 1)
