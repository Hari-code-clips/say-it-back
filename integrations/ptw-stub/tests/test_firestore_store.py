"""PTW_STORE=firestore: the permit board survives a new instance. One permit per briefing, numbers
given out once across instances, newest first, over a fake Firestore that interleaves like the real
one (tests/fake_firestore.py)."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from ptw_stub.app import create_app
from ptw_stub.firestore_book import COUNTER, COUNTERS, ORDER, PERMITS
from ptw_stub.permits import PermitBook, parse_record
from tests.fake_firestore import FakeBackedBook, FakeFirestore
from tests.test_stub import NOW, SECRET, post, record


def instance(fake: FakeFirestore) -> TestClient:
    """One Cloud Run instance of the stub over the shared database."""
    return TestClient(create_app(secret=SECRET, clock=lambda: NOW, book=FakeBackedBook(fake)))


def as_record(**kw):
    return parse_record(json.dumps(record(**kw)).encode())


class TestTheBoardSurvivesANewInstance:
    def test_permits_are_stored_by_briefing_id_and_listed_newest_first(self):
        fake = FakeFirestore()
        client = instance(fake)
        post(client, record("go", bid="b_aaaaaaaaaaaa"))
        post(client, record("no_go", bid="b_bbbbbbbbbbbb", open_steps=["s4"]))
        permits = client.get("/api/permits").json()["permits"]
        assert [(p["id"], p["status"], p["briefingId"]) for p in permits] == [
            ("PTW-2", "held", "b_bbbbbbbbbbbb"),
            ("PTW-1", "released", "b_aaaaaaaaaaaa"),
        ]
        assert set(fake.docs) == {
            (PERMITS, "b_aaaaaaaaaaaa"),
            (PERMITS, "b_bbbbbbbbbbbb"),
            (COUNTERS, COUNTER),
        }
        assert fake.docs[(COUNTERS, COUNTER)] == {"issued": 2}
        assert (PERMITS, "seq", True) in fake.orders  # a single-field order: no composite index

    def test_a_new_instance_shows_the_same_board_and_numbers_on(self):
        fake = FakeFirestore()
        post(instance(fake), record("go", bid="b_aaaaaaaaaaaa"))
        fresh = instance(fake)  # scaled to zero and back, or a second instance
        assert [p["id"] for p in fresh.get("/api/permits").json()["permits"]] == ["PTW-1"]
        assert "PTW-1" in fresh.get("/").text
        post(fresh, record("no_go", bid="b_bbbbbbbbbbbb"))
        assert [p["id"] for p in fresh.get("/api/permits").json()["permits"]] == ["PTW-2", "PTW-1"]
        assert fresh.get("/healthz").json() == {
            "ok": True,
            "signed": True,
            "store": "firestore",
            "permits": 2,
        }

    def test_a_repeat_post_returns_the_permit_it_has(self):
        fake = FakeFirestore()
        first = post(instance(fake), record("go")).json()["permit"]
        again = post(instance(fake), record("no_go"))
        assert again.status_code == 200 and again.json() == {"permit": first, "created": False}
        assert fake.docs[(COUNTERS, COUNTER)] == {"issued": 1}

    def test_the_deciders_name_is_kept_in_the_record_but_never_served(self):
        fake = FakeFirestore()
        client = instance(fake)
        post(client, record("no_go"))
        assert fake.docs[(PERMITS, "b_abcdefghijkl")]["decided_by"] == "Sam"
        assert "Sam" not in client.get("/api/permits").text and "Sam" not in client.get("/").text


class TestConcurrentPosts:
    def test_two_instances_never_give_out_the_same_number(self):
        fake = FakeFirestore()
        books = [FakeBackedBook(fake), FakeBackedBook(fake)]
        bids = [f"b_{c * 12}" for c in "abcdefgh"]

        async def race():
            posts = (books[i % 2].record(as_record(bid=bid)) for i, bid in enumerate(bids))
            return await asyncio.gather(*posts)

        made = asyncio.run(race())
        numbers = sorted(int(p.id.removeprefix("PTW-")) for p, created in made if created)
        assert numbers == list(range(1, len(bids) + 1))
        assert fake.docs[(COUNTERS, COUNTER)] == {"issued": len(bids)}

    def test_a_retried_post_racing_the_first_makes_one_permit(self):
        fake = FakeFirestore()

        async def race():
            return await asyncio.gather(
                FakeBackedBook(fake).record(as_record(value="go")),
                FakeBackedBook(fake).record(as_record(value="go")),
            )

        made = asyncio.run(race())
        assert sorted(created for _, created in made) == [False, True]
        assert made[0][0].id == made[1][0].id == "PTW-1"
        assert len([k for k in fake.docs if k[0] == PERMITS]) == 1


class TestPickingTheStore:
    def test_memory_is_the_default(self, monkeypatch):
        monkeypatch.delenv("PTW_STORE", raising=False)
        app = create_app(secret=SECRET)
        assert isinstance(app.state.book, PermitBook)
        assert TestClient(app).get("/healthz").json()["store"] == "memory"

    def test_firestore_is_picked_by_ptw_store(self, monkeypatch):
        fake_book = FakeBackedBook()
        monkeypatch.setenv("PTW_STORE", "Firestore")
        monkeypatch.setattr(
            "ptw_stub.firestore_book.FirestorePermitBook.from_env",
            classmethod(lambda cls: fake_book),
        )
        assert create_app(secret=SECRET).state.book is fake_book

    def test_an_unknown_store_stops_the_service_at_start_up(self, monkeypatch):
        monkeypatch.setenv("PTW_STORE", "redis")
        with pytest.raises(ValueError, match="PTW_STORE"):
            create_app(secret=SECRET)

    def test_memory_needs_no_firestore_client(self, monkeypatch):
        """google-cloud-firestore is imported only for PTW_STORE=firestore."""
        monkeypatch.setitem(sys.modules, "google.cloud.firestore", None)  # importing it now fails
        monkeypatch.delenv("PTW_STORE", raising=False)
        client = TestClient(create_app(secret=SECRET, clock=lambda: NOW))
        assert post(client, record()).status_code == 201
        monkeypatch.setenv("PTW_STORE", "firestore")
        with pytest.raises(ImportError):
            create_app(secret=SECRET)


class TestTheRealClient:
    """The calls the book makes exist on google-cloud-firestore's AsyncClient, with the same
    arguments the fake takes. Nothing here sends a request."""

    def test_the_book_builds_its_references_and_query_on_a_real_client(self):
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import firestore

        client = firestore.AsyncClient(project="ptw-test", credentials=AnonymousCredentials())
        ref = client.collection(PERMITS).document("b_abcdefghijkl")
        assert ref.path == f"{PERMITS}/b_abcdefghijkl"
        assert client.collection(COUNTERS).document(COUNTER).path == f"{COUNTERS}/{COUNTER}"
        field, direction = ORDER
        query = client.collection(PERMITS).order_by(field, direction=direction)  # the book's order
        assert direction == firestore.Query.DESCENDING
        assert hasattr(query, "stream") and hasattr(client.transaction(), "set")
        assert callable(firestore.async_transactional)
