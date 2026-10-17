"""Security fixes A (build-notes/36-security-fixes-a.md: H1 to H3 of build-notes/35; API.md
Deviations 2026-10-16 "security fixes A").

- H1: the e-permit link (SIB_OUTBOX, SIB_PTW_URL) needs accounts. In device mode the service does
  not start with it on; SIB_WEBHOOK_URL (the demo permit stub, Google Chat) needs none.
- H2: on a sopRef briefing, endpoint 9 takes only the signed-off version's steps, unchanged and in
  order, compared on every Step field after validators.steps; anything else is 409
  sop_steps_locked and changes nothing.
- H3: with no accounts a catalogue SOP takes no new version (403 forbidden); the caller's own SOPs
  keep the whole flow, and with accounts the roles decide as before.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

import pytest

from sayitback import catalog
from sayitback.auth import member_hash
from sayitback.caller import Caller, owner_hash
from sayitback.main import create_app
from sayitback.settings import PERMIT_LINK_NEEDS_ACCOUNTS, ConfigError, Settings
from sayitback.sop_library import CATALOGUE_READ_ONLY, NewVersion, SopLibrary
from sayitback.store import LocalStore
from tests.fakes import FakeTtsClient
from tests.helpers import api_client, make_app

VENDOR = "https://epermit.vendor.example/api/clearances?tenant=SITEKEY42"
ACCOUNTS = {"SIB_AUTH_MODE": "firebase", "SIB_AUTH_PROJECT": "sib-pilot", "SIB_AUTH_ORG": "acme"}
LIFT_BODY = {
    "siteId": "sg",
    "taskId": "lifting-zone",
    "supervisorLang": "en",
    "workerLang": "ta",
    "instruction": "Keep out from under the load and stay behind the barricade.",
}
LIFT_REF = {"sopId": "SOP-LF-03", "version": 2}
LOCKED = (
    "These steps are signed off in {sop}. To change them, a safety officer signs off a new "
    "version, or start the briefing with Gemini's steps."
)
STEP = {"id": "s1", "text": "Stay behind the barricade", "hazard": "Struck by the load"}


@pytest.fixture
def app(settings):
    return make_app(settings, tts_client=FakeTtsClient())[0]


@pytest.fixture
def api(app):
    return api_client(app)


def library_briefing(api, ref: Mapping[str, Any] = LIFT_REF, body=LIFT_BODY) -> tuple[str, list]:
    """A briefing started from a signed-off version, and the steps endpoint 8 proposed."""
    made = api.post("/api/briefings", json={**body, "sopRef": ref})
    assert made.status_code == 200, made.text
    extracted = api.post(f"/api/briefings/{made.json()['id']}/steps/extract")
    assert extracted.status_code == 200, extracted.text
    return made.json()["id"], extracted.json()["steps"]


def own_sop(api, path: str = "/api/sites/sg/sops") -> dict[str, Any]:
    """The caller's own lifting SOP, v1 with STEP signed off."""
    made = api.post(path, json={"title": "Lifting", "text": "Our SOP.", "taskId": "lifting-zone"})
    assert made.status_code == 200, made.text
    own = f"{path}/{made.json()['id']}/versions/1"
    assert api.put(f"{own}/steps", json={"steps": [STEP]}).status_code == 200
    signed = api.post(f"{own}/approve")
    assert signed.status_code == 200, signed.text
    return signed.json()


# H1: the e-permit link needs accounts -----------------------------------------------------------


class TestThePermitLinkNeedsAccounts:
    LINKS = (
        {"SIB_OUTBOX": "true"},
        {"SIB_PTW_URL": VENDOR},
        {"SIB_OUTBOX": "true", "SIB_PTW_URL": VENDOR, "SIB_PTW_TOKEN": "vendor-bearer-0f9e8d7c"},
    )

    @pytest.mark.parametrize("link", LINKS)
    @pytest.mark.parametrize("mode", [{}, {"SIB_AUTH_MODE": "device"}])
    def test_device_mode_with_the_link_does_not_start(self, link, mode):
        with pytest.raises(ConfigError) as refused:
            Settings.from_env({**mode, **link})
        assert str(refused.value) == PERMIT_LINK_NEEDS_ACCOUNTS
        assert "SITEKEY42" not in str(refused.value) and "epermit" not in str(refused.value)

    def test_the_message_says_why(self):
        assert PERMIT_LINK_NEEDS_ACCOUNTS == (
            "The e-permit link (SIB_OUTBOX, SIB_PTW_URL) needs SIB_AUTH_MODE=firebase: in device "
            "mode no person stands behind a decision."
        )

    def test_the_service_itself_does_not_start(self, monkeypatch):
        monkeypatch.setenv("SIB_PTW_URL", VENDOR)
        with pytest.raises(ConfigError, match="needs SIB_AUTH_MODE=firebase"):
            create_app()  # what `uvicorn sayitback.main:app` runs at import

    @pytest.mark.parametrize("link", LINKS)
    def test_with_accounts_the_link_starts(self, link):
        s = Settings.from_env({**ACCOUNTS, **link})
        assert s.auth_mode == "firebase" and (s.outbox or s.ptw_url)

    def test_the_demo_stub_and_chat_need_no_accounts(self):
        urls = "https://ptw.example.run.app/webhook,https://chat.googleapis.com/v1/spaces/X?key=k"
        s = Settings.from_env({"SIB_WEBHOOK_URL": urls, "SIB_WEBHOOK_SECRET": "s" * 32})
        assert s.auth_mode == "device" and len(s.webhook_urls) == 2

    def test_the_link_switched_off_starts_in_device_mode(self):
        s = Settings.from_env({"SIB_OUTBOX": "false", "SIB_PTW_URL": "  "})
        assert (s.auth_mode, s.outbox, s.ptw_url) == ("device", False, "")


# H2: signed-off steps stay as signed off --------------------------------------------------------


def _edit(i: int, **change: Any) -> Callable[[list], list]:
    return lambda steps: [{**s, **change} if j == i else s for j, s in enumerate(steps)]


def _other_source(steps: list) -> list:
    return [{**steps[0], "source": "both" if steps[0]["source"] != "both" else "sop"}, *steps[1:]]


CHANGED: dict[str, Callable[[list], list]] = {
    "text": _edit(0, text="Wear a hat."),
    "hazard": _edit(1, hazard="Nothing much"),
    "an essential added": lambda st: _edit(0, essential=[*st[0]["essential"], "wave"])(st),
    "the essentials emptied": _edit(1, essential=[]),
    "source": _other_source,
    "sopQuote": _edit(2, sopQuote="Stand where you like."),
    "speakable": _edit(3, speakable=False),
    "id": _edit(0, id="s9"),
    "order": lambda st: [st[1], st[0], *st[2:]],
    "one removed": lambda st: st[:-1],
    "one added": lambda st: [*st, {"id": "s5", "text": "Wave at the crane driver."}],
    "all replaced (the review's probe)": lambda _st: [{"id": "s1", "text": "Wear a hat."}],
}
SAME_AFTER_CLEANING: dict[str, Callable[[list], list]] = {
    "spaces around a text": lambda st: [{**st[0], "text": f"  {st[0]['text']} "}, *st[1:]],
    "an empty essential": lambda st: _edit(0, essential=[*st[0]["essential"], " "])(st),
    "a default left out": lambda st: [{k: v for k, v in s.items() if k != "speakable"} for s in st],
    "a key the model has not": lambda st: [{**s, "note": "ignored"} for s in st],
}


class TestSignedOffStepsStayAsSignedOff:
    @pytest.mark.parametrize("task", catalog.load_catalog()["tasks"], ids=lambda t: t["id"])
    def test_every_seed_confirms_as_it_was_signed_off(self, api, task):
        site = catalog.site(task["demoSite"])
        body = {
            **LIFT_BODY, "siteId": task["demoSite"], "taskId": task["id"],
            "workerLang": site["defaultWorkerLanguage"],
        }  # fmt: skip
        ref = {"sopId": task["sop"]["id"], "version": int(task["sop"]["version"].lstrip("v"))}
        bid, proposed = library_briefing(api, ref, body)
        confirmed = api.put(f"/api/briefings/{bid}/steps", json={"steps": proposed})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["steps"] == proposed

    @pytest.mark.parametrize("change", list(CHANGED.values()), ids=list(CHANGED))
    def test_any_change_is_409_and_changes_nothing(self, api, change):
        bid, proposed = library_briefing(api)
        before = api.get(f"/api/briefings/{bid}").json()
        refused = api.put(f"/api/briefings/{bid}/steps", json={"steps": change(copy.deepcopy(proposed))})
        assert refused.status_code == 409
        assert refused.json()["error"] == {
            "code": "sop_steps_locked",
            "message": LOCKED.format(sop="SOP-LF-03 v2"),
        }
        assert api.get(f"/api/briefings/{bid}").json() == before  # status, steps, chain alike
        assert api.get(f"/api/briefings/{bid}/verify").json()["ok"] is True

    @pytest.mark.parametrize("same", list(SAME_AFTER_CLEANING.values()), ids=list(SAME_AFTER_CLEANING))
    def test_the_same_steps_after_cleaning_are_accepted(self, api, same):
        bid, proposed = library_briefing(api)
        confirmed = api.put(f"/api/briefings/{bid}/steps", json={"steps": same(copy.deepcopy(proposed))})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["steps"] == proposed

    def test_after_a_refusal_the_signed_off_steps_confirm_and_confirm_again(self, api):
        bid, proposed = library_briefing(api)
        path = f"/api/briefings/{bid}/steps"
        assert api.put(path, json={"steps": CHANGED["text"](proposed)}).status_code == 409
        first = api.put(path, json={"steps": proposed}).json()
        again = api.put(path, json={"steps": proposed}).json()
        assert (first["status"], first["stepsVersion"], again["stepsVersion"]) == (
            "steps_confirmed", 1, 2,
        )  # fmt: skip

    def test_a_briefing_without_a_sop_ref_takes_edited_steps_as_before(self, api):
        bid = api.post("/api/briefings", json=LIFT_BODY).json()["id"]
        steps = api.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
        confirmed = api.put(f"/api/briefings/{bid}/steps", json={"steps": CHANGED["text"](steps)})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["steps"][0]["text"] == "Wear a hat."

    def test_an_own_version_is_locked_too_under_its_own_id(self, api):
        entry = own_sop(api)
        bid, proposed = library_briefing(api, {"sopId": entry["id"], "version": 1})
        refused = api.put(f"/api/briefings/{bid}/steps", json={"steps": CHANGED["text"](proposed)})
        assert refused.json()["error"] == {
            "code": "sop_steps_locked",
            "message": LOCKED.format(sop=f"{entry['id']} v1"),
        }


class Verifier:
    """google-auth's place, as in tests/test_auth_api.py: a known token gives its claims."""

    USERS = {"boss": ("uid-boss", "boss@acme.example"), "sup": ("uid-sup", "sup@acme.example")}

    async def __call__(self, token: str) -> Mapping[str, Any]:
        uid, email = self.USERS[token.split(".")[1]]
        iss = "https://securetoken.google.com/sib-pilot"
        return {"iss": iss, "aud": "sib-pilot", "sub": uid, "email": email, "email_verified": True}


def test_with_accounts_a_supervisor_cannot_replace_the_signed_off_steps(settings):
    """The review's L1b: a supervisor at the site, who may neither draft nor sign off."""
    s = settings.with_overrides(
        auth_mode="firebase", auth_project="sib-pilot", auth_org="acme",
        bootstrap_admins=("boss@acme.example",),
    )  # fmt: skip
    app, *_ = make_app(s, tts_client=FakeTtsClient(), token_verifier=Verifier())

    def as_user(name: str):
        return api_client(app, device=None, headers={"Authorization": f"Bearer h.{name}.s"})

    as_user("boss").get("/api/me")  # the bootstrap admin, first
    as_user("sup").get("/api/me")  # the first sign-in makes the member
    member = member_hash(Verifier.USERS["sup"][0])
    grant = {"roles": {"sg": ["supervisor"]}}
    assert as_user("boss").put(f"/api/orgs/acme/members/{member}", json=grant).status_code == 200
    sup = as_user("sup")
    bid, proposed = library_briefing(sup)
    refused = sup.put(f"/api/briefings/{bid}/steps", json={"steps": CHANGED["text"](proposed)})
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "sop_steps_locked")
    assert sup.put(f"/api/briefings/{bid}/steps", json={"steps": proposed}).status_code == 200


# H3: no new version of a catalogue SOP without accounts -----------------------------------------


class TestNoCatalogueVersionWithoutAccounts:
    @pytest.mark.parametrize("site", ["sg", "chennai"])
    def test_every_seed_refuses_a_new_version_and_nothing_is_stored(self, api, settings, site):
        for entry in api.get(f"/api/sites/{site}/sops").json()["items"]:
            path = f"/api/sites/{site}/sops/{entry['id']}/versions"
            refused = api.post(path, json={"text": "Stand under the load.", "changeNote": "x"})
            assert refused.status_code == 403
            assert refused.json()["error"] == {"code": "forbidden", "message": CATALOGUE_READ_ONLY}
        assert not (settings.data_dir / "sop_library").exists()

    def test_the_message_says_what_to_do_instead(self):
        assert CATALOGUE_READ_ONLY == (
            "Catalogue SOPs are read-only in this demo. Add your own SOP instead."
        )

    def test_an_unknown_sop_or_site_is_still_404(self, api):
        assert api.post("/api/sites/sg/sops/SOP-NOPE/versions", json={"text": "x"}).status_code == 404
        unknown = api.post("/api/sites/mars/sops/SOP-LF-03/versions", json={"text": "x"})
        assert unknown.json()["error"]["code"] == "unknown_site"

    def test_the_callers_own_sop_keeps_the_whole_flow_under_its_own_id(self, api):
        entry = own_sop(api)
        path = f"/api/sites/sg/sops/{entry['id']}/versions"
        assert api.post(path, json={"text": "Revised."}).status_code == 200
        assert api.put(f"{path}/2/steps", json={"steps": [STEP]}).status_code == 200
        assert api.post(f"{path}/2/approve").status_code == 200
        b = api.post("/api/briefings", json={**LIFT_BODY, "sopRef": {"sopId": entry["id"], "version": 2}})
        assert b.status_code == 200, b.text
        assert (b.json()["sop"]["id"], b.json()["sop"]["version"]) == (entry["id"], "v2")
        assert entry["id"] not in {t["sop"]["id"] for t in catalog.load_catalog()["tasks"]}

    def test_the_catalogue_versions_still_start_a_briefing(self, api):
        bid, proposed = library_briefing(api)
        assert api.get(f"/api/briefings/{bid}").json()["sop"]["version"] == "v2" and proposed

    async def test_with_accounts_the_roles_decide_as_before(self, tmp_path):
        library = SopLibrary(LocalStore(tmp_path), Settings(data_dir=tmp_path))
        roles = MappingProxyType({"sg": frozenset({"safety_officer"})})
        officer = Caller(owner_hash("o-acme-device-key-aaaaaaaaaa"), "203.0.113.9", "acme", "o", roles)
        entry = await library.add_version(officer, "sg", "SOP-LF-03", NewVersion(text="Revised."))
        assert [v.number for v in entry.versions] == [2, 3]
        assert entry.versions[-1].created_by == "safety_officer"
