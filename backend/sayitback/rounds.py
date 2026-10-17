"""Rounds: create a round's script, approve it, run the check, hand out Live tickets.

Each is for a caller (caller.py), whose briefings only it can reach. Each of the three model-backed
ones reserves its share of the daily Gemini cap (daily_cap.py), against the caller's address too,
after its validation and state checks, just before its first model call. A round whose script needs
a retry reserves that one more call just before the retry runs (`phases.make_script`'s
`before_retry`). Approval (v0.4) is the supervisor's gate: nothing is spoken (live ticket, TTS) or
judged before it. Each change appends its event to the record chain (chain.py).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from functools import partial
from typing import Any

from sayitback import (
    catalog,
    chain,
    consent,
    guards,
    live_session,
    phases,
    state_machine,
    validators,
)
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
    ApproveBody,
    Briefing,
    CheckMeta,
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
        chain.append(cur, "round_created", chain.round_created(created), at=created.created_at)

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

    async def approve(self, briefing_id: str, n: int, body: ApproveBody, caller: Caller) -> Round:
        """Endpoint 23: the supervisor has read round `n`'s script and its back-translation. A
        second approval is a no-op that returns the round as it is."""
        s = self.rt.settings
        by = validators.clean_text(body.by, field="by", limit=s.approve_by_max_chars)
        current = state_machine.require_round(await self.repo.get(briefing_id, caller.owner), n)
        if current.approved_at is not None:
            return current

        def change(cur: Briefing) -> None:
            rnd = state_machine.require_round(cur, n)
            if rnd.approved_at is not None:  # approved by a request that raced this one
                return
            rnd = state_machine.require_unjudged_round(cur, n)
            rnd.approved_at, rnd.approved_by = now_iso(), by or None
            chain.append(cur, "script_approved", chain.script_approved(rnd), at=rnd.approved_at)

        return (await self.repo.mutate(briefing_id, caller.owner, change)).rounds[n - 1]

    async def live_ticket(
        self, briefing_id: str, n: int, caller: Caller, samples_only: bool = False
    ) -> dict[str, Any]:
        """Endpoint 11: a single-use WebSocket ticket for round `n`, issued to the briefing's owner
        (the WebSocket carries no device key: the ticket is its capability). The round's script
        must be approved (409 script_not_approved). Security fixes B: with SIB_REQUIRE_CONSENT, a
        round with no recorded choice needs the request's `samplesOnly` (409 consent_required)."""
        s = self.rt.settings
        b = await self.repo.get(briefing_id, caller.owner)
        rnd = state_machine.require_approved_round(b, n)
        consent.require_for_live(rnd, samples_only, s.require_consent)  # privacy, 16 Oct
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
        """The round exists, is unjudged and approved (else 404 or 409), before any upload is
        read."""
        b = await self.repo.get(briefing_id, caller.owner)
        consent.refuse_declined(state_machine.require_approved_round(b, n))  # privacy, 16 Oct

    async def check(
        self, briefing_id: str, n: int, clips: dict[str, bytes], meta: CheckMeta, caller: Caller
    ) -> Round:
        s = self.rt.settings
        mode = meta.mode
        b = await self.repo.get(briefing_id, caller.owner)
        rnd = state_machine.require_approved_round(b, n)
        samples = sample_answers(meta.sample_answers, rnd, clips)
        consent.require_for_check(rnd, samples, s.require_consent)  # privacy, 16 Oct
        live = rnd.live  # whatever the mode: anything Live said reached the worker
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
                min_similarity=s.delivery_min_similarity,
                markers=catalog.markers(b.worker_lang),
                reply_max_chars=s.reply_max_chars,
            )
            if live
            else []
        )
        if mode == "turn":  # TTS read the script: only what Live did say is checked
            delivery = [d for d in delivery if "not_spoken" not in d.issues]
        if delivery:  # guard rule 8, whenever Live spoke: run_check (and eval/) know nothing of it
            ratings, next_action = guards.apply_delivery(
                result.ratings, delivery, rnd.script.questions, rnd.step_ids
            )
            result = result.model_copy(update={"ratings": ratings, "next_action": next_action})
        self._keep_audio(briefing_id, n, clips)

        def change(cur: Briefing) -> None:
            record_check(cur, n, mode, result, delivery, samples)

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


def sample_answers(
    requested: list[str] | None, rnd: Round, clips: dict[str, bytes]
) -> list[str] | None:
    """`meta.sampleAnswers`: question ids of this round, each answered by a clip in this request
    that the browser played from a stored synthetic sample (endpoint 24), not a person."""
    if not requested:
        return None
    asked = [q.id for q in rnd.script.questions]
    wanted = set(requested)
    if not wanted <= set(asked) or not wanted <= set(clips):
        raise Unprocessable(
            "meta.sampleAnswers must list question ids of this round that have a clip here."
        )
    return [qid for qid in asked if qid in wanted]


def record_check(
    cur: Briefing,
    n: int,
    mode: Mode,
    result: CheckResult,
    delivery: list[DeliveryCheck],
    samples: list[str] | None = None,
) -> None:
    """Write a check's outcome into round `n`, move the briefing to `judged` and record it."""
    consent.refuse_declined(state_machine.require_approved_round(cur, n))  # declined mid-check
    target = cur.rounds[n - 1]
    target.mode = mode
    target.sample_answers = samples
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
    chain.append(cur, "round_judged", chain.round_judged(target), at=target.judged_at)


def _merge(into: phases.Meta, other: phases.Meta) -> None:
    into.model_ids.update(other.model_ids)
    for key, ms in other.timings_ms.items():
        into.timings_ms[key] = round(into.timings_ms.get(key, 0.0) + ms, 1)
