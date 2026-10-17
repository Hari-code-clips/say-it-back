"""Local store: JSON files under backend/.data/ (gitignored). Single process, for development.

Writes are atomic (temp file then rename) and serialised by a lock, so the read-modify-write in
`update` and `reserve_calls` is safe against concurrent requests in the one process: none of them
awaits while it holds the lock.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sayitback import retention
from sayitback.store.base import (
    BRIEFING_ID,
    DIGEST,
    ORG_ID,
    Briefing,
    Reserved,
    Store,
    check_key_is_live,
    iso,
    parse_iso,
    ticket_is_live,
)

SAFE_KEY = "abcdefghijklmnopqrstuvwxyz0123456789_."


class LocalStore(Store):
    def __init__(self, root: Path, retention_days: int = 0) -> None:
        self._root = root
        self._lock = threading.RLock()
        self.retention_days = retention_days  # retention.py: 0 = keep; make_store sets it

    def _briefing(self, path: Path) -> dict[str, Any] | None:
        """A stored briefing, or None. An expired one is deleted as it is read (retention.py)."""
        raw = self._read(path)
        if raw is not None and retention.is_expired(raw):
            path.unlink(missing_ok=True)
            (self._root / "outbox" / path.name).unlink(missing_ok=True)  # its deliveries go too
            return None
        return raw

    def _path(self, kind: str, name: str) -> Path:
        if not name or any(c not in SAFE_KEY for c in name):
            raise KeyError(name)
        return self._root / kind / f"{name}.json"

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def _write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            Path(tmp).replace(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    # Briefings -------------------------------------------------------------------------------

    async def create(self, briefing: Briefing) -> None:
        with self._lock:
            stored = retention.stamp(briefing, self.retention_days)
            self._write(self._path("briefings", briefing["id"]), stored)

    async def get(self, briefing_id: str) -> Briefing | None:
        if not BRIEFING_ID.fullmatch(briefing_id):
            return None
        with self._lock:
            return self._briefing(self._path("briefings", briefing_id))

    async def delete(self, briefing_id: str) -> None:
        if BRIEFING_ID.fullmatch(briefing_id):
            with self._lock:
                self._path("briefings", briefing_id).unlink(missing_ok=True)
                self._path("outbox", briefing_id).unlink(missing_ok=True)  # outbox.py: deliveries

    async def update(self, briefing_id: str, fn: Callable[[Briefing], Briefing]) -> Briefing:
        if not BRIEFING_ID.fullmatch(briefing_id):
            raise KeyError(briefing_id)
        with self._lock:
            path = self._path("briefings", briefing_id)
            current = self._briefing(path)
            if current is None:
                raise KeyError(briefing_id)
            updated = retention.keep_expiry(current, fn(deepcopy(current)))
            self._write(path, updated)
            return updated

    async def recent(self, limit: int, owner: str) -> list[Briefing]:
        with self._lock:
            folder = self._root / "briefings"
            items = [self._briefing(p) for p in folder.glob("b_*.json")] if folder.is_dir() else []
        rows = [i for i in items if i and owner and i.get("owner") == owner]
        return sorted(rows, key=lambda b: b["createdAt"], reverse=True)[:limit]

    # Tickets and the live lease ---------------------------------------------------------------

    async def issue_ticket(
        self, digest: str, record: dict[str, Any], *, key: str, max_per_round: int
    ) -> bool:
        if not DIGEST.fullmatch(digest):
            raise ValueError("ticket digest must be a SHA-256 hex string")
        with self._lock:
            counter_path = self._path("counters", key)
            count = (self._read(counter_path) or {}).get("tickets", 0)
            if count >= max_per_round:
                return False
            self._write(counter_path, {"tickets": count + 1})
            self._write(self._path("tickets", digest), record)
            return True

    async def redeem_ticket(self, digest: str, now: datetime) -> dict[str, Any] | None:
        if not DIGEST.fullmatch(digest):
            return None
        with self._lock:
            path = self._path("tickets", digest)
            record = self._read(path)
            if not ticket_is_live(record, now):
                return None
            assert record is not None
            record["usedAt"] = iso(now)
            self._write(path, record)
            return record

    async def acquire_live(self, key: str, owner: str, now: datetime, ttl_s: float) -> bool:
        with self._lock:
            path = self._path("live", key)
            held = self._read(path)
            if held and held["owner"] != owner and parse_iso(held["expiresAt"]) > now:
                return False
            self._write(path, {"owner": owner, "expiresAt": iso(now + timedelta(seconds=ttl_s))})
            return True

    async def release_live(self, key: str, owner: str) -> None:
        with self._lock:
            path = self._path("live", key)
            held = self._read(path)
            if held and held["owner"] == owner:
                path.unlink(missing_ok=True)

    # The daily Gemini call counts ---------------------------------------------------------------

    def _count(self, kind: str, name: str) -> tuple[Path, int]:
        path = self._path(kind, name)
        return path, (self._read(path) or {}).get("calls", 0)

    async def reserve_calls(
        self, day: str, calls: int, cap: int, *, address: str = "", address_cap: int = 0
    ) -> Reserved:
        with self._lock:
            mine, mine_used = self._count("gemini_calls_ip", address) if address else (None, 0)
            if mine is not None and mine_used + calls > address_cap:
                return Reserved.ADDRESS_FULL
            shared, used = self._count("gemini_calls", day)
            if used + calls > cap:
                return Reserved.GLOBAL_FULL
            self._write(shared, {"calls": used + calls})  # the shared count first: it is the spend
            if mine is not None:
                self._write(mine, {"calls": mine_used + calls})
            return Reserved.GRANTED

    # Idempotent answer uploads (idempotency.py) ---------------------------------------------------

    def _check_key(self, digest: str) -> Path:
        if not DIGEST.fullmatch(digest):
            raise ValueError("check key digest must be a SHA-256 hex string")
        return self._path("check_keys", digest)

    async def claim_check_key(
        self, digest: str, record: dict[str, Any], now: datetime
    ) -> dict[str, Any] | None:
        with self._lock:
            path = self._check_key(digest)
            held = self._read(path)
            if check_key_is_live(held, now):
                return held
            self._write(path, record)
            return None

    async def set_check_key(self, digest: str, record: dict[str, Any] | None) -> None:
        with self._lock:
            path = self._check_key(digest)
            if record is None:
                path.unlink(missing_ok=True)
            else:
                self._write(path, record)

    # The SOP library (sop_library.py) ----------------------------------------------------------

    async def get_sop_library(self, key: str) -> dict[str, Any] | None:
        if not DIGEST.fullmatch(key):
            return None
        with self._lock:
            return self._read(self._path("sop_library", key))

    async def update_sop_library(
        self, key: str, fn: Callable[[dict[str, Any] | None], dict[str, Any]]
    ) -> dict[str, Any]:
        if not DIGEST.fullmatch(key):
            raise KeyError(key)
        with self._lock:
            path = self._path("sop_library", key)
            updated = fn(self._read(path))
            self._write(path, updated)
            return updated

    # Org members (auth.py) -----------------------------------------------------------------------

    def _member_dir(self, org_id: str) -> Path:
        if not ORG_ID.fullmatch(org_id):
            raise KeyError(org_id)
        return self._root / "orgs" / org_id / "members"

    async def member_get(self, org_id: str, member_id: str) -> dict[str, Any] | None:
        if not (ORG_ID.fullmatch(org_id) and DIGEST.fullmatch(member_id)):
            return None
        with self._lock:
            return self._read(self._member_dir(org_id) / f"{member_id}.json")

    async def member_update(
        self,
        org_id: str,
        member_id: str,
        fn: Callable[[dict[str, Any] | None], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        if not DIGEST.fullmatch(member_id):
            raise KeyError(member_id)
        with self._lock:
            path = self._member_dir(org_id) / f"{member_id}.json"
            current = self._read(path)
            updated = fn(deepcopy(current))
            if updated is None:
                return current
            self._write(path, updated)
            return updated

    async def members_list(self, org_id: str, limit: int) -> list[dict[str, Any]]:
        if not ORG_ID.fullmatch(org_id):
            return []
        with self._lock:
            folder = self._member_dir(org_id)
            paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
            return [m for m in (self._read(p) for p in paths[:limit]) if m]

    # The delivery outbox (outbox.py) -------------------------------------------------------------

    async def outbox_get(self, briefing_id: str) -> dict[str, Any] | None:
        if not BRIEFING_ID.fullmatch(briefing_id):
            return None
        with self._lock:
            return self._read(self._path("outbox", briefing_id))

    async def outbox_update(
        self, briefing_id: str, fn: Callable[[dict[str, Any] | None], dict[str, Any] | None]
    ) -> dict[str, Any] | None:
        if not BRIEFING_ID.fullmatch(briefing_id):
            raise KeyError(briefing_id)
        with self._lock:
            path = self._path("outbox", briefing_id)
            current = self._read(path)
            updated = fn(deepcopy(current))
            if updated is None:
                return current
            parent = None if current else self._read(self._path("briefings", briefing_id))
            updated = retention.inherit_expiry(current, updated, parent)  # dies with its briefing
            self._write(path, updated)
            return updated

    async def outbox_due(self, now: str, limit: int) -> list[str]:
        with self._lock:
            folder = self._root / "outbox"
            docs = [self._read(p) for p in folder.glob("b_*.json")] if folder.is_dir() else []
        due = sorted((d["due"], d["briefingId"]) for d in docs if d and d["due"] <= now)
        return [briefing_id for _, briefing_id in due[:limit]]
