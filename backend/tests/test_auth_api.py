"""Pilot accounts through the app (SIB_AUTH_MODE=firebase), with a fake token verifier: the 401 and
403 paths, first sign-in, roles, org-owned records, /api/me and the org admin's routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sayitback.auth import Auth, member_hash, org_owner
from sayitback.store import LocalStore
from tests.fake_firestore import FakeBackedStore
from tests.helpers import ORIGIN, PANEL, api_client, make_app, run_sync

PROJECT = "sib-pilot"
ISS = f"https://securetoken.google.com/{PROJECT}"
USERS = {
    "boss": ("uid-boss", "boss@acme.example", True),
    "sup": ("uid-sup", "sup@acme.example", True),
    "unverified": ("uid-unv", "sneaky@acme.example", False),
    "outsider": ("uid-out", "someone@gmail.example", True),
}


class FakeVerifier:
    """Stands in for google-auth: a known token gives its claims; any other raises, as an
    expired or forged token does there."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, token: str) -> Mapping[str, Any]:
        self.calls += 1
        name = token.split(".")[1]
        if name not in USERS:
            raise ValueError("Token expired")
        uid, email, verified = USERS[name]
        return {"iss": ISS, "aud": PROJECT, "sub": uid, "email": email, "email_verified": verified}


def token(name: str) -> str:
    return f"h.{name}.s"


def firebase_settings(settings, **changes):
    base = {
        "auth_mode": "firebase",
        "auth_project": PROJECT,
        "auth_org": "acme",
        "auth_allowed_domains": ("acme.example",),
        "bootstrap_admins": ("boss@acme.example",),
    }
    return settings.with_overrides(**{**base, **changes})


@pytest.fixture
def fb(settings):
    """A firebase-mode app over a local store, plus a client per user."""
    s = firebase_settings(settings)
    store = LocalStore(s.data_dir)
    app, *_ = make_app(s, store=store, token_verifier=FakeVerifier())

    def as_user(name: str | None) -> TestClient:
        headers = {"Authorization": f"Bearer {token(name)}"} if name else {}
        return api_client(app, device=None, headers=headers)

    return app, store, as_user


def grant(as_user, name: str, roles: dict[str, list[str]], **extra: Any):
    as_user(name).get("/api/me")  # the first sign-in creates the member
    member = member_hash(USERS[name][0])
    body = {"roles": roles, **extra}
    return as_user("boss").put(f"/api/orgs/acme/members/{member}", json=body)


class TestRefusals:
    def test_no_header_is_401_auth_required_and_health_stays_open(self, fb):
        _, _, as_user = fb
        for path in ("/api/briefings", "/api/catalog", "/api/me"):
            reply = as_user(None).get(path)
            assert (reply.status_code, reply.json()["error"]["code"]) == (401, "auth_required")
        assert as_user(None).get("/api/health").status_code == 200

    def test_a_device_key_alone_is_not_enough(self, fb):
        app, *_ = fb
        reply = api_client(app).get("/api/briefings")  # X-SIB-Device only
        assert reply.json()["error"]["code"] == "auth_required"

    @pytest.mark.parametrize("value", ["Bearer h.expired.s", "Bearer nonsense", "Basic h.boss.s"])
    def test_a_bad_expired_or_malformed_token_is_401_bad_token(self, fb, value):
        app, *_ = fb
        reply = api_client(app, device=None, headers={"Authorization": value}).get("/api/me")
        assert (reply.status_code, reply.json()["error"]["code"]) == (401, "bad_token")
        assert "expired" not in reply.text.lower() or "sign in" in reply.text.lower()

    @pytest.mark.parametrize("name", ["outsider", "unverified"])
    def test_an_outside_or_unverified_email_is_403_domain_not_allowed(self, fb, name):
        _, store, as_user = fb
        reply = as_user(name).get("/api/me")
        assert (reply.status_code, reply.json()["error"]["code"]) == (403, "domain_not_allowed")
        assert run_sync(store.member_get("acme", member_hash(USERS[name][0]))) is None

    def test_with_no_domain_list_any_account_signs_in(self, settings):
        s = firebase_settings(settings, auth_allowed_domains=())
        app, *_ = make_app(s, token_verifier=FakeVerifier())
        headers = {"Authorization": f"Bearer {token('outsider')}"}
        assert api_client(app, device=None, headers=headers).get("/api/me").status_code == 200

    def test_a_member_with_no_role_may_only_ask_who_they_are(self, fb):
        _, _, as_user = fb
        assert as_user("sup").get("/api/me").json()["roles"] == {}
        reply = as_user("sup").get("/api/briefings")
        assert (reply.status_code, reply.json()["error"]["code"]) == (403, "forbidden")
        assert as_user("sup").post("/api/briefings", json=PANEL).status_code == 403


class TestMe:
    def test_device_mode_says_device_only(self, client):
        assert client.get("/api/me").json() == {"mode": "device"}

    def test_a_bootstrap_admin_is_org_admin_with_admin_at_every_site(self, fb):
        _, _, as_user = fb
        body = as_user("boss").get("/api/me").json()
        assert body["mode"] == "firebase" and body["org"] == {"id": "acme"}
        assert body["member"]["email"] == "boss@acme.example" and body["member"]["orgAdmin"]
        assert body["roles"] == {"chennai": ["admin"], "sg": ["admin"]}

    def test_no_response_carries_the_uid_or_the_org_owner(self, fb):
        _, _, as_user = fb
        grant(as_user, "sup", {"sg": ["supervisor"]})
        texts = [
            as_user("sup").get("/api/me").text,
            as_user("boss").get("/api/orgs/acme/members").text,
            as_user("sup").post("/api/briefings", json=PANEL).text,
        ]
        for text in texts:
            assert "uid-sup" not in text and "uid-boss" not in text
            assert org_owner("acme") not in text and "owner" not in text


class TestRecordsBelongToTheOrg:
    def test_members_of_the_org_share_briefings(self, fb):
        _, _, as_user = fb
        grant(as_user, "sup", {"sg": ["supervisor"]})
        created = as_user("sup").post("/api/briefings", json=PANEL)
        assert created.status_code == 200, created.text
        bid = created.json()["id"]
        assert as_user("boss").get(f"/api/briefings/{bid}").status_code == 200
        listed = [b["id"] for b in as_user("boss").get("/api/briefings").json()["items"]]
        assert listed == [bid]

    def test_device_and_org_records_never_mix(self, settings):
        store = LocalStore(settings.data_dir)
        device_app, *_ = make_app(settings, store=store)
        fb_app, *_ = make_app(
            firebase_settings(settings), store=store, token_verifier=FakeVerifier()
        )
        device_bid = api_client(device_app).post("/api/briefings", json=PANEL).json()["id"]
        boss = api_client(fb_app, device=None, headers={"Authorization": f"Bearer {token('boss')}"})
        assert boss.get(f"/api/briefings/{device_bid}").status_code == 404
        assert boss.get("/api/briefings").json()["items"] == []
        org_bid = boss.post("/api/briefings", json=PANEL).json()["id"]
        assert api_client(device_app).get(f"/api/briefings/{org_bid}").status_code == 404


class TestTeam:
    def test_the_admin_lists_members_by_email(self, fb):
        _, _, as_user = fb
        as_user("sup").get("/api/me")
        items = as_user("boss").get("/api/orgs/acme/members").json()["items"]
        assert [m["email"] for m in items] == ["boss@acme.example", "sup@acme.example"]
        assert items[1] == {
            "id": member_hash("uid-sup"),
            "email": "sup@acme.example",
            "orgAdmin": False,
            "roles": {},
            "createdAt": items[1]["createdAt"],
            "updatedAt": items[1]["updatedAt"],
        }

    def test_the_admin_sets_roles_and_they_apply_on_the_next_request(self, fb):
        _, _, as_user = fb
        reply = grant(as_user, "sup", {"sg": ["supervisor", "safety_officer", "supervisor"]})
        assert reply.status_code == 200, reply.text
        assert reply.json()["roles"] == {"sg": ["safety_officer", "supervisor"]}
        assert as_user("sup").get("/api/me").json()["roles"] == {
            "sg": ["safety_officer", "supervisor"]
        }
        cleared = grant(as_user, "sup", {"sg": []})
        assert cleared.json()["roles"] == {}
        assert as_user("sup").get("/api/briefings").status_code == 403

    def test_an_admin_can_make_another_org_admin_but_not_unmake_themselves(self, fb):
        _, _, as_user = fb
        assert grant(as_user, "sup", {}, orgAdmin=True).json()["orgAdmin"] is True
        assert as_user("sup").get("/api/orgs/acme/members").status_code == 200
        me = member_hash("uid-boss")
        reply = as_user("boss").put(
            f"/api/orgs/acme/members/{me}", json={"roles": {}, "orgAdmin": False}
        )
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "cannot_demote_self")

    @pytest.mark.parametrize(
        ("body", "status"),
        [
            ({"roles": {"mars": ["supervisor"]}}, 422),
            ({"roles": {"sg": ["owner"]}}, 422),
            ({"roles": {"sg": ["supervisor"]}, "email": "x@y.z"}, 422),
            ({}, 422),
        ],
    )
    def test_a_bad_body_is_422(self, fb, body, status):
        _, _, as_user = fb
        as_user("sup").get("/api/me")
        member = member_hash("uid-sup")
        reply = as_user("boss").put(f"/api/orgs/acme/members/{member}", json=body)
        assert (reply.status_code, reply.json()["error"]["code"]) == (status, "validation_error")

    def test_unknown_members_orgs_and_non_admins(self, fb):
        _, _, as_user = fb
        grant(as_user, "sup", {"sg": ["supervisor"]})
        body = {"roles": {}}
        boss = as_user("boss")
        assert boss.put(f"/api/orgs/acme/members/{'0' * 64}", json=body).status_code == 404
        assert boss.put("/api/orgs/acme/members/not-a-hash", json=body).status_code == 404
        assert boss.get("/api/orgs/other/members").status_code == 404
        refused = as_user("sup").get("/api/orgs/acme/members")
        assert (refused.status_code, refused.json()["error"]["code"]) == (403, "forbidden")
        target = member_hash("uid-boss")
        assert as_user("sup").put(f"/api/orgs/acme/members/{target}", json=body).status_code == 403

    def test_device_mode_has_no_org_routes(self, client):
        assert client.get("/api/orgs/acme/members").status_code == 404
        put = client.put(f"/api/orgs/acme/members/{'0' * 64}", json={"roles": {}})
        assert put.status_code == 404

    def test_the_write_is_rate_limited_per_address(self, settings):
        s = firebase_settings(settings, rate_limit_per_min=2)
        app, *_ = make_app(s, token_verifier=FakeVerifier())
        boss = api_client(app, device=None, headers={"Authorization": f"Bearer {token('boss')}"})
        url = f"/api/orgs/acme/members/{member_hash('uid-boss')}"
        codes = [boss.put(url, json={"roles": {"sg": ["admin"]}}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]


class TestCors:
    def preflight(self, app, headers: str):
        return TestClient(app).options(
            "/api/me",
            headers={
                "origin": ORIGIN,
                "access-control-request-method": "GET",
                "access-control-request-headers": headers,
            },
        )

    def test_authorization_is_allowed_in_firebase_mode_only(self, settings):
        fb_app, *_ = make_app(firebase_settings(settings), token_verifier=FakeVerifier())
        assert self.preflight(fb_app, "authorization").status_code == 200
        device_app, *_ = make_app(settings)
        refused = self.preflight(device_app, "authorization")
        assert refused.status_code == 400
        allowed = self.preflight(device_app, "x-sib-device").headers["access-control-allow-headers"]
        assert "authorization" not in allowed.lower()


class TestMembersInFirestore:
    def test_the_firestore_store_keeps_members_under_the_org(self, settings):
        store = FakeBackedStore()
        auth = Auth(firebase_settings(settings), store, FakeVerifier())
        boss = run_sync(auth.sign_in("uid-boss", "boss@acme.example", True))
        assert boss["orgAdmin"] is True and boss["roles"] == {}
        assert ("orgs/acme/members", member_hash("uid-boss")) in store.fake.docs
        listed = run_sync(store.members_list("acme", 10))
        assert [m["memberId"] for m in listed] == [member_hash("uid-boss")]
        assert (
            run_sync(store.member_update("acme", member_hash("uid-boss"), lambda m: None)) == boss
        )

    def test_two_first_sign_ins_at_once_make_one_member(self, settings):
        store = FakeBackedStore()
        auth = Auth(firebase_settings(settings), store, FakeVerifier())

        async def both():
            return await asyncio.gather(
                auth.sign_in("uid-sup", "sup@acme.example", True),
                auth.sign_in("uid-sup", "sup@acme.example", True),
            )

        first, second = run_sync(both())
        assert first == second
        assert len([k for k in store.fake.docs if k[0] == "orgs/acme/members"]) == 1

    def test_an_unverified_bootstrap_email_is_no_admin_and_stores_no_email(self, settings):
        auth = Auth(firebase_settings(settings), FakeBackedStore(), FakeVerifier())
        member = run_sync(auth.sign_in("uid-x", "boss@acme.example", False))
        assert member["orgAdmin"] is False and member["email"] == ""
        assert json.dumps(member).count("uid-x") == 0


@pytest.mark.parametrize("kind", ["local", "firestore"])
def test_each_org_lists_and_reads_only_its_own_members(settings, kind):
    store = LocalStore(settings.data_dir) if kind == "local" else FakeBackedStore()
    for org, uid in (("acme", "uid-a"), ("other", "uid-b")):
        record = {"memberId": member_hash(uid)}
        run_sync(store.member_update(org, member_hash(uid), lambda _, r=record: r))
    assert run_sync(store.members_list("acme", 10)) == [{"memberId": member_hash("uid-a")}]
    assert run_sync(store.member_get("acme", member_hash("uid-b"))) is None
    if kind == "local":  # a path-unsafe org id never reaches the disk
        assert run_sync(store.member_get("../acme", member_hash("uid-a"))) is None
        with pytest.raises(KeyError):
            run_sync(store.member_update("../x", member_hash("uid-a"), lambda _: {}))
