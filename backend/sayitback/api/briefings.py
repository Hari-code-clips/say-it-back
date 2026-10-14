"""Endpoints 4-11, 13 and 14: briefings, steps, rounds, live tickets, check and decision.

Every route is for the caller (api/device.py): a briefing belongs to the device key that created
it, and any other key gets the 404 an unknown id gets.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from sayitback.api.context import CallerDep, ctx_of, rate_limited, within_budget
from sayitback.api.uploads import read_check_form
from sayitback.errors import NotFound
from sayitback.models import (
    Briefing,
    CreateBriefing,
    CreateRound,
    DecisionBody,
    PatchBriefing,
    PutSteps,
)
from sayitback.repo import summarise

router = APIRouter(prefix="/api/briefings")


def _wire(briefing: Briefing) -> dict[str, Any]:
    return briefing.wire()


@router.post("", dependencies=[Depends(rate_limited)])
async def create_briefing(
    body: CreateBriefing, request: Request, caller: CallerDep
) -> dict[str, Any]:
    return _wire(await ctx_of(request).briefings.create(body, caller))


@router.get("")
async def list_briefings(
    request: Request, caller: CallerDep, limit: int = Query(20, ge=1, le=100)
) -> dict[str, Any]:
    ctx = ctx_of(request)
    items = await ctx.repo.recent(min(limit, ctx.settings.list_max_limit), caller.owner)
    return {"items": [summarise(b).wire() for b in items]}


@router.get("/{briefing_id}")
async def get_briefing(briefing_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    return _wire(await ctx_of(request).repo.get(briefing_id, caller.owner))


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


@router.post("/{briefing_id}/rounds/{n}/live-session", dependencies=[Depends(rate_limited)])
async def live_session(
    briefing_id: str, n: int, request: Request, caller: CallerDep
) -> dict[str, Any]:
    if n < 1:
        raise NotFound("Round not found.", code="round_not_found")
    return await ctx_of(request).rounds.live_ticket(briefing_id, n, caller)


@router.post("/{briefing_id}/rounds/{n}/check", dependencies=[Depends(rate_limited)])
async def check_round(
    briefing_id: str, n: int, request: Request, caller: CallerDep
) -> dict[str, Any]:
    ctx = ctx_of(request)
    await ctx.rounds.precheck(briefing_id, n, caller)  # 404 and 409 before the upload is read
    clips, meta = await read_check_form(request, ctx.settings)
    work = ctx.rounds.check(briefing_id, n, clips, meta.mode, caller)
    return (await within_budget(request, work)).wire()


@router.post("/{briefing_id}/decision")
async def decide(
    briefing_id: str,
    body: DecisionBody,
    request: Request,
    background: BackgroundTasks,
    caller: CallerDep,
) -> dict[str, Any]:
    ctx = ctx_of(request)
    decided = await ctx.briefings.decide(briefing_id, body, caller)
    if ctx.webhook.enabled:
        background.add_task(ctx.webhook.send, decided)  # best effort, after the response
    return _wire(decided)
