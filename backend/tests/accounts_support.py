"""Shared pieces of the pilot-account tests of security fixes B (build-notes/36): a fake token
verifier over named users, firebase-mode settings, and an app with a signed-in client per user."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from sayitback.auth import member_hash
from tests.fakes import FakeTtsClient, Scenario
from tests.helpers import api_client, make_app

PROJECT = "sib-pilot"
ISS = f"https://securetoken.google.com/{PROJECT}"
BOOTSTRAP = "boss@acme.example"
USERS = {
    "boss": ("uid-boss", BOOTSTRAP, True),
    "boss-new-uid": ("uid-boss-2", BOOTSTRAP, True),  # the same Google identity, a new Firebase uid
    "boss-third-uid": ("uid-boss-3", BOOTSTRAP, True),
    "boss-unverified": ("uid-boss-4", BOOTSTRAP, False),
    "admin2": ("uid-admin2", "admin2@acme.example", True),
    "sup": ("uid-sup", "sup@acme.example", True),
    "officer": ("uid-officer", "officer@acme.example", True),
    "second-admin": ("uid-second", "second@acme.example", True),
}


class FakeVerifier:
    """Stands in for google-auth: a known name gives its claims; any other raises, as an expired or
    forged token does there."""

    async def __call__(self, token: str) -> Mapping[str, Any]:
        uid, email, verified = USERS[token.split(".")[1]]
        return {"iss": ISS, "aud": PROJECT, "sub": uid, "email": email, "email_verified": verified}


def firebase_settings(settings, **changes):
    base = {
        "auth_mode": "firebase",
        "auth_project": PROJECT,
        "auth_org": "acme",
        "auth_allowed_domains": ("acme.example",),
        "bootstrap_admins": (BOOTSTRAP,),
    }
    return settings.with_overrides(**{**base, **changes})


def accounts(settings, scenario: Scenario | None = None, store=None, **changes) -> SimpleNamespace:
    """A firebase-mode app; `as_user(name)` is a client signed in as that user."""
    s = firebase_settings(settings, **changes)
    app, _rt, llm, store = make_app(
        s, scenario, store=store, token_verifier=FakeVerifier(), tts_client=FakeTtsClient()
    )

    def as_user(name: str) -> TestClient:
        return api_client(app, device=None, headers={"Authorization": f"Bearer h.{name}.s"})

    return SimpleNamespace(app=app, store=store, llm=llm, settings=s, as_user=as_user)


def member_id(name: str) -> str:
    return member_hash(USERS[name][0])


def grant(env: SimpleNamespace, name: str, roles: dict[str, list[str]], by: str = "boss", **extra):
    """`name` signs in once, then `by` (an org admin) sets their roles. Returns the member."""
    env.as_user(name).get("/api/me")
    body = {"roles": roles, **extra}
    reply = env.as_user(by).put(f"/api/orgs/acme/members/{member_id(name)}", json=body)
    assert reply.status_code == 200, reply.text
    return reply.json()
