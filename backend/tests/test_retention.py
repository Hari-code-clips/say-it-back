"""Privacy, 16 Oct: retention (`expireAt`, SIB_RETENTION_DAYS) and deletion (DELETE
/api/briefings/{id}) of briefing records (retention.py, API.md Deviations). Both stores: the local
one prunes on read; the Firestore one writes `expireAt` as a Timestamp for its TTL policy and reads
back the ISO string it was written from."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from sayitback import retention
from sayitback.caller import owner_hash
from sayitback.store import LocalStore, make_store
from tests.fake_firestore import FakeBackedStore
from tests.fakes import FakeTtsClient
from tests.helpers import (
    DEVICE,
    ORIGIN,
    OTHER_DEVICE,
    PANEL,
    api_client,
    error_of,
    make_app,
    run_sync,
)

CREATED = "2026-10-16T10:00:00.000Z"
PAST = "2001-01-01T00:00:00.000Z"


def record(bid: str = "b_aaaaaaaaaaaa", created: str = CREATED) -> dict:
    return {"id": bid, "createdAt": created, "owner": owner_hash(DEVICE), "status": "draft"}


class TestExpiry:
    def test_expire_at_is_created_at_plus_the_days(self):
        assert retention.expire_at(CREATED, 90) == "2027-01-14T10:00:00.000Z"
        assert retention.expire_at(CREATED, 0) is None

    def test_a_past_or_unreadable_expiry_has_expired_and_none_never_expires(self):
        assert retention.is_expired({"expireAt": PAST})
        assert retention.is_expired({"expireAt": "not a time"})
        assert not retention.is_expired({"expireAt": "2999-01-01T00:00:00.000Z"})
        assert not retention.is_expired({}) and not retention.is_expired(None)

    def test_make_store_passes_the_setting(self, settings):
        assert make_store(settings.with_overrides(retention_days=7)).retention_days == 7


class TestLocalStore:
    def test_a_new_record_carries_expire_at_and_every_update_keeps_it(self, tmp_path):
        store = LocalStore(tmp_path, retention_days=90)
        run_sync(store.create(record()))
        assert run_sync(store.get("b_aaaaaaaaaaaa"))["expireAt"] == "2027-01-14T10:00:00.000Z"
        # The repository rebuilds the dict on every change (without storage metadata it does not
        # know): the store keeps the expiry set at creation, and a change cannot move it.
        updated = run_sync(store.update("b_aaaaaaaaaaaa", lambda r: {"id": r["id"], "x": 1}))
        assert updated["expireAt"] == "2027-01-14T10:00:00.000Z"
        moved = run_sync(store.update("b_aaaaaaaaaaaa", lambda r: {**r, "expireAt": PAST}))
        assert moved["expireAt"] == "2027-01-14T10:00:00.000Z"

    def test_zero_days_keeps_records_with_no_expiry(self, tmp_path):
        store = LocalStore(tmp_path, retention_days=0)
        run_sync(store.create(record()))
        assert "expireAt" not in run_sync(store.get("b_aaaaaaaaaaaa"))

    def test_an_expired_record_is_deleted_when_it_is_read(self, tmp_path):
        store = LocalStore(tmp_path, retention_days=90)
        for bid in ("b_aaaaaaaaaaaa", "b_bbbbbbbbbbbb", "b_cccccccccccc"):
            run_sync(store.create(record(bid)))
        for bid in ("b_aaaaaaaaaaaa", "b_bbbbbbbbbbbb", "b_cccccccccccc"):
            path = tmp_path / "briefings" / f"{bid}.json"
            path.write_text(json.dumps({**record(bid), "expireAt": PAST}), "utf-8")
        assert run_sync(store.get("b_aaaaaaaaaaaa")) is None
        assert not (tmp_path / "briefings" / "b_aaaaaaaaaaaa.json").exists()
        assert run_sync(store.recent(10, owner_hash(DEVICE))) == []
        assert not (tmp_path / "briefings" / "b_bbbbbbbbbbbb.json").exists()
        with pytest.raises(KeyError):
            run_sync(store.update("b_cccccccccccc", lambda r: r))
        assert not (tmp_path / "briefings" / "b_cccccccccccc.json").exists()

    def test_delete_removes_the_file_and_a_missing_one_is_a_no_op(self, tmp_path):
        store = LocalStore(tmp_path)
        run_sync(store.create(record()))
        run_sync(store.delete("b_aaaaaaaaaaaa"))
        run_sync(store.delete("b_aaaaaaaaaaaa"))
        assert run_sync(store.get("b_aaaaaaaaaaaa")) is None


class TestFirestoreStore:
    """The ops builder's TTL policy deletes a document only when `expireAt` is a Timestamp."""

    def store(self) -> FakeBackedStore:
        store = FakeBackedStore()
        store.retention_days = 90
        return store

    def test_expire_at_is_stored_as_a_utc_datetime_and_read_back_as_the_iso_string(self):
        store = self.store()
        run_sync(store.create(record()))
        kept = store.fake.docs[("briefings", "b_aaaaaaaaaaaa")]["expireAt"]
        assert isinstance(kept, datetime) and kept.tzinfo is not None
        assert kept == datetime(2027, 1, 14, 10, 0, tzinfo=UTC)
        assert run_sync(store.get("b_aaaaaaaaaaaa"))["expireAt"] == "2027-01-14T10:00:00.000Z"

    def test_an_update_round_trip_keeps_both_forms(self):
        store = self.store()
        run_sync(store.create(record()))
        # As the repository does: the change rebuilds the dict without the storage metadata.
        rebuilt = {**record(), "status": "steps_proposed"}
        out = run_sync(store.update("b_aaaaaaaaaaaa", lambda r: rebuilt))
        assert out["expireAt"] == "2027-01-14T10:00:00.000Z"
        assert isinstance(store.fake.docs[("briefings", "b_aaaaaaaaaaaa")]["expireAt"], datetime)
        listed = run_sync(store.recent(5, owner_hash(DEVICE)))
        assert [(r["status"], r["expireAt"]) for r in listed] == [
            ("steps_proposed", "2027-01-14T10:00:00.000Z")
        ]

    def test_an_expired_document_the_ttl_has_not_removed_yet_is_gone(self):
        store = self.store()
        run_sync(store.create(record()))
        doc = store.fake.docs[("briefings", "b_aaaaaaaaaaaa")]
        doc["expireAt"] = datetime(2001, 1, 1, tzinfo=UTC)
        assert run_sync(store.get("b_aaaaaaaaaaaa")) is None
        assert run_sync(store.recent(5, owner_hash(DEVICE))) == []
        with pytest.raises(KeyError):
            run_sync(store.update("b_aaaaaaaaaaaa", lambda r: r))

    def test_delete_removes_the_document(self):
        store = self.store()
        run_sync(store.create(record()))
        run_sync(store.delete("b_aaaaaaaaaaaa"))
        assert ("briefings", "b_aaaaaaaaaaaa") not in store.fake.docs
        run_sync(store.delete("b_aaaaaaaaaaaa"))


class TestApi:
    def app(self, settings, days: int = 90):
        store = LocalStore(settings.data_dir, retention_days=days)
        app, *_ = make_app(settings, tts_client=FakeTtsClient(), store=store)
        return app

    def test_expire_at_is_storage_metadata_never_in_a_response(self, settings):
        client = api_client(self.app(settings))
        created = client.post("/api/briefings", json=PANEL).json()
        raw = json.loads((settings.data_dir / "briefings" / f"{created['id']}.json").read_text())
        assert raw["expireAt"] == retention.expire_at(created["createdAt"], 90)
        assert "expireAt" not in created
        assert "expireAt" not in client.get(f"/api/briefings/{created['id']}").json()
        client.patch(f"/api/briefings/{created['id']}", json={"instruction": "Lock it first."})
        raw = json.loads((settings.data_dir / "briefings" / f"{created['id']}.json").read_text())
        assert raw["expireAt"] == retention.expire_at(created["createdAt"], 90)

    def test_the_owner_deletes_a_record_at_once(self, settings):
        client = api_client(self.app(settings))
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        kept = settings.data_dir / "audio" / bid
        kept.mkdir(parents=True)
        (kept / "r1-q1.wav").write_bytes(b"RIFF")
        assert client.delete(f"/api/briefings/{bid}").json() == {"ok": True, "id": bid}
        assert error_of(client.get(f"/api/briefings/{bid}")) == (404, "not_found")
        assert client.get("/api/briefings").json()["items"] == []
        assert not kept.exists()
        assert error_of(client.delete(f"/api/briefings/{bid}")) == (404, "not_found")

    def test_another_caller_cannot_delete_it_and_gets_the_unknown_id_404(self, settings):
        app = self.app(settings)
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        assert error_of(api_client(app, OTHER_DEVICE).delete(f"/api/briefings/{bid}")) == (
            404,
            "not_found",
        )
        assert error_of(client.delete("/api/briefings/b_zzzzzzzzzzzz")) == (404, "not_found")
        assert error_of(client.delete("/api/briefings/..%2F..%2Fetc")) == (404, "not_found")
        assert client.get(f"/api/briefings/{bid}").status_code == 200
        assert api_client(app, None).delete(f"/api/briefings/{bid}").status_code == 401

    def test_a_browser_may_send_delete_cross_origin(self, settings):
        client = api_client(self.app(settings), None)
        preflight = client.options(
            "/api/briefings/b_aaaaaaaaaaaa",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "x-sib-device",
            },
        )
        assert preflight.status_code == 200
        assert "DELETE" in preflight.headers["access-control-allow-methods"]


class TestOutbox:
    """outbox.py keeps one delivery document per decided briefing (`outbox/{briefingId}`). It goes
    with the briefing when the owner deletes it, and it expires with it."""

    BID = "b_aaaaaaaaaaaa"
    EXPIRY = "2027-01-14T10:00:00.000Z"

    @staticmethod
    def doc(**extra: object) -> dict:
        return {"briefingId": "b_aaaaaaaaaaaa", "due": CREATED, "targets": [], **extra}

    def stores(self, tmp_path):
        local = LocalStore(tmp_path, retention_days=90)
        firestore = FakeBackedStore()
        firestore.retention_days = 90
        return {"local": local, "firestore": firestore}

    @pytest.mark.parametrize("kind", ["local", "firestore"])
    def test_a_new_outbox_document_takes_its_briefing_s_expiry_and_keeps_it(self, tmp_path, kind):
        store = self.stores(tmp_path)[kind]
        run_sync(store.create(record(self.BID)))
        made = run_sync(store.outbox_update(self.BID, lambda d: None if d else self.doc()))
        assert made["expireAt"] == self.EXPIRY
        # outbox.py rebuilds the document on each attempt; the expiry stays as it was set.
        settled = run_sync(store.outbox_update(self.BID, lambda d: self.doc(due="x")))
        assert (settled["due"], settled["expireAt"]) == ("x", self.EXPIRY)
        assert run_sync(store.outbox_get(self.BID))["expireAt"] == self.EXPIRY

    def test_on_firestore_the_outbox_expiry_is_a_timestamp_for_its_ttl_policy(self, tmp_path):
        store = self.stores(tmp_path)["firestore"]
        run_sync(store.create(record(self.BID)))
        run_sync(store.outbox_update(self.BID, lambda d: self.doc()))
        kept = store.fake.docs[("outbox", self.BID)]["expireAt"]
        assert kept == datetime(2027, 1, 14, 10, 0, tzinfo=UTC)

    @pytest.mark.parametrize("kind", ["local", "firestore"])
    def test_deleting_a_briefing_deletes_its_outbox_document(self, tmp_path, kind):
        store = self.stores(tmp_path)[kind]
        run_sync(store.create(record(self.BID)))
        run_sync(store.outbox_update(self.BID, lambda d: self.doc()))
        run_sync(store.delete(self.BID))
        assert run_sync(store.outbox_get(self.BID)) is None
        assert run_sync(store.get(self.BID)) is None

    def test_an_expired_local_briefing_takes_its_outbox_document_with_it(self, tmp_path):
        store = self.stores(tmp_path)["local"]
        run_sync(store.create(record(self.BID)))
        run_sync(store.outbox_update(self.BID, lambda d: self.doc()))
        path = tmp_path / "briefings" / f"{self.BID}.json"
        path.write_text(json.dumps({**record(self.BID), "expireAt": PAST}), "utf-8")
        assert run_sync(store.get(self.BID)) is None
        assert run_sync(store.outbox_get(self.BID)) is None

    def test_delete_over_http_removes_the_outbox_document(self, settings):
        store = LocalStore(settings.data_dir, retention_days=90)
        app, *_ = make_app(settings, tts_client=FakeTtsClient(), store=store)
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        run_sync(store.outbox_update(bid, lambda d: {**self.doc(), "briefingId": bid}))
        assert client.delete(f"/api/briefings/{bid}").status_code == 200
        assert run_sync(store.outbox_get(bid)) is None
