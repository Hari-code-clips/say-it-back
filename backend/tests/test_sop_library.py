"""The SOP library over the API in device (demo) mode (sop_library.py, api/sops.py; API.md
Deviations 2026-10-16 "library"): seeds, drafts and approvals, the device scope, and a briefing
that starts from an approved version without an extraction call. In device mode a catalogue SOP
takes no new version (security fixes A, H3; tests/test_security_fixes_a.py), so a device's drafts
and sign-offs here are under its own SOPs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from sayitback import catalog
from sayitback.caller import owner_hash
from tests.fakes import FakeTtsClient, Scenario
from tests.helpers import DEVICE, OTHER_DEVICE, api_client, make_app

LIFT = "/api/sites/sg/sops/SOP-LF-03"
LIFT_REF = {"sopId": "SOP-LF-03", "version": 2}  # the catalog's own number for SOP-LF-03
LIFT_BODY = {
    "siteId": "sg",
    "taskId": "lifting-zone",
    "supervisorLang": "en",
    "workerLang": "ta",
    "instruction": "Keep out from under the load and stay behind the barricade.",
}
STEP = {"id": "s1", "text": "Stay behind the barricade", "hazard": "Struck by the load"}
STEP2 = {"id": "s1", "text": "Keep the red barricade closed", "hazard": "Struck by the load"}
OWN = {"title": "Lifting, our site", "text": "Lifting SOP, our own.", "taskId": "lifting-zone"}


@dataclass
class Counting(Scenario):
    """The default scenario, recording the schema of every model call."""

    seen: list[Any] = field(default_factory=list)

    def handler(self, seen):  # noqa: ANN001, ANN201
        self.seen.append(seen.schema)
        return super().handler(seen)


@pytest.fixture
def app_parts(settings):
    scenario = Counting()
    app, _rt, _llm, store = make_app(settings, scenario, tts_client=FakeTtsClient())
    return app, scenario, store


@pytest.fixture
def api(app_parts):
    return api_client(app_parts[0])


def lift(api) -> dict[str, Any]:
    got = api.get(LIFT)
    assert got.status_code == 200, got.text
    return got.json()


def own_sop(api, *, signed: bool = True, text: str = OWN["text"]) -> tuple[str, dict[str, Any]]:
    """The caller's own SOP for the lifting task: its path and entry, v1 with STEP signed off (or
    a draft with no steps, `signed=False`)."""
    made = api.post("/api/sites/sg/sops", json={**OWN, "text": text})
    assert made.status_code == 200, made.text
    path = f"/api/sites/sg/sops/{made.json()['id']}"
    if not signed:
        return path, made.json()
    assert api.put(f"{path}/versions/1/steps", json={"steps": [STEP]}).status_code == 200
    approved = api.post(f"{path}/versions/1/approve")
    assert approved.status_code == 200, approved.text
    return path, approved.json()


# Seeds ------------------------------------------------------------------------------------------


def test_each_catalog_task_is_an_approved_read_only_seed_of_its_demo_site(api):
    for site in ("sg", "chennai"):
        items = api.get(f"/api/sites/{site}/sops").json()["items"]
        tasks = [t for t in catalog.load_catalog()["tasks"] if t["demoSite"] == site]
        assert [e["taskId"] for e in items] == [t["id"] for t in tasks]
        for entry, task in zip(items, tasks, strict=True):
            (version,) = entry["versions"]
            assert entry["seeded"] and entry["id"] == task["sop"]["id"]
            assert version["status"] == "approved" and version["readOnly"]
            assert f"v{version['number']}" == task["sop"]["version"]
            assert version["text"] == task["sop"]["text"]
            assert [s["text"] for s in version["steps"]] == [
                s["text"] for s in task["referenceSteps"]
            ]


def test_an_unknown_site_is_404(api):
    assert api.get("/api/sites/mars/sops").json()["error"]["code"] == "unknown_site"
    assert api.get("/api/sites/sg/sops/SOP-NOPE").json()["error"]["code"] == "sop_not_found"


def test_a_seeded_version_never_changes(api):
    steps = api.put(f"{LIFT}/versions/2/steps", json={"steps": [STEP]})
    approve = api.post(f"{LIFT}/versions/2/approve")
    assert steps.status_code == approve.status_code == 409
    assert steps.json()["error"]["code"] == approve.json()["error"]["code"] == "read_only"
    assert lift(api)["versions"][0]["steps"][0]["text"] != STEP["text"]


# Drafts and approval ----------------------------------------------------------------------------


def test_a_new_version_is_a_draft_with_the_approved_steps_until_approved(api):
    path, signed = own_sop(api)
    made = api.post(f"{path}/versions", json={"text": "Revised.", "changeNote": "New barricade"})
    assert made.status_code == 200, made.text
    draft = made.json()["versions"][-1]
    assert (draft["number"], draft["status"], draft["createdBy"]) == (2, "draft", "device")
    assert draft["steps"] == signed["versions"][0]["steps"]  # starts from v1's approved steps
    assert api.post(f"{path}/versions", json={"text": "x"}).json()["error"]["code"] == (
        "draft_exists"
    )

    edited = api.put(f"{path}/versions/2/steps", json={"steps": [STEP2]})
    assert edited.status_code == 200, edited.text
    approved = api.post(f"{path}/versions/2/approve")
    assert approved.status_code == 200, approved.text

    v2 = approved.json()["versions"][-1]
    assert (v2["status"], v2["approvedBy"], [s["text"] for s in v2["steps"]]) == (
        "approved",
        "device",
        [STEP2["text"]],
    )
    again = api.put(f"{path}/versions/2/steps", json={"steps": [STEP, {**STEP, "id": "s2"}]})
    assert (again.status_code, again.json()["error"]["code"]) == (409, "invalid_state")


def test_a_new_sop_needs_steps_before_its_approval(api):
    made = api.post("/api/sites/sg/sops", json={"title": "Night lifting", "text": "1. Lights."})
    assert made.status_code == 200, made.text
    entry = made.json()
    assert not entry["seeded"] and entry["versions"][0]["status"] == "draft"
    assert entry["versions"][0]["lang"] == "en"  # the site's default supervisor language
    path = f"/api/sites/sg/sops/{entry['id']}/versions/1"
    refused = api.post(f"{path}/approve")
    assert (refused.status_code, refused.json()["error"]["code"]) == (422, "steps_required")
    assert api.put(f"{path}/steps", json={"steps": []}).json()["error"]["code"] == "invalid_steps"


def test_one_devices_drafts_never_reach_another(app_parts, api):
    path, entry = own_sop(api, signed=False)
    other = api_client(app_parts[0], device=OTHER_DEVICE)
    listed = {e["id"] for e in other.get("/api/sites/sg/sops").json()["items"]}
    assert entry["id"] not in listed and "SOP-LF-03" in listed
    assert entry["id"] in {e["id"] for e in api.get("/api/sites/sg/sops").json()["items"]}
    refused = other.put(f"{path}/versions/1/steps", json={"steps": [STEP]})
    assert refused.json()["error"]["code"] == "sop_not_found"
    assert [v["number"] for v in lift(other)["versions"]] == [2]  # the seed, alike for both


def test_the_store_keeps_no_seed_and_no_device_key(app_parts, api, settings):
    _path, entry = own_sop(api, signed=False)
    (path,) = (settings.data_dir / "sop_library").glob("*.json")
    raw = path.read_text(encoding="utf-8")
    for secret in (DEVICE, owner_hash(DEVICE)):  # neither the key nor its hash, in the name or the content
        assert secret not in raw and secret not in path.name
    (stored,) = json.loads(raw)["sops"]
    assert (stored["id"], stored["seeded"]) == (entry["id"], False)  # no seed is stored


# A briefing from a library version --------------------------------------------------------------


def test_a_briefing_from_an_approved_version_skips_extraction(app_parts, api, settings):
    _app, scenario, _store = app_parts
    created = api.post("/api/briefings", json={**LIFT_BODY, "sopRef": LIFT_REF})
    assert created.status_code == 200, created.text
    b = created.json()
    assert b["sopRef"] == LIFT_REF and b["status"] == "draft"
    assert b["sop"] == catalog.task("lifting-zone")["sop"]  # the seed is the catalog's SOP

    extracted = api.post(f"/api/briefings/{b['id']}/steps/extract")
    assert extracted.status_code == 200, extracted.text
    proposed = extracted.json()
    assert scenario.seen == []  # no model call at all
    assert not (settings.data_dir / "gemini_calls").exists()  # and nothing reserved
    assert proposed["status"] == "steps_proposed" and proposed["conflicts"] == []
    reference = catalog.reference_steps("lifting-zone")
    assert [s["text"] for s in proposed["steps"]] == [s["text"] for s in reference]

    confirmed = api.put(f"/api/briefings/{b['id']}/steps", json={"steps": proposed["steps"]})
    assert confirmed.json()["status"] == "steps_confirmed"  # the supervisor's gate, unchanged


def test_a_briefing_from_an_own_approved_draft(api):
    _path, entry = own_sop(api, text="Lifting SOP, revision 3.")
    ref = {"sopId": entry["id"], "version": 1}
    b = api.post("/api/briefings", json={**LIFT_BODY, "sopRef": ref})
    assert b.status_code == 200, b.text
    sop = b.json()["sop"]
    assert (sop["id"], sop["version"], sop["text"]) == (entry["id"], "v1", "Lifting SOP, revision 3.")
    steps = api.post(f"/api/briefings/{b.json()['id']}/steps/extract").json()["steps"]
    assert [s["text"] for s in steps] == [STEP["text"]]


def test_a_draft_cannot_start_a_briefing(api):
    _path, entry = own_sop(api, signed=False)
    ref = {"sopId": entry["id"], "version": 1}
    refused = api.post("/api/briefings", json={**LIFT_BODY, "sopRef": ref})
    assert (refused.status_code, refused.json()["error"]["code"]) == (422, "sop_not_approved")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"sopRef": {**LIFT_REF, "version": 7}}, "unknown_sop"),
        ({"sopRef": {"sopId": "SOP-EL-04", "version": 4}}, "sop_task_mismatch"),
        ({"sopRef": LIFT_REF, "supervisorLang": "zh"}, "sop_language_mismatch"),
        ({"sopRef": LIFT_REF, "sop": {"title": "t", "text": "x"}}, "sop_conflict"),
        ({"sopRef": {**LIFT_REF, "version": "2"}}, "validation_error"),
        ({"sopRef": {**LIFT_REF, "by": "Ravi"}}, "validation_error"),
    ],
)
def test_a_sop_ref_that_cannot_start_a_briefing_is_refused(api, change, code):
    refused = api.post("/api/briefings", json={**LIFT_BODY, **change})
    assert (refused.status_code, refused.json()["error"]["code"]) == (422, code)


def test_another_devices_approved_version_is_unknown(app_parts, api):
    _path, entry = own_sop(api)
    other = api_client(app_parts[0], device=OTHER_DEVICE)
    ref = {"sopId": entry["id"], "version": 1}
    refused = other.post("/api/briefings", json={**LIFT_BODY, "sopRef": ref})
    assert refused.json()["error"]["code"] == "unknown_sop"


def test_the_record_chain_binds_the_sop_ref(app_parts, api, settings):
    b = api.post("/api/briefings", json={**LIFT_BODY, "sopRef": LIFT_REF}).json()
    assert b["events"][0]["data"]["sopRef"] == LIFT_REF
    assert api.get(f"/api/briefings/{b['id']}/verify").json()["ok"] is True

    path = settings.data_dir / "briefings" / f"{b['id']}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["sopRef"] = {**LIFT_REF, "version": 3}
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    broken = api.get(f"/api/briefings/{b['id']}/verify").json()
    assert (broken["ok"], broken["brokenAt"], broken["reason"]) == (False, 1, "created_mismatch")


def test_a_briefing_without_a_sop_ref_keeps_the_old_created_event(api):
    b = api.post("/api/briefings", json=LIFT_BODY).json()
    assert "sopRef" not in b["events"][0]["data"] and "sopRef" not in b
    assert api.get(f"/api/briefings/{b['id']}/verify").json()["ok"] is True
