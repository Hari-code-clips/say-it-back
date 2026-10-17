"""Pilot accounts, the pure parts (sayitback/auth.py): settings, roles, claims, the bearer header,
the certificate cache and the real verifier's call shape. No network: google-auth is faked."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

import pytest
from starlette.requests import HTTPConnection

from sayitback import auth
from sayitback.auth import (
    AuthRequired,
    BadToken,
    Forbidden,
    effective_roles,
    identity,
    member_hash,
    org_owner,
    require_role,
)
from sayitback.caller import Caller, owner_hash
from sayitback.settings import ConfigError, Settings

PROJECT = "sib-pilot"
FIREBASE = {"SIB_AUTH_MODE": "firebase", "GOOGLE_CLOUD_PROJECT": PROJECT, "SIB_AUTH_ORG": "acme"}


def conn(*authorization: str) -> HTTPConnection:
    headers = [(b"authorization", v.encode()) for v in authorization]
    return HTTPConnection({"type": "http", "headers": headers, "path": "/api/x"})


def claims(**changes: object) -> dict[str, object]:
    base = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": "uid-1",
        "email": "Supervisor@Acme.example",
        "email_verified": True,
    }
    return {**base, **changes}


class TestSettings:
    def test_device_mode_is_the_default_and_needs_nothing(self):
        s = Settings.from_env({})
        assert (s.auth_mode, s.auth_org, s.auth_allowed_domains) == ("device", "", ())

    @pytest.mark.parametrize(
        "env",
        [
            {"SIB_AUTH_MODE": "firebase", "SIB_AUTH_ORG": "acme"},  # no project
            {**FIREBASE, "SIB_AUTH_ORG": ""},
            {**FIREBASE, "SIB_AUTH_ORG": "Acme Corp"},
            {**FIREBASE, "SIB_AUTH_ALLOWED_DOMAINS": "acme.example,@bad"},
            {**FIREBASE, "SIB_BOOTSTRAP_ADMINS": "not-an-email"},
            {"SIB_AUTH_MODE": "saml"},
        ],
    )
    def test_a_firebase_deployment_without_what_it_needs_stops_at_start_up(self, env):
        with pytest.raises(ConfigError):
            Settings.from_env(env)

    def test_firebase_settings_are_read_lowercased_and_the_admins_stay_out_of_repr(self):
        env = {
            **FIREBASE,
            "SIB_AUTH_PROJECT": "other-project",
            "SIB_AUTH_ALLOWED_DOMAINS": " Acme.Example , ",
            "SIB_BOOTSTRAP_ADMINS": "Boss@Acme.Example",
        }
        s = Settings.from_env(env)
        assert s.auth_project == "other-project"  # SIB_AUTH_PROJECT wins over the cloud project
        assert s.auth_allowed_domains == ("acme.example",)
        assert s.bootstrap_admins == ("boss@acme.example",)
        assert "boss@acme.example" not in repr(s)


class TestRequireRole:
    def firebase_caller(self, roles: dict[str, set[str]]) -> Caller:
        held = MappingProxyType({k: frozenset(v) for k, v in roles.items()})
        return Caller("o" * 64, "203.0.113.7", org_id="acme", user_id="u" * 64, roles=held)

    def test_device_mode_is_never_refused(self):
        require_role(Caller(owner_hash("k" * 22), "203.0.113.7"), "sg", "admin")

    def test_a_role_at_the_site_passes_and_one_elsewhere_does_not(self):
        caller = self.firebase_caller({"sg": {"supervisor"}})
        require_role(caller, "sg", "supervisor", "safety_officer")
        with pytest.raises(Forbidden) as refused:
            require_role(caller, "chennai", "supervisor")
        assert (refused.value.status, refused.value.code) == (403, "forbidden")
        with pytest.raises(Forbidden):
            require_role(caller, "sg", "admin")

    def test_no_roles_named_means_any_role_at_the_site(self):
        require_role(self.firebase_caller({"sg": {"safety_officer"}}), "sg")
        with pytest.raises(Forbidden):
            require_role(self.firebase_caller({}), "sg")

    def test_a_misspelt_role_is_a_bug_even_in_device_mode(self):
        with pytest.raises(ValueError):
            require_role(Caller(owner_hash("k" * 22), "a"), "sg", "safety-officer")

    def test_the_caller_shows_no_member_or_roles_and_stays_hashable(self):
        caller = self.firebase_caller({"sg": {"admin"}})
        assert "u" * 64 not in repr(caller) and "admin" not in repr(caller)
        hash(caller)
        assert Caller("o", "a").roles == {} and Caller("o", "a").org_id is None


class TestRoles:
    def test_only_catalog_sites_and_known_roles_count(self):
        roles = effective_roles({"roles": {"sg": ["supervisor", "owner"], "mars": ["admin"]}})
        assert dict(roles) == {"sg": frozenset({"supervisor"})}

    def test_an_org_admin_is_admin_at_every_catalog_site(self):
        roles = effective_roles({"orgAdmin": True, "roles": {"sg": ["supervisor"]}})
        assert roles["sg"] == {"admin", "supervisor"} and roles["chennai"] == {"admin"}

    def test_ids_are_hashes_and_the_org_owner_cannot_be_a_device_owner(self):
        assert len(member_hash("uid-1")) == 64 and "uid-1" not in member_hash("uid-1")
        assert org_owner("acme") != owner_hash("acme") and len(org_owner("acme")) == 64


class TestClaims:
    def test_good_claims_give_the_uid_and_the_lowercased_email(self):
        assert identity(claims(), PROJECT) == ("uid-1", "supervisor@acme.example", True)

    @pytest.mark.parametrize(
        "bad",
        [
            {"iss": "https://accounts.google.com"},
            {"iss": "https://securetoken.google.com/someone-else"},
            {"aud": "someone-else"},
            {"sub": ""},
            {"sub": "x" * 129},
            {"sub": None},
        ],
    )
    def test_a_wrong_issuer_audience_or_subject_is_a_bad_token(self, bad):
        with pytest.raises(BadToken):
            identity(claims(**bad), PROJECT)

    def test_only_a_true_email_verified_is_verified(self):
        assert identity(claims(email_verified="true"), PROJECT)[2] is False
        assert identity(claims(email=None), PROJECT)[1] == ""


class TestBearer:
    def test_no_header_is_auth_required(self):
        with pytest.raises(AuthRequired):
            auth.bearer_token(conn())

    @pytest.mark.parametrize(
        "value",
        ["Basic abc", "Bearer", "Bearer not-a-jwt", "Bearer a.b", "Bearer a.b.c d", "a.b.c"],
    )
    def test_a_malformed_header_is_a_bad_token(self, value):
        with pytest.raises(BadToken):
            auth.bearer_token(conn(value))

    def test_two_headers_or_a_huge_token_are_bad(self):
        with pytest.raises(BadToken):
            auth.bearer_token(conn("Bearer a.b.c", "Bearer d.e.f"))
        with pytest.raises(BadToken):
            auth.bearer_token(conn(f"Bearer a.{'b' * 4096}.c"))

    def test_the_token_is_taken_from_either_case_of_bearer(self):
        assert auth.bearer_token(conn("bearer h.p.s")) == "h.p.s"


class TestTheRealVerifier:
    def test_it_calls_verify_firebase_token_with_the_project_as_audience(self, monkeypatch):
        from google.oauth2 import id_token

        seen: list[tuple] = []

        def fake_verify(token, request, audience=None, clock_skew_in_seconds=0):
            seen.append((token, request, audience, clock_skew_in_seconds))
            return claims()

        monkeypatch.setattr(id_token, "verify_firebase_token", fake_verify)
        from tests.helpers import run_sync

        result = run_sync(auth.google_verifier(PROJECT)("h.p.s"))
        assert result == claims()
        token, request, audience, _ = seen[0]
        assert (token, audience) == ("h.p.s", PROJECT)
        assert isinstance(request, auth.CachedCerts)

    def test_the_certificates_are_fetched_once_per_ttl(self):
        calls: list[str] = []
        now = [0.0]

        def inner(url, method="GET", **_):
            calls.append(url)
            return SimpleNamespace(status=200 if url.endswith("ok") else 500)

        cached = auth.CachedCerts(inner, ttl_s=60, clock=lambda: now[0])
        cached("https://certs/ok")
        cached("https://certs/ok")
        assert calls == ["https://certs/ok"]
        now[0] = 61.0
        cached("https://certs/ok")
        cached("https://certs/fail")
        cached("https://certs/fail")  # a failed fetch is not kept
        assert calls == ["https://certs/ok", "https://certs/ok", "https://certs/fail"] + [
            "https://certs/fail"
        ]
