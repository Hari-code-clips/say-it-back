"""The daily cap on Gemini calls (API.md, "Daily cap"): one count for everyone, and one for each
client address.

The service is public, so the per-minute limit (in memory, per instance) cannot bound total spend.
The cap lives in the store instead: one counter per UTC day, shared by every instance and untouched
by a restart. A Gemini-backed request reserves the calls it is about to make in one atomic step,
after its validation and state checks and just before its first Gemini call. A request that does
not fit is refused with 429 `daily_limit` and makes no call. Nothing is refunded: a call that fails
after the reservation stays counted.

Each client address also has its own daily allowance (SIB_DAILY_CALLS_PER_IP), so one client cannot
spend the shared count that every visitor needs. It is kept under a SHA-256 of the day and the
address, never the address itself, and reserved in the same atomic step: either count refuses the
request, and then neither moves.

The counts are the model calls each request makes, read from the code, except the live ticket: its 4
is a weight for one Live session (the relay lets each cue and each answer window be used once, and
the script's length limits bound what is read, which together bound the session), charged with the
ticket and not per socket. A script retry (the second `write_script` call, made when the first
script fails the code checks) reserves SCRIPT_RETRY_CALLS just before it runs; if the cap refuses,
the round fails with 429 `daily_limit` and the retry is never made. One thing goes uncounted: the
SDK's one retry after a Gemini 429 or 5xx. A day can overshoot the cap by those few calls.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta

from sayitback.errors import RateLimited
from sayitback.settings import Settings
from sayitback.store import Store
from sayitback.store.base import Reserved

log = logging.getLogger("sayitback.daily_cap")

TRANSCRIBE_CALLS = 1  # endpoint 3: transcribe_instruction
EXTRACT_CALLS = 1  # endpoint 8: extract_steps
SCRIPT_CALLS = 2  # endpoint 10: write_script, then back_translate
RE_EXPLAIN_CALLS = 1  # endpoint 10: re_explain, only for a re-explain round with no supervisor note
SCRIPT_RETRY_CALLS = 1  # endpoint 10: the second write_script call, reserved just before it runs
LIVE_TICKET_CALLS = 4  # endpoint 11: a weight for one Live session, charged with its ticket
TTS_CALLS = 1  # endpoint 12: one generate_content; a cache hit makes none
CHECK_BASE_CALLS = 1  # endpoints 13 and 19: the blind transcriber, plus one call per judge pass
HAZARD_CALLS = 1  # endpoint 21 with audio: hazard_report; a tap (no audio) makes none

Clock = Callable[[], datetime]


def check_calls(s: Settings) -> int:
    """A check or an eval try: the blind transcriber plus one call per judge pass."""
    return CHECK_BASE_CALLS + s.judge_passes


def round_calls(kind: str, note: str) -> int:
    """A round: script and back-translation, plus a re-explanation the supervisor did not write."""
    explains = kind == "reexplain" and not note
    return SCRIPT_CALLS + (RE_EXPLAIN_CALLS if explains else 0)


def utc_now() -> datetime:
    return datetime.now(UTC)


def day_key(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y%m%d")


def seconds_until_utc_midnight(now: datetime) -> int:
    """Whole seconds from `now` to the next 00:00 UTC (a full day at midnight itself); never 0."""
    moment = now.astimezone(UTC)
    midnight = datetime.combine(moment.date() + timedelta(days=1), time.min, tzinfo=UTC)
    return max(1, math.ceil((midnight - moment).total_seconds()))


def address_key(day: str, address: str) -> str:
    """Where a client address's count for `day` is kept: a hash, so the store holds no address."""
    return hashlib.sha256(f"{day}:{address}".encode()).hexdigest()


class DailyCap:
    def __init__(
        self, store: Store, limit: int, clock: Clock = utc_now, per_address: int = 0
    ) -> None:
        self._store = store
        self._limit = limit
        self._per_address = per_address  # each client address's share; 0 = no per-address count
        self._clock = clock
        self._warned_day = ""

    async def reserve(self, calls: int, address: str) -> None:
        """Count `calls` against today's cap and `address`'s own allowance, or raise 429
        `daily_limit` so the caller makes none.

        A store failure propagates: with the count unknown the request is refused (500), so the
        cap fails closed."""
        if calls < 1:
            raise ValueError("a reservation is at least one call")
        now = self._clock()
        day = day_key(now)
        share = {}
        if self._per_address:
            share = {"address": address_key(day, address), "address_cap": self._per_address}
        outcome = await self._store.reserve_calls(day, calls, self._limit, **share)
        if outcome:
            return
        if outcome is Reserved.GLOBAL_FULL:  # a client over its own allowance is routine, not news
            self._warn_once(day)
        raise RateLimited(
            "The daily limit of AI calls has been reached. Try again after 00:00 UTC.",
            code="daily_limit",
            retry_after=seconds_until_utc_midnight(now),
        )

    def _warn_once(self, day: str) -> None:
        """One WARNING per UTC day per instance, for a log-based alert. No request content."""
        if self._warned_day != day:
            self._warned_day = day
            log.warning("daily Gemini call cap reached: limit %d, UTC day %s", self._limit, day)
