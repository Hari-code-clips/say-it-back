"""API v0.4, "Record chain" and endpoint 25: every state change appends one hash-chained event in the
same atomic update, and verify finds an edit to the stored record at the event that binds it.

The hashes here are recomputed from the formula in API.md, not with chain.py, so a change to the
formula on either side fails these tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import pytest

from sayitback import chain
from sayitback.caller import owner_hash
from sayitback.models import Briefing
from sayitback.repo import Repo
from sayitback.store import LocalStore
from tests.cap_support import over_http, script_for_open_steps
from tests.fake_firestore import FakeBackedStore
from tests.fakes import tone_wav
from tests.flow_support import ANSWER_1, ANSWER_2, round_1_scenario, round_2_answers
from tests.helpers import (
    DEVICE,
    PANEL,
    api_client,
    approve_round,
    drive_to_round,
    make_app,
    post_check,
    run_sync,
    seed_round,
)

ZEROS = "0" * 64
NOTE = "Stopped the lift and replaced the sling."
REASON = "Checked the lock in person."


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def full_briefing(client) -> str:
    """Every kind of event: created, an edit, extract, confirm, two rounds (each approved and
    judged), a voice hazard and its acknowledgement, and the decision."""
    bid = client.post("/api/briefings", json=PANEL).json()["id"]
    client.patch(f"/api/briefings/{bid}", json={"instruction": PANEL["instruction"] + " Now."})
    steps = client.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
    client.put(f"/api/briefings/{bid}/steps", json={"steps": steps})
    client.post(f"/api/briefings/{bid}/rounds", json={})
    approve_round(client, bid, 1, by="Sam")
    assert post_check(client, bid, 1, q1=tone_wav()).status_code == 200
    scenario = client.scenario
    script_for_open_steps(scenario)
    client.post(f"/api/briefings/{bid}/rounds", json={"supervisorNote": "again"})
    approve_round(client, bid, 2)
    round_2_answers(scenario)
    assert post_check(client, bid, 2, q3=tone_wav()).status_code == 200
    files = {"audio": ("h.wav", tone_wav(), "audio/wav")}
    assert client.post(f"/api/briefings/{bid}/hazards", files=files).status_code == 200
    client.post(f"/api/briefings/{bid}/hazards/h1/ack", json={"note": NOTE, "by": "Sam"})
    decided = client.post(
        f"/api/briefings/{bid}/decision", json={"value": "go", "reason": REASON, "by": "Sam"}
    )
    assert decided.status_code == 200, decided.text
    return bid


def build(settings, store=None):
    scenario = round_1_scenario()
    app, _rt, _llm, store = make_app(settings, scenario, store=store)
    client = api_client(app)
    client.scenario = scenario
    return client, store


@pytest.fixture
def local(settings):
    client, store = build(settings)
    return client, store, full_briefing(client)


@pytest.fixture
def firestore(settings):
    client, store = build(settings, FakeBackedStore())
    return client, store, full_briefing(client)


TYPES = [
    "created", "instruction_edited", "steps_proposed", "steps_confirmed",
    "round_created", "script_approved", "round_judged",
    "round_created", "script_approved", "round_judged",
    "hazard_raised", "hazard_acknowledged", "decided",
]  # fmt: skip


def seq_of(events, kind: str, n: int | None = None) -> int:
    return next(
        e["seq"] for e in events if e["type"] == kind and (n is None or e["data"].get("n") == n)
    )


class TestTheChain:
    def test_every_state_change_appends_its_event_in_order(self, local):
        client, _, bid = local
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        assert [e["type"] for e in events] == TYPES
        assert [e["seq"] for e in events] == list(range(1, len(TYPES) + 1))
        assert set(events[0]) == {"seq", "type", "at", "data", "prevHash", "hash"}

    def test_each_hash_links_to_the_previous_one_by_the_api_md_formula(self, local):
        client, _, bid = local
        briefing = client.get(f"/api/briefings/{bid}").json()
        prev = ZEROS
        for e in briefing["events"]:
            body = {k: e[k] for k in ("seq", "type", "at", "data")}
            assert e["prevHash"] == prev
            assert e["hash"] == sha(prev + "\n" + canon(body))
            prev = e["hash"]
        assert briefing["recordHash"] == prev

    def test_the_bound_digests_are_of_the_wire_forms(self, local):
        client, _, bid = local
        b = client.get(f"/api/briefings/{bid}").json()
        by_type = {}
        for e in b["events"]:
            by_type.setdefault(e["type"], []).append(e["data"])
        assert by_type["created"][0]["instructionSha256"] == sha(canon(PANEL["instruction"]))
        assert by_type["instruction_edited"][0]["instructionSha256"] == sha(canon(b["instruction"]))
        confirmed = by_type["steps_confirmed"][0]
        assert confirmed["stepsSha256"] == sha(canon(b["steps"])) and confirmed["stepsVersion"] == 1
        for i, rnd in enumerate(b["rounds"]):
            created, approved, judged = (
                by_type[k][i] for k in ("round_created", "script_approved", "round_judged")
            )
            assert created == {"n": rnd["n"], "kind": rnd["kind"], "stepIds": rnd["stepIds"],
                               "scriptSha256": sha(canon(rnd["script"]))}  # fmt: skip
            assert approved["scriptSha256"] == created["scriptSha256"]
            assert judged["ratingsSha256"] == sha(canon(rnd["ratings"]))
            assert judged["verdicts"] == {r["stepId"]: r["verdict"] for r in rnd["ratings"]}
            assert (judged["mode"], judged["deliveryOk"], judged["sampleAnswers"]) == (
                "turn",
                True,
                [],
            )
        assert by_type["script_approved"][0]["by"] == "Sam"
        assert (
            by_type["hazard_raised"][0]["hazardId"] == "h1"
            and by_type["hazard_raised"][0]["kind"] == "voice"
        )
        assert by_type["hazard_acknowledged"][0]["noteSha256"] == sha(canon(NOTE))
        assert by_type["decided"][0] == {
            "value": "go", "openStepIds": [], "openHazardIds": [],
            "reasonSha256": sha(canon(REASON)), "by": "Sam",
        }  # fmt: skip

    def test_no_event_carries_a_transcript_an_answer_a_note_or_a_device_key(self, local):
        client, _, bid = local
        blob = json.dumps(client.get(f"/api/briefings/{bid}").json()["events"], ensure_ascii=False)
        from tests.fakes import HAZARD_REPORT

        for secret in (ANSWER_1, ANSWER_2, HAZARD_REPORT["original"], HAZARD_REPORT["translation"],
                       NOTE, REASON, PANEL["instruction"], DEVICE, owner_hash(DEVICE)):  # fmt: skip
            assert secret not in blob

    def test_verify_is_ok_for_an_untouched_record(self, local):
        client, _, bid = local
        b = client.get(f"/api/briefings/{bid}").json()
        assert client.get(f"/api/briefings/{bid}/verify").json() == {
            "ok": True,
            "events": len(TYPES),
            "recordHash": b["recordHash"],
        }

    def test_a_new_briefing_has_one_event_and_verifies(self, settings):
        client, _ = build(settings)
        b = client.post("/api/briefings", json=PANEL).json()
        assert [e["type"] for e in b["events"]] == ["created"] and b["events"][0][
            "prevHash"
        ] == ZEROS
        assert b["recordHash"] == b["events"][0]["hash"]
        assert client.get(f"/api/briefings/{b['id']}/verify").json()["ok"] is True

    def test_a_refused_change_appends_nothing(self, local):
        client, _, bid = local
        before = client.get(f"/api/briefings/{bid}").json()["events"]
        assert (
            client.post(f"/api/briefings/{bid}/decision", json={"value": "no_go"}).status_code
            == 409
        )
        assert client.get(f"/api/briefings/{bid}").json()["events"] == before

    def test_verify_is_the_callers_own(self, local):
        client, _, bid = local
        other = api_client(client.app, device="someone-else-device-key-0000")
        assert other.get(f"/api/briefings/{bid}/verify").status_code == 404


class TestABriefingFromBeforeV04:
    def test_it_verifies_as_no_chain(self, settings):
        client, store = build(settings)
        bid = seed_round(store)
        assert client.get(f"/api/briefings/{bid}/verify").json() == {
            "ok": False, "events": 0, "recordHash": "", "reason": "no_chain",
        }  # fmt: skip

    def test_a_later_change_does_not_start_a_chain_part_way(self, settings):
        client, store = build(settings)
        bid = seed_round(store, approved=False)
        approve_round(client, bid, 1)
        b = client.get(f"/api/briefings/{bid}").json()
        assert b["events"] == [] and b["recordHash"] == ""


# Tampering with the stored record -------------------------------------------------------------


def edit_local(store: LocalStore, settings, bid: str, edit) -> None:
    path = settings.data_dir / "briefings" / f"{bid}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    edit(raw)
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def edit_firestore(store: FakeBackedStore, bid: str, edit) -> None:
    edit(store.fake.docs[("briefings", bid)])


def set_rating(raw):
    raw["rounds"][0]["ratings"][1]["verdict"] = "covered"  # s2: missed in round 1


def set_step(raw):
    raw["steps"][2]["text"] = "Open the panel"


def set_decision(raw):
    raw["decision"]["reason"] = "Something else entirely."


TAMPERING = [
    ("a rating", set_rating, ("round_judged", 1), "ratings_mismatch"),
    ("a step", set_step, ("steps_confirmed", None), "steps_mismatch"),
    ("the decision", set_decision, ("decided", None), "decision_mismatch"),
]


class TestTamperingIsFoundAtTheRightEvent:
    @pytest.mark.parametrize(
        ("what", "edit", "event", "reason"), TAMPERING, ids=[t[0] for t in TAMPERING]
    )
    def test_on_the_local_store(self, local, settings, what, edit, event, reason):
        client, store, bid = local
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        edit_local(store, settings, bid, edit)
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["ok"], result["brokenAt"], result["reason"]) == (
            False,
            seq_of(events, *event),
            reason,
        )

    @pytest.mark.parametrize(
        ("what", "edit", "event", "reason"), TAMPERING, ids=[t[0] for t in TAMPERING]
    )
    def test_on_firestore(self, firestore, what, edit, event, reason):
        client, store, bid = firestore
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True
        edit_firestore(store, bid, edit)
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["ok"], result["brokenAt"], result["reason"]) == (
            False,
            seq_of(events, *event),
            reason,
        )

    def test_an_edited_event_breaks_its_own_hash(self, local, settings):
        client, store, bid = local
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        target = seq_of(events, "round_judged", 1)

        def edit(raw):
            raw["events"][target - 1]["data"]["verdicts"]["s2"] = "covered"
            raw["rounds"][0]["ratings"][1]["verdict"] = "covered"  # and the rating, consistently

        edit_local(store, settings, bid, edit)
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["brokenAt"], result["reason"]) == (target, "hash_mismatch")

    def test_a_rebuilt_event_breaks_the_next_link(self, local, settings):
        """Someone who recomputes the edited event's own hash still breaks the next link."""
        client, store, bid = local
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        target = seq_of(events, "decided") - 1

        def edit(raw):
            e = raw["events"][target - 1]
            e["at"] = "2026-01-01T00:00:00.000Z"
            body = {k: e[k] for k in ("seq", "type", "at", "data")}
            e["hash"] = sha(e["prevHash"] + "\n" + canon(body))

        edit_local(store, settings, bid, edit)
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["brokenAt"], result["reason"]) == (target + 1, "prev_hash_mismatch")

    def test_a_dropped_event_is_found(self, local, settings):
        client, store, bid = local
        edit_local(store, settings, bid, lambda raw: raw["events"].pop(4))
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["brokenAt"], result["reason"]) == (5, "seq_mismatch")

    def test_an_edited_record_hash_is_found(self, local, settings):
        client, store, bid = local
        edit_local(store, settings, bid, lambda raw: raw.update(recordHash="f" * 64))
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["brokenAt"], result["reason"]) == (len(TYPES), "record_hash_mismatch")

    def test_edited_hazard_text_and_scripts_and_instruction_are_found(self, local, settings):
        client, store, bid = local
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        cases = [
            (lambda raw: raw["hazards"][0].update(original=""), seq_of(events, "hazard_raised"), "hazard_mismatch"),
            (lambda raw: raw["hazards"][0]["ack"].update(note="Nothing."), seq_of(events, "hazard_acknowledged"), "hazard_mismatch"),
            (lambda raw: raw["rounds"][1]["script"].update(closing="Go ahead."), seq_of(events, "round_created", 2), "script_mismatch"),
            (lambda raw: raw.update(instruction="Just open it."), seq_of(events, "instruction_edited"), "instruction_mismatch"),
            (lambda raw: raw["sop"].update(text="Anything goes."), 1, "sop_mismatch"),
            (lambda raw: raw.update(hazards=[]), seq_of(events, "hazard_raised"), "hazard_missing"),
            (lambda raw: raw.update(status="judged"), seq_of(events, "decided"), "decision_mismatch"),
        ]  # fmt: skip
        path = settings.data_dir / "briefings" / f"{bid}.json"
        pristine = path.read_text(encoding="utf-8")
        for edit, seq, reason in cases:
            path.write_text(pristine, encoding="utf-8")
            edit_local(store, settings, bid, edit)
            result = client.get(f"/api/briefings/{bid}/verify").json()
            assert (result["brokenAt"], result["reason"]) == (seq, reason), reason

    def test_content_no_event_records_is_found(self, local, settings):
        client, store, bid = local

        def add_hazard(raw):
            raw["hazards"].append({**raw["hazards"][0], "id": "h2", "ack": None})

        edit_local(store, settings, bid, add_hazard)
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["brokenAt"], result["reason"]) == (len(TYPES), "unrecorded_change")


class TestOnlyTheServerWritesEvents:
    def test_a_change_that_rewrites_an_earlier_event_is_refused(self, settings):
        client, store = build(settings)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]

        def rewrite(b: Briefing) -> None:
            b.events[0].data["instructionSha256"] = "0" * 64

        with pytest.raises(RuntimeError, match="append-only"):
            run_sync(Repo(store).mutate(bid, owner_hash(DEVICE), rewrite))
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True

    def test_a_change_that_drops_an_event_is_refused(self, settings):
        client, store = build(settings)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        with pytest.raises(RuntimeError, match="append-only"):
            run_sync(Repo(store).mutate(bid, owner_hash(DEVICE), lambda b: b.events.clear()))

    def test_the_browser_cannot_send_events(self, settings):
        client, _ = build(settings)
        forged = {**PANEL, "events": [{"seq": 1, "type": "decided", "at": "x", "data": {},
                                       "prevHash": ZEROS, "hash": ZEROS}], "recordHash": ZEROS}  # fmt: skip
        b = client.post("/api/briefings", json=forged).json()
        assert [e["type"] for e in b["events"]] == ["created"] and b["recordHash"] != ZEROS


async def test_concurrent_writes_on_firestore_keep_one_valid_chain(settings):
    """The fake Firestore interleaves transactions as the real one does: five hazard taps at once
    each append one event, with no seq taken twice, and the chain verifies."""
    store = FakeBackedStore()
    app, *_ = make_app(settings, round_1_scenario(), store=store)
    client = api_client(app)
    bid = drive_to_round(client)[0]
    env = type("Env", (), {"app": app})()
    async with over_http(env) as http:
        replies = await asyncio.gather(
            *(http.post(f"/api/briefings/{bid}/hazards") for _ in range(5))
        )
    assert sorted(r.json()["id"] for r in replies) == ["h1", "h2", "h3", "h4", "h5"]
    b = client.get(f"/api/briefings/{bid}").json()
    assert [e["seq"] for e in b["events"]] == list(range(1, len(b["events"]) + 1))
    assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True


def test_the_chain_module_matches_the_formula_for_a_known_event():
    b = Briefing.model_validate(
        {"id": "b_aaaaaaaaaaaa", "siteId": "sg", "taskId": "custom", "sop": {"id": "c", "version": "v1",
         "title": "t", "text": "x"}, "supervisorLang": "en", "workerLang": "ta", "instruction": "Läuft",
         "promptVersion": "p", "createdAt": "2026-10-14T00:00:00.000Z", "updatedAt": "x"}
    )  # fmt: skip
    event = chain.append(b, "created", {"note": "தமிழ்"}, at="2026-10-14T00:00:00.000Z")
    assert event is not None and event.prev_hash == ZEROS
    body = '{"at":"2026-10-14T00:00:00.000Z","data":{"note":"தமிழ்"},"seq":1,"type":"created"}'
    assert (
        chain.canonical({"seq": 1, "type": "created", "at": event.at, "data": event.data}) == body
    )
    assert event.hash == sha(ZEROS + "\n" + body) and b.record_hash == event.hash
