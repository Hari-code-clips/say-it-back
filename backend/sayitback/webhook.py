"""SIB_WEBHOOK_URL: post each decided briefing, best effort.

A chat.googleapis.com URL (a Google Chat incoming webhook) gets {"text": ...}, a short summary of
the decision. Any other URL gets the JSON record. Neither carries a transcript or audio. The URL
holds a key and a secret, so it is never logged; only its host is.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from sayitback import catalog
from sayitback.models import Briefing

log = logging.getLogger("sayitback.webhook")
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs full URLs at INFO; ours is secret
CHAT_HOST = "chat.googleapis.com"
CHAT_MAX_CHARS = 3500  # Chat messages are limited to 4096 bytes


def is_chat_url(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower() == CHAT_HOST


def _lang_pair(b: Briefing) -> str:
    return f"{catalog.lang_name(b.supervisor_lang)} to {catalog.lang_name(b.worker_lang)}"


CHAT_MARKUP = re.compile(r"[<>*_`~]")


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
        f"Covered {covered} of {len(b.steps)} steps.",
    ]
    open_steps = [s for s in b.steps if s.id in b.decision.open_step_ids]
    lines += [f"Open: {_plain(s.text)}" for s in open_steps]
    if b.decision.reason:
        lines.append(f"Reason: {_plain(b.decision.reason)}")
    if b.decision.by:
        lines.append(f"By: {_plain(b.decision.by)}")
    return {"text": "\n".join(lines)[:CHAT_MAX_CHARS]}


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
        "decision": b.decision.wire(),
        "promptVersion": b.prompt_version,
    }


def payload_for(url: str, b: Briefing) -> dict[str, Any]:
    return chat_payload(b) if is_chat_url(url) else json_record(b)


class WebhookSender:
    def __init__(
        self, url: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.url = url
        self.timeout_s = timeout_s
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    async def send(self, b: Briefing) -> bool:
        """POST the decision. Never raises: a failed webhook must not fail the decision."""
        if not self.enabled or b.decision is None:
            return False
        host = urlsplit(self.url).hostname or "?"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as http:
                response = await http.post(self.url, json=payload_for(self.url, b))
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - best effort by contract
            log.warning("webhook to %s failed: %s", host, type(exc).__name__)
            return False
        log.info("webhook to %s delivered", host)
        return True
