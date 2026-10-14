"""Each client address has its own daily allowance (API.md v0.3, "Daily cap"; security review S2).

`SIB_DAILY_CALLS_PER_IP` (default 100, 0 = off) uses the same costs and the same UTC day as the
shared cap, is kept under a SHA-256 of the day and the address, and is reserved in the same atomic
step: either count refuses the request (429 `daily_limit`), and then neither moves. Bursts and the
Firestore fake: test_daily_cap_address_shared.py.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from sayitback.daily_cap import DailyCap, address_key
from sayitback.errors import RateLimited
from sayitback.settings import ConfigError, Settings
from sayitback.store import LocalStore
from sayitback.store.base import Reserved
from tests.cap_support import (
    TODAY,
    UNTIL_MIDNIGHT,
    Clock,
    confirmed,
    make_capped,
    new_briefing,
    script_for_open_steps,
    speak,
    write_eval_set,
)
from tests.fake_firestore import FakeBackedStore
from tests.fakes import panel_script, tone_wav
from tests.flow_support import round_1_scenario
from tests.helpers import (
    DEVICE,
    OTHER_DEVICE,
    PANEL,
    api_client,
    drive_to_round,
    error_of,
    post_check,
)

A, B, C = "203.0.113.7", "203.0.113.8", "203.0.113.9"


def at(env, address: str, device: str = DEVICE):
    """A browser at `address`: its socket peer, as a Cloud Run instance sees it."""
    return api_client(env.app, device=device, client=(address, 5000))


def transcribe(client):
    """POST /api/transcribe: a Gemini-backed call that needs no briefing, so no owner."""
    return client.post(
        "/api/transcribe", files={"audio": ("a.wav", tone_wav(), "audio/wav")}, data={"lang": "en"}
    )


@pytest.fixture(params=["local", "firestore"])
def store(request, tmp_path):
    return LocalStore(tmp_path / ".data") if request.param == "local" else FakeBackedStore()


def stored_names(store) -> list[str]:
    """Every document the store holds, as 'collection/name'."""
    if isinstance(store, FakeBackedStore):
        return [f"{collection}/{name}" for collection, name in store.fake.docs]
    return [str(p.relative_to(store._root).with_suffix("")) for p in store._root.rglob("*.json")]


def stored_text(store) -> str:
    if isinstance(store, FakeBackedStore):
        return repr(store.fake.docs)
    return "".join(p.read_text() for p in store._root.rglob("*.json"))


class TestTheSetting:
    def test_it_defaults_to_100_and_reads_the_environment(self):
        assert Settings.from_env({}).daily_calls_per_ip == 100
        assert Settings.from_env({"SIB_DAILY_CALLS_PER_IP": " 40 "}).daily_calls_per_ip == 40

    def test_zero_turns_it_off(self):
        assert Settings.from_env({"SIB_DAILY_CALLS_PER_IP": "0"}).daily_calls_per_ip == 0

    @pytest.mark.parametrize("value", ["-1", "abc", "1.5", "1e2", "100 calls"])
    def test_anything_but_an_integer_of_zero_or_more_fails_at_start_up(self, value):
        with pytest.raises(ConfigError, match="SIB_DAILY_CALLS_PER_IP"):
            Settings.from_env({"SIB_DAILY_CALLS_PER_IP": value})


class TestTheReservation:
    async def test_an_address_is_refused_at_its_own_allowance_and_not_before(self, store):
        cap = DailyCap(store, 100, Clock(), per_address=3)
        await cap.reserve(2, A)
        with pytest.raises(RateLimited) as err:
            await cap.reserve(2, A)  # 4 would pass its 3
        assert (err.value.status, err.value.code) == (429, "daily_limit")
        assert err.value.retry_after == UNTIL_MIDNIGHT
        await cap.reserve(1, A)  # the refused two used nothing, so one still fits
        with pytest.raises(RateLimited):
            await cap.reserve(1, A)
        await cap.reserve(3, B)  # another address has an allowance of its own

    async def test_the_shared_cap_refusing_charges_the_address_nothing(self, store):
        tight = DailyCap(store, 4, Clock(), per_address=2)
        await tight.reserve(2, B)
        await tight.reserve(2, C)  # the shared count is now 4 of 4
        with pytest.raises(RateLimited):
            await tight.reserve(1, A)  # refused by the shared cap
        roomy = DailyCap(store, 100, Clock(), per_address=2)  # the same store, a bigger cap
        await roomy.reserve(2, A)  # A's whole allowance: the refusal had not charged it

    async def test_the_address_refusing_charges_the_shared_count_nothing(self, store):
        cap = DailyCap(store, 6, Clock(), per_address=2)
        await cap.reserve(2, A)
        with pytest.raises(RateLimited):
            await cap.reserve(1, A)  # refused by A's allowance
        await cap.reserve(2, B)
        await cap.reserve(2, C)  # 2 + 2 + 2 = 6: had A's refused call counted, this would not fit
        with pytest.raises(RateLimited):
            await cap.reserve(1, "203.0.113.10")  # and now it is exactly full

    async def test_the_outcome_says_which_cap_refused_and_the_address_comes_first(self, store):
        day = "20261014"
        mine, theirs, third = (address_key(day, a) for a in (A, B, C))
        grant = await store.reserve_calls(day, 1, 2, address=mine, address_cap=1)
        assert grant is Reserved.GRANTED and bool(grant)
        # A is at its allowance of 1 and the shared cap has one left: A's own allowance refuses.
        refused = await store.reserve_calls(day, 1, 2, address=mine, address_cap=1)
        assert refused is Reserved.ADDRESS_FULL and not refused
        assert await store.reserve_calls(day, 1, 2, address=theirs, address_cap=1)  # shared: 2 of 2
        # C has room of its own but the shared cap is used up.
        full = await store.reserve_calls(day, 1, 2, address=third, address_cap=1)
        assert full is Reserved.GLOBAL_FULL and not full
        # Both are full for A: the address's own answer comes first.
        both = await store.reserve_calls(day, 1, 2, address=mine, address_cap=1)
        assert both is Reserved.ADDRESS_FULL

    async def test_a_new_utc_day_is_a_new_allowance(self, store):
        clock = Clock(datetime(2026, 10, 14, 23, 59, 59, tzinfo=UTC))
        cap = DailyCap(store, 10, clock, per_address=1)
        await cap.reserve(1, A)
        with pytest.raises(RateLimited):
            await cap.reserve(1, A)
        clock.now = datetime(2026, 10, 15, 0, 0, 1, tzinfo=UTC)
        await cap.reserve(1, A)

    async def test_zero_keeps_no_per_address_count_at_all(self, store):
        cap = DailyCap(store, 10, Clock(), per_address=0)
        for _ in range(10):
            await cap.reserve(1, A)  # only the shared cap binds
        assert stored_names(store) == [f"gemini_calls/{TODAY}"]

    async def test_the_store_holds_a_hash_of_the_day_and_the_address_never_the_address(self, store):
        await DailyCap(store, 10, Clock(), per_address=5).reserve(1, A)
        assert f"gemini_calls_ip/{address_key(TODAY, A)}" in stored_names(store)
        assert A not in stored_text(store) and A not in " ".join(stored_names(store))

    def test_the_key_is_the_sha256_of_the_day_and_the_address(self):
        assert address_key("20261014", A) == hashlib.sha256(f"20261014:{A}".encode()).hexdigest()
        assert (
            len(
                {address_key("20261014", A), address_key("20261015", A), address_key("20261014", B)}
            )
            == 3
        )

    async def test_only_the_shared_cap_logs_its_warning(self, store, caplog):
        cap = DailyCap(store, 2, Clock(), per_address=1)
        await cap.reserve(1, A)
        with caplog.at_level("WARNING", logger="sayitback.daily_cap"):
            for _ in range(3):
                with pytest.raises(RateLimited):
                    await cap.reserve(1, A)  # A's own allowance: routine, and says nothing
            assert caplog.records == []
            await cap.reserve(1, B)
            with pytest.raises(RateLimited):
                await cap.reserve(1, C)  # the shared cap: the one line a log alert looks for
        assert [r.getMessage() for r in caplog.records] == [
            "daily Gemini call cap reached: limit 2, UTC day 20261014"
        ]


class TestThroughTheApi:
    def test_review_f3_one_address_can_no_longer_drain_the_day_for_everyone(self, settings):
        """One client inside its per-minute allowance spent the whole day's budget in ten minutes,
        and a judge's real briefing was then refused too."""
        env = make_capped(settings, limit=12, rate_limit_per_min=30, daily_calls_per_ip=5)
        attacker, judge = at(env, A), at(env, B, OTHER_DEVICE)
        for i in range(5):
            assert speak(env, f"line {i}", client=attacker).status_code == 200
        refused = speak(env, "one more", client=attacker)
        assert error_of(refused) == (429, "daily_limit")
        assert refused.headers["retry-after"] == str(UNTIL_MIDNIGHT)
        assert env.ledger.spent == 5 and len(env.tts.calls) == 5  # nothing counted, nothing called

        bid = judge.post("/api/briefings", json=PANEL).json()["id"]  # the judge's briefing works
        assert judge.post(f"/api/briefings/{bid}/steps/extract").status_code == 200
        assert env.ledger.spent == 6

    def test_review_f3b_the_stateless_eval_try_is_bounded_by_the_allowance_too(self, settings):
        """Each try costs three and needs no briefing: three hits spent a day's budget of nine."""
        item = write_eval_set(settings)
        env = make_capped(settings, limit=100, daily_calls_per_ip=6)
        me = at(env, A)
        assert [me.post(f"/api/eval/items/{item}/try").status_code for _ in range(2)] == [200, 200]
        assert error_of(me.post(f"/api/eval/items/{item}/try")) == (429, "daily_limit")
        assert (
            env.ledger.spent == 6
            and at(env, B).post(f"/api/eval/items/{item}/try").status_code == 200
        )

    def test_the_same_address_with_another_device_key_shares_the_allowance(self, settings):
        env = make_capped(settings, daily_calls_per_ip=2)
        assert transcribe(at(env, A, DEVICE)).status_code == 200
        assert transcribe(at(env, A, OTHER_DEVICE)).status_code == 200
        # A third key does not buy a third call: the address is what is counted.
        third = transcribe(at(env, A, "third-device-key-cccccccccccc"))
        assert error_of(third) == (429, "daily_limit")

    def test_the_same_device_key_at_another_address_has_its_own(self, settings):
        env = make_capped(settings, daily_calls_per_ip=1)
        assert transcribe(at(env, A)).status_code == 200
        assert error_of(transcribe(at(env, A))) == (429, "daily_limit")
        assert transcribe(at(env, B)).status_code == 200

    def test_a_forged_header_does_not_open_a_new_allowance(self, settings):
        env = make_capped(settings, daily_calls_per_ip=2)
        for i, expected in enumerate([200, 200, 429, 429, 429]):
            forged = {"X-Forwarded-For": f"10.0.0.{i}, {A}"}  # the front end appended A
            reply = transcribe(api_client(env.app, headers=forged))
            assert reply.status_code == expected, i

    def test_zero_is_off_and_only_the_shared_cap_binds(self, settings):
        env = make_capped(settings, limit=30, daily_calls_per_ip=0)
        client = at(env, A)
        assert [transcribe(client).status_code for _ in range(30)] == [200] * 30
        assert all(e.address == "" for e in env.ledger.entries)

    def test_the_shared_kill_switch_still_refuses_every_address(self, settings):
        env = make_capped(settings, limit=0, daily_calls_per_ip=100)
        assert error_of(transcribe(at(env, A))) == (429, "daily_limit")
        assert env.ledger.entries[-1].outcome is Reserved.GLOBAL_FULL

    def test_the_free_endpoints_keep_working_for_an_address_over_its_allowance(self, settings):
        env = make_capped(settings, daily_calls_per_ip=1)
        client = at(env, A)
        assert transcribe(client).status_code == 200
        assert error_of(transcribe(client)) == (429, "daily_limit")
        for path in ("/api/health", "/api/catalog", "/api/briefings", "/api/export/briefings.csv"):
            assert client.get(path).status_code == 200
        assert client.post("/api/briefings", json=PANEL).status_code == 200

    def test_the_per_minute_limit_still_answers_before_the_daily_allowance(self, settings):
        env = make_capped(settings, daily_calls_per_ip=100, rate_limit_per_min=1)
        client = at(env, A)
        assert transcribe(client).status_code == 200
        assert error_of(transcribe(client)) == (429, "rate_limited")
        assert len(env.ledger.entries) == 1  # the refused one never reached the cap

    def test_a_spent_allowance_refuses_every_gemini_backed_endpoint_whole(self, settings):
        scenario = round_1_scenario()
        setup = make_capped(settings, scenario, daily_calls_per_ip=0)  # no per-address counts yet
        draft, ready = new_briefing(setup), confirmed(setup)
        rounded = drive_to_round(setup.client)[0]
        item = write_eval_set(settings)
        env = make_capped(
            settings, scenario, store=LocalStore(settings.data_dir), daily_calls_per_ip=1
        )
        me = at(env, A)
        assert transcribe(me).status_code == 200  # the one call this address has today

        replies = {
            "transcribe": transcribe(me),
            "extract": me.post(f"/api/briefings/{draft}/steps/extract"),
            "round": me.post(f"/api/briefings/{ready}/rounds", json={}),
            "live ticket": me.post(f"/api/briefings/{rounded}/rounds/1/live-session"),
            "tts": speak(env, "a", client=me),
            "check": post_check(me, rounded, 1),
            "eval try": me.post(f"/api/eval/items/{item}/try"),
        }

        assert {k: error_of(v) for k, v in replies.items()} == dict.fromkeys(
            replies, (429, "daily_limit")
        )
        assert env.ledger.model_calls() == 1  # no other model call was made


class TestEveryReservationNamesTheAddress:
    """The allowance is reserved with the shared cap, at every site that reserves."""

    def test_each_gemini_backed_endpoint_reserves_for_the_callers_address(self, settings):
        env = make_capped(settings, round_1_scenario())
        item = write_eval_set(settings)
        me = at(env, A)

        transcribe(me)
        bid, _ = drive_to_round(me)  # extract, then the round
        me.post(f"/api/briefings/{bid}/rounds/1/live-session")
        speak(env, "a", client=me)
        post_check(me, bid, 1)
        me.post(f"/api/eval/items/{item}/try")

        entries = env.ledger.entries
        assert [e.calls for e in entries] == [1, 1, 2, 4, 1, 3, 3]
        assert {e.address for e in entries} == {address_key(TODAY, A)}
        assert all(e.granted for e in entries)

    def test_a_script_retry_reserves_for_the_address_too(self, settings):
        scenario = round_1_scenario()
        env = make_capped(settings, scenario)
        bid = confirmed(env)
        scenario.script_drafts = [panel_script(closing="x" * 161)]  # breaks a limit: one retry
        before = len(env.ledger.entries)
        assert at(env, A).post(f"/api/briefings/{bid}/rounds", json={}).status_code == 200
        made = env.ledger.entries[before:]
        assert [e.calls for e in made] == [2, 1]
        assert {e.address for e in made} == {address_key(TODAY, A)}

    def test_a_re_explain_round_reserves_for_the_address_too(self, settings):
        scenario = round_1_scenario()
        env = make_capped(settings, scenario)
        me = at(env, A)
        bid, _ = drive_to_round(me)
        post_check(me, bid, 1)
        script_for_open_steps(scenario)
        before = len(env.ledger.entries)
        assert me.post(f"/api/briefings/{bid}/rounds", json={}).status_code == 200
        assert {e.address for e in env.ledger.entries[before:]} == {address_key(TODAY, A)}
