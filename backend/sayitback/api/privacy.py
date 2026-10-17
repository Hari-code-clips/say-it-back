"""Privacy endpoints (16 Oct; API.md Deviations): the worker's consent for a round, and deleting
a record. Both are for the briefing's owner (api/device.py): any other key gets the same 404 as an
unknown id. Logic lives in consent.py and retention.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from sayitback import consent, retention
from sayitback.api.context import CallerDep, ctx_of, rate_limited
from sayitback.models import ConsentBody

router = APIRouter(prefix="/api/briefings")


@router.post("/{briefing_id}/rounds/{n}/consent", dependencies=[Depends(rate_limited)])
async def record_consent(
    briefing_id: str, n: int, body: ConsentBody, request: Request, caller: CallerDep
) -> dict[str, Any]:
    """The worker's own choice before any answer of round n is recorded: `{given: true}` ("I
    agree") or `{given: false}` ("Not now"). Returns the round. The round must be approved and
    unjudged (409 otherwise); the same choice again is a no-op."""
    repo = ctx_of(request).repo
    return (await consent.record_for(repo, briefing_id, n, body.given, caller.owner)).wire()


@router.delete("/{briefing_id}", dependencies=[Depends(rate_limited)])
async def delete_briefing(briefing_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    """Remove the record at once, with any audio kept under SIB_KEEP_AUDIO. A copy already sent by
    webhook belongs to the system that received it (the permit-to-work system, Google Chat)."""
    ctx = ctx_of(request)
    await retention.delete_briefing(ctx.repo, briefing_id, caller.owner, ctx.settings.data_dir)
    return {"ok": True, "id": briefing_id}
