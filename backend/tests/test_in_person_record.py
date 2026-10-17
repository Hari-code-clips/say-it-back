"""2026-10-17, the in-person check outside the store: the JSON webhook record always carries
`decision.inPerson`, the Chat text says the check was in person, the CSV gains an `inPerson`
column, and the real permit-to-work stub releases the permit and shows the slot as checked in
person with its open steps, never the reason (build-notes/38-in-person-check.md)."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from sayitback.models import Decision
from sayitback.webhook import IN_PERSON_LINE, chat_payload, json_record
from tests.fakes import FakeTtsClient, tone_wav
from tests.flow_support import round_1_scenario
from tests.helpers import PANEL, api_client, drive_to_round, make_app, post_check
from tests.test_webhook import decided as decided_briefing

REASON = "Went through every step face to face; he showed me each one."
STUB = Path(__file__).resolve().parents[2] / "integrations" / "ptw-stub"
SECRET = "in-person-test-secret"
URL = "http://ptw.internal/webhook"


def in_person(b):
    assert b.decision is not None
    b.decision = Decision(**{**b.decision.model_dump(), "in_person": True})
    return b


class TestWebhook:
    def test_the_json_record_always_says_whether_the_check_was_in_person(self):
        assert json_record(in_person(decided_briefing()))["decision"]["inPerson"] is True
        assert json_record(decided_briefing())["decision"]["inPerson"] is False

    def test_the_chat_text_says_no_ai_check_was_made_only_for_an_in_person_check(self):
        assert IN_PERSON_LINE in chat_payload(in_person(decided_briefing()))["text"]
        assert IN_PERSON_LINE not in chat_payload(decided_briefing())["text"]
        assert "no AI check was made" in IN_PERSON_LINE


def rows(client) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(client.get("/api/export/briefings.csv").text)))


def test_the_csv_has_an_in_person_column(settings):
    app, *_ = make_app(
        settings.with_overrides(require_consent=True),
        round_1_scenario(),
        tts_client=FakeTtsClient(),
    )
    client = api_client(app)
    checked_in_person, _ = drive_to_round(client)
    client.post(f"/api/briefings/{checked_in_person}/rounds/1/consent", json={"given": False})
    client.post(
        f"/api/briefings/{checked_in_person}/decision", json={"value": "go", "reason": REASON}
    )
    by_ai, _ = drive_to_round(client)
    client.post(f"/api/briefings/{by_ai}/rounds/1/consent", json={"given": True})
    post_check(client, by_ai, 1, q1=tone_wav())
    client.post(f"/api/briefings/{by_ai}/decision", json={"value": "no_go"})
    undecided, _ = drive_to_round(client)
    found = {(r["briefingId"], r["inPerson"]) for r in rows(client)}
    assert found == {(checked_in_person, "true"), (by_ai, "false"), (undecided, "")}


pytestmark_stub = pytest.mark.skipif(
    not (STUB / "ptw_stub").is_dir(), reason="needs integrations/ptw-stub"
)


@pytest.fixture
def stub():
    sys.path.insert(0, str(STUB))
    try:
        from ptw_stub.app import create_app

        yield create_app(secret=SECRET)
    finally:
        sys.path.remove(str(STUB))


def backend(settings, stub):
    s = settings.with_overrides(webhook_url=URL, webhook_secret=SECRET, require_consent=True)
    app, *_ = make_app(s, webhook_transport=httpx.ASGITransport(app=stub))
    return api_client(app)


def in_person_go(client, body=None) -> tuple[str, dict]:
    bid, _ = drive_to_round(client, body)
    client.post(f"/api/briefings/{bid}/rounds/1/consent", json={"given": False})
    decided = client.post(f"/api/briefings/{bid}/decision", json={"value": "go", "reason": REASON})
    assert decided.status_code == 200, decided.text
    return bid, decided.json()


@pytestmark_stub
def test_the_stub_releases_the_permit_and_says_it_was_checked_in_person(settings, stub):
    client = backend(settings, stub)
    bid, decided = in_person_go(client)
    (permit,) = TestClient(stub).get("/api/permits").json()["permits"]
    assert (permit["status"], permit["briefingId"], permit["inPerson"]) == ("released", bid, True)
    assert [s["id"] for s in permit["openSteps"]] == decided["decision"]["openStepIds"]
    assert permit["recordHash"] == decided["recordHash"]
    page = TestClient(stub).get("/").text
    assert "checked the worker in person" in page and REASON not in page


@pytestmark_stub
def test_a_grouped_permit_shows_the_slot_as_checked_in_person_with_its_open_steps(settings, stub):
    client = backend(settings, stub)
    _, decided = in_person_go(
        client, {**PANEL, "permit": {"ref": "PTW-77", "crewSize": 2, "slot": 1}}
    )
    (permit,) = TestClient(stub).get("/api/permits").json()["permits"]
    (slot,) = permit["slots"]
    assert (slot["slot"], slot["decision"], slot["inPerson"]) == (1, "go", True)
    assert [s["id"] for s in slot["openSteps"]] == decided["decision"]["openStepIds"]
    assert (permit["status"], permit["waiting"]) == ("held", [2])
    page = TestClient(stub).get("/").text
    assert "Go · checked in person" in page and REASON not in page
