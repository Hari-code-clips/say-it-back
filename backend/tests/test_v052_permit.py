"""API v0.5.2, "Permit-to-work grouping": a briefing may name the permit-to-work it checks and which
worker on it this is (`permit` = {ref, crewSize, slot}). The slot number is the only per-worker
field, never a name, ID or nationality (Rule 6). The permit is immutable, bound by the `created`
chain event, and carried in the list, the CSV export, the webhook record and the Chat text."""

from __future__ import annotations

import csv
import io
import json

import pytest

from sayitback.models import Briefing, PermitLink
from sayitback.webhook import chat_payload, json_record
from tests.helpers import PANEL, api_client, drive_to_round, error_of, make_app
from tests.test_webhook import decided

PERMIT = {"ref": "PTW-123", "crewSize": 3, "slot": 2}


@pytest.fixture
def client(settings):
    app, *_ = make_app(settings)
    return api_client(app)


def create(client, permit=None, **extra):
    body = {**PANEL, **extra}
    if permit is not None:
        body["permit"] = permit
    return client.post("/api/briefings", json=body)


class TestTheBlock:
    def test_a_briefing_carries_its_permit(self, client):
        created = create(client, {"ref": "  PTW-123 ", "crewSize": 3, "slot": 2})
        assert created.status_code == 200, created.text
        assert created.json()["permit"] == PERMIT  # trimmed, stored as typed
        bid = created.json()["id"]
        assert client.get(f"/api/briefings/{bid}").json()["permit"] == PERMIT

    def test_without_a_permit_it_is_null_and_nothing_else_changes(self, client):
        body = create(client).json()
        assert body["permit"] is None
        assert body["status"] == "draft"

    @pytest.mark.parametrize(
        "permit",
        [
            {"ref": "", "crewSize": 1, "slot": 1},
            {"ref": "   ", "crewSize": 1, "slot": 1},
            {"ref": "P" * 33, "crewSize": 1, "slot": 1},
            {"ref": "PTW 12", "crewSize": 1, "slot": 1},
            {"ref": "PTW#12", "crewSize": 1, "slot": 1},
            {"ref": "PTWü", "crewSize": 1, "slot": 1},
            {"ref": 12, "crewSize": 1, "slot": 1},
            {"ref": "PTW-1", "crewSize": 0, "slot": 1},
            {"ref": "PTW-1", "crewSize": 7, "slot": 1},
            {"ref": "PTW-1", "crewSize": "3", "slot": 1},
            {"ref": "PTW-1", "crewSize": True, "slot": 1},
            {"ref": "PTW-1", "crewSize": 2.5, "slot": 1},
            {"ref": "PTW-1", "crewSize": 3, "slot": 0},
            {"ref": "PTW-1", "crewSize": 3, "slot": 4},
            {"ref": "PTW-1", "crewSize": 3},
            {"crewSize": 3, "slot": 1},
            "PTW-1",
        ],
    )
    def test_anything_else_is_422(self, client, permit):
        assert error_of(create(client, permit)) == (422, "validation_error")

    def test_the_longest_and_every_allowed_character(self, client):
        ref = "Az09._/-" * 4
        assert create(client, {"ref": ref, "crewSize": 6, "slot": 6}).json()["permit"]["ref"] == ref

    @pytest.mark.parametrize("extra", ["workerName", "name", "workerId", "nationality", "phone"])
    def test_rule_6_the_block_carries_no_other_field(self, client, extra):
        response = create(client, {**PERMIT, extra: "Ravi"})
        assert error_of(response) == (422, "validation_error")
        assert "Ravi" not in response.text

    def test_the_model_itself_refuses_extra_keys(self):
        with pytest.raises(ValueError):
            PermitLink.model_validate({**PERMIT, "workerName": "Ravi"})
        assert set(PermitLink.model_validate(PERMIT).wire()) == {"ref", "crewSize", "slot"}

    def test_it_cannot_be_edited_after_creation(self, client):
        bid = create(client, PERMIT).json()["id"]
        patched = client.patch(
            f"/api/briefings/{bid}",
            json={
                "instruction": "New words.",
                "permit": {"ref": "OTHER", "crewSize": 1, "slot": 1},
            },
        )
        assert patched.status_code == 200 and patched.json()["permit"] == PERMIT


class TestTheRecordChain:
    def test_the_created_event_binds_the_permit_and_verify_checks_it(self, client, settings):
        bid = create(client, PERMIT).json()["id"]
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True
        path = next(settings.data_dir.rglob(f"{bid}.json"))
        stored = json.loads(path.read_text())
        assert stored["events"][0]["data"]["permit"] == PERMIT
        stored["permit"]["slot"] = 1  # someone edits the stored record
        path.write_text(json.dumps(stored))
        report = client.get(f"/api/briefings/{bid}/verify").json()
        created_seq = stored["events"][0]["seq"]
        assert (report["ok"], report["brokenAt"], report["reason"]) == (
            False,
            created_seq,
            "created_mismatch",
        )

    def test_a_permit_added_to_a_record_made_without_one_is_found(self, client, settings):
        bid = create(client).json()["id"]
        path = next(settings.data_dir.rglob(f"{bid}.json"))
        stored = json.loads(path.read_text())
        assert "permit" not in stored["events"][0]["data"]  # the v0.4 event shape, unchanged
        stored["permit"] = PERMIT
        path.write_text(json.dumps(stored))
        assert client.get(f"/api/briefings/{bid}/verify").json()["reason"] == "created_mismatch"

    def test_a_record_without_a_permit_still_verifies(self, client):
        bid = create(client).json()["id"]
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True


class TestWhereItShows:
    def test_the_list(self, client):
        create(client, PERMIT)
        create(client)
        items = client.get("/api/briefings").json()["items"]
        assert sorted(json.dumps(i["permit"]) for i in items) == sorted(
            [json.dumps(PERMIT), "null"]
        )

    def test_the_csv_export(self, client):
        # rows are per step: drive both to confirmed steps
        drive_to_round(client, {**PANEL, "permit": {"ref": "-12", "crewSize": 2, "slot": 1}})
        drive_to_round(client)  # a formula-looking ref above
        rows = list(csv.DictReader(io.StringIO(client.get("/api/export/briefings.csv").text)))
        assert {"permitRef", "crewSize", "workerSlot"} <= set(rows[0])
        with_permit = [r for r in rows if r["permitRef"]]
        without = [r for r in rows if not r["permitRef"]]
        assert with_permit and without
        assert {(r["permitRef"], r["crewSize"], r["workerSlot"]) for r in with_permit} == {
            ("'-12", "2", "1")
        }
        assert {(r["crewSize"], r["workerSlot"]) for r in without} == {("", "")}

    def test_the_webhook_record_and_the_chat_text(self):
        b = decided().model_copy(update={"permit": PermitLink.model_validate(PERMIT)})
        assert json_record(b)["permit"] == PERMIT
        assert "Permit `PTW-123`, worker 2 of 3" in chat_payload(b)["text"]
        plain = decided()
        assert json_record(plain)["permit"] is None
        assert "Permit" not in chat_payload(plain)["text"]

    def test_an_underscore_in_a_ref_is_not_chat_markup(self):
        b = decided().model_copy(
            update={
                "permit": PermitLink.model_validate({"ref": "PTW_1_2", "crewSize": 1, "slot": 1})
            }
        )
        assert "`PTW_1_2`" in chat_payload(b)["text"]

    def test_a_stored_briefing_round_trips(self):
        b = decided().model_copy(update={"permit": PermitLink.model_validate(PERMIT)})
        again = Briefing.model_validate(b.stored())
        assert again.permit == b.permit
