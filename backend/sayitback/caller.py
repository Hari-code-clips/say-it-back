"""Who is calling (API.md, "Callers and ownership").

There are no accounts: each browser makes a random device key once and sends it as X-SIB-Device.
A briefing belongs to the key that created it, and only the key's SHA-256 is ever kept, so a leaked
store holds nothing a browser can present. The client address is the other half of a caller: the
per-address limits and the daily allowance read it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

DEVICE_HEADER = "x-sib-device"
DEVICE_KEY = re.compile(r"[A-Za-z0-9_-]{22,64}")  # at least 128 bits, as the web client makes it


@dataclass(frozen=True)
class Caller:
    """What the service knows about one request's sender. Neither field is shown by `repr`, so a
    caller that ends up in a log line or an error shows nothing."""

    owner: str = field(repr=False)  # SHA-256 (hex) of the device key; never leaves the service
    address: str = field(repr=False)  # the client address, as ratelimit.client_ip gives it


def owner_hash(device_key: str) -> str:
    return hashlib.sha256(device_key.encode()).hexdigest()
