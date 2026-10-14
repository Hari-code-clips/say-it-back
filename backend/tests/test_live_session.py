"""Live tickets: random, single use, 120 s, hash-only storage, two per round, across instances."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from sayitback import live_session
from sayitback.errors import RateLimited
from sayitback.settings import Settings
from sayitback.store import LocalStore

NOW = datetime(2026, 10, 14, 10, 0, 0, tzinfo=UTC)
BID = "b_abcdefghijkl"
OWNER = "1" * 64  # the SHA-256 of a device key


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path / ".data")


def stored_text(root) -> str:
    """Everything the store wrote: file names and contents."""
    return "\n".join(
        f"{p.relative_to(root)}\n{p.read_text()}" for p in root.rglob("*") if p.is_file()
    )


async def test_a_ticket_is_random_and_unguessable():
    tickets = {live_session.new_ticket() for _ in range(50)}
    assert len(tickets) == 50
    assert all(len(t) >= 43 for t in tickets)  # 32 random bytes, base64url


async def test_a_ticket_redeems_once(store):
    ticket, _ = await live_session.issue_ticket(store, Settings(), BID, 1, owner=OWNER, now=NOW)
    first = await live_session.redeem_ticket(store, ticket, now=NOW + timedelta(seconds=5))
    second = await live_session.redeem_ticket(store, ticket, now=NOW + timedelta(seconds=6))
    assert first and first["briefingId"] == BID and first["n"] == 1
    assert second is None


async def test_a_ticket_expires_after_120_seconds(store):
    ticket, expires = await live_session.issue_ticket(
        store, Settings(), BID, 1, owner=OWNER, now=NOW
    )
    assert expires == "2026-10-14T10:02:00.000Z"
    assert await live_session.redeem_ticket(store, ticket, now=NOW + timedelta(seconds=121)) is None


async def test_a_ticket_still_works_just_before_it_expires(store):
    ticket, _ = await live_session.issue_ticket(store, Settings(), BID, 1, owner=OWNER, now=NOW)
    assert (
        await live_session.redeem_ticket(store, ticket, now=NOW + timedelta(seconds=119))
        is not None
    )


async def test_an_unknown_or_malformed_ticket_is_refused(store):
    for ticket in ("", "nope", "a" * 400, "../../etc/passwd", "b_abcdefghijkl"):
        assert await live_session.redeem_ticket(store, ticket, now=NOW) is None


async def test_only_the_sha256_is_stored_never_the_ticket(store, tmp_path):
    ticket, _ = await live_session.issue_ticket(store, Settings(), BID, 1, owner=OWNER, now=NOW)
    on_disk = stored_text(tmp_path / ".data")
    assert ticket not in on_disk
    assert hashlib.sha256(ticket.encode()).hexdigest() in on_disk
    assert live_session.digest_of(ticket) == hashlib.sha256(ticket.encode()).hexdigest()


async def test_at_most_two_tickets_per_round(store):
    s = Settings()
    await live_session.issue_ticket(store, s, BID, 1, owner=OWNER, now=NOW)
    await live_session.issue_ticket(store, s, BID, 1, owner=OWNER, now=NOW)
    with pytest.raises(RateLimited) as err:
        await live_session.issue_ticket(store, s, BID, 1, owner=OWNER, now=NOW)
    assert (err.value.status, err.value.code) == (429, "limit")
    await live_session.issue_ticket(
        store, s, BID, 2, owner=OWNER, now=NOW
    )  # another round has its own allowance


async def test_a_spent_ticket_still_counts_against_the_allowance(store):
    s = Settings()
    ticket, _ = await live_session.issue_ticket(store, s, BID, 1, owner=OWNER, now=NOW)
    await live_session.redeem_ticket(store, ticket, now=NOW)
    await live_session.issue_ticket(store, s, BID, 1, owner=OWNER, now=NOW)
    with pytest.raises(RateLimited):
        await live_session.issue_ticket(store, s, BID, 1, owner=OWNER, now=NOW)


async def test_tickets_live_in_the_store_so_a_second_instance_can_redeem(store, tmp_path):
    ticket, _ = await live_session.issue_ticket(store, Settings(), BID, 1, owner=OWNER, now=NOW)
    other_instance = LocalStore(tmp_path / ".data")  # a different process would see the same files
    assert await live_session.redeem_ticket(other_instance, ticket, now=NOW) is not None
    assert (
        await live_session.redeem_ticket(store, ticket, now=NOW) is None
    )  # and it is spent for both


async def test_a_ticket_names_the_owner_it_was_issued_to(store):
    ticket, _ = await live_session.issue_ticket(store, Settings(), BID, 1, owner=OWNER, now=NOW)
    record = await live_session.redeem_ticket(store, ticket, now=NOW)
    assert live_session.ticket_owner(record, BID, 1) == OWNER


@pytest.mark.parametrize(
    ("record", "briefing_id", "n"),
    [
        (None, BID, 1),
        ({"briefingId": BID, "n": 1}, BID, 1),  # issued with no owner: nobody
        ({"briefingId": BID, "n": 1, "owner": ""}, BID, 1),
        ({"briefingId": BID, "n": 1, "owner": OWNER}, "b_zzzzzzzzzzzz", 1),  # another briefing
        ({"briefingId": BID, "n": 1, "owner": OWNER}, BID, 2),  # another round
    ],
)
def test_a_ticket_is_good_only_for_its_own_round_and_only_with_an_owner(record, briefing_id, n):
    assert live_session.ticket_owner(record, briefing_id, n) is None


def test_ws_url_is_absolute_with_a_public_base_and_a_path_without():
    assert live_session.ws_url(Settings(), BID, 2) == "/api/live/b_abcdefghijkl/2"
    s = Settings(public_ws_base="wss://say-it-back-api-x.a.run.app")
    assert (
        live_session.ws_url(s, BID, 2)
        == "wss://say-it-back-api-x.a.run.app/api/live/b_abcdefghijkl/2"
    )
