"""Idempotent answer uploads (endpoint 13, `Idempotency-Key`; idempotency.py, 2026-10-16).

A retried upload with the same key returns the round its first upload judged, with no second model
call and no second daily-cap charge; without a key, or with another key, nothing changes."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.datastructures import Headers

from sayitback.caller import owner_hash
from sayitback.errors import InvalidState, Unprocessable
from sayitback.idempotency import KEY_HEADER, idempotent_check, key_digest
from sayitback.models import Round, now_iso
from sayitback.repo import Repo
from sayitback.settings import ConfigError, Settings
from sayitback.store import LocalStore
from sayitback.store.base import iso
from tests.cap_support import make_capped
from tests.fake_firestore import FakeBackedStore
from tests.fakes import tone_wav
from tests.flow_support import round_1_scenario
from tests.helpers import (
    CALLER,
    DEVICE,
    OTHER_DEVICE,
    api_client,
    check_files,
    error_of,
    seed_round,
)

KEY = "Kq3vX9_tY2-pLm8RwZ4sNa"  # 22 characters, the browser's shape
OTHER_KEY = "Bz7Qe1-uWc5_oPx0LdHk9J"


def upload(client, bid: str, key: str | None, n: int = 1, *headers: tuple[str, str]):
    sent = [(KEY_HEADER, key)] if key else []
    return client.post(
        f"/api/briefings/{bid}/rounds/{n}/check",
        files=check_files(q1=tone_wav()),
        data={"meta": json.dumps({"mode": "turn"})},
        headers=Headers(raw=[(k.lower().encode(), v.encode()) for k, v in [*sent, *headers]]),
    )


def model_calls(env) -> int:
    return len(env.llm.seen)


class TestOverHttp:
    def test_the_same_key_again_returns_the_same_round_with_no_model_call_and_no_charge(
        self, settings
    ):
        env = make_capped(settings, round_1_scenario())
        bid = seed_round(env.store)
        first = upload(env.client, bid, KEY)
        assert first.status_code == 200, first.text
        calls, charged = model_calls(env), env.ledger.spent

        again = upload(env.client, bid, KEY)

        assert again.status_code == 200, again.text
        assert again.json() == first.json()
        assert model_calls(env) == calls and env.ledger.spent == charged
        assert len(env.ledger.entries) == 1  # the retry never reached the cap

    def test_another_key_for_a_judged_round_keeps_todays_409(self, settings):
        env = make_capped(settings, round_1_scenario())
        bid = seed_round(env.store)
        assert upload(env.client, bid, KEY).status_code == 200
        calls = model_calls(env)

        assert error_of(upload(env.client, bid, OTHER_KEY)) == (409, "invalid_state")
        assert error_of(upload(env.client, bid, None)) == (409, "invalid_state")
        assert model_calls(env) == calls

    def test_without_a_key_nothing_changes(self, settings):
        env = make_capped(settings, round_1_scenario())
        bid = seed_round(env.store)
        assert upload(env.client, bid, None).status_code == 200
        assert error_of(upload(env.client, bid, None)) == (409, "invalid_state")
        assert not (settings.data_dir / "check_keys").exists()  # no record without a key

    def test_another_device_with_the_same_key_gets_the_404_of_an_unknown_id(self, settings):
        env = make_capped(settings, round_1_scenario())
        bid = seed_round(env.store)
        assert upload(env.client, bid, KEY).status_code == 200

        other = api_client(env.app, device=OTHER_DEVICE)
        assert error_of(upload(other, bid, KEY)) == (404, "not_found")

    def test_a_failed_upload_drops_its_claim_so_the_retry_runs_the_check(self, settings):
        env = make_capped(settings, round_1_scenario(), limit=2)  # a check needs 3
        bid = seed_round(env.store)
        assert error_of(upload(env.client, bid, KEY)) == (429, "daily_limit")
        assert not list((settings.data_dir / "check_keys").glob("*.json"))

        roomy = make_capped(settings, round_1_scenario(), store=env.store)
        assert upload(roomy.client, bid, KEY).status_code == 200

    @pytest.mark.parametrize("bad", ["short", "x" * 65, "has space in it here!", "dots.are.not.allowed.here", "a=b=c=d=e=f=g=h=i"])
    def test_a_malformed_key_is_422_and_is_never_echoed(self, settings, bad):
        env = make_capped(settings, round_1_scenario())
        bid = seed_round(env.store)
        response = upload(env.client, bid, bad)
        assert error_of(response) == (422, "validation_error")
        assert bad not in response.text and model_calls(env) == 0

    def test_two_keys_on_one_request_are_422(self, settings):
        env = make_capped(settings, round_1_scenario())
        bid = seed_round(env.store)
        response = upload(env.client, bid, KEY, 1, (KEY_HEADER, OTHER_KEY))
        assert error_of(response) == (422, "validation_error") and model_calls(env) == 0

    def test_the_store_keeps_a_digest_never_the_key_or_the_owner(self, settings):
        env = make_capped(settings, round_1_scenario())
        bid = seed_round(env.store)
        assert upload(env.client, bid, KEY).status_code == 200
        [path] = (settings.data_dir / "check_keys").glob("*.json")
        stored = path.read_text()
        assert path.stem == key_digest(owner_hash(DEVICE), bid, 1, KEY)
        assert KEY not in stored and owner_hash(DEVICE) not in stored and DEVICE not in stored
        assert set(json.loads(stored)) == {"state", "expiresAt"}

    def test_after_the_ttl_a_retry_gets_todays_409(self, settings):
        env = make_capped(settings, round_1_scenario(), idempotency_ttl_s=0.01)
        bid = seed_round(env.store)
        assert upload(env.client, bid, KEY).status_code == 200
        [path] = (settings.data_dir / "check_keys").glob("*.json")
        path.write_text(json.dumps({"state": "done", "expiresAt": "2000-01-01T00:00:00.000Z"}))
        assert error_of(upload(env.client, bid, KEY)) == (409, "invalid_state")

    def test_ttl_zero_ignores_the_header(self, settings):
        env = make_capped(settings, round_1_scenario(), idempotency_ttl_s=0)
        bid = seed_round(env.store)
        assert upload(env.client, bid, KEY).status_code == 200
        assert error_of(upload(env.client, bid, KEY)) == (409, "invalid_state")

    def test_the_preflight_allows_the_header(self, settings):
        env = make_capped(settings)
        response = env.client.options(
            "/api/briefings/b_aaaaaaaaaaaa/rounds/1/check",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": f"x-sib-device,{KEY_HEADER.lower()}",
            },
        )
        assert response.status_code == 200
        assert KEY_HEADER.lower() in response.headers["access-control-allow-headers"].lower()


def fake_request(store, settings: Settings, key: str | None = KEY):
    headers = Headers({KEY_HEADER: key} if key else {})
    ctx = SimpleNamespace(settings=settings, repo=Repo(store))
    return SimpleNamespace(headers=headers, app=SimpleNamespace(state=SimpleNamespace(ctx=ctx)))


def judging_run(store, bid: str, gate: asyncio.Event, calls: list[int]):
    """A stand-in for the check: counts its calls, waits for `gate`, then judges round 1."""
    repo = Repo(store)

    async def run() -> Round:
        calls.append(1)
        await gate.wait()

        def judge(cur) -> None:
            cur.rounds[0].judged_at = now_iso()
            cur.status = "judged"

        return (await repo.mutate(bid, CALLER.owner, judge)).rounds[0]

    return run


@pytest.mark.parametrize("make_store", [LocalStore, None], ids=["local", "firestore"])
class TestConcurrentRetry:
    def store_for(self, make_store, settings):
        return make_store(settings.data_dir) if make_store else FakeBackedStore()

    def test_a_retry_while_the_first_upload_runs_waits_for_its_round(self, make_store, settings):
        store = self.store_for(make_store, settings)
        bid = seed_round(store)
        gate, calls = asyncio.Event(), []
        run = judging_run(store, bid, gate, calls)

        async def both():
            first = asyncio.create_task(
                idempotent_check(fake_request(store, settings), bid, 1, CALLER, run)
            )
            await asyncio.sleep(0.05)
            retry = asyncio.create_task(
                idempotent_check(fake_request(store, settings), bid, 1, CALLER, run)
            )
            await asyncio.sleep(0.3)  # the retry is waiting, not running
            assert len(calls) == 1 and not retry.done()
            gate.set()
            return await first, await retry

        first, retry = asyncio.run(both())

        assert len(calls) == 1
        assert first.wire() == retry.wire() and retry.judged_at is not None

    def test_a_retry_after_a_failed_first_upload_runs_the_check(self, make_store, settings):
        store = self.store_for(make_store, settings)
        bid = seed_round(store)

        async def boom() -> Round:
            raise RuntimeError("the connection to the model dropped")

        gate, calls = asyncio.Event(), []
        gate.set()

        async def flow():
            with pytest.raises(RuntimeError):
                await idempotent_check(fake_request(store, settings), bid, 1, CALLER, boom)
            return await idempotent_check(
                fake_request(store, settings), bid, 1, CALLER, judging_run(store, bid, gate, calls)
            )

        assert asyncio.run(flow()).judged_at is not None and calls == [1]

    def test_a_retry_gives_up_with_409_check_in_progress_at_its_budget(self, make_store, settings):
        store = self.store_for(make_store, settings)
        bid = seed_round(store)
        quick = settings.with_overrides(request_timeout_s=0.3)
        gate, calls = asyncio.Event(), []
        run = judging_run(store, bid, gate, calls)

        async def flow():
            first = asyncio.create_task(idempotent_check(fake_request(store, quick), bid, 1, CALLER, run))
            await asyncio.sleep(0.05)
            with pytest.raises(InvalidState) as refused:
                await idempotent_check(fake_request(store, quick), bid, 1, CALLER, run)
            gate.set()
            await first
            return refused.value

        assert asyncio.run(flow()).code == "check_in_progress" and calls == [1]

    def test_an_expired_pending_claim_does_not_block(self, make_store, settings):
        """A claim left by an instance that died mid-check expires; the retry then runs."""
        store = self.store_for(make_store, settings)
        bid = seed_round(store)
        digest = key_digest(CALLER.owner, bid, 1, KEY)
        stale = {"state": "pending", "expiresAt": "2000-01-01T00:00:00.000Z"}
        asyncio.run(store.set_check_key(digest, stale))
        gate, calls = asyncio.Event(), []
        gate.set()
        run = judging_run(store, bid, gate, calls)

        judged = asyncio.run(idempotent_check(fake_request(store, settings), bid, 1, CALLER, run))

        assert judged.judged_at is not None and calls == [1]


class TestStoreRecords:
    @pytest.mark.parametrize("make_store", [LocalStore, None], ids=["local", "firestore"])
    def test_claim_holds_until_expiry_and_set_none_drops_it(self, make_store, settings):
        from datetime import UTC, datetime, timedelta

        store = make_store(settings.data_dir) if make_store else FakeBackedStore()
        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        digest = "a" * 64
        mine = {"state": "pending", "expiresAt": iso(now + timedelta(seconds=10))}

        async def flow():
            assert await store.claim_check_key(digest, mine, now) is None
            assert await store.claim_check_key(digest, {**mine, "state": "x"}, now) == mine
            later = now + timedelta(seconds=11)
            assert await store.claim_check_key(digest, {**mine, "state": "y"}, later) is None
            await store.set_check_key(digest, None)
            assert await store.claim_check_key(digest, mine, now) is None

        asyncio.run(flow())

    def test_the_local_store_refuses_a_name_that_is_not_a_digest(self, settings):
        with pytest.raises(ValueError):
            asyncio.run(LocalStore(settings.data_dir).set_check_key("../escape", None))


class TestSettings:
    def test_default_is_an_hour(self):
        assert Settings.from_env({}).idempotency_ttl_s == 3600

    @pytest.mark.parametrize("raw", ["-1", "86401"])
    def test_out_of_range_stops_start_up(self, raw):
        with pytest.raises(ConfigError):
            Settings.from_env({"SIB_IDEMPOTENCY_TTL_S": raw})

    def test_zero_is_allowed(self):
        assert Settings.from_env({"SIB_IDEMPOTENCY_TTL_S": "0"}).idempotency_ttl_s == 0


def test_request_key_rejects_an_empty_value():
    request = SimpleNamespace(headers=Headers({KEY_HEADER: ""}))
    from sayitback.idempotency import request_key

    with pytest.raises(Unprocessable):
        request_key(request)  # type: ignore[arg-type]
