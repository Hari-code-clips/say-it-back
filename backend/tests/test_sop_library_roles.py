"""The SOP library with accounts (SIB_AUTH_MODE=firebase; auth.require_role) and on both stores:
roles per action, the org scope, and the atomic update (sop_library.py)."""

from __future__ import annotations

import asyncio
from types import MappingProxyType

import pytest

from sayitback.caller import Caller, owner_hash
from sayitback.errors import ApiError
from sayitback.settings import Settings
from sayitback.sop_library import NewSop, NewVersion, SopLibrary
from sayitback.store import LocalStore
from tests.fake_firestore import FakeBackedStore, FakeFirestore
from tests.helpers import CALLER

STEP = {"id": "s1", "text": "Stay behind the barricade"}
LIFT = "SOP-LF-03"


def member(org: str, *roles: str, site: str = "sg", who: str = "m") -> Caller:
    return Caller(
        owner_hash(f"{who}-{org}-device-key-aaaaaaaa"),
        "203.0.113.9",
        org_id=org,
        user_id=f"{who}-{org}",
        roles=MappingProxyType({site: frozenset(roles)}),
    )


@pytest.fixture(params=["local", "firestore"])
def library(request, tmp_path) -> SopLibrary:
    store = LocalStore(tmp_path) if request.param == "local" else FakeBackedStore()
    return SopLibrary(store, Settings(data_dir=tmp_path))


def code_of(excinfo: pytest.ExceptionInfo[ApiError]) -> tuple[int, str]:
    return excinfo.value.status, excinfo.value.code


async def test_a_supervisor_reads_but_never_writes(library):
    supervisor = member("org1", "supervisor")
    assert [e.id for e in await library.list(supervisor, "sg")][0] == LIFT
    for write in (
        library.add_version(supervisor, "sg", LIFT, NewVersion(text="x")),
        library.create(supervisor, "sg", NewSop(title="t", text="x")),
        library.approve(supervisor, "sg", LIFT, 2),
    ):
        with pytest.raises(ApiError) as refused:
            await write
        assert code_of(refused) == (403, "forbidden")


async def test_only_a_safety_officer_approves(library):
    admin, officer = member("org1", "admin", who="a"), member("org1", "safety_officer", who="o")
    entry = await library.add_version(admin, "sg", LIFT, NewVersion(text="Revised."))
    assert entry.versions[-1].created_by == "admin"
    with pytest.raises(ApiError) as refused:
        await library.approve(admin, "sg", LIFT, 3)
    assert code_of(refused) == (403, "forbidden")

    approved = (await library.approve(officer, "sg", LIFT, 3)).versions[-1]
    assert (approved.status, approved.approved_by) == ("approved", "safety_officer")


async def test_no_role_at_the_site_is_403_even_to_read(library):
    elsewhere = member("org1", "safety_officer", site="chennai")
    with pytest.raises(ApiError) as refused:
        await library.list(elsewhere, "sg")
    assert code_of(refused) == (403, "forbidden")


async def test_an_orgs_library_is_shared_by_its_members_and_no_one_else(library):
    officer, colleague = member("org1", "safety_officer"), member("org1", "supervisor", who="c")
    await library.add_version(officer, "sg", LIFT, NewVersion(text="Revised."))
    assert [v.number for v in (await library.get(colleague, "sg", LIFT)).versions] == [2, 3]
    stranger = member("org2", "safety_officer")
    assert [v.number for v in (await library.get(stranger, "sg", LIFT)).versions] == [2]
    assert [v.number for v in (await library.get(CALLER, "sg", LIFT)).versions] == [2]


async def test_device_mode_records_the_device_not_a_role(library):
    """Its own SOP: in device mode a seed takes no new version (security fixes A, H3)."""
    entry = await library.create(CALLER, "sg", NewSop(title="Night lifting", text="1. Lights."))
    assert entry.versions[-1].created_by == "device"


async def test_two_drafts_at_once_make_one_version():
    fake = FakeFirestore()
    one, two = SopLibrary(FakeBackedStore(fake), Settings()), SopLibrary(FakeBackedStore(fake), Settings())
    admin = member("org1", "admin")
    results = await asyncio.gather(
        one.add_version(admin, "sg", LIFT, NewVersion(text="A")),
        two.add_version(admin, "sg", LIFT, NewVersion(text="B")),
        return_exceptions=True,
    )
    refused = [r for r in results if isinstance(r, ApiError)]
    assert [r.code for r in refused] == ["draft_exists"]
    assert [v.number for v in (await one.get(admin, "sg", LIFT)).versions] == [2, 3]
