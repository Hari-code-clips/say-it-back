"""A library step signed off with no essentials gets its own text as its one essential (17 Oct,
build-notes/37-review-remainder.md; the open issue 3 of note 36-a): the library editor has no
"what the worker must state" field, and since H2 a signed-off step reaches the judge as it was
signed off, so without this it would be judged against "(none given)". A draft keeps what was
saved; the text is written at sign-off, so it is always the signed-off text."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes import FakeTtsClient
from tests.helpers import api_client, make_app

LIFT_BODY = {
    "siteId": "sg",
    "taskId": "lifting-zone",
    "supervisorLang": "en",
    "workerLang": "ta",
    "instruction": "Keep out from under the load and stay behind the barricade.",
}
OWN = {"title": "Lifting, our site", "text": "Lifting SOP, our own.", "taskId": "lifting-zone"}
BARE = {"id": "s1", "text": "  Keep the red barricade closed  ", "hazard": "Struck by the load"}
BLANKS = {"id": "s2", "text": "Tag lines only", "essential": ["  ", ""]}
KEPT = {"id": "s3", "text": "Follow the signalman", "essential": ["only the signalman"]}


@pytest.fixture
def api(settings):
    return api_client(make_app(settings, tts_client=FakeTtsClient())[0])


def drafted(api, steps: list[dict[str, Any]]) -> str:
    """The path of the caller's own SOP, its v1 draft holding `steps`."""
    made = api.post("/api/sites/sg/sops", json=OWN)
    assert made.status_code == 200, made.text
    path = f"/api/sites/sg/sops/{made.json()['id']}"
    saved = api.put(f"{path}/versions/1/steps", json={"steps": steps})
    assert saved.status_code == 200, saved.text
    return path


def v1_steps(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return next(v for v in entry["versions"] if v["number"] == 1)["steps"]


def test_a_draft_keeps_the_essentials_it_was_saved_with(api):
    path = drafted(api, [BARE, BLANKS, KEPT])

    steps = v1_steps(api.get(path).json())

    assert [s["essential"] for s in steps] == [[], [], ["only the signalman"]]


def test_sign_off_gives_a_step_with_no_essentials_its_own_text(api):
    path = drafted(api, [BARE, BLANKS, KEPT])

    signed = api.post(f"{path}/versions/1/approve")

    assert signed.status_code == 200, signed.text
    steps = v1_steps(signed.json())
    assert [s["essential"] for s in steps] == [
        ["Keep the red barricade closed"],  # the cleaned text, as stored
        ["Tag lines only"],  # blank essentials were dropped on save
        ["only the signalman"],  # a step with an essential keeps it
    ]
    assert [s["text"] for s in steps] == [
        "Keep the red barricade closed",
        "Tag lines only",
        "Follow the signalman",
    ]
    assert v1_steps(api.get(path).json()) == steps  # what was signed off is what is kept


def test_the_signed_off_text_is_the_essential_after_a_late_edit(api):
    path = drafted(api, [BARE])
    edited = {**BARE, "text": "Keep the red barricade closed and locked"}
    assert api.put(f"{path}/versions/1/steps", json={"steps": [edited]}).status_code == 200

    steps = v1_steps(api.post(f"{path}/versions/1/approve").json())

    assert steps[0]["essential"] == ["Keep the red barricade closed and locked"]


def test_a_briefing_from_it_judges_against_the_step_and_confirms_unchanged(api):
    path = drafted(api, [BARE, KEPT])
    entry = api.post(f"{path}/versions/1/approve").json()
    ref = {"sopId": entry["id"], "version": 1}
    created = api.post("/api/briefings", json={**LIFT_BODY, "sopRef": ref})
    assert created.status_code == 200, created.text
    bid = created.json()["id"]

    proposed = api.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
    confirmed = api.put(f"/api/briefings/{bid}/steps", json={"steps": proposed})

    assert [s["essential"] for s in proposed] == [
        ["Keep the red barricade closed"],
        ["only the signalman"],
    ]
    assert confirmed.status_code == 200, confirmed.text  # H2: the signed-off steps, unchanged
    assert [s["essential"] for s in confirmed.json()["steps"]] == [s["essential"] for s in proposed]


def test_a_new_version_starts_from_the_signed_off_essentials(api):
    path = drafted(api, [BARE])
    api.post(f"{path}/versions/1/approve")

    entry = api.post(f"{path}/versions", json={"text": "Lifting SOP, revision 2."}).json()

    v2 = next(v for v in entry["versions"] if v["number"] == 2)
    assert v2["status"] == "draft"
    assert v2["steps"][0]["essential"] == ["Keep the red barricade closed"]
