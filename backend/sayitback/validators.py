"""Input validation at the API boundary: limits from settings, language codes from the catalog."""

from __future__ import annotations

import re

from sayitback import catalog
from sayitback.errors import Unprocessable, quote
from sayitback.models import CreateBriefing, Sop, Step
from sayitback.settings import Settings

STEP_ID = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str | None, *, field: str, limit: int, required: bool = False) -> str:
    text = CONTROL_CHARS.sub("", (value or "")).strip()
    try:
        text.encode("utf-8")  # a lone surrogate cannot be stored (JSON file or Firestore)
    except UnicodeEncodeError:
        raise Unprocessable(f"{field} contains invalid characters.", code="invalid_text") from None
    if required and not text:
        raise Unprocessable(f"{field} must not be empty.")
    if len(text) > limit:
        raise Unprocessable(f"{field} is longer than {limit} characters.", code="too_long")
    return text


def instruction(value: str | None, s: Settings) -> str:
    return clean_text(value, field="instruction", limit=s.max_instruction_chars, required=True)


def sop_for(body: CreateBriefing, s: Settings) -> Sop:
    """The SOP: the catalog's for a catalog task, or the caller's (title and text) for "custom"."""
    if body.task_id == catalog.CUSTOM_TASK_ID:
        if body.sop is None:
            raise Unprocessable("A custom task needs sop {title, text}.", code="sop_required")
        title = clean_text(
            body.sop.title, field="sop.title", limit=s.max_custom_sop_title_chars, required=True
        )
        text = clean_text(
            body.sop.text, field="sop.text", limit=s.max_custom_sop_chars, required=True
        )
        return Sop(id="custom", version="v1", title=title, text=text)
    task = catalog.task(body.task_id)
    if task is None:
        what = quote(body.task_id, s.max_echo_chars)
        raise Unprocessable(f"Unknown taskId {what}.", code="unknown_task")
    return Sop.model_validate(task["sop"])


def briefing_request(body: CreateBriefing, s: Settings) -> Sop:
    """Validate a create-briefing request and return its SOP."""
    if catalog.site(body.site_id) is None:
        what = quote(body.site_id, s.max_echo_chars)
        raise Unprocessable(f"Unknown siteId {what}.", code="unknown_site")
    catalog.require_lang(body.supervisor_lang, "supervisorLang")
    catalog.require_lang(body.worker_lang, "workerLang")
    instruction(body.instruction, s)
    return sop_for(body, s)


def steps(items: list[Step], s: Settings) -> list[Step]:
    """PUT /steps: 1 to 6 steps, unique ids, non-empty text. Strings are trimmed and capped."""
    if not s.min_steps <= len(items) <= s.max_steps:
        raise Unprocessable(
            f"Send between {s.min_steps} and {s.max_steps} steps.", code="invalid_steps"
        )
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids) or not all(STEP_ID.fullmatch(i) for i in ids):
        raise Unprocessable("Step ids must be unique, short and URL-safe.", code="invalid_steps")
    cleaned = []
    for item in items:
        essentials = [
            clean_text(e, field="essential", limit=s.max_step_text_chars)
            for e in item.essential[: s.max_essentials]
        ]
        cleaned.append(
            item.model_copy(
                update={
                    "text": clean_text(
                        item.text, field="step text", limit=s.max_step_text_chars, required=True
                    ),
                    "hazard": clean_text(item.hazard, field="hazard", limit=s.max_step_text_chars),
                    "essential": [e for e in essentials if e],
                    "sop_quote": clean_text(
                        item.sop_quote, field="sopQuote", limit=s.max_custom_sop_chars
                    )
                    or None,
                }
            )
        )
    return cleaned
