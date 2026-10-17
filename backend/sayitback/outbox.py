"""SIB_OUTBOX: durable delivery of each decision to the permit system (docs/EPERMIT_ADAPTER.md).

Off by default, so the decision behaves as in v0.5. With it on, the decision first stores one
delivery per target (every SIB_WEBHOOK_URL entry, plus SIB_PTW_URL) in the store's outbox
(`outbox/{briefingId}`; local files or Firestore), then tries them at once, each within
SIB_WEBHOOK_TIMEOUT_S, before it answers. Each target keeps `status` (pending, delivered, failed),
`attempts`, `lastError` (a class: http_503, timeout, ConnectError; never a URL, a header or a
body), `nextAttemptAt` and `deliveredAt`.

- Retries: a post that timed out, could not connect, or got 408/425/429/5xx waits
  SIB_OUTBOX_BACKOFF_S, doubling each time up to SIB_OUTBOX_MAX_BACKOFF_S, and is `failed` after
  SIB_OUTBOX_MAX_ATTEMPTS. Any other 4xx is a refusal: `failed` at once, never retried. Cloud Run
  gives an instance CPU only while it serves a request, so the retries run inside one:
  POST /admin/outbox/retry (bearer SIB_OUTBOX_TOKEN), which Cloud Scheduler calls (api/outbox.py).
- Never twice by accident: an attempt first claims its due targets in one atomic update (attempts
  + 1, the next attempt pushed past the post's own cut-off), so two passes never post one target
  at the same time, and an instance that dies mid-post leaves a claim that expires and is retried.
  Every post of a decision carries the same Idempotency-Key, and the receiver keeps one.
- The store holds no URL and no token: a target is a SHA-256 prefix of its URL (webhook.Target.id),
  matched to the configured targets at each attempt. One no longer configured is `target_removed`;
  a briefing no longer stored (retention) is `briefing_gone`. Both are failed, never retried.
- The record shows it: `delivery` on endpoints 6 and 14 (`public`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sayitback import webhook
from sayitback.models import Briefing
from sayitback.settings import Settings
from sayitback.store import Store
from sayitback.store.base import iso
from sayitback.webhook import Outcome, WebhookSender, idempotency_key

log = logging.getLogger("sayitback.outbox")
PENDING, DELIVERED, FAILED = "pending", "delivered", "failed"
NOTHING_DUE = "9999-12-31T23:59:59.999Z"  # `due` with nothing pending: the ordered query needs it
PUBLIC_FIELDS = ("kind", "status", "attempts", "lastError", "nextAttemptAt", "deliveredAt")
Doc = dict[str, Any]


def backoff_s(attempts: int, base_s: float, ceiling_s: float) -> float:
    """The wait after the `attempts`-th failed try: base, then doubling, at most the ceiling."""
    return min(base_s * 2 ** max(attempts - 1, 0), ceiling_s)


def overall(targets: list[Doc]) -> str:
    """Pending while any target is; else failed if any failed; else delivered."""
    statuses = {t["status"] for t in targets}
    return PENDING if PENDING in statuses else FAILED if FAILED in statuses else DELIVERED


def public(doc: Doc | None) -> Doc | None:
    """What the record shows: no target id, URL, host, key or token."""
    if doc is None:
        return None
    targets = [{name: t.get(name) for name in PUBLIC_FIELDS} for t in doc["targets"]]
    return {"status": overall(doc["targets"]), "targets": targets}


def _due(targets: list[Doc]) -> str:
    return min((t["nextAttemptAt"] for t in targets if t["status"] == PENDING), default=NOTHING_DUE)


def _now() -> datetime:
    return datetime.now(UTC)


class Outbox:
    def __init__(
        self,
        store: Store,
        sender: WebhookSender,
        settings: Settings,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.store, self.sender, self._clock = store, sender, clock
        self.timeout_s = settings.webhook_timeout_s
        self.max_attempts = settings.outbox_max_attempts
        self.backoff = (settings.outbox_backoff_s, settings.outbox_max_backoff_s)
        self.batch = settings.outbox_retry_batch

    def __repr__(self) -> str:
        return f"Outbox({self.sender!r})"

    def _new(self, b: Briefing) -> Doc:
        stamp, key = iso(self._clock()), idempotency_key(b)
        targets = [
            {"id": t.id, "kind": t.kind, "adapter": t.adapter, "key": key, "status": PENDING,
             "attempts": 0, "lastError": None, "nextAttemptAt": stamp, "lastAttemptAt": None,
             "deliveredAt": None}
            for t in self.sender.targets
        ]  # fmt: skip
        return {"briefingId": b.id, "createdAt": stamp, "due": stamp, "targets": targets}

    async def deliver(self, b: Briefing) -> Doc | None:
        """At the decision: store its deliveries (once: a repeat keeps the first), then try every
        due target now. Never raises; with the store down it posts directly, as without the
        outbox. The record's `delivery`, or None."""
        if not self.sender.enabled or b.decision is None:
            return None
        try:
            await self.store.outbox_update(b.id, lambda doc: None if doc else self._new(b))
        except Exception as exc:  # noqa: BLE001 - the decision stands; send as v0.5 did
            log.warning("outbox not stored, posting directly: %s", type(exc).__name__)
            await webhook.deliver(self.sender, b, self.timeout_s)
            return None
        return public(await self._attempt(b.id, b))

    async def status(self, briefing_id: str) -> Doc | None:
        try:
            return public(await self.store.outbox_get(briefing_id))
        except Exception as exc:  # noqa: BLE001 - a status line must not fail the record
            log.warning("outbox status unavailable: %s", type(exc).__name__)
            return None

    async def retry_due(self) -> dict[str, int]:
        """One pass: every briefing with a target due now, at most SIB_OUTBOX_RETRY_BATCH, all at
        once. Counts the briefings by their status after the pass."""
        ids = await self.store.outbox_due(iso(self._clock()), self.batch)
        docs = await asyncio.gather(*(self._attempt(i) for i in ids))
        summary = {"checked": len(ids), DELIVERED: 0, PENDING: 0, FAILED: 0}
        for doc in docs:
            if doc is not None:
                summary[overall(doc["targets"])] += 1
        return summary

    async def _attempt(self, briefing_id: str, b: Briefing | None = None) -> Doc | None:
        """Claim the due targets, post them, record what happened. Never raises."""
        try:
            claimed: list[str] = []
            doc = await self.store.outbox_update(briefing_id, lambda d: self._claim(d, claimed))
            if not claimed:
                return doc
            if b is None:
                raw = await self.store.get(briefing_id)
                b = Briefing.model_validate(raw) if raw else None
            outcomes = await self._send(b, list(claimed))
            return await self.store.outbox_update(briefing_id, lambda d: self._settle(d, outcomes))
        except Exception as exc:  # noqa: BLE001 - the claim expires and a later pass retries
            log.warning("outbox attempt failed: %s", type(exc).__name__)
            return None

    def _claim(self, doc: Doc | None, claimed: list[str]) -> Doc | None:
        claimed.clear()  # a retried transaction runs this again from the stored document
        if doc is None:
            return None
        now = self._clock()
        stamp, lease = iso(now), iso(now + timedelta(seconds=2 * self.timeout_s + 1))
        for t in doc["targets"]:
            if t["status"] == PENDING and t["nextAttemptAt"] <= stamp:
                t["attempts"] += 1
                t["lastAttemptAt"], t["nextAttemptAt"] = stamp, lease
                claimed.append(t["id"])
        if not claimed:
            return None
        doc["due"] = _due(doc["targets"])
        return doc

    async def _send(self, b: Briefing | None, ids: list[str]) -> dict[str, Outcome]:
        if b is None or b.decision is None:
            return {i: Outcome(False, error="briefing_gone") for i in ids}
        configured = {t.id: t for t in self.sender.targets}
        outcomes = {i: Outcome(False, error="target_removed") for i in ids if i not in configured}
        live = [configured[i] for i in ids if i in configured]
        async with self.sender.client() as http:
            results = await asyncio.gather(*(self.sender.attempt(http, t, b) for t in live))
        return {**outcomes, **{t.id: r for t, r in zip(live, results, strict=True)}}

    def _settle(self, doc: Doc | None, outcomes: dict[str, Outcome]) -> Doc | None:
        if doc is None:
            return None
        now = self._clock()
        for t in doc["targets"]:
            outcome = outcomes.get(t["id"])
            if outcome is None or t["status"] != PENDING:
                continue
            t["lastError"] = outcome.error
            if outcome.delivered:
                t["status"], t["deliveredAt"], t["nextAttemptAt"] = DELIVERED, iso(now), None
            elif outcome.retry and t["attempts"] < self.max_attempts:
                wait = backoff_s(t["attempts"], *self.backoff)
                t["nextAttemptAt"] = iso(now + timedelta(seconds=wait))
            else:
                t["status"], t["nextAttemptAt"] = FAILED, None
                log.warning(
                    "outbox gave up on a %s target after %d attempt(s): %s",
                    t["kind"],
                    t["attempts"],
                    outcome.error,
                )
        doc["due"] = _due(doc["targets"])
        return doc
