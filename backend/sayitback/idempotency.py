"""Idempotent answer uploads (endpoint 13, `Idempotency-Key`, 2026-10-16).

On a weak signal the browser retries the check upload when the connection drops, and the first
upload may have reached the server: it may still be running, or it may have judged the round and
lost only its response. A retry with the same key must then return that round, with no second model
call and no second daily-cap charge.

Each upload with a key claims a record in the store, under the SHA-256 of (owner, briefing, round,
key), so the key itself is never stored and another device's key can never match. The record is
`pending` while the first upload runs (it expires a little after the request budget, so a crashed
instance cannot hold it) and `done` once it judged the round (it expires after
SIB_IDEMPOTENCY_TTL_S). A retry that finds `pending` waits for it, polling with backoff (0.25 s
doubling to 2 s, security fixes B: about 64 store reads over a 120 s budget, not 480); one that
finds `done` answers with the judged round from the briefing. A failed upload drops its claim, so
its retry runs the check again, as a supervisor's Retry does today. Without a key, or with a
different key for a round that is already judged, nothing changes (409 `invalid_state`).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request

from sayitback.caller import Caller
from sayitback.daily_cap import utc_now
from sayitback.errors import InvalidState, Unprocessable
from sayitback.models import Round
from sayitback.store.base import iso

KEY_HEADER = "Idempotency-Key"
KEY = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
PENDING, DONE = "pending", "done"
PENDING_MARGIN_S = 15.0  # a pending claim outlives the request budget by this much
POLL_S = 0.25  # the first wait for another upload's check; each wait doubles, up to POLL_MAX_S
POLL_MAX_S = 2.0


def request_key(request: Request) -> str | None:
    """The upload's key, or None without one. A malformed key or two of them is 422: the value is
    never echoed (it works like a capability for this round's result)."""
    values = request.headers.getlist(KEY_HEADER)
    if not values:
        return None
    if len(values) > 1 or not KEY.fullmatch(values[0]):
        raise Unprocessable(
            f"{KEY_HEADER} must be one value of 16 to 64 characters: letters, digits, _ and -."
        )
    return values[0]


def key_digest(owner: str, briefing_id: str, n: int, key: str) -> str:
    return hashlib.sha256(f"{owner}\n{briefing_id}\n{n}\n{key}".encode()).hexdigest()


def _record(state: str, now: datetime, ttl_s: float) -> dict[str, str]:
    return {"state": state, "expiresAt": iso(now + timedelta(seconds=ttl_s))}


async def idempotent_check(
    request: Request,
    briefing_id: str,
    n: int,
    caller: Caller,
    run: Callable[[], Awaitable[Round]],
    *,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    clock: Callable[[], float] | None = None,
) -> Round:
    """Run the check (`run`) once per key: a retry with the same key gets the round the first
    upload judged. With no key, or SIB_IDEMPOTENCY_TTL_S=0, this is just `run()`. Tests pass
    `sleep` and `clock` (the event loop's by default) to count the polls of a long wait."""
    ctx = request.app.state.ctx
    s = ctx.settings
    key = request_key(request)
    if key is None or s.idempotency_ttl_s <= 0:
        return await run()
    store = ctx.repo.store
    digest = key_digest(caller.owner, briefing_id, n, key)
    pending_ttl = s.request_timeout_s + PENDING_MARGIN_S
    clock = clock or asyncio.get_running_loop().time
    deadline = clock() + s.request_timeout_s
    wait = POLL_S
    while True:
        now = utc_now()
        held = await store.claim_check_key(digest, _record(PENDING, now, pending_ttl), now)
        if held is None:
            break  # this upload holds the claim
        if held.get("state") == DONE:
            briefing = await ctx.repo.get(briefing_id, caller.owner)
            judged = briefing.round_n(n)
            if judged is not None and judged.judged_at is not None:
                return judged
            return await run()  # cannot happen (a done claim judged its round): as without a key
        left = deadline - clock()
        if left <= 0:
            raise InvalidState(
                "These answers are still being checked. Try again in a moment.",
                code="check_in_progress",
            )
        await sleep(min(wait, left))  # the last wait ends at the budget, never after it
        wait = min(wait * 2, POLL_MAX_S)
    try:
        judged = await run()
    except BaseException:
        await store.set_check_key(digest, None)  # failed: the retry runs the check again
        raise
    await store.set_check_key(digest, _record(DONE, utc_now(), s.idempotency_ttl_s))
    return judged
