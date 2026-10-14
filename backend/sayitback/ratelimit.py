"""Who the client is, and the per-address rate limit on the Gemini-backed endpoints (3, 8, 10-13,
19) and the free writes (4, 7).

In memory and per instance: it protects the model quota from one noisy client, not from a
distributed attack (put Cloud Armor in front of the service for that).
"""

from __future__ import annotations

import ipaddress
import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable

from starlette.requests import HTTPConnection

from sayitback.errors import RateLimited

WINDOW_S = 60.0
MAX_KEYS = 10_000  # addresses remembered at once; the least recently seen is forgotten first
IPV6_PREFIX_BITS = 64  # one network: its owner can use any address in it


def _normalise(text: str) -> str | None:
    """One form for one client: an IPv4-mapped IPv6 address is its IPv4 address, and an IPv6
    address stands for its whole /64 (a client can switch between billions of addresses in it, so
    a per-address limit on the exact one would never bind). None if `text` is not an address."""
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv4Address):
        return str(ip)
    if ip.ipv4_mapped:
        return str(ip.ipv4_mapped)
    network = ipaddress.IPv6Address(int(ip) >> (128 - IPV6_PREFIX_BITS) << (128 - IPV6_PREFIX_BITS))
    return f"{network}/{IPV6_PREFIX_BITS}"


def client_ip(conn: HTTPConnection, hops: int) -> str:
    """The client's address (API.md, "Callers and ownership").

    X-Forwarded-For lists every address the request came through, each proxy appending the one it
    saw. Only the entry `hops` from the right was appended by a proxy we trust (Cloud Run's front
    end, with the default of 1); the entries to its left were written by the caller and are never
    read. With no such entry (or `hops` of 0, no proxy), the socket peer is the client."""
    lines = conn.headers.getlist("x-forwarded-for")
    entries = [entry.strip() for line in lines for entry in line.split(",")]
    if 0 < hops <= len(entries):
        trusted = _normalise(entries[-hops])
        if trusted:
            return trusted
    peer = conn.client.host if conn.client else "unknown"
    return _normalise(peer) or peer


class RateLimiter:
    """At most `per_minute` requests per key in any 60 s. The keys are client addresses, which a
    caller may have many of, so the table is bounded (`max_keys`) and every request costs the same
    however many keys there are: idle keys are dropped from the front of the table, in the order
    they were last used, and the least recently used key goes when the table is full."""

    def __init__(
        self,
        per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = MAX_KEYS,
    ) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._max_keys = max_keys
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()  # least recently used first

    def check(self, key: str) -> None:
        now = self._clock()
        self._forget_idle(now)
        hits = self._hits.get(key) or deque()
        while hits and now - hits[0] >= WINDOW_S:
            hits.popleft()
        if len(hits) >= self.per_minute:
            wait = math.ceil(WINDOW_S - (now - hits[0]))
            raise RateLimited(f"Too many requests. Try again in {wait} s.", retry_after=wait)
        hits.append(now)
        self._hits[key] = hits
        self._hits.move_to_end(key)
        if len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)

    def _forget_idle(self, now: float) -> None:
        """Drop keys with no hit in the window. They sit at the front, so this stops at the first
        key still in use: the work is the number dropped, never the number kept."""
        while self._hits:
            hits = next(iter(self._hits.values()))
            if hits and now - hits[-1] < WINDOW_S:
                return
            self._hits.popitem(last=False)
