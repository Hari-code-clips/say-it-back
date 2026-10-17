"""Endpoints 4-11, 13, 14 and 21-23, 25: briefings, steps, rounds, script approval, live tickets,
check, decision, hazard reports and the record's verification.

Every route is for the caller (api/device.py): a briefing belongs to the device key that created
it, and any other key gets the 404 an unknown id gets. In firebase mode a member also reaches only
the briefings of the sites where they hold a role (`CallerDep`, api/context.py; security fixes B).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ConfigDict, StrictBool
from pydantic.alias_generators import to_camel

from sayitback import idempotency, webhook
from sayitback.api.context import CallerDep, ctx_of, rate_limited, site_briefings, within_budget
from sayitback.api.uploads import read_check_form, read_hazard_form
from sayitback.auth import require_role
from sayitback.errors import NotFound
from sayitback.models import (
    ApproveBody,
    Briefing,
    CreateBriefing,
    CreateRound,
    DecisionBody,
    HazardAckBody,
    PatchBriefing,
    PutSteps,
    Round,
    Wire,
)
from sayitback.repo import summarise

router = APIRouter(prefix="/api/briefings")


class LiveSessionBody(Wire):
    """Endpoint 11's optional body (security fixes B): `samplesOnly` declares that every answer of
    the round is a stored sample, as the web sends exactly when it shows no consent screen. Strict,
    like the consent body: "true" or 1 is 422, never read as a yes."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    samples_only: StrictBool = False


def _wire(briefing: Briefing) -> dict[str, Any]:
    return briefing.wire()


@router.post("", dependencies=[Depends(rate_limited)])
async def create_briefing(
    body: CreateBriefing, request: Request, caller: CallerDep
) -> dict[str, Any]:
    require_role(caller, body.site_id)  # security fixes B: a site where the caller holds a role
    return _wire(await ctx_of(request).briefings.create(body, caller))


@router.get("")
async def list_briefings(
    request: Request, caller: CallerDep, limit: int = Query(20, ge=1, le=100)
) -> dict[str, Any]:
    most = ctx_of(request).settings.list_max_limit
    items = await site_briefings(request, caller, min(limit, most), most)
    return {"items": [summarise(b).wire() for b in items]}


@router.get("/{briefing_id}")
async def get_briefing(briefing_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    ctx = ctx_of(request)
    briefing = await ctx.repo.get(briefing_id, caller.owner)
    if ctx.outbox is not None:  # SIB_OUTBOX: where the decision was sent, never a URL
        return {**_wire(briefing), "delivery": await ctx.outbox.status(briefing.id)}
    return _wire(briefing)


@router.patch("/{briefing_id}", dependencies=[Depends(rate_limited)])
async def patch_briefing(
    briefing_id: str, body: PatchBriefing, request: Request, caller: CallerDep
) -> dict[str, Any]:
    briefings = ctx_of(request).briefings
    return _wire(await briefings.patch_instruction(briefing_id, body.instruction, caller))


@router.post("/{briefing_id}/steps/extract", dependencies=[Depends(rate_limited)])
async def extract_steps(briefing_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    work = ctx_of(request).briefings.extract(briefing_id, caller)
    return _wire(await within_budget(request, work))


@router.put("/{briefing_id}/steps")
async def confirm_steps(
    briefing_id: str, body: PutSteps, request: Request, caller: CallerDep
) -> dict[str, Any]:
    return _wire(await ctx_of(request).briefings.confirm_steps(briefing_id, body.steps, caller))


@router.post("/{briefing_id}/rounds", dependencies=[Depends(rate_limited)])
async def create_round(
    briefing_id: str, request: Request, caller: CallerDep, body: CreateRound | None = None
) -> dict[str, Any]:
    work = ctx_of(request).rounds.create(briefing_id, body or CreateRound(), caller)
    created = await within_budget(request, work)
    return created.wire()


@router.post("/{briefing_id}/rounds/{n}/approve", dependencies=[Depends(rate_limited)])
async def approve_round(
    briefing_id: str, n: int, request: Request, caller: CallerDep, body: ApproveBody | None = None
) -> dict[str, Any]:
    """Endpoint 23 (v0.4): the supervisor approves the script; nothing is spoken before."""
    if n < 1:
        raise NotFound("Round not found.", code="round_not_found")
    rounds = ctx_of(request).rounds
    return (await rounds.approve(briefing_id, n, body or ApproveBody(), caller)).wire()


@router.post("/{briefing_id}/rounds/{n}/live-session", dependencies=[Depends(rate_limited)])
async def live_session(
    briefing_id: str,
    n: int,
    request: Request,
    caller: CallerDep,
    body: LiveSessionBody | None = None,
) -> dict[str, Any]:
    if n < 1:
        raise NotFound("Round not found.", code="round_not_found")
    samples_only = body is not None and body.samples_only  # no body: not declared samples-only
    return await ctx_of(request).rounds.live_ticket(briefing_id, n, caller, samples_only)


@router.post("/{briefing_id}/rounds/{n}/check", dependencies=[Depends(rate_limited)])
async def check_round(
    briefing_id: str, n: int, request: Request, caller: CallerDep
) -> dict[str, Any]:
    ctx = ctx_of(request)

    async def run() -> Round:
        await ctx.rounds.precheck(briefing_id, n, caller)  # 404 and 409 before the upload is read
        clips, meta = await read_check_form(request, ctx.settings)
        work = ctx.rounds.check(briefing_id, n, clips, meta, caller)
        return await within_budget(request, work)

    # 2026-10-16 signal: a retry with the same Idempotency-Key gets the round the first one judged.
    return (await idempotency.idempotent_check(request, briefing_id, n, caller, run)).wire()


@router.post("/{briefing_id}/decision")
async def decide(
    briefing_id: str, body: DecisionBody, request: Request, caller: CallerDep
) -> dict[str, Any]:
    ctx = ctx_of(request)
    decided = await ctx.briefings.decide(briefing_id, body, caller)
    if ctx.outbox is not None:  # SIB_OUTBOX: stored first, tried now, retried later (outbox.py)
        return {**_wire(decided), "delivery": await ctx.outbox.deliver(decided)}
    if ctx.webhook.enabled:  # v0.5: before the response, bounded; it never fails the decision
        await webhook.deliver(ctx.webhook, decided, ctx.settings.webhook_timeout_s)
    return _wire(decided)


@router.post("/{briefing_id}/hazards", dependencies=[Depends(rate_limited)])
async def raise_hazard(briefing_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    """Endpoint 21 (v0.4): a worker's hazard report, by voice (one Flash call) or by tap."""
    ctx = ctx_of(request)
    await ctx.briefings.precheck_hazard(briefing_id, caller)  # before the upload is read
    audio, round_n = await read_hazard_form(request, ctx.settings)
    work = ctx.briefings.raise_hazard(briefing_id, caller, audio=audio, round_n=round_n)
    hazard = await (within_budget(request, work) if audio is not None else work)
    return hazard.wire()


@router.post("/{briefing_id}/hazards/{hazard_id}/ack", dependencies=[Depends(rate_limited)])
async def acknowledge_hazard(
    briefing_id: str, hazard_id: str, body: HazardAckBody, request: Request, caller: CallerDep
) -> dict[str, Any]:
    """Endpoint 22 (v0.4): what the supervisor did about it. Go is blocked until then."""
    briefings = ctx_of(request).briefings
    return _wire(await briefings.acknowledge_hazard(briefing_id, hazard_id, body, caller))


@router.get("/{briefing_id}/verify")
async def verify(briefing_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    """Endpoint 25 (v0.4): recompute the record chain against the stored record."""
    return await ctx_of(request).briefings.verify(briefing_id, caller)
