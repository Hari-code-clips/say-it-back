"""The backend's signed webhook against the real permit-to-work stub (integrations/ptw-stub), in one
process over ASGI: a change to the signature, the record or the stub's checks on either side fails
here. The stub needs only FastAPI and pydantic, which the backend has too."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.fakes import tone_wav
from tests.flow_support import round_1_scenario
from tests.helpers import api_client, drive_to_round, make_app, post_check

STUB = Path(__file__).resolve().parents[2] / "integrations" / "ptw-stub"
SECRET = "contract-test-secret"
URL = "http://ptw.internal/webhook"

pytestmark = pytest.mark.skipif(
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


def backend(settings, stub, secret=SECRET):
    s = settings.with_overrides(webhook_url=URL, webhook_secret=secret)
    transport = httpx.ASGITransport(app=stub)
    app, *_ = make_app(s, round_1_scenario(), webhook_transport=transport)
    return api_client(app)


def test_a_no_go_holds_a_permit_with_what_was_open_and_the_record_hash(settings, stub):
    client = backend(settings, stub)
    bid = drive_to_round(client)[0]
    post_check(client, bid, 1)
    client.post(f"/api/briefings/{bid}/hazards")
    decided = client.post(
        f"/api/briefings/{bid}/decision", json={"value": "no_go", "by": "Sam"}
    ).json()
    (permit,) = TestClient(stub).get("/api/permits").json()["permits"]
    assert (permit["id"], permit["status"], permit["briefingId"]) == ("PTW-1", "held", bid)
    assert [s["id"] for s in permit["openSteps"]] == ["s2", "s3"] and permit["openHazards"] == [
        "h1"
    ]
    assert permit["recordHash"] == decided["recordHash"]
    assert permit["recordHash"] == client.get(f"/api/briefings/{bid}/verify").json()["recordHash"]
    assert permit["decidedAt"] == decided["decision"]["at"] and "decidedBy" not in permit
    assert permit["demo"] is None


def test_a_go_releases_one(settings, stub):
    client = backend(settings, stub)
    bid = drive_to_round(client)[0]
    post_check(client, bid, 1)
    client.post(
        f"/api/briefings/{bid}/decision", json={"value": "go", "reason": "Checked in person."}
    )
    (permit,) = TestClient(stub).get("/api/permits").json()["permits"]
    assert permit["status"] == "released" and permit["openHazards"] == []


def test_a_backend_with_another_secret_gets_no_permit(settings, stub):
    client = backend(settings, stub, secret="not-the-shared-one")
    bid = drive_to_round(client)[0]
    client.post(f"/api/briefings/{bid}/decision", json={"value": "no_go"})
    assert TestClient(stub).get("/api/permits").json() == {"permits": []}


def test_a_decision_on_sample_answers_gives_a_demo_permit(settings, stub):
    import json

    client = backend(settings, stub)
    bid = drive_to_round(client)[0]
    files = [("q1", ("q1.wav", tone_wav(), "audio/wav")),
             ("meta", (None, json.dumps({"mode": "turn", "sampleAnswers": ["q1"]})))]  # fmt: skip
    assert client.post(f"/api/briefings/{bid}/rounds/1/check", files=files).status_code == 200
    client.post(f"/api/briefings/{bid}/decision", json={"value": "no_go"})
    (permit,) = TestClient(stub).get("/api/permits").json()["permits"]
    assert permit["demo"] == "Demo: synthetic sample answers"
    assert permit["sampleAnswers"] == [{"round": 1, "questionId": "q1"}]


def test_v052_two_workers_on_one_permit_release_it_only_together(settings, stub):
    """API v0.5.2: each worker's briefing names the permit and its slot; the stub releases the
    permit when both have a Go, and each slot carries its own briefing's record hash."""
    from tests.helpers import PANEL

    client = backend(settings, stub)
    hashes = {}
    for slot in (1, 2):
        body = {**PANEL, "permit": {"ref": "ptw-9", "crewSize": 2, "slot": slot}}
        bid = drive_to_round(client, body)[0]
        post_check(client, bid, 1)
        decided = client.post(
            f"/api/briefings/{bid}/decision", json={"value": "go", "reason": "Checked in person."}
        ).json()
        hashes[slot] = (bid, decided["recordHash"])
        (permit,) = TestClient(stub).get("/api/permits").json()["permits"]
        assert permit["status"] == ("held" if slot == 1 else "released")
    assert (permit["ref"], permit["crewSize"], permit["verified"], permit["waiting"]) == (
        "ptw-9", 2, 2, [],
    )  # fmt: skip
    assert {s["slot"]: (s["briefingId"], s["recordHash"]) for s in permit["slots"]} == hashes
