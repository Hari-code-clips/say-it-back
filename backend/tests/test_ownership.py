"""Callers and ownership (API.md v0.3; security review S1, S5, S16).

There are no accounts: each browser sends a device key in X-SIB-Device, a briefing belongs to the
key that created it, and any other key is told 404 `not_found` exactly as for an unknown id.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sayitback.caller import owner_hash
from tests.fakes import FakeTtsClient, tone_wav
from tests.flow_support import round_1_scenario
from tests.helpers import (
    DEVICE,
    OTHER_DEVICE,
    PANEL,
    SPOKEN,
    api_client,
    drive_to_round,
    error_of,
    make_app,
    seed_round,
)

UNKNOWN = "b_aaaaaaaaaaaa"
MALFORMED_KEYS = {
    "too short": "a" * 21,
    "too long": "a" * 65,
    "a space": "a" * 21 + " ",
    "a slash": "a" * 21 + "/",
    "a comma": "a" * 10 + "," + "a" * 11,
    "non-ASCII": ("a" * 21 + "é").encode("latin-1"),  # httpx sends a bytes value as it is
    "empty": "",
}


def briefing_routes(bid: str) -> dict[str, tuple[str, str, dict]]:
    """Every route that takes a briefing id: (method, path, request arguments)."""
    base = f"/api/briefings/{bid}"
    clip = [("q1", ("q1.wav", tone_wav(), "audio/wav"))]
    return {
        "read": ("GET", base, {}),
        "edit the instruction": ("PATCH", base, {"json": {"instruction": "Do anything."}}),
        "extract": ("POST", f"{base}/steps/extract", {}),
        "confirm steps": ("PUT", f"{base}/steps", {"json": {"steps": [{"id": "s1", "text": "x"}]}}),
        "create a round": ("POST", f"{base}/rounds", {"json": {}}),
        "approve a script": ("POST", f"{base}/rounds/1/approve", {"json": {"by": "mallory"}}),
        "get a live ticket": ("POST", f"{base}/rounds/1/live-session", {}),
        "check": ("POST", f"{base}/rounds/1/check", {"files": clip}),
        "report a hazard": ("POST", f"{base}/hazards", {}),
        "acknowledge a hazard": ("POST", f"{base}/hazards/h1/ack", {"json": {"note": "All fine."}}),
        "verify": ("GET", f"{base}/verify", {}),
        "decide": ("POST", f"{base}/decision", {"json": {"value": "no_go", "by": "mallory"}}),
    }


@pytest.fixture
def app_parts(settings):
    app, rt, llm, store = make_app(settings, round_1_scenario(), tts_client=FakeTtsClient())
    return app, store


@pytest.fixture
def victim(app_parts):
    return api_client(app_parts[0], device=DEVICE)


@pytest.fixture
def attacker(app_parts):
    return api_client(app_parts[0], device=OTHER_DEVICE)


@pytest.fixture
def anonymous(app_parts):
    return TestClient(app_parts[0])  # a client that sends no key at all


class TestTheDeviceKeyIsRequired:
    ROUTES = {
        "catalog": ("GET", "/api/catalog", {}),
        "transcribe": ("POST", "/api/transcribe", {"data": {"lang": "en"}}),
        "tts": ("POST", "/api/tts", {"json": {"briefingId": UNKNOWN, "n": 1, "text": "x"}}),
        "create": ("POST", "/api/briefings", {"json": PANEL}),
        "list": ("GET", "/api/briefings", {}),
        "export": ("GET", "/api/export/briefings.csv", {}),
        "eval report": ("GET", "/api/eval/latest", {}),
        "eval items": ("GET", "/api/eval/items", {}),
        "eval audio": ("GET", "/api/eval/items/x/audio", {}),
        "eval try": ("POST", "/api/eval/items/x/try", {}),
        "sample answers": ("GET", "/api/demo-answers", {}),
        "sample answer audio": ("GET", "/api/demo-answers/lifting-zone/ta/1/audio", {}),
        **{f"briefing: {k}": v for k, v in briefing_routes(UNKNOWN).items()},
    }

    @pytest.mark.parametrize("name", list(ROUTES))
    def test_a_request_with_no_key_is_401_device_required(self, anonymous, name):
        method, path, args = self.ROUTES[name]
        assert error_of(anonymous.request(method, path, **args)) == (401, "device_required")

    @pytest.mark.parametrize("key", list(MALFORMED_KEYS.values()), ids=list(MALFORMED_KEYS))
    def test_a_malformed_key_is_401_on_every_route(self, anonymous, key):
        for method, path, args in self.ROUTES.values():
            headers = {"X-SIB-Device": key}
            response = anonymous.request(method, path, headers=headers, **args)
            assert error_of(response) == (401, "device_required"), path

    def test_two_key_headers_are_refused(self, anonymous):
        headers = [("X-SIB-Device", DEVICE), ("X-SIB-Device", OTHER_DEVICE)]
        assert error_of(anonymous.get("/api/catalog", headers=headers)) == (401, "device_required")

    @pytest.mark.parametrize("key", ["a" * 22, "A" * 64, "a-b_c" * 5, DEVICE])
    def test_a_key_of_22_to_64_url_safe_characters_is_accepted(self, anonymous, key):
        assert anonymous.get("/api/catalog", headers={"X-SIB-Device": key}).status_code == 200

    def test_health_takes_no_key(self, anonymous):
        assert anonymous.get("/api/health").status_code == 200

    def test_the_websocket_takes_no_key_its_ticket_is_the_capability(self, app_parts):
        """Endpoint 20 is refused for its ticket, never for a missing key header."""
        from tests.relay_support import ORIGIN, Wire

        client = TestClient(app_parts[0])  # no X-SIB-Device
        with client.websocket_connect(f"/api/live/{UNKNOWN}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket="x" * 43)
            assert wire.next()[1]["code"] == "bad_ticket"

    def test_the_refusal_comes_before_the_body_is_read(self, anonymous, victim):
        """No key, a body over the cap: 401, not 413. The check never touches the upload."""
        big = b"x" * (300 * 1024)
        assert error_of(anonymous.post("/api/briefings", content=big))[0] == 401
        assert error_of(victim.post("/api/briefings", content=big))[0] == 413

    def test_a_cross_site_simple_post_cannot_carry_the_key(self, anonymous):
        """Review S16: a multipart POST needs no preflight, so any page can send one. It cannot
        set a custom header, so it is refused before the upload is parsed."""
        audio = {"audio": ("a.wav", tone_wav(), "audio/wav")}
        origin = {"origin": "https://evil.example"}
        response = anonymous.post(
            "/api/transcribe", files=audio, data={"lang": "en"}, headers=origin
        )
        assert error_of(response) == (401, "device_required")


class TestOneBrowsersBriefingsAreItsOwn:
    """Review F2 turned round: the attacker who could list, read, edit, decide and lock another
    visitor's briefing now finds nothing."""

    def test_every_briefing_route_is_a_404_for_another_key_the_same_as_an_unknown_id(
        self, victim, attacker
    ):
        bid, _ = drive_to_round(victim)
        for name, (method, path, args) in briefing_routes(bid).items():
            theirs = attacker.request(method, path, **args)
            _, _, unknown_args = briefing_routes(UNKNOWN)[name]
            unknown = attacker.request(method, path.replace(bid, UNKNOWN), **unknown_args)
            assert error_of(theirs) == (404, "not_found"), name
            assert (theirs.status_code, theirs.json()) == (unknown.status_code, unknown.json())

    def test_the_attack_changes_nothing_and_the_owner_is_unharmed(self, victim, attacker):
        bid, _ = drive_to_round(victim)  # at round 1, status briefing
        before = victim.get(f"/api/briefings/{bid}").json()
        for method, path, args in briefing_routes(bid).values():
            attacker.request(method, path, **args)

        assert victim.get(f"/api/briefings/{bid}").json() == before  # not even updatedAt moved
        # Both live tickets are still the owner's (the attacker burned none), and a decision is open.
        for _ in range(2):
            assert victim.post(f"/api/briefings/{bid}/rounds/1/live-session").status_code == 200
        assert (
            victim.post(f"/api/briefings/{bid}/decision", json={"value": "no_go"}).status_code
            == 200
        )

    def test_a_draft_cannot_be_rewritten_by_another_key(self, victim, attacker):
        bid = victim.post("/api/briefings", json=PANEL).json()["id"]
        edit = attacker.patch(
            f"/api/briefings/{bid}", json={"instruction": "Do whatever you like."}
        )
        assert error_of(edit) == (404, "not_found")
        assert victim.get(f"/api/briefings/{bid}").json()["instruction"] == PANEL["instruction"]

    def test_a_ticket_is_issued_only_to_the_owner(self, victim, attacker):
        bid, _ = drive_to_round(victim)
        assert error_of(attacker.post(f"/api/briefings/{bid}/rounds/1/live-session")) == (
            404,
            "not_found",
        )

    def test_the_list_holds_only_the_callers_briefings_newest_first(self, victim, attacker):
        mine = [victim.post("/api/briefings", json=PANEL).json()["id"] for _ in range(3)]
        theirs = [attacker.post("/api/briefings", json=PANEL).json()["id"] for _ in range(2)]

        seen_by_victim = [i["id"] for i in victim.get("/api/briefings").json()["items"]]
        seen_by_attacker = [i["id"] for i in attacker.get("/api/briefings").json()["items"]]

        assert seen_by_victim == mine[::-1] and seen_by_attacker == theirs[::-1]
        assert [i["id"] for i in victim.get("/api/briefings?limit=2").json()["items"]] == mine[
            :0:-1
        ]

    def test_a_browser_with_no_briefings_sees_an_empty_list(self, victim, attacker):
        victim.post("/api/briefings", json=PANEL)
        assert attacker.get("/api/briefings").json() == {"items": []}

    def test_the_export_holds_only_the_callers_rows(self, victim, attacker):
        """Review F2: the CSV carried every visitor's rows, with free-text decision fields."""
        mine, _ = drive_to_round(victim)
        victim.post(f"/api/briefings/{mine}/decision", json={"value": "no_go", "by": "Ravi"})
        theirs, _ = drive_to_round(attacker)
        attacker.post(f"/api/briefings/{theirs}/decision", json={"value": "no_go", "by": "mallory"})

        victim_csv = victim.get("/api/export/briefings.csv").text
        attacker_csv = attacker.get("/api/export/briefings.csv").text

        assert mine in victim_csv and "Ravi" in victim_csv
        assert theirs not in victim_csv and "mallory" not in victim_csv
        assert theirs in attacker_csv and mine not in attacker_csv and "Ravi" not in attacker_csv

    def test_a_browser_with_no_briefings_exports_only_the_header(self, victim, attacker):
        drive_to_round(victim)
        lines = attacker.get("/api/export/briefings.csv").text.splitlines()
        assert len(lines) == 1 and lines[0].startswith("briefingId,")

    def test_a_briefing_made_before_device_keys_belongs_to_no_one(self, app_parts, victim):
        """No owner, so no key matches it: not found, absent from the list and the export."""
        from tests.helpers import run_sync

        _, store = app_parts
        old = seed_round(store, DEVICE)
        record = run_sync(store.get(old))
        del record["owner"]
        run_sync(store.create(record))

        assert error_of(victim.get(f"/api/briefings/{old}")) == (404, "not_found")
        assert old not in victim.get("/api/export/briefings.csv").text
        assert victim.get("/api/briefings").json() == {"items": []}

    def test_a_key_that_is_only_a_prefix_or_a_case_change_of_another_is_not_it(
        self, app_parts, victim
    ):
        bid, _ = drive_to_round(victim)
        for key in (DEVICE[:-1] + "b", DEVICE.upper(), DEVICE + "x"):
            other = api_client(app_parts[0], device=key)
            assert error_of(other.get(f"/api/briefings/{bid}")) == (404, "not_found")


class TestTheOwnerIsNeverShown:
    def test_the_key_is_stored_only_as_its_sha256_as_the_owner(self, app_parts, victim, settings):
        from tests.helpers import run_sync

        _, store = app_parts
        bid, _ = drive_to_round(victim)
        record = run_sync(store.get(bid))
        assert record["owner"] == owner_hash(DEVICE)
        on_disk = "".join(p.read_text() for p in settings.data_dir.rglob("*.json"))
        assert DEVICE not in on_disk  # the key itself is never stored

    def test_the_hash_is_in_no_response_and_no_log(self, app_parts, attacker, caplog):
        from tests.relay_support import ORIGIN, Wire

        address = "203.0.113.77"
        victim = api_client(app_parts[0], device=DEVICE, client=(address, 5000))
        owner = owner_hash(DEVICE)
        seen: list[str] = []

        def look(response):
            seen.append(response.text + json.dumps(dict(response.headers)))
            return response

        with caplog.at_level("DEBUG"):
            bid, rnd = drive_to_round(victim)
            look(victim.get(f"/api/briefings/{bid}"))
            look(victim.get("/api/briefings"))
            look(victim.get("/api/export/briefings.csv"))
            ticket = look(victim.post(f"/api/briefings/{bid}/rounds/1/live-session")).json()
            look(attacker.get(f"/api/briefings/{bid}"))  # a 404
            look(TestClient(app_parts[0]).get("/api/briefings"))  # a 401
            look(victim.post("/api/tts", json={"briefingId": bid, "n": 1, "text": SPOKEN[:5]}))
            look(victim.post("/api/tts", json={"briefingId": bid, "n": 1, "text": "not in it"}))
            look(victim.post(f"/api/briefings/{bid}/rounds/1/approve"))
            look(victim.post(f"/api/briefings/{bid}/hazards"))
            look(victim.post(f"/api/briefings/{bid}/hazards/h1/ack", json={"note": "Checked it."}))
            look(victim.get(f"/api/briefings/{bid}/verify"))
            look(victim.get("/api/demo-answers"))
            with victim.websocket_connect(f"/api/live/{bid}/1", headers={"origin": ORIGIN}) as ws:
                wire = Wire(ws)
                wire.start(ticket["ticket"])
                wire.send(type="stop")
                wire.next()
            look(victim.get(f"/api/briefings/{bid}"))  # after the relay wrote round.live

        assert rnd["n"] == 1 and len(seen) >= 14
        assert not [text for text in seen if owner in text or DEVICE in text or address in text]
        for secret_text in (owner, DEVICE, address):  # key, hash and client address: none is logged
            assert secret_text not in caplog.text

    def test_the_owner_never_reaches_the_decision_webhook_payload(self, victim, app_parts):
        bid, _ = drive_to_round(victim)
        body = victim.post(f"/api/briefings/{bid}/decision", json={"value": "no_go"}).json()
        assert "owner" not in body and owner_hash(DEVICE) not in json.dumps(body)

    def test_a_caller_prints_as_nothing(self):
        from sayitback.caller import Caller

        text = repr(Caller(owner_hash(DEVICE), "203.0.113.7"))
        assert owner_hash(DEVICE) not in text and "203.0.113.7" not in text


class TestTheLiveSocketActsForTheOwnerThroughItsTicket:
    def test_the_relay_writes_round_live_to_the_owners_briefing(self, settings):
        from tests.fake_live import fake_opener
        from tests.relay_support import ORIGIN, Wire

        app, *_ = make_app(settings, live_opener=fake_opener([]))
        owner, other = api_client(app, device=DEVICE), api_client(app, device=OTHER_DEVICE)
        bid, _ = drive_to_round(owner)
        ticket = owner.post(f"/api/briefings/{bid}/rounds/1/live-session").json()["ticket"]
        with other.websocket_connect(f"/api/live/{bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)  # the socket carries no key: whoever holds the ticket runs the session
            assert wire.start(ticket)[1]["type"] == "ready"
            wire.send(type="cue", cue="READ_INSTRUCTION")
            wire.until("turn_complete")
            wire.send(type="stop")
            wire.next()

        live = owner.get(f"/api/briefings/{bid}").json()["rounds"][0]["live"]
        assert live["delivered"] == {"instruction": "said:READ_INSTRUCTION"}

    def test_a_ticket_that_names_no_owner_is_refused(self, settings):
        """Tickets from before device keys (valid for 120 s at most) open nothing."""
        from sayitback import live_session
        from tests.fake_live import fake_opener
        from tests.helpers import run_sync
        from tests.relay_support import ORIGIN, Wire

        handles: list = []
        app, _rt, _llm, store = make_app(settings, live_opener=fake_opener(handles))
        bid = seed_round(store, DEVICE)
        ticket, _ = run_sync(live_session.issue_ticket(store, settings, bid, 1, owner=""))
        client = api_client(app)
        with client.websocket_connect(f"/api/live/{bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            wire.send(type="start", ticket=ticket)
            assert wire.next()[1]["code"] == "bad_ticket"
        assert handles == []


class TestTheFreeWritesAreRateLimited:
    """Review S5 and F9: creating and editing a briefing cost no Gemini call, so nothing bounded
    them. They share the per-address limit of the Gemini-backed endpoints."""

    def test_create_is_limited_per_address(self, settings):
        """F9 turned round: 50 creates at a limit of 1 a minute used to all pass."""
        app, *_ = make_app(settings.with_overrides(rate_limit_per_min=1))
        client = api_client(app)
        assert client.post("/api/briefings", json=PANEL).status_code == 200
        for _ in range(5):
            refused = client.post("/api/briefings", json=PANEL)
            assert error_of(refused) == (429, "rate_limited")
            assert int(refused.headers["retry-after"]) > 0
        assert len(client.get("/api/briefings").json()["items"]) == 1

    def test_editing_the_instruction_is_limited_too(self, settings):
        app, *_ = make_app(settings.with_overrides(rate_limit_per_min=2))
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        edit = {"instruction": "Isolate it first."}
        assert client.patch(f"/api/briefings/{bid}", json=edit).status_code == 200
        assert error_of(client.patch(f"/api/briefings/{bid}", json=edit)) == (429, "rate_limited")

    def test_reads_and_the_other_free_writes_are_not_limited(self, settings):
        app, *_ = make_app(settings.with_overrides(rate_limit_per_min=1))
        client = api_client(app)
        client.post("/api/briefings", json=PANEL)  # the one request the address has
        assert client.get("/api/briefings").status_code == 200
        assert client.get("/api/catalog").status_code == 200
        assert client.get("/api/export/briefings.csv").status_code == 200

    def test_another_address_has_its_own_allowance(self, settings):
        app, *_ = make_app(settings.with_overrides(rate_limit_per_min=1))
        one = api_client(app, client=("203.0.113.1", 1000))
        two = api_client(app, client=("203.0.113.2", 1000))
        assert one.post("/api/briefings", json=PANEL).status_code == 200
        assert two.post("/api/briefings", json=PANEL).status_code == 200
        assert one.post("/api/briefings", json=PANEL).status_code == 429
