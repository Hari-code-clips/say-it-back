"""The webhook signature (Say It Back API.md v0.4, "Webhooks").

The sender posts `X-SIB-Timestamp` (Unix seconds) and
`X-SIB-Signature: sha256=<hex HMAC-SHA256 of "<timestamp>.<raw body>">`, keyed with the shared
SIB_WEBHOOK_SECRET. A post is refused when either is
missing, when the timestamp is more than 300 s from now (either way: a replay, or a skewed clock),
or when the signature does not match the raw bytes received.
"""

from __future__ import annotations

import hashlib
import hmac

WINDOW_S = 300
PREFIX = "sha256="


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256)
    return PREFIX + mac.hexdigest()


def problem(
    secret: str, timestamp: str | None, signature: str | None, body: bytes, now: float
) -> str | None:
    """None when the post is signed by `secret` within the window, else why it is refused."""
    if not timestamp or not signature:
        return "unsigned"
    if not timestamp.isascii() or not timestamp.isdigit() or len(timestamp) > 12:
        return "bad_timestamp"
    if abs(now - int(timestamp)) > WINDOW_S:
        return "stale"
    expected = sign(secret, timestamp, body).encode("ascii")
    if not hmac.compare_digest(expected, signature.strip().encode("utf-8", "replace")):
        return "bad_signature"
    return None
