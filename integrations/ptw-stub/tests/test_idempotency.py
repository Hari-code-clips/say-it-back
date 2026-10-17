"""The stub as the reference e-permit system (Say It Back docs/EPERMIT_ADAPTER.md): it keeps each
post's Idempotency-Key with the permit it filed, answers the same key again with 409 `duplicate`
and changes nothing, refuses a key reused for another briefing, and serves a permit's status for a
site's systems to poll, never the supervisor's reason or name. Both stores, the same rules."""

from __future__ import annotations

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from ptw_stub.app import create_app
from ptw_stub.firestore_book import DELIVERIES
from ptw_stub.permits import Duplicate, PermitBook, parse_record
from tests.fake_firestore import FakeBackedBook, FakeFirestore
from tests.test_permit_groups import LATE, worker
from tests.test_stub import NOW, SECRET, record, signed

KEY = "sib-b_abcdefghijkl-a1a1a1a1a1a1a1a1"  # record("go")'s own key
OWN = object()  # deliver(): the key Say It Back derives from the record (security fixes B)


def own_key(payload) -> str:
    return f"sib-{payload['briefingId']}-{payload['recordHash'][:16]}"


@pytest.fixture(params=["memory", "firestore"])
def make(request, tmp_path):
    """Instances of the stub over one store: a memory book (with its file) or a fake Firestore."""
    fake, path = FakeFirestore(), tmp_path / "permits.json"

    def instance() -> TestClient:
        store = FakeBackedBook(fake) if request.param == "firestore" else PermitBook(path)
        return TestClient(create_app(secret=SECRET, clock=lambda: NOW, book=store))

    instance.fake = fake
    instance.kind = request.param
    return instance


def deliver(client, payload, key=OWN):
    body = json.dumps(payload).encode()
    key = own_key(payload) if key is OWN else key
    headers = signed(body) | ({"Idempotency-Key": key} if key is not None else {})
    return client.post("/webhook", content=body, headers=headers)


def permits(client):
    return client.get("/api/permits").json()["permits"]


class TestTheIdempotencyKey:
    def test_the_same_delivery_twice_is_a_duplicate_and_changes_nothing(self, make):
        client = make()
        first = deliver(client, record("go"))
        assert first.status_code == 201
        again = deliver(client, record("go"))
        assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate"
        assert again.json()["permit"] == first.json()["permit"] and len(permits(client)) == 1

    def test_a_key_is_kept_across_instances(self, make):
        assert deliver(make(), record("go")).status_code == 201
        assert deliver(make(), record("go")).status_code == 409  # a new instance, the same store

    def test_a_key_reused_for_another_briefing_is_refused(self, make):
        """Security fixes B: it is not that briefing's own key, so it is a mismatch now; a key held
        for another briefing (stored before the check) is still refused as reused (test_key_binding)."""
        client = make()
        deliver(client, record("go"))
        reused = deliver(client, record("go", bid="b_bbbbbbbbbbbb"), key=KEY)
        assert reused.status_code == 422 and reused.json()["error"]["code"] == "idempotency_key_mismatch"
        assert [p["briefingId"] for p in permits(client)] == ["b_abcdefghijkl"]

    @pytest.mark.parametrize("bad", ["short", "x" * 129, "has space here", "sl/ash/1234"])
    def test_a_malformed_key_is_refused(self, make, bad):
        response = deliver(make(), record("go"), key=bad)
        assert response.status_code == 422 and response.json()["error"]["code"] == "bad_idempotency_key"

    def test_without_a_key_a_repeat_post_returns_its_permit_as_before(self, make):
        client = make()
        assert deliver(client, record("go"), key=None).status_code == 201
        assert deliver(client, record("go"), key=None).status_code == 200

    def test_a_retried_delivery_never_undoes_a_re_brief(self, make):
        client = make()
        deliver(client, worker(1, "go"))
        rebrief = worker(1, "no_go", bid="b_zzzzzzzzzzzz", at=LATE, open_steps=["s4"])
        assert deliver(client, rebrief).status_code == 200
        assert deliver(client, worker(1, "go")).status_code == 409
        (permit,) = permits(client)
        assert permit["slots"][0]["decision"] == "no_go" and permit["verified"] == 0

    def test_the_duplicate_answer_names_the_permit(self):
        book = PermitBook()
        rec = parse_record(json.dumps(record("no_go")).encode())
        asyncio.run(book.record(rec, key=KEY))
        with pytest.raises(Duplicate) as dup:
            asyncio.run(book.record(rec, key=KEY))
        assert dup.value.permit.id == "PTW-1" and dup.value.permit.status == "held"


class TestTheStatusReadApi:
    def test_one_permit_by_id(self, make):
        client = make()
        deliver(client, worker(1, "go"), key=None)
        deliver(client, worker(2, "go"), key=None)
        response = client.get("/api/permits/PTW-1")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        permit = response.json()["permit"]
        assert (permit["ref"], permit["status"], permit["verified"], permit["waiting"]) == (
            "PTW-123", "held", 2, [3]
        )  # fmt: skip

    def test_it_answers_304_until_the_permit_changes(self, make):
        client = make()
        deliver(client, worker(1, "go"), key=None)
        etag = client.get("/api/permits/PTW-1").headers["etag"]
        assert client.get("/api/permits/PTW-1", headers={"If-None-Match": etag}).status_code == 304
        deliver(client, worker(2, "go"), key=None)
        changed = client.get("/api/permits/PTW-1", headers={"If-None-Match": etag})
        assert changed.status_code == 200 and changed.headers["etag"] != etag

    def test_an_unknown_permit_is_404(self, make):
        response = make().get("/api/permits/PTW-99")
        assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"

    def test_the_list_can_be_narrowed_to_one_permit_ref(self, make):
        client = make()
        deliver(client, worker(1, ref="Crane-7"), key=None)
        deliver(client, record("go", bid="b_bbbbbbbbbbbb"), key=None)
        assert [p["ref"] for p in client.get("/api/permits?ref=crane-7").json()["permits"]] == ["Crane-7"]
        assert client.get("/api/permits?ref=nope").json() == {"permits": []}
        assert len(permits(client)) == 2

    def test_no_route_shows_the_supervisors_reason_or_name(self, make):
        client = make()
        deliver(client, worker(1, "go", open_steps=["s4"]))
        deliver(client, worker(1, "go"))
        pages = [client.get(p).text for p in ("/", "/api/permits", "/api/permits/PTW-1", "/api/permits?ref=PTW-123")]
        for page in pages:
            assert "Checked in person." not in page and "Sam" not in page


class TestOnFirestoreAcrossInstances:
    def test_two_instances_racing_one_key_file_one_permit(self):
        fake = FakeFirestore()
        rec = parse_record(json.dumps(record("go")).encode())

        async def race():
            books = (FakeBackedBook(fake), FakeBackedBook(fake))
            return await asyncio.gather(
                *(b.record(rec, key=KEY) for b in books), return_exceptions=True
            )

        results = asyncio.run(race())
        assert sorted(type(r).__name__ for r in results) == ["Duplicate", "tuple"]
        assert fake.docs[(DELIVERIES, KEY)] == {"briefingId": "b_abcdefghijkl", "permit": "b_abcdefghijkl"}
        assert len([k for k in fake.docs if k[0] == "permits"]) == 1

    def test_a_duplicate_writes_nothing(self):
        fake = FakeFirestore()
        client = TestClient(create_app(secret=SECRET, clock=lambda: NOW, book=FakeBackedBook(fake)))
        deliver(client, worker(2))
        before = copy.deepcopy(fake.docs)
        assert deliver(client, worker(2)).status_code == 409
        assert fake.docs == before
