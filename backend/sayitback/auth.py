"""Pilot accounts (API.md Deviations 2026-10-16, build-notes/34): SIB_AUTH_MODE=firebase.

Device mode (the default) is today's anonymous device key (api/device.py) and nothing here runs.
In firebase mode every /api request but health carries a Firebase ID token (Google sign-in through
Firebase Authentication or Identity Platform, which is also where a company's SAML or OIDC SSO
plugs in, by configuration). The token is verified with google-auth, the email domain is checked,
and the member of the deployment's one org (SIB_AUTH_ORG) is read or, at the first sign-in,
created. The request's `Caller` then names the org, the member (a hash of the Firebase uid, never
the uid) and the member's roles per site, and its `owner` is the org's, so the org's records are
stored under one owner (repo.py scopes by owner, unchanged); a member reaches only those at the
sites where they hold a role (api/context.py, security fixes B).

Only supervisors, safety officers and admins sign in. A worker is never a member, so no worker
identity is stored; a member's email is their work identity, kept for the admin's list.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from collections.abc import Awaitable, Callable, Collection, Mapping
from types import MappingProxyType
from typing import Any

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sayitback import catalog
from sayitback.api.device import DeviceMiddleware
from sayitback.caller import Caller
from sayitback.errors import ApiError
from sayitback.models import now_iso
from sayitback.ratelimit import client_ip
from sayitback.settings import ConfigError, Settings
from sayitback.store.base import ORG_ID, Store

log = logging.getLogger("sayitback.auth")

AUTH_MODES = ("device", "firebase")
ROLES = ("admin", "safety_officer", "supervisor")
ISSUER = "https://securetoken.google.com/"
ME_PATH = "/api/me"
ORGS_PREFIX = "/api/orgs/"
MAX_TOKEN_CHARS = 4096
MAX_UID_CHARS = 128  # Firebase's own limit on a uid
CLOCK_SKEW_S = 10
CERTS_TTL_S = 3600.0  # Google publishes a new signing key well before it signs with it
ADMIN_SCAN = 10_000  # members read, for a bootstrap email's first sign-in, to find an org admin
BEARER = re.compile(r"[Bb]earer +([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")

Verifier = Callable[[str], Awaitable[Mapping[str, Any]]]


class AuthRequired(ApiError):
    status = 401
    code = "auth_required"


class BadToken(ApiError):
    status = 401
    code = "bad_token"


class DomainNotAllowed(ApiError):
    status = 403
    code = "domain_not_allowed"


class Forbidden(ApiError):
    status = 403
    code = "forbidden"


SIGN_IN = "Sign in to continue."
SIGN_IN_AGAIN = "Your sign-in has expired or is not valid. Sign in again."
NOT_ALLOWED = "This account's email domain is not allowed here."
NO_ROLE = "You are signed in, but you have no role at any site yet. Ask your admin."
NOT_YOUR_ROLE = "Your role at this site does not allow this."


def csv_lower(raw: str) -> tuple[str, ...]:
    """A comma-separated setting as lowercase entries, blanks dropped."""
    return tuple(x.strip().lower() for x in raw.split(",") if x.strip())


def check_settings(values: Mapping[str, Any]) -> None:
    """Start-up check of the auth settings (settings._auth_settings)."""
    if values["auth_mode"] != "firebase":
        return
    if not values["auth_project"]:
        raise ConfigError("SIB_AUTH_MODE=firebase needs SIB_AUTH_PROJECT or GOOGLE_CLOUD_PROJECT")
    if not ORG_ID.fullmatch(values["auth_org"]):
        raise ConfigError("SIB_AUTH_MODE=firebase needs SIB_AUTH_ORG ([a-z0-9][a-z0-9_-]{0,39})")
    if not all(DOMAIN.fullmatch(d) for d in values["auth_allowed_domains"]):
        raise ConfigError("SIB_AUTH_ALLOWED_DOMAINS must be domains like example.com")
    if not all("@" in e for e in values["bootstrap_admins"]):
        raise ConfigError("SIB_BOOTSTRAP_ADMINS must be email addresses")


def member_hash(uid: str) -> str:
    """A member's id: the SHA-256 of the Firebase uid, so the store never holds the uid."""
    return hashlib.sha256(f"uid:{uid}".encode()).hexdigest()


def org_owner(org_id: str) -> str:
    """The owner of every record of the org (a device key cannot contain ':', so no device's
    owner hash can equal it)."""
    return hashlib.sha256(f"org:{org_id}".encode()).hexdigest()


def site_ids() -> tuple[str, ...]:
    return tuple(s["id"] for s in catalog.load_catalog()["sites"])


def require_role(caller: Caller, site_id: str, *roles: str) -> None:
    """403 `forbidden` unless the caller holds one of `roles` (any of the three when none is
    named) at `site_id`. Device mode has no accounts (`org_id` is None), so this does nothing."""
    unknown = set(roles) - set(ROLES)
    if unknown:
        raise ValueError(f"unknown roles {sorted(unknown)}")  # a bug in the caller, never a request
    if caller.org_id is None:
        return
    if not caller.roles.get(site_id, frozenset()) & set(roles or ROLES):
        raise Forbidden(NOT_YOUR_ROLE)


def effective_roles(member: Mapping[str, Any]) -> Mapping[str, frozenset[str]]:
    """The member's roles per catalog site; an org admin also holds `admin` at every site."""
    sites = site_ids()
    stored = member.get("roles") or {}
    roles = {site: frozenset(r for r in stored.get(site, ()) if r in ROLES) for site in sites}
    if member.get("orgAdmin") is True:
        roles = {site: held | {"admin"} for site, held in roles.items()}
    return MappingProxyType({site: held for site, held in roles.items() if held})


def bearer_token(conn: HTTPConnection) -> str:
    values = conn.headers.getlist("authorization")
    if not values:
        raise AuthRequired(SIGN_IN)
    match = BEARER.fullmatch(values[0].strip()) if len(values) == 1 else None
    if match is None or len(match.group(1)) > MAX_TOKEN_CHARS:
        raise BadToken(SIGN_IN_AGAIN)
    return match.group(1)


def identity(claims: Mapping[str, Any], project: str) -> tuple[str, str, bool]:
    """(uid, email, email_verified) from verified claims. google-auth checks the signature, the
    audience and the expiry; the issuer and the subject are checked here."""
    uid = claims.get("sub")
    if claims.get("iss") != f"{ISSUER}{project}" or claims.get("aud") != project:
        raise BadToken(SIGN_IN_AGAIN)
    if not isinstance(uid, str) or not 0 < len(uid) <= MAX_UID_CHARS:
        raise BadToken(SIGN_IN_AGAIN)
    email = claims.get("email")
    email = email.strip().lower() if isinstance(email, str) else ""
    return uid, email, claims.get("email_verified") is True


def email_domain(email: str) -> str:
    return email.rpartition("@")[2] if "@" in email else ""


class CachedCerts:
    """A google-auth transport request that keeps the signing certificates' response for
    `ttl_s`, so verifying a token makes no network call (and a flood of bad tokens makes none)."""

    def __init__(self, inner: Any, ttl_s: float = CERTS_TTL_S, clock=time.monotonic) -> None:
        self.inner, self.ttl_s, self.clock = inner, ttl_s, clock
        self._hits: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def __call__(self, url: str, method: str = "GET", **kwargs: Any) -> Any:
        if method != "GET":
            return self.inner(url, method=method, **kwargs)
        with self._lock:
            hit = self._hits.get(url)
        if hit and hit[0] > self.clock():
            return hit[1]
        response = self.inner(url, method=method, **kwargs)
        if response.status == 200:
            with self._lock:
                self._hits[url] = (self.clock() + self.ttl_s, response)
        return response


def google_verifier(project: str) -> Verifier:
    """The real check: google-auth's `verify_firebase_token`, off the event loop."""
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    request = CachedCerts(Request())

    def verify(token: str) -> Mapping[str, Any]:
        return id_token.verify_firebase_token(
            token, request, audience=project, clock_skew_in_seconds=CLOCK_SKEW_S
        )

    async def run(token: str) -> Mapping[str, Any]:
        return await asyncio.to_thread(verify, token)

    return run


class Auth:
    """Firebase mode: from a request's token to its `Caller`."""

    def __init__(self, settings: Settings, store: Store, verifier: Verifier) -> None:
        self.project = settings.auth_project
        self.org = settings.auth_org
        self.domains = frozenset(settings.auth_allowed_domains)
        self.admins = frozenset(settings.bootstrap_admins)
        self.store = store
        self.verifier = verifier

    async def claims(self, token: str) -> tuple[str, str, bool]:
        try:
            return identity(await self.verifier(token), self.project)
        except ApiError:
            raise
        except Exception as exc:  # google-auth raises ValueError and its own errors
            log.debug("token refused: %s", type(exc).__name__)  # never the token or its claims
            raise BadToken(SIGN_IN_AGAIN) from None

    async def sign_in(self, uid: str, email: str, verified: bool) -> dict[str, Any]:
        """The member, created with no roles at the first sign-in. A verified email in
        SIB_BOOTSTRAP_ADMINS is created an org admin only while the org has none (security fixes
        B): the list seeds the first admin, then grants nothing, so a demotion sticks even for a
        new uid of the same email. A known member costs one read and no write."""
        member_id = member_hash(uid)
        current = await self.store.member_get(self.org, member_id)
        if current is not None:
            return current
        admin = verified and email in self.admins and not await self._has_admin()

        def create(existing: dict[str, Any] | None) -> dict[str, Any] | None:
            if existing is not None:  # another request created it first
                return None
            now = now_iso()
            return {
                "memberId": member_id,
                "email": email if verified else "",
                "orgAdmin": admin,
                "roles": {},
                "createdAt": now,
                "updatedAt": now,
            }

        member = await self.store.member_update(self.org, member_id, create)
        assert member is not None
        return member

    async def _has_admin(self) -> bool:
        """Whether a member of the org is an org admin. Once one is, one stays: the members route
        lets an admin demote only another admin (orgs.py, `cannot_demote_self`)."""
        members = await self.store.members_list(self.org, ADMIN_SCAN)
        return any(m.get("orgAdmin") is True for m in members)

    async def caller_for(self, conn: HTTPConnection, address: str) -> tuple[Caller, dict]:
        uid, email, verified = await self.claims(bearer_token(conn))
        if self.domains and not (verified and email_domain(email) in self.domains):
            raise DomainNotAllowed(NOT_ALLOWED)
        member = await self.sign_in(uid, email, verified)
        roles = effective_roles(member)
        path = conn.url.path
        if not roles and path != ME_PATH and not path.startswith(ORGS_PREFIX):
            raise Forbidden(NO_ROLE)
        caller = Caller(
            org_owner(self.org),
            address,
            org_id=self.org,
            user_id=member["memberId"],
            roles=roles,
        )
        return caller, member


class FirebaseMiddleware(DeviceMiddleware):
    """In firebase mode, in place of the device key check: the same routes need a caller, and
    the caller comes from the ID token. The member record rides along for /api/me and /api/orgs."""

    def __init__(self, app: ASGIApp, auth: Auth, hops: int, open_paths: Collection[str]) -> None:
        super().__init__(app, hops, open_paths)
        self.auth = auth

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._needs_key(scope):
            await self.app(scope, receive, send)
            return
        conn = HTTPConnection(scope)
        try:
            caller, member = await self.auth.caller_for(conn, client_ip(conn, self.hops))
        except ApiError as refusal:
            await JSONResponse(refusal.body(), refusal.status)(scope, receive, send)
            return
        except Exception as exc:  # the store failed: a JSON answer the browser can read
            log.error("sign-in failed: %s", type(exc).__name__)
            body = {"error": {"code": "internal_error", "message": "Something went wrong."}}
            await JSONResponse(body, 500)(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        state["caller"], state["member"] = caller, member
        await self.app(scope, receive, send)


def build_auth(settings: Settings, store: Store, verifier: Verifier | None = None) -> Auth | None:
    """The firebase-mode `Auth`, or None in device mode."""
    if settings.auth_mode != "firebase":
        return None
    check_settings(
        {
            "auth_mode": settings.auth_mode,
            "auth_project": settings.auth_project,
            "auth_org": settings.auth_org,
            "auth_allowed_domains": settings.auth_allowed_domains,
            "bootstrap_admins": settings.bootstrap_admins,
        }
    )
    return Auth(settings, store, verifier or google_verifier(settings.auth_project))


def cors_headers(settings: Settings) -> list[str]:
    """Headers CORS allows beyond today's: only firebase mode adds Authorization."""
    return ["Authorization"] if settings.auth_mode == "firebase" else []
