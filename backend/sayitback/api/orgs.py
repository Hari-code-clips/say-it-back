"""Pilot accounts' routes (API.md Deviations 2026-10-16): who am I, and the org admin's member list.

`GET /api/me` answers in both modes (device mode: `{mode: "device"}`). The org routes exist only in
firebase mode (device mode has no orgs: 404) and only for an org admin of the deployment's org.
None of them calls Gemini, so none costs the daily cap; the write is rate-limited per address like
the other free writes, and every body is under the 256 KB JSON limit (api/limits.py).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from sayitback.api.context import CallerDep, ctx_of, rate_limited
from sayitback.auth import ROLES, Auth, Forbidden, site_ids
from sayitback.caller import Caller
from sayitback.errors import InvalidState, NotFound, Unprocessable, quote
from sayitback.models import Wire, now_iso
from sayitback.store.base import DIGEST

router = APIRouter(prefix="/api")
MAX_MEMBERS = 500
NOT_FOUND = "Not found."


class PutMember(Wire):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    roles: dict[str, list[str]]
    org_admin: bool | None = None


def auth_of(request: Request) -> Auth | None:
    return getattr(request.app.state, "auth", None)


def wire_roles(roles: Any) -> dict[str, list[str]]:
    return {site: sorted(held) for site, held in sorted(dict(roles or {}).items()) if held}


def wire_member(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m["memberId"],
        "email": m.get("email", ""),
        "orgAdmin": m.get("orgAdmin") is True,
        "roles": wire_roles(m.get("roles")),
        "createdAt": m.get("createdAt", ""),
        "updatedAt": m.get("updatedAt", ""),
    }


def clean_roles(raw: dict[str, list[str]], limit: int) -> dict[str, list[str]]:
    """Catalog sites and the three roles only (422), deduplicated and sorted; an empty list drops
    the site."""
    sites = set(site_ids())
    for site, roles in raw.items():
        if site not in sites:
            raise Unprocessable(f"roles: {quote(site, limit)} is not a site.")
        for role in roles:
            if role not in ROLES:
                raise Unprocessable(f"roles: {quote(role, limit)} is not a role.")
    return {site: sorted(set(roles)) for site, roles in sorted(raw.items()) if roles}


def require_org_admin(request: Request, caller: Caller, org_id: str) -> Auth:
    auth = auth_of(request)
    if auth is None or caller.org_id is None or org_id != caller.org_id:
        raise NotFound(NOT_FOUND)  # device mode has no orgs; another org is not found either
    member = getattr(request.state, "member", None) or {}
    if member.get("orgAdmin") is not True:
        raise Forbidden("Only an org admin can see or change the team.")
    return auth


@router.get("/me")
async def me(request: Request, caller: CallerDep) -> dict[str, Any]:
    if auth_of(request) is None or caller.org_id is None:
        return {"mode": "device"}
    member = getattr(request.state, "member", None) or {}
    return {
        "mode": "firebase",
        "org": {"id": caller.org_id},
        "member": {
            "id": caller.user_id,
            "email": member.get("email", ""),
            "orgAdmin": member.get("orgAdmin") is True,
        },
        "roles": wire_roles(caller.roles),
    }


@router.get("/orgs/{org_id}/members")
async def list_members(org_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    auth = require_org_admin(request, caller, org_id)
    items = [wire_member(m) for m in await auth.store.members_list(org_id, MAX_MEMBERS)]
    return {"items": sorted(items, key=lambda m: (m["email"], m["id"]))}


@router.put("/orgs/{org_id}/members/{member_id}", dependencies=[Depends(rate_limited)])
async def put_member(
    org_id: str, member_id: str, body: PutMember, request: Request, caller: CallerDep
) -> dict[str, Any]:
    auth = require_org_admin(request, caller, org_id)
    if not DIGEST.fullmatch(member_id):
        raise NotFound("Member not found.")
    roles = clean_roles(body.roles, ctx_of(request).settings.max_echo_chars)
    if member_id == caller.user_id and body.org_admin is False:
        raise InvalidState("You cannot remove your own org admin.", code="cannot_demote_self")

    def change(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is None:
            raise NotFound("Member not found.")
        admin = current.get("orgAdmin") is True if body.org_admin is None else body.org_admin
        return {**current, "roles": roles, "orgAdmin": admin, "updatedAt": now_iso()}

    updated = await auth.store.member_update(org_id, member_id, change)
    assert updated is not None
    return wire_member(updated)
