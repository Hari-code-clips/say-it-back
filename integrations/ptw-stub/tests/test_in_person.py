"""2026-10-17, the in-person check (Say It Back docs/API.md Deviations): a Go after the worker
declined the AI check carries `decision.inPerson: true`. The stub keeps it on the permit and on
the worker's slot, serves it, and shows the slot as checked in person with its open steps, never
the supervisor's reason. A record without the field (an older backend) is not in person."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ptw_stub.app import create_app
from ptw_stub.permits import PermitBook
from tests.fake_firestore import FakeBackedBook, FakeFirestore
from tests.test_permit_groups import worker
from tests.test_stub import NOW, SECRET, post, record

STEPS = ["s1", "s4"]
REASON = "Walked him through the lift face to face"  # the supervisor's words: never on the board


def in_person(payload: dict) -> dict:
    payload["decision"].update(inPerson=True, reason=REASON)
    return payload


@pytest.fixture(params=["memory", "firestore"])
def client(request):
    book = FakeBackedBook(FakeFirestore()) if request.param == "firestore" else PermitBook()
    return TestClient(create_app(secret=SECRET, clock=lambda: NOW, book=book))


def only(client) -> dict:
    (permit,) = client.get("/api/permits").json()["permits"]
    return permit


class TestOnePermitPerBriefing:
    def test_an_in_person_go_releases_the_permit_and_says_so(self, client):
        assert post(client, in_person(record("go", open_steps=STEPS))).status_code == 201
        permit = only(client)
        assert (permit["status"], permit["inPerson"]) == ("released", True)
        assert [s["id"] for s in permit["openSteps"]] == STEPS
        page = client.get("/").text
        assert "checked the worker in person" in page and "No AI check was made" in page
        assert REASON not in page  # the supervisor's reason is never shown

    def test_a_record_without_the_field_is_not_in_person(self, client):
        post(client, record("go"))
        assert only(client)["inPerson"] is False
        assert "in person" not in client.get("/").text


class TestAGroupedPermit:
    def test_the_slot_shows_checked_in_person_with_its_open_steps(self, client):
        post(client, in_person(worker(1, open_steps=STEPS, crew=2)))
        post(client, worker(2, crew=2))
        permit = only(client)
        one, two = permit["slots"]
        assert (one["inPerson"], one["openSteps"][0]["id"], two["inPerson"]) == (True, "s1", False)
        assert (permit["status"], permit["inPerson"]) == ("released", True)
        page = client.get("/").text
        assert "Go · checked in person" in page and "Worker 1 was checked in person" in page
        assert "Use the tag line" in page  # s4's text: the open steps are listed
        assert REASON not in page

    def test_a_re_brief_by_the_ai_check_replaces_the_in_person_slot(self, client):
        post(client, in_person(worker(1, open_steps=STEPS, crew=2)))
        post(client, worker(1, crew=2, bid="b_zzzzzzzzzzzz", at="2026-10-14T11:30:00.000Z"))
        assert (only(client)["slots"][0]["inPerson"], only(client)["inPerson"]) == (False, False)


@pytest.mark.parametrize("value", ["true", 1, "yes", None])
def test_only_a_json_boolean_is_read(client, value):
    payload = record("go")
    payload["decision"]["inPerson"] = value
    response = post(client, payload)
    assert response.status_code == 422 and response.json()["error"]["code"] == "bad_record"
    assert client.get("/api/permits").json() == {"permits": []}
