"""API v0.5.2, "Permit-to-work grouping": a decision record with `permit` is filed under that
permit ref, one entry per worker slot, and the permit is released only when every slot 1..crewSize
holds a Go. A re-brief replaces its slot; a different crewSize is 409 crew_mismatch and changes
nothing; a record without `permit` keeps the per-briefing permit. Both stores, the same rules."""

from __future__ import annotations

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from ptw_stub.app import create_app
from ptw_stub.firestore_book import PERMITS, group_id
from ptw_stub.permits import CrewMismatch, PermitBook, parse_record
from tests.fake_firestore import FakeBackedBook, FakeFirestore
from tests.test_stub import NOW, SECRET, post, record

EARLY, LATE = "2026-10-14T10:00:00.000Z", "2026-10-14T11:30:00.000Z"


def worker(slot, value="go", *, ref="PTW-123", crew=3, bid=None, at=EARLY, **extra):
    """The decision record of worker `slot` on permit `ref`."""
    bid = bid or f"b_{'abcdef'[slot - 1] * 12}"
    permit = {"ref": ref, "crewSize": crew, "slot": slot}
    return record(
        value, bid=bid, permit=permit, decidedAt=at, recordHash=f"{slot:02d}" * 32, **extra
    )


@pytest.fixture(params=["memory", "firestore"])
def make(request):
    """Instances of the stub over one shared store: the memory book in one process, or a fake
    Firestore that two Cloud Run instances share."""
    fake, book = FakeFirestore(), PermitBook()

    def instance() -> TestClient:
        store = FakeBackedBook(fake) if request.param == "firestore" else book
        return TestClient(create_app(secret=SECRET, clock=lambda: NOW, book=store))

    instance.kind = request.param
    instance.fake = fake
    return instance


def only(client):
    (permit,) = client.get("/api/permits").json()["permits"]
    return permit


class TestOnePermitManyWorkers:
    def test_held_until_every_worker_has_a_go(self, make):
        client = make()
        first = post(client, worker(1))
        assert first.status_code == 201 and first.json()["created"] is True
        p = only(client)
        assert (p["ref"], p["crewSize"], p["status"]) == ("PTW-123", 3, "held")
        assert (p["verified"], p["waiting"]) == (1, [2, 3])
        assert post(client, worker(2)).status_code == 200
        assert (only(client)["verified"], only(client)["waiting"]) == (2, [3])
        post(client, worker(3))
        p = only(client)
        assert (p["status"], p["verified"], p["waiting"], p["decision"]) == (
            "released",
            3,
            [],
            "go",
        )
        assert [s["slot"] for s in p["slots"]] == [1, 2, 3]

    def test_a_no_go_holds_the_permit(self, make):
        client = make()
        post(client, worker(1))
        post(client, worker(2, "no_go", open_steps=["s4"]))
        post(client, worker(3))
        p = only(client)
        assert (p["status"], p["verified"], p["waiting"]) == ("held", 2, [2])
        assert p["openSteps"] == [
            {"slot": 2, "id": "s4", "text": "Use the tag line <never your hand>"}
        ]

    def test_a_re_brief_replacing_a_no_go_with_a_go_releases_the_permit(self, make):
        client = make()
        post(client, worker(1))
        post(client, worker(2, "no_go", open_steps=["s4"]))
        post(client, worker(3))
        assert only(client)["status"] == "held"
        rebrief = post(client, worker(2, bid="b_zzzzzzzzzzzz", at=LATE))
        assert rebrief.status_code == 200
        p = only(client)
        assert (p["status"], p["verified"], p["waiting"], p["openSteps"]) == ("released", 3, [], [])
        assert next(s for s in p["slots"] if s["slot"] == 2)["briefingId"] == "b_zzzzzzzzzzzz"

    def test_an_older_decision_arriving_late_does_not_undo_a_re_brief(self, make):
        client = make()
        post(client, worker(1, crew=2))
        post(client, worker(2, crew=2, bid="b_zzzzzzzzzzzz", at=LATE))
        post(client, worker(2, "no_go", crew=2, at=EARLY))  # a retried, older webhook
        assert only(client)["status"] == "released"

    def test_a_repeat_post_for_the_same_briefing_changes_nothing(self, make):
        client = make()
        post(client, worker(1, crew=2))
        before = only(client)
        again = post(client, worker(1, "no_go", crew=2))
        assert again.status_code == 200 and again.json()["created"] is False
        assert only(client) == before

    def test_the_ref_matches_case_insensitively_and_keeps_its_first_spelling(self, make):
        client = make()
        post(client, worker(1, ref="ptw-123", crew=2))
        post(client, worker(2, ref="PTW-123 ", crew=2))
        p = only(client)
        assert (p["ref"], p["status"]) == ("ptw-123", "released")

    def test_a_crew_size_that_differs_is_409_and_changes_nothing(self, make):
        client = make()
        post(client, worker(1, crew=3))
        before = only(client)
        response = post(client, worker(2, crew=4))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "crew_mismatch"
        assert only(client) == before

    def test_two_permits_are_two_cards(self, make):
        client = make()
        post(client, worker(1, ref="PTW-1", crew=1))
        post(client, worker(1, ref="PTW-2", crew=1, bid="b_qqqqqqqqqqqq"))
        permits = client.get("/api/permits").json()["permits"]
        assert [p["ref"] for p in permits] == ["PTW-2", "PTW-1"]


class TestWhatIsServed:
    def test_the_slots_carry_exactly_the_contract_fields_and_no_name(self, make):
        client = make()
        post(client, worker(1))
        text = client.get("/api/permits").text
        (slot,) = only(client)["slots"]
        assert set(slot) == {
            "slot", "decision", "briefingId", "recordHash", "decidedAt",
            "openSteps", "openHazards", "goWithOpenSteps", "inPerson",  # inPerson: 2026-10-17
        }  # fmt: skip
        assert "Sam" not in text and "decidedBy" not in text and "decided_by" not in text

    def test_a_permit_block_with_another_field_is_refused(self, make):
        client = make()
        payload = worker(1)
        payload["permit"]["workerName"] = "Ravi"
        response = post(client, payload)
        assert response.status_code == 422 and response.json()["error"]["code"] == "bad_record"
        assert client.get("/api/permits").json() == {"permits": []}

    @pytest.mark.parametrize(
        "permit",
        [{"ref": "PTW 1", "crewSize": 2, "slot": 1}, {"ref": "PTW-1", "crewSize": 2, "slot": 3},
         {"ref": "PTW-1", "crewSize": 7, "slot": 1}, {"ref": "PTW-1", "crewSize": "2", "slot": 1}],
    )  # fmt: skip
    def test_a_malformed_permit_is_422(self, make, permit):
        assert post(make(), {**record(), "permit": permit}).status_code == 422

    def test_the_legacy_path_is_unchanged(self, make):
        client = make()
        first = post(client, record("go"))
        assert first.status_code == 201
        p = only(client)
        assert (p["id"], p["status"], p["ref"], p["crewSize"], p["verified"]) == (
            "PTW-1", "released", None, None, None,
        )  # fmt: skip
        assert (p["waiting"], p["slots"]) == ([], [])


class TestTheBoard:
    def test_a_grouped_card_counts_the_workers_and_names_none(self, make):
        client = make()
        post(client, worker(1))
        post(client, worker(2, "no_go", open_steps=["s4"]))
        html = client.get("/").text
        assert "PTW-123" in html and "2 of 3 workers verified" not in html
        assert "1 of 3 workers verified · held" in html
        assert "Worker 1" in html and "Worker 2" in html and "Worker 3" in html
        assert "No decision yet" in html and "Waiting on workers 2 and 3." in html
        assert "Sam" not in html
        post(client, worker(3))
        post(client, worker(2, bid="b_zzzzzzzzzzzz", at=LATE))
        html = client.get("/").text
        assert "3 of 3 workers verified · released" in html
        for word in ("approved", "passed", "understood"):
            assert word not in html.lower()

    def test_the_contract_line_two_of_three(self, make):
        client = make()
        post(client, worker(1))
        post(client, worker(2))
        assert "2 of 3 workers verified · held" in client.get("/").text

    def test_the_footer_names_the_store(self, make):
        html = make().get("/").text
        assert ("Kept in Firestore" if make.kind == "firestore" else "Kept in memory") in html


class TestFirestore:
    def test_one_document_per_permit_ref_and_a_ref_with_a_slash(self):
        fake = FakeFirestore()
        client = TestClient(create_app(secret=SECRET, clock=lambda: NOW, book=FakeBackedBook(fake)))
        post(client, worker(1, ref="ptw/2026/07", crew=2))
        post(client, worker(2, ref="PTW/2026/07", crew=2))
        groups = [k for k in fake.docs if k[0] == PERMITS]
        assert groups == [(PERMITS, group_id("PTW/2026/07"))]
        assert "/" not in group_id("PTW/2026/07").removeprefix("ref:")
        assert only(client)["status"] == "released"

    def test_concurrent_posts_for_different_slots_across_two_instances_all_land(self):
        fake = FakeFirestore()
        books = [FakeBackedBook(fake), FakeBackedBook(fake)]
        posts = [parse_record(json.dumps(worker(n, crew=6)).encode()) for n in range(1, 7)]

        async def race():
            return await asyncio.gather(*(books[i % 2].record(p) for i, p in enumerate(posts)))

        made = asyncio.run(race())
        assert sorted(created for _, created in made) == [False] * 5 + [True]
        (doc,) = [v for k, v in fake.docs.items() if k[0] == PERMITS]
        assert sorted(s["slot"] for s in doc["slots"]) == [1, 2, 3, 4, 5, 6]
        assert doc["status"] == "released"
        assert len({p.id for p, _ in made}) == 1  # one permit, one number

    def test_a_crew_mismatch_writes_nothing(self):
        fake = FakeFirestore()
        book = FakeBackedBook(fake)
        asyncio.run(book.record(parse_record(json.dumps(worker(1)).encode())))
        before = copy.deepcopy(fake.docs)
        with pytest.raises(CrewMismatch):
            asyncio.run(book.record(parse_record(json.dumps(worker(2, crew=2)).encode())))
        assert fake.docs == before


class TestAGoGivenWithStepsOpen:
    """The supervisor may give Go with a step still "Ask again" (with a typed reason, in the
    record). An auditor reading the permit must see that, worker by worker, not "None open"."""

    def setup_permit(self, make):
        client = make()
        post(client, worker(1, crew=2, open_steps=["s4"]))  # Go, s4 still open
        post(client, worker(2, "no_go", crew=2, open_steps=["s1"], open_hazards=["h1"]))
        return client

    def test_each_slot_carries_what_was_open_at_its_decision(self, make):
        client = self.setup_permit(make)
        slots = {s["slot"]: s for s in only(client)["slots"]}
        assert slots[1]["goWithOpenSteps"] is True
        assert slots[1]["openSteps"] == [{"id": "s4", "text": "Use the tag line <never your hand>"}]
        assert slots[1]["openHazards"] == []
        assert slots[2]["goWithOpenSteps"] is False  # a No-go is not a Go with steps open
        assert slots[2]["openSteps"] == [{"id": "s1", "text": "Never stand or walk under the load"}]
        assert slots[2]["openHazards"] == ["h1"]

    def test_the_permit_lists_every_workers_open_steps_labelled(self, make):
        client = self.setup_permit(make)
        p = only(client)
        assert p["openSteps"] == [
            {"slot": 1, "id": "s4", "text": "Use the tag line <never your hand>"},
            {"slot": 2, "id": "s1", "text": "Never stand or walk under the load"},
        ]
        assert p["openHazards"] == ["h1 (worker 2)"]

    def test_a_released_permit_still_shows_the_go_given_with_a_step_open(self, make):
        client = self.setup_permit(make)
        post(client, worker(2, crew=2, bid="b_zzzzzzzzzzzz", at=LATE))  # re-brief: a clean Go
        p = only(client)
        assert p["status"] == "released"
        assert p["openSteps"] == [
            {"slot": 1, "id": "s4", "text": "Use the tag line <never your hand>"}
        ]
        html = client.get("/").text
        assert "None open" not in html.split("Open steps")[1].split("</dd>")[0]
        assert (
            "1 step open at decision" in html and "Use the tag line &lt;never your hand&gt;" in html
        )
        assert "the supervisor's reason is in the Say It Back record" in html
        assert "Worker 1 had a Go with a step still open" in html

    def test_a_clean_go_has_none(self, make):
        client = make()
        post(client, worker(1, crew=1))
        (slot,) = only(client)["slots"]
        assert (slot["goWithOpenSteps"], slot["openSteps"], slot["openHazards"]) == (False, [], [])
        assert "step open at decision" not in client.get("/").text

    def test_the_reason_text_never_reaches_the_board_or_the_api(self, make):
        client = self.setup_permit(make)
        # record() sends decision.reason "Checked in person.", as the backend's webhook does
        assert "Checked in person." not in client.get("/").text
        assert "Checked in person." not in client.get("/api/permits").text


def old_shape_permit() -> dict:
    """A grouped permit as the first v0.5.2 code persisted it: the aggregate saved from the slots
    as they were then (no open steps for a Go, status "released"), here contradicting them."""
    slot = {"briefing_id": "b_aaaaaaaaaaaa", "decided_by": "Sam", "decided_at": EARLY,
            "record_hash": "01" * 32, "received_at": "2026-10-15T09:00:00Z", "sample_answers": []}  # fmt: skip
    return {
        "id": "PTW-1", "status": "released", "briefing_id": "b_bbbbbbbbbbbb", "site_id": "sg",
        "task_id": "lifting-zone", "decision": "go", "decided_by": "Sam", "decided_at": EARLY,
        "open_steps": [], "open_hazards": [], "record_hash": "02" * 32,
        "received_at": "2026-10-15T09:05:00Z", "sample_answers": [],
        "ref": "PTW-0427", "crew_size": 3,
        "slots": [
            {**slot, "slot": 1, "decision": "go",
             "open_steps": [{"id": "s4", "text": "Use the tag line"}], "open_hazards": []},
            {**slot, "slot": 2, "briefing_id": "b_bbbbbbbbbbbb", "decision": "go",
             "record_hash": "02" * 32, "open_steps": [], "open_hazards": []},
        ],
    }  # fmt: skip


class TestAPermitPersistedByOlderCode:
    """The permit's own status, decision, open steps and hazards are derived from its slots when
    it is read, so a permit stored before a change displays by today's rules, with no migration."""

    def check(self, client):
        p = only(client)
        assert p["openSteps"] == [{"slot": 1, "id": "s4", "text": "Use the tag line"}]
        assert (p["status"], p["decision"], p["verified"], p["waiting"]) == (
            "held",
            "no_go",
            2,
            [3],
        )
        html = client.get("/").text
        assert 'Worker 1 · <span class="mono">s4</span> Use the tag line' in html
        assert "None open" not in html.split("Open steps")[1].split("</dd>")[0]

    def test_from_the_memory_stores_file(self, tmp_path):
        path = tmp_path / "permits.json"
        path.write_text(json.dumps({"permits": [old_shape_permit()]}))
        self.check(TestClient(create_app(secret=SECRET, clock=lambda: NOW, store_file=path)))

    def test_from_a_firestore_document(self):
        fake = FakeFirestore()
        fake.docs[(PERMITS, group_id("PTW-0427"))] = {**old_shape_permit(), "seq": 1}
        client = TestClient(create_app(secret=SECRET, clock=lambda: NOW, book=FakeBackedBook(fake)))
        self.check(client)

    def test_the_next_post_settles_it_for_good(self, tmp_path):
        path = tmp_path / "permits.json"
        path.write_text(json.dumps({"permits": [old_shape_permit()]}))
        client = TestClient(create_app(secret=SECRET, clock=lambda: NOW, store_file=path))
        post(client, worker(3, ref="ptw-0427", at=LATE))
        stored = json.loads(path.read_text())["permits"][0]
        assert stored["status"] == "released" and stored["open_steps"][0]["id"] == "s4"
