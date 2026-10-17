"""The SOP library of a site (sop_library.py, API.md Deviations 2026-10-16 "library").

    GET  /api/sites/{siteId}/sops                                     {items: LibraryEntry[]}
    GET  /api/sites/{siteId}/sops/{sopId}                             LibraryEntry
    POST /api/sites/{siteId}/sops                {title, text, ...}   LibraryEntry (draft v1)
    POST /api/sites/{siteId}/sops/{sopId}/versions   {text, ...}      LibraryEntry (a new draft)
    PUT  /api/sites/{siteId}/sops/{sopId}/versions/{n}/steps {steps}  LibraryEntry
    POST /api/sites/{siteId}/sops/{sopId}/versions/{n}/approve        LibraryEntry

No route makes a model call. The writes are free writes: per-address rate limited, like endpoint 4.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Request

from sayitback.api.context import CallerDep, ctx_of, rate_limited
from sayitback.models import SOP_ID_PATTERN
from sayitback.sop_library import NewSop, NewVersion, PutVersionSteps, SopLibrary

router = APIRouter(prefix="/api/sites/{site_id}/sops")
SopId = Path(pattern=SOP_ID_PATTERN)
VersionNumber = Path(ge=1, le=9999)


def _library(request: Request) -> SopLibrary:
    ctx = ctx_of(request)
    return SopLibrary(ctx.repo.store, ctx.settings)


@router.get("")
async def list_sops(site_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    return {"items": [e.wire() for e in await _library(request).list(caller, site_id)]}


@router.get("/{sop_id}")
async def get_sop(
    site_id: str, request: Request, caller: CallerDep, sop_id: str = SopId
) -> dict[str, Any]:
    return (await _library(request).get(caller, site_id, sop_id)).wire()


@router.post("", dependencies=[Depends(rate_limited)])
async def create_sop(
    site_id: str, body: NewSop, request: Request, caller: CallerDep
) -> dict[str, Any]:
    return (await _library(request).create(caller, site_id, body)).wire()


@router.post("/{sop_id}/versions", dependencies=[Depends(rate_limited)])
async def create_version(
    site_id: str, body: NewVersion, request: Request, caller: CallerDep, sop_id: str = SopId
) -> dict[str, Any]:
    return (await _library(request).add_version(caller, site_id, sop_id, body)).wire()


@router.put("/{sop_id}/versions/{n}/steps", dependencies=[Depends(rate_limited)])
async def set_version_steps(
    site_id: str,
    body: PutVersionSteps,
    request: Request,
    caller: CallerDep,
    sop_id: str = SopId,
    n: int = VersionNumber,
) -> dict[str, Any]:
    library = _library(request)
    return (await library.set_steps(caller, site_id, sop_id, n, body.steps)).wire()


@router.post("/{sop_id}/versions/{n}/approve", dependencies=[Depends(rate_limited)])
async def approve_version(
    site_id: str, request: Request, caller: CallerDep, sop_id: str = SopId, n: int = VersionNumber
) -> dict[str, Any]:
    return (await _library(request).approve(caller, site_id, sop_id, n)).wire()
