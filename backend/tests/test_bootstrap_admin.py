"""Security fixes B, M2 (build-notes/36-security-fixes-b.md): SIB_BOOTSTRAP_ADMINS seeds the first
org admin only.

A listed, verified email is made an org admin at a new member's first sign-in only while the org
has no org admin. Once one exists the list grants nothing, so a demoted admin who comes back on a
new Firebase uid (an account re-created, another provider for the same email) stays demoted. It
holds on the local store and the fake Firestore, and with two first sign-ins at once.
"""

from __future__ import annotations

import asyncio

import pytest

from sayitback.auth import Auth
from sayitback.store import LocalStore
from tests.accounts_support import (
    USERS,
    FakeVerifier,
    accounts,
    firebase_settings,
    grant,
    member_id,
)
from tests.fake_firestore import FakeBackedStore
from tests.helpers import error_of, run_sync


def store_for(kind: str, settings):
    return LocalStore(settings.data_dir) if kind == "local" else FakeBackedStore()


def auth_over(store, settings) -> Auth:
    return Auth(firebase_settings(settings), store, FakeVerifier())


async def sign_in(auth: Auth, name: str) -> dict:
    return await auth.sign_in(*USERS[name])


def members(store) -> list[dict]:
    return run_sync(store.members_list("acme", 100_000))


@pytest.mark.parametrize("kind", ["local", "firestore"])
class TestTheListSeedsTheFirstAdminOnly:
    def test_the_first_listed_sign_in_is_the_org_admin(self, settings, kind):
        auth = auth_over(store_for(kind, settings), settings)
        assert run_sync(sign_in(auth, "boss"))["orgAdmin"] is True

    def test_members_without_admin_who_came_first_do_not_stop_it(self, settings, kind):
        auth = auth_over(store_for(kind, settings), settings)
        run_sync(sign_in(auth, "sup"))
        assert run_sync(sign_in(auth, "boss"))["orgAdmin"] is True

    def test_once_an_admin_exists_a_new_uid_of_the_listed_email_is_a_plain_member(
        self, settings, kind
    ):
        auth = auth_over(store_for(kind, settings), settings)
        run_sync(sign_in(auth, "boss"))
        again = run_sync(sign_in(auth, "boss-new-uid"))
        assert (again["orgAdmin"], again["roles"], again["email"]) == (False, {}, USERS["boss"][1])

    def test_two_first_sign_ins_at_once_make_one_member_and_it_is_the_admin(self, settings, kind):
        store = store_for(kind, settings)
        auth = auth_over(store, settings)

        async def both():
            return await asyncio.gather(sign_in(auth, "boss"), sign_in(auth, "boss"))

        first, second = run_sync(both())
        assert first == second and first["orgAdmin"] is True
        assert len(members(store)) == 1

    def test_with_an_admin_two_new_uids_at_once_are_both_plain_members(self, settings, kind):
        store = store_for(kind, settings)
        auth = auth_over(store, settings)
        run_sync(sign_in(auth, "boss"))

        async def both():
            return await asyncio.gather(
                sign_in(auth, "boss-new-uid"), sign_in(auth, "boss-third-uid")
            )

        assert [m["orgAdmin"] for m in run_sync(both())] == [False, False]
        assert sum(m["orgAdmin"] for m in members(store)) == 1

    def test_an_admin_past_the_team_lists_500_rows_still_counts(self, settings, kind):
        """The team list stops at 500 by member id; the check reads past it, so junk members
        whose ids sort first cannot hide the admin from it."""
        store = store_for(kind, settings)
        for i in range(600):
            record = {"memberId": f"{i:064x}", "email": "", "orgAdmin": False, "roles": {}}
            run_sync(store.member_update("acme", record["memberId"], lambda _, r=record: r))
        admin = {"memberId": "f" * 64, "email": "a@acme.example", "orgAdmin": True, "roles": {}}
        run_sync(store.member_update("acme", "f" * 64, lambda _: admin))

        assert run_sync(sign_in(auth_over(store, settings), "boss"))["orgAdmin"] is False

    def test_an_unverified_listed_email_is_never_admin(self, settings, kind):
        auth = auth_over(store_for(kind, settings), settings)
        assert run_sync(sign_in(auth, "boss-unverified"))["orgAdmin"] is False


def test_only_a_listed_emails_first_sign_in_reads_the_members(settings):
    store = LocalStore(settings.data_dir)
    scans, real = [], store.members_list

    async def counted(org_id, limit):
        scans.append(org_id)
        return await real(org_id, limit)

    store.members_list = counted  # type: ignore[method-assign]
    auth = auth_over(store, settings)
    for name in ("sup", "officer", "sup", "boss-unverified"):
        run_sync(sign_in(auth, name))
    assert scans == []
    run_sync(sign_in(auth, "boss"))
    run_sync(sign_in(auth, "boss"))  # a known member: one read, no scan
    assert scans == ["acme"]


class TestTheDemotionSticksOverHttp:
    def test_a_demoted_admin_back_on_a_new_uid_is_no_admin(self, settings):
        """The review's A2: admin2 demotes boss; boss signs in on a fresh uid."""
        env = accounts(settings)
        env.as_user("boss").get("/api/me")
        grant(env, "admin2", {}, orgAdmin=True)
        demote = {"roles": {}, "orgAdmin": False}
        reply = env.as_user("admin2").put(
            f"/api/orgs/acme/members/{member_id('boss')}", json=demote
        )
        assert reply.json()["orgAdmin"] is False

        back = env.as_user("boss-new-uid")
        me = back.get("/api/me").json()

        assert (me["member"]["orgAdmin"], me["roles"]) == (False, {})
        assert error_of(back.get("/api/orgs/acme/members")) == (403, "forbidden")
        assert env.as_user("boss").get("/api/me").json()["member"]["orgAdmin"] is False

    def test_a_second_listed_email_after_the_first_admin_gets_nothing(self, settings):
        env = accounts(settings, bootstrap_admins=(USERS["boss"][1], USERS["second-admin"][1]))
        assert env.as_user("boss").get("/api/me").json()["member"]["orgAdmin"] is True
        assert env.as_user("second-admin").get("/api/me").json()["member"]["orgAdmin"] is False
