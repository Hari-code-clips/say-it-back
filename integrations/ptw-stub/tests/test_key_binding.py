"""Security fixes B, L3 (Say It Back build-notes/36-security-fixes-b.md): the reference receiver
binds a post's Idempotency-Key to its signed body. Say It Back's key is
`sib-<briefingId>-<first 16 hex of recordHash>`, both parts inside the signed record, so a key that
is not the record's own is refused with 422 `idempotency_key_mismatch` and changes nothing. A
replayed body can then no longer take the key a later briefing's delivery needs. A post without the
header behaves as before. Both stores, the same rules."""

from __future__ import annotations

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from ptw_stub.app import create_app
from ptw_stub.firestore_book import DELIVERIES
from ptw_stub.permits import KeyMismatch, PermitBook, parse_record, record_key
from tests.fake_firestore import FakeBackedBook, FakeFirestore
from tests.test_idempotency import deliver, own_key, permits
from tests.test_permit_groups import worker
from tests.test_stub import NOW, SECRET, record

A, B = "b_aaaaaaaaaaaa", "b_bbbbbbbbbbbb"


def decided(bid: str, value: str = "go") -> dict:
    return record(value, bid=bid, recordHash=("a" if bid == A else "b") * 64)


@pytest.fixture(params=["memory", "firestore"])
def make(request, tmp_path):
    fake, path = FakeFirestore(), tmp_path / "permits.json"

    def instance() -> TestClient:
        store = FakeBackedBook(fake) if request.param == "firestore" else PermitBook(path)
        return TestClient(create_app(secret=SECRET, clock=lambda: NOW, book=store))

    instance.fake, instance.path, instance.kind = fake, path, request.param
    return instance


def refused(response) -> bool:
    return response.status_code == 422 and response.json()["error"]["code"] == "idempotency_key_mismatch"


class TestTheKeyBelongsToTheBody:
    def test_the_records_own_key_is_taken_and_answered_as_before(self, make):
        client = make()
        assert deliver(client, decided(A)).status_code == 201
        again = deliver(client, decided(A))
        assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate"

    @pytest.mark.parametrize(
        "key",
        [
            "attacker-chosen-key-1",
            f"sib-{B}-{'b' * 16}",  # B's future key, carried by A's signed body
            f"sib-{A}-{'b' * 16}",  # A's id with another hash
            f"sib-{A}-{'a' * 15}",  # one hex short
            f"SIB-{A}-{'a' * 16}",
        ],
    )
    def test_any_other_key_is_422_and_files_nothing(self, make, key):
        client = make()
        assert refused(deliver(client, decided(A), key=key))
        assert permits(client) == []

    def test_a_replayed_body_cannot_squat_a_later_briefings_key(self, make):
        """The review's probe: A's signed body re-sent under B's key, then B's real delivery."""
        client = make()
        assert deliver(client, decided(A)).status_code == 201
        assert refused(deliver(client, decided(A), key=own_key(decided(B))))
        genuine = deliver(client, decided(B))
        assert genuine.status_code == 201, genuine.text
        assert sorted(p["briefingId"] for p in permits(client)) == [A, B]

    def test_a_grouped_permits_post_is_bound_the_same_way(self, make):
        client = make()
        assert refused(deliver(client, worker(1), key=own_key(worker(2))))
        assert deliver(client, worker(1)).status_code == 201

    def test_without_the_header_a_post_behaves_as_before(self, make):
        client = make()
        assert deliver(client, decided(A), key=None).status_code == 201
        assert deliver(client, decided(A), key=None).status_code == 200

    def test_a_key_held_for_another_briefing_from_before_the_check_is_still_refused(self, make):
        """A key stored by an older stub for another briefing still answers 422 reused."""
        client = make()
        assert deliver(client, decided(A)).status_code == 201
        taken = {"briefingId": A, "permit": A if make.kind == "firestore" else "PTW-1"}
        if make.kind == "firestore":
            make.fake.docs[(DELIVERIES, own_key(decided(B)))] = taken
        else:
            stored = json.loads(make.path.read_text("utf-8"))
            stored["deliveries"][own_key(decided(B))] = taken
            make.path.write_text(json.dumps(stored), "utf-8")
            client = make()  # a new instance reads the file
        reused = deliver(client, decided(B))
        assert reused.status_code == 422 and reused.json()["error"]["code"] == "idempotency_key_reused"


class TestInTheBooks:
    @pytest.mark.parametrize("kind", ["memory", "firestore"])
    def test_each_book_refuses_a_foreign_key_before_any_read_or_write(self, kind):
        fake = FakeFirestore()
        book = FakeBackedBook(fake) if kind == "firestore" else PermitBook()
        rec = parse_record(json.dumps(decided(A)).encode())
        before = copy.deepcopy(fake.docs)

        with pytest.raises(KeyMismatch):
            asyncio.run(book.record(rec, key=own_key(decided(B))))

        assert fake.docs == before and asyncio.run(book.newest_first()) == []

    def test_the_key_is_the_one_say_it_back_derives(self):
        rec = parse_record(json.dumps(decided(A)).encode())
        assert record_key(rec) == f"sib-{A}-{'a' * 16}"
