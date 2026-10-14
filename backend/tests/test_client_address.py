"""The client address and the per-minute limiter (API.md v0.3; security review S3 and S15).

The address is the X-Forwarded-For entry `SIB_TRUSTED_PROXY_HOPS` from the right, the one Cloud
Run's front end appended: the entries to its left are the caller's own words. The limiter that keys
on it stays small and cheap however many addresses it is shown.
"""

from __future__ import annotations

import contextlib
import time

import pytest
from starlette.requests import HTTPConnection

from sayitback.errors import RateLimited
from sayitback.ratelimit import MAX_KEYS, RateLimiter, client_ip
from sayitback.settings import MAX_PROXY_HOPS, ConfigError, Settings
from tests.fakes import FakeTtsClient
from tests.helpers import PANEL, SPOKEN, api_client, error_of, make_app, seed_round


def conn(*forwarded: str, peer: tuple[str, int] | None = ("10.0.0.1", 4242)) -> HTTPConnection:
    """A connection whose X-Forwarded-For arrived as one header line per argument."""
    headers = [(b"x-forwarded-for", line.encode()) for line in forwarded]
    return HTTPConnection({"type": "http", "headers": headers, "client": peer})


class TestWhichEntryIsTheClient:
    def test_it_is_the_last_entry_the_one_the_front_end_appended(self):
        assert client_ip(conn("198.51.100.7"), 1) == "198.51.100.7"
        assert client_ip(conn("203.0.113.9, 198.51.100.7"), 1) == "198.51.100.7"

    def test_what_the_caller_wrote_to_the_left_is_never_read(self):
        """Review F1: the leftmost entry was the key, and the client chose it."""
        forged = "1.2.3.4, 5.6.7.8, 9.9.9.9, 198.51.100.7"
        assert client_ip(conn(forged), 1) == "198.51.100.7"

    def test_hops_count_from_the_right(self):
        chain = "203.0.113.9, 198.51.100.7, 192.0.2.1"
        assert [client_ip(conn(chain), n) for n in (1, 2, 3)] == [
            "192.0.2.1",
            "198.51.100.7",
            "203.0.113.9",
        ]

    def test_with_no_such_entry_the_socket_peer_is_the_client(self):
        assert client_ip(conn(), 1) == "10.0.0.1"
        assert client_ip(conn("198.51.100.7"), 2) == "10.0.0.1"  # one entry, two hops
        assert client_ip(conn(peer=None), 1) == "unknown"

    def test_zero_hops_means_no_proxy_so_the_header_is_ignored(self):
        assert client_ip(conn("198.51.100.7"), 0) == "10.0.0.1"

    def test_several_header_lines_are_one_list_in_order(self):
        """A proxy may add its own line instead of extending the first."""
        assert client_ip(conn("203.0.113.9", "198.51.100.7"), 1) == "198.51.100.7"
        assert client_ip(conn("203.0.113.9", "198.51.100.7, 192.0.2.1"), 2) == "198.51.100.7"

    def test_spaces_around_entries_are_dropped(self):
        assert client_ip(conn("  203.0.113.9 ,  198.51.100.7  "), 1) == "198.51.100.7"

    @pytest.mark.parametrize("bad", ["", "unknown", "198.51.100.7:8080", "not-an-ip", "1.2.3"])
    def test_a_trusted_entry_that_is_not_an_address_falls_back_to_the_peer(self, bad):
        """No key built from a made-up string, and no string of any length as a key."""
        assert client_ip(conn(f"203.0.113.9, {bad}"), 1) == "10.0.0.1"
        assert client_ip(conn(f"203.0.113.9, 198.51.100.7, {bad}"), 1) == "10.0.0.1"

    def test_a_peer_that_is_not_an_address_is_used_as_it_is(self):
        """The test client's peer is 'testclient'; a Unix socket has none ('unknown')."""
        assert client_ip(conn(peer=("testclient", 50000)), 1) == "testclient"


class TestOneKeyPerClientNotPerAddress:
    def test_an_ipv6_address_stands_for_its_slash_64(self):
        """Its owner can use any address in the prefix, so a limit on the exact one never binds."""
        a = client_ip(conn("2001:db8:1:2:aaaa:bbbb:cccc:dddd"), 1)
        b = client_ip(conn("2001:db8:1:2::1"), 1)
        elsewhere = client_ip(conn("2001:db8:1:3::1"), 1)
        assert a == b == "2001:db8:1:2::/64" and elsewhere == "2001:db8:1:3::/64"

    def test_ipv6_in_any_spelling_is_one_key(self):
        spellings = ["2001:DB8:1:2:0:0:0:5", "2001:db8:1:2::5", "2001:0db8:0001:0002::0005"]
        assert len({client_ip(conn(s), 1) for s in spellings}) == 1

    def test_an_ipv4_mapped_ipv6_address_is_the_ipv4_address(self):
        assert client_ip(conn("::ffff:198.51.100.7"), 1) == "198.51.100.7"

    def test_the_peer_is_normalised_the_same_way(self):
        assert client_ip(conn(peer=("2001:db8:1:2::9", 1)), 1) == "2001:db8:1:2::/64"
        assert client_ip(conn(peer=("198.51.100.7", 1)), 1) == "198.51.100.7"


class TestASpoofedHeaderBuysNothing:
    def test_review_f1_fresh_leftmost_entries_do_not_get_fresh_allowances(self, settings):
        """With the limit at 1 a minute, 20 calls that each wrote a new leftmost entry all passed."""
        app, _rt, _llm, store = make_app(settings.with_overrides(rate_limit_per_min=1))
        client = api_client(app)
        first = client.post(
            "/api/briefings", json=PANEL, headers={"X-Forwarded-For": "203.0.113.9"}
        )
        assert first.status_code == 200
        for i in range(20):
            forged = {
                "X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"
            }  # the front end appended 203.0.113.9
            refused = client.post("/api/briefings", json=PANEL, headers=forged)
            assert error_of(refused) == (429, "rate_limited"), i

    def test_a_different_appended_address_is_a_different_client(self, settings):
        app, *_ = make_app(settings.with_overrides(rate_limit_per_min=1))
        client = api_client(app)
        for i in range(5):
            headers = {"X-Forwarded-For": f"10.0.0.1, 203.0.113.{i}"}
            assert client.post("/api/briefings", json=PANEL, headers=headers).status_code == 200

    def test_the_proxy_setting_reaches_the_limiter(self, settings):
        """Two hops: the address two from the right is the client, and the last is a proxy."""
        app, *_ = make_app(settings.with_overrides(rate_limit_per_min=1, trusted_proxy_hops=2))
        client = api_client(app)
        ok = {"X-Forwarded-For": "198.51.100.7, 192.0.2.1"}
        assert client.post("/api/briefings", json=PANEL, headers=ok).status_code == 200
        same = {"X-Forwarded-For": "forged, 198.51.100.7, 192.0.2.2"}
        assert client.post("/api/briefings", json=PANEL, headers=same).status_code == 429


class TestTheSetting:
    def test_the_default_is_one_hop(self):
        assert Settings.from_env({}).trusted_proxy_hops == 1

    @pytest.mark.parametrize("value", ["0", "1", "2", " 3 ", str(MAX_PROXY_HOPS)])
    def test_a_small_whole_number_is_read(self, value):
        got = Settings.from_env({"SIB_TRUSTED_PROXY_HOPS": value}).trusted_proxy_hops
        assert got == int(value)

    @pytest.mark.parametrize("value", ["-1", str(MAX_PROXY_HOPS + 1), "1.5", "two", "1e1", "1 hop"])
    def test_anything_else_fails_at_start_up(self, value):
        with pytest.raises(ConfigError, match="SIB_TRUSTED_PROXY_HOPS"):
            Settings.from_env({"SIB_TRUSTED_PROXY_HOPS": value})

    def test_the_service_does_not_start_with_a_bad_value(self, monkeypatch):
        from sayitback.main import create_app

        monkeypatch.setenv("SIB_TRUSTED_PROXY_HOPS", "many")
        with pytest.raises(ConfigError):
            create_app()


class TestTheLimiterStaysSmallAndCheap:
    def test_the_table_never_holds_more_than_its_limit_of_keys(self):
        limiter = RateLimiter(5, clock=lambda: 0.0, max_keys=4)
        for i in range(50):
            limiter.check(f"198.51.100.{i}")
        assert len(limiter._hits) == 4
        assert list(limiter._hits) == [f"198.51.100.{i}" for i in range(46, 50)]  # the latest four

    def test_a_key_pushed_out_starts_again_with_a_clean_window(self):
        """The limit is best effort: it protects the quota from one noisy client."""
        limiter = RateLimiter(1, clock=lambda: 0.0, max_keys=2)
        limiter.check("a")
        with pytest.raises(RateLimited):
            limiter.check("a")
        limiter.check("b")
        limiter.check("c")  # "a" is the least recently used: out
        limiter.check("a")

    def test_idle_keys_are_forgotten_as_time_passes(self):
        now = [0.0]
        limiter = RateLimiter(3, clock=lambda: now[0])
        for i in range(100):
            limiter.check(f"198.51.100.{i}")
        assert len(limiter._hits) == 100
        now[0] = 61.0
        limiter.check("203.0.113.1")
        assert list(limiter._hits) == ["203.0.113.1"]

    def test_a_key_in_use_is_not_forgotten(self):
        now = [0.0]
        limiter = RateLimiter(3, clock=lambda: now[0])
        limiter.check("busy")
        now[0] = 40.0
        limiter.check("quiet")
        limiter.check("busy")
        now[0] = 70.0  # "quiet" last hit at 40 s, "busy" at 40 s: both still in their minute
        limiter.check("new")
        assert set(limiter._hits) == {"busy", "quiet", "new"}

    def test_a_hammered_key_costs_a_few_timestamps_not_a_request_log(self):
        limiter = RateLimiter(3, clock=lambda: 0.0)
        for _ in range(1000):
            with contextlib.suppress(RateLimited):
                limiter.check("noisy")
        assert len(limiter._hits) == 1 and len(limiter._hits["noisy"]) == 3

    def test_the_window_still_slides_and_the_wait_is_still_reported(self):
        now = [0.0]
        limiter = RateLimiter(3, clock=lambda: now[0])
        for _ in range(3):
            limiter.check("a")
        with pytest.raises(RateLimited) as err:
            limiter.check("a")
        assert err.value.retry_after == 60
        now[0] = 59.0
        with pytest.raises(RateLimited) as err:
            limiter.check("a")
        assert err.value.retry_after == 1
        now[0] = 60.5
        limiter.check("a")

    def test_review_s15_a_flood_of_addresses_costs_each_request_the_same(self):
        """Over 10,000 keys the old limiter rebuilt its whole table on every request, and kept every
        key seen in the last minute, so a flood left it doing that for a minute. 30,000 distinct
        addresses took it tens of seconds; here it is a few dozen milliseconds."""
        limiter = RateLimiter(30, clock=lambda: 0.0)
        started = time.perf_counter()
        for i in range(3 * MAX_KEYS):
            limiter.check(f"key-{i}")
        elapsed = time.perf_counter() - started
        assert len(limiter._hits) == MAX_KEYS
        assert elapsed < 3.0, f"{3 * MAX_KEYS} distinct keys took {elapsed:.2f} s"


def test_the_limit_applies_to_what_the_front_end_appended_for_tts_too(settings):
    """The same address rule for a Gemini-backed endpoint (here TTS, with a briefing seeded)."""
    s = settings.with_overrides(rate_limit_per_min=1)
    app, _rt, _llm, store = make_app(s, tts_client=FakeTtsClient())
    client = api_client(app)
    body = {"briefingId": seed_round(store), "n": 1, "text": SPOKEN[:4]}
    first = client.post("/api/tts", json=body, headers={"X-Forwarded-For": "7.7.7.7, 203.0.113.9"})
    assert first.status_code == 200
    again = client.post("/api/tts", json=body, headers={"X-Forwarded-For": "8.8.8.8, 203.0.113.9"})
    assert error_of(again) == (429, "rate_limited")
