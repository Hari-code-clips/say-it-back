"""Model probe (API.md v0.5): before a deploy, check that every configured model answers where the
service will call it, with one tiny call each.

    uv run python -m sayitback.probe [--also-location us-central1]

It reads the same environment as the service (settings.py) and builds the same clients
(backends.py). The probes, each bounded by 30 s and run at once:
  flash    SIB_FLASH_MODEL, "Reply OK" (thinking_level medium, max_output_tokens 64)
  judge_b  SIB_JUDGE_B_MODEL the same way, when it is set
  tts      SIB_TTS_MODEL, one short text with the AUDIO modality, at SIB_TTS_LOCATION and at each
           --also-location (Agent Platform only)
  live     SIB_LIVE_MODEL at SIB_LIVE_LOCATION: open an audio session and close it at once

One line per model: `OK <kind> <model> <location> <latency>ms` or `FAIL <kind> <model> <location>
<reason>`, the reason one of not_found, permission, quota, bad_request, timeout, other. The
location is `developer-api` off Agent Platform. Exit code 0 when every model answered, else 1.
Nothing an error says is printed (it can name the project number or carry a key): only its class.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from google.auth import exceptions as auth_errors
from google.genai import types

from sayitback.backends import (
    DEVELOPER_API,
    Kind,
    backend_for,
    client_kwargs,
    make_genai_client,
    thinking_config,
)
from sayitback.settings import ConfigError, Settings
from sayitback.tts import Tts

PROBE_TIMEOUT_S = 30.0
FLASH_PROMPT = "Reply OK"
FLASH_THINKING = "medium"
FLASH_MAX_OUTPUT_TOKENS = 64
TTS_TEXT = "OK."
LIVE_CONFIG = {"response_modalities": ["AUDIO"]}
REASONS = ("not_found", "permission", "quota", "bad_request", "timeout", "other")
STATUS_REASONS = {
    400: "bad_request",
    401: "permission",
    403: "permission",
    404: "not_found",
    429: "quota",
    1007: "bad_request",  # a Live close frame: invalid argument
}
# A Live close frame (websocket close code 1008 and the like) says why only in its text
CLOSE_TEXT_REASONS = (
    ("not found", "not_found"),
    ("not supported", "not_found"),
    ("permission", "permission"),
    ("denied", "permission"),
    ("quota", "quota"),
    ("exhausted", "quota"),
    ("invalid argument", "bad_request"),
)
FIRST_CLOSE_CODE = 1000

ClientFactory = Callable[[Kind, Settings], Any]


def _status_code(exc: BaseException) -> int | None:
    """The HTTP status (google-genai's APIError.code, or an httpx or websockets response's
    status_code), or a Live close code."""
    for source in (exc, getattr(exc, "response", None)):
        for attr in ("code", "status_code"):
            value = getattr(source, attr, None)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def classify_error(exc: BaseException) -> str:
    """One of REASONS, from the exception's type and status. Its text is read only for a Live
    close frame, and never printed."""
    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, auth_errors.GoogleAuthError):
        return "permission"
    code = _status_code(exc)
    if code in STATUS_REASONS:
        return STATUS_REASONS[code]
    if code is not None and code >= FIRST_CLOSE_CODE:
        text = str(exc).lower()
        return next((reason for words, reason in CLOSE_TEXT_REASONS if words in text), "other")
    return "other"


@dataclass(frozen=True)
class Result:
    kind: str
    model: str
    location: str
    ok: bool
    detail: str  # the latency in ms, or a reason

    def line(self) -> str:
        if self.ok:
            return f"OK {self.kind} {self.model} {self.location} {self.detail}ms"
        return f"FAIL {self.kind} {self.model} {self.location} {self.detail}"


def location_of(kind: Kind, s: Settings) -> str:
    if backend_for(kind, s) == DEVELOPER_API:
        return DEVELOPER_API
    return str(client_kwargs(kind, s)["location"])


def flash_config() -> types.GenerateContentConfig:
    # Gemini 3.x: no temperature, top_p or top_k; effort is thinking_level
    return types.GenerateContentConfig(
        thinking_config=thinking_config(FLASH_THINKING),
        max_output_tokens=FLASH_MAX_OUTPUT_TOKENS,
    )


def tts_config(s: Settings) -> types.GenerateContentConfig:
    """Turn mode's TTS config, exactly as tts.py sends it (no max_output_tokens: Agent Platform's
    TTS refuses it with 400)."""
    return Tts.config_for(s)


@dataclass(frozen=True)
class Probe:
    kind: str  # what the line calls it
    client_kind: Kind  # which client (backends.py) makes the call
    model: str
    settings: Settings
    contents: str = ""  # generate_content's text and config; Live sends nothing
    config: Any = None

    async def call(self, client: Any) -> None:
        if self.client_kind == "live":
            async with client.aio.live.connect(model=self.model, config=LIVE_CONFIG):
                return  # the session opened: close it at once
        await client.aio.models.generate_content(
            model=self.model, contents=self.contents, config=self.config
        )

    async def run(self, factory: ClientFactory, timeout_s: float) -> Result:
        location = location_of(self.client_kind, self.settings)
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout_s):
                await self.call(factory(self.client_kind, self.settings))
        except Exception as exc:  # noqa: BLE001 - every failure is reported, none is raised
            return Result(self.kind, self.model, location, False, classify_error(exc))
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return Result(self.kind, self.model, location, True, str(elapsed_ms))


def probes(s: Settings, also_locations: Sequence[str] = ()) -> list[Probe]:
    """Every probe, in print order."""
    out = [Probe("flash", "flash", s.flash_model, s, FLASH_PROMPT, flash_config())]
    if s.judge_b_model:
        out.append(Probe("judge_b", "flash", s.judge_b_model, s, FLASH_PROMPT, flash_config()))
    tts_at = [s]
    if backend_for("tts", s) != DEVELOPER_API:
        tts_at += [s.with_overrides(tts_location=loc) for loc in also_locations]
    out += [Probe("tts", "tts", t.tts_model, t, TTS_TEXT, tts_config(t)) for t in tts_at]
    out.append(Probe("live", "live", s.live_model, s))
    return out


async def probe_all(
    s: Settings,
    *,
    also_locations: Sequence[str] = (),
    client_factory: ClientFactory = make_genai_client,
    timeout_s: float = PROBE_TIMEOUT_S,
) -> list[Result]:
    runs = (p.run(client_factory, timeout_s) for p in probes(s, also_locations))
    return list(await asyncio.gather(*runs))


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    client_factory: ClientFactory = make_genai_client,
    timeout_s: float = PROBE_TIMEOUT_S,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m sayitback.probe",
        description="Check that every configured Gemini model answers. Exit 0 when all do.",
    )
    parser.add_argument(
        "--also-location",
        action="append",
        default=[],
        metavar="LOCATION",
        help="probe TTS at this Agent Platform location too (repeatable)",
    )
    args = parser.parse_args(argv)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines carry project paths
    try:
        s = settings or Settings.from_env()
    except ConfigError as exc:  # its messages name a setting, never a secret value
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    if args.also_location and backend_for("tts", s) == DEVELOPER_API:
        print("--also-location applies to Agent Platform only; skipped", file=sys.stderr)
    results = asyncio.run(
        probe_all(
            s,
            also_locations=args.also_location,
            client_factory=client_factory,
            timeout_s=timeout_s,
        )
    )
    for r in results:
        print(r.line())
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
