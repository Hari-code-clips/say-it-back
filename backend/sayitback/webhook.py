"""SIB_WEBHOOK_URL: post each decided briefing to up to 3 URLs, best effort (API.md v0.4,
"Webhooks").

A chat.googleapis.com URL (a Google Chat incoming webhook) gets {"text": ...}, a short summary of
the decision. Any other URL gets the JSON record, which carries the record's `recordHash`, so the
chain is anchored outside the store (chain.py). Neither carries a transcript or audio.

With SIB_WEBHOOK_SECRET set, each JSON post is signed: `X-SIB-Timestamp` (Unix seconds) and
`X-SIB-Signature: sha256=<hex HMAC-SHA256 of "<timestamp>.<raw body>">`. A receiver refuses a
timestamp more than 300 s old (integrations/ptw-stub). Chat posts are not signed: Chat ignores it.

A URL can hold a key and a secret, so it is never logged; only its host is. The secret is never
logged either.

v0.5: the decision endpoint awaits the posts (`deliver`), all URLs at once, within
SIB_WEBHOOK_TIMEOUT_S in all, before it answers: Cloud Run may stop an instance's CPU once the
response is sent, so a post left to run after it might never leave.

Pilot (docs/EPERMIT_ADAPTER.md): every JSON post carries `Idempotency-Key`, one per decision, the
same on every retry. SIB_PTW_URL adds a site's e-permit system as one more target: the native
record, or with SIB_PTW_FIELD_MAP the `generic` adapter's mapping of it onto the vendor's field
names, signed the same way and, with SIB_PTW_TOKEN, sent with `Authorization: Bearer`. The token
is never logged, never in a repr. `attempt` classifies the answer for the outbox (outbox.py): 2xx
(or 409 `duplicate`) delivered, 408/425/429/5xx or no answer retried, any other 4xx refused.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from sayitback import catalog
from sayitback.models import Briefing
from sayitback.settings import ConfigError, webhook_urls

log = logging.getLogger("sayitback.webhook")
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs full URLs at INFO; ours is secret
CHAT_HOST = "chat.googleapis.com"
CHAT_MAX_CHARS = 3500  # Chat messages are limited to 4096 bytes
TIMESTAMP_HEADER = "X-SIB-Timestamp"
SIGNATURE_HEADER = "X-SIB-Signature"
IDEMPOTENCY_HEADER = "Idempotency-Key"
RETRY_STATUS = frozenset({408, 425, 429})  # and every 5xx: try again later
DUPLICATE_CODE = "duplicate"  # a 409 with this error code: the receiver already has it
# The top-level fields of json_record: what SIB_PTW_FIELD_MAP may read.
RECORD_FIELDS = frozenset(
    {
        "event", "briefingId", "siteId", "taskId", "sop", "supervisorLang", "workerLang",
        "rounds", "steps", "decision", "decidedAt", "hazards", "sampleAnswers", "permit",
        "events", "recordHash", "promptVersion",
    }
)  # fmt: skip
KEY_SOURCE = "$idempotencyKey"  # a field map may put the delivery's key into the body too
MAX_MAPPED_FIELDS = 64
FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}(\.[A-Za-z_][A-Za-z0-9_-]{0,63}){0,3}$")
SOURCE_PATH = re.compile(r"^[A-Za-z][A-Za-z0-9]*(\.[A-Za-z0-9_]+){0,3}$")
SCALAR = (str, int, float, bool, type(None))


def is_chat_url(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower() == CHAT_HOST


def _lang_pair(b: Briefing) -> str:
    return f"{catalog.lang_name(b.supervisor_lang)} to {catalog.lang_name(b.worker_lang)}"


CHAT_MARKUP = re.compile(r"[<>*_`~]")
IN_PERSON_LINE = "Checked in person: the worker chose not to be recorded, so no AI check was made."


def _plain(text: str) -> str:
    """Chat renders <users/all>, <url|label>, *bold*, _italic_ and `code` in message text. The
    supervisor's words go in as plain text, so none of it can mention everyone or hide a link."""
    return CHAT_MARKUP.sub("", text)


def chat_payload(b: Briefing) -> dict[str, str]:
    """Google Chat message: {"text": "..."}."""
    assert b.decision is not None
    site = catalog.site(b.site_id)
    title = catalog.task_title(b.task_id, b.supervisor_lang, fallback=b.sop.title)
    covered = len(b.steps) - len(b.decision.open_step_ids)
    verdict = "GO" if b.decision.value == "go" else "NO-GO"
    lines = [
        f"*Say It Back: {verdict}* at {site['name'] if site else b.site_id}",
        f"{title} ({_lang_pair(b)}), {len(b.rounds)} round(s)",
    ]
    if b.permit:  # v0.5.2; in code format so an underscore in the ref is not italics
        lines.append(f"Permit `{b.permit.ref}`, worker {b.permit.slot} of {b.permit.crew_size}")
    if b.decision.in_person:  # 2026-10-17: the worker declined the AI check for the latest round
        lines.append(IN_PERSON_LINE)
    lines += [
        f"Covered {covered} of {len(b.steps)} steps.",
    ]
    open_steps = [s for s in b.steps if s.id in b.decision.open_step_ids]
    lines += [f"Open: {_plain(s.text)}" for s in open_steps]
    if sample_answers(b):
        lines.append("Demo: synthetic sample answers were used, not the worker's own.")
    if b.decision.reason:
        lines.append(f"Reason: {_plain(b.decision.reason)}")
    if b.decision.by:
        lines.append(f"By: {_plain(b.decision.by)}")
    return {"text": "\n".join(lines)[:CHAT_MAX_CHARS]}


def sample_answers(b: Briefing) -> list[dict[str, Any]]:
    """Which answers were stored synthetic samples (endpoint 24), not the worker: `[{round,
    questionId}]`."""
    return [{"round": r.n, "questionId": q} for r in b.rounds for q in (r.sample_answers or [])]


def json_record(b: Briefing) -> dict[str, Any]:
    """The decision record for any other webhook: ids, verdicts and the decision. No content."""
    assert b.decision is not None
    return {
        "event": "briefing_decided",
        "briefingId": b.id,
        "siteId": b.site_id,
        "taskId": b.task_id,
        "sop": {"id": b.sop.id, "version": b.sop.version},
        "supervisorLang": b.supervisor_lang,
        "workerLang": b.worker_lang,
        "rounds": len(b.rounds),
        "steps": [
            {
                "id": s.id,
                "text": s.text,
                "source": s.source,
                "finalVerdict": b.latest_verdicts.get(s.id),
            }
            for s in b.steps
        ],
        # 2026-10-17: `inPerson` always, true or false, so a receiver never has to read an absence
        "decision": {**b.decision.wire(), "inPerson": bool(b.decision.in_person)},
        "decidedAt": b.decision.at,
        "hazards": [
            {"id": h.id, "kind": h.kind, "acknowledged": h.ack is not None} for h in b.hazards
        ],
        "sampleAnswers": sample_answers(b),
        "permit": b.permit.wire() if b.permit else None,  # v0.5.2: {ref, crewSize, slot}
        "events": len(b.events),
        "recordHash": b.record_hash,
        "promptVersion": b.prompt_version,
    }


def payload_for(url: str, b: Briefing) -> dict[str, Any]:
    return chat_payload(b) if is_chat_url(url) else json_record(b)


def signature(secret: str, timestamp: str, body: bytes) -> str:
    """`sha256=<hex HMAC-SHA256 of "<timestamp>.<raw body>">`, keyed with SIB_WEBHOOK_SECRET."""
    mac = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def idempotency_key(b: Briefing) -> str:
    """One key per decision, the same on every retry: `sib-<briefingId>-<first 16 hex of
    recordHash>`. Both parts are in the signed record, so a receiver can check that the key
    belongs to the body (docs/EPERMIT_ADAPTER.md)."""
    return f"sib-{b.id}-{(b.record_hash or '0' * 16)[:16]}"


# The generic adapter (SIB_PTW_FIELD_MAP) -------------------------------------------------------


def parse_field_map(raw: str) -> dict[str, Any] | None:
    """SIB_PTW_FIELD_MAP: `{"<vendor field>": <source>}`, where a source is a record path
    ("permit.ref"), "$idempotencyKey", `{"const": <scalar>}` or `{"from": <path>, "map": {<record
    value>: <vendor value>}, "default": <scalar>}`. A dotted vendor field nests ("job.permitNo").
    None when empty; anything malformed stops start-up (the map holds no secret, so the error may
    name the field)."""
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        raise ConfigError("SIB_PTW_FIELD_MAP is not JSON") from None
    if not isinstance(data, dict) or not 1 <= len(data) <= MAX_MAPPED_FIELDS:
        raise ConfigError(f"SIB_PTW_FIELD_MAP must be an object of 1 to {MAX_MAPPED_FIELDS} fields")
    for name, source in data.items():
        if not FIELD_NAME.fullmatch(name):
            raise ConfigError(f"SIB_PTW_FIELD_MAP: {name[:40]!r} is not a field name")
        if not _valid_source(source):
            raise ConfigError(f"SIB_PTW_FIELD_MAP: the source of {name!r} is not valid")
    parents = {n.rsplit(".", i)[0] for n in data for i in range(1, n.count(".") + 1)}
    if parents & set(data):
        raise ConfigError("SIB_PTW_FIELD_MAP: a field is both a value and a parent")
    return data


def _valid_path(path: Any) -> bool:
    if path == KEY_SOURCE:
        return True
    return (
        isinstance(path, str)
        and SOURCE_PATH.fullmatch(path) is not None
        and path.split(".")[0] in RECORD_FIELDS
    )


def _valid_source(source: Any) -> bool:
    if isinstance(source, str):
        return _valid_path(source)
    if not isinstance(source, dict):
        return False
    if set(source) == {"const"}:
        return isinstance(source["const"], SCALAR)
    if not {"from"} <= set(source) <= {"from", "map", "default"} or not _valid_path(source["from"]):
        return False
    table = source.get("map", {})
    return (
        isinstance(table, dict)
        and all(isinstance(v, SCALAR) for v in table.values())
        and isinstance(source.get("default"), SCALAR)
    )


def _read(record: Mapping[str, Any], path: str, key: str) -> Any:
    if path == KEY_SOURCE:
        return key
    value: Any = record
    for part in path.split("."):
        value = value.get(part) if isinstance(value, Mapping) else None
    return value


def map_record(record: Mapping[str, Any], field_map: Mapping[str, Any], key: str) -> dict:
    """The vendor's body: each mapped field from the decision record. A path the record lacks is
    null; a `map` value with no entry takes its `default` (null when none)."""
    out: dict[str, Any] = {}
    for name, source in field_map.items():
        if isinstance(source, str):
            value = _read(record, source, key)
        elif "const" in source:
            value = source["const"]
        else:
            raw = _read(record, source["from"], key)
            table = source.get("map")
            value = raw if table is None else table.get(str(raw), source.get("default"))
        *parents, leaf = name.split(".")
        node = out
        for parent in parents:
            node = node.setdefault(parent, {})
        node[leaf] = value
    return out


# Targets and their answers ---------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """Where a decision goes: a Chat space, a receiver of the native record (the stub), or the
    site's e-permit system (SIB_PTW_URL). The URL and the token never reach a repr or a log."""

    url: str = field(repr=False)
    adapter: str  # "chat" | "record" | "generic"
    field_map: Mapping[str, Any] | None = field(default=None, repr=False, compare=False)
    token: str = field(default="", repr=False)

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or "?"

    @property
    def id(self) -> str:
        """A stable reference the outbox stores instead of the URL: 16 hex of its SHA-256."""
        return hashlib.sha256(self.url.encode("utf-8")).hexdigest()[:16]

    @property
    def kind(self) -> str:
        """What the record screen calls it: "chat", or "permit" for a permit system."""
        return "chat" if self.adapter == "chat" else "permit"


def target_for(url: str) -> Target:
    return Target(url, "chat" if is_chat_url(url) else "record")


@dataclass(frozen=True)
class Outcome:
    """One post's result: delivered, or not and whether a retry may help. `error` is a class
    ("http_503", "timeout", "ConnectError"), never a URL, a body or a header."""

    delivered: bool
    retry: bool = False
    error: str | None = None


def classify(response: httpx.Response) -> Outcome:
    status = response.status_code
    if 200 <= status < 300:
        return Outcome(True)
    if status == 409 and _error_code(response) == DUPLICATE_CODE:
        return Outcome(True, error="duplicate")
    retry = status in RETRY_STATUS or status >= 500
    return Outcome(False, retry, f"http_{status}")


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    return error.get("code") if isinstance(error, dict) else None


class WebhookSender:
    def __init__(
        self,
        urls: str | Sequence[str],
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        secret: str = "",
        clock: Callable[[], float] = time.time,
        vendor_url: str = "",
        field_map: str = "",
        vendor_token: str = "",
    ) -> None:
        self.urls = webhook_urls(urls) if isinstance(urls, str) else tuple(urls)
        self.timeout_s = timeout_s
        self._transport = transport
        self._secret = secret
        self._clock = clock
        self.targets = tuple(target_for(u) for u in self.urls)
        if vendor_url:  # SIB_PTW_URL: the site's e-permit system
            mapping = parse_field_map(field_map)
            adapter = "generic" if mapping else "record"
            self.targets += (Target(vendor_url, adapter, mapping, vendor_token),)

    def __repr__(self) -> str:  # the URLs hold keys and the secret signs: show neither
        return f"WebhookSender({len(self.targets)} URLs, signed={bool(self._secret)})"

    @property
    def enabled(self) -> bool:
        return bool(self.targets)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport)

    async def send(self, b: Briefing) -> bool:
        """POST the decision to every URL at once. Never raises: a failed webhook must not fail
        the decision. True when every URL took it."""
        if not self.enabled or b.decision is None:
            return False
        async with self.client() as http:
            results = await asyncio.gather(*(self._post(http, t, b) for t in self.targets))
        return all(results)

    def request_for(self, target: Target | str, b: Briefing) -> tuple[bytes, dict[str, str]]:
        """The exact body and headers posted to `target`: the signature covers these bytes."""
        target = target_for(target) if isinstance(target, str) else target
        if target.adapter == "chat":
            return json.dumps(chat_payload(b)).encode("utf-8"), {"Content-Type": "application/json"}
        key = idempotency_key(b)
        record = json_record(b)
        if target.field_map:
            record = map_record(record, target.field_map, key)
        body = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", IDEMPOTENCY_HEADER: key}
        if self._secret:
            stamp = str(int(self._clock()))
            headers[TIMESTAMP_HEADER] = stamp
            headers[SIGNATURE_HEADER] = signature(self._secret, stamp, body)
        if target.token:
            headers["Authorization"] = f"Bearer {target.token}"
        return body, headers

    async def attempt(self, http: httpx.AsyncClient, target: Target, b: Briefing) -> Outcome:
        """One post, within timeout_s. Never raises; logs the host and the outcome's class only."""
        try:
            async with asyncio.timeout(self.timeout_s):
                body, headers = self.request_for(target, b)
                outcome = classify(await http.post(target.url, content=body, headers=headers))
        except TimeoutError:
            outcome = Outcome(False, True, "timeout")
        except Exception as exc:  # noqa: BLE001 - best effort by contract
            outcome = Outcome(False, True, type(exc).__name__)
        if outcome.delivered:
            log.info("webhook to %s delivered", target.host)
        else:
            log.warning("webhook to %s failed: %s", target.host, outcome.error)
        return outcome

    async def _post(self, http: httpx.AsyncClient, target: Target, b: Briefing) -> bool:
        return (await self.attempt(http, target, b)).delivered


async def deliver(sender: WebhookSender, b: Briefing, timeout_s: float) -> bool:
    """`sender.send(b)` within `timeout_s` in all (API.md v0.5). Never raises: a webhook that
    hangs or fails is logged by its exception's name only and the decision stands. True when every
    URL took it in time."""
    try:
        return await asyncio.wait_for(sender.send(b), timeout_s)
    except TimeoutError:
        log.warning("webhooks not finished within %.1f s, stopped", timeout_s)
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        log.warning("webhooks failed: %s", type(exc).__name__)
    return False
