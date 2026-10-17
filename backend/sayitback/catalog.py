"""The task catalog (sayitback/data/catalog.json) and its public view.

The catalog file is read-only data. The public view never carries `referenceSteps`,
`referenceQuestions`, `demoScripts` or the design notes, which are the answers to the demo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from sayitback.errors import Unprocessable

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog.json"
CUSTOM_TASK_ID = "custom"
# `domain` (2026-10-17): the work domain the Start screen groups its task picker by.
PUBLIC_TASK_FIELDS = (
    "id",
    "icon",
    "domain",
    "title",
    "demoSite",
    "demoPair",
    "sop",
    "sampleInstruction",
)
PUBLIC_TOP_FIELDS = ("version", "languages", "sites", "tasks")

Range = tuple[int, int]


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def public_view(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Endpoint 2: the catalog without the reference answers."""
    cat = catalog or load_catalog()
    view = {k: cat[k] for k in PUBLIC_TOP_FIELDS if k in cat and k != "tasks"}
    view["tasks"] = [{k: t[k] for k in PUBLIC_TASK_FIELDS if k in t} for t in cat["tasks"]]
    return view


def lang_codes() -> tuple[str, ...]:
    return tuple(load_catalog()["languages"])


def lang_name(code: str) -> str:
    return load_catalog()["languages"][code]["name"]


def language_native(code: str) -> str:
    return load_catalog()["languages"][code]["native"]


def require_lang(code: str, field: str = "lang") -> str:
    if code not in load_catalog()["languages"]:
        raise Unprocessable(
            f"{field} must be one of {', '.join(lang_codes())}.", code="unsupported_language"
        )
    return code


def unicode_ranges(code: str) -> tuple[Range, ...]:
    raw = load_catalog()["languages"][code]["unicodeRanges"]
    return tuple((int(lo, 16), int(hi, 16)) for lo, hi in raw)


def all_ranges() -> dict[str, tuple[Range, ...]]:
    return {code: unicode_ranges(code) for code in lang_codes()}


@dataclass(frozen=True)
class LanguageMarkers:
    """What the delivery check counts in a worker language (API.md v0.4, "Delivery check").

    `match` is "word" (a marker is a whole word of the normalised text) or "substring" (it may be
    part of a word: a suffix, or a script without spaces). Both lists are drafts pending
    native-speaker review, like every non-English catalog string."""

    match: str
    negation_markers: tuple[str, ...]
    number_words: tuple[str, ...]
    thanks_words: tuple[str, ...] = ()  # what a neutral thanks may say (reply_not_neutral)
    spaced: bool = True  # False for a script written without spaces between words (Chinese)


UNSPACED_SCRIPTS = frozenset({"Hans", "Hant", "Jpan", "Thai"})


@lru_cache(maxsize=16)
def markers(code: str) -> LanguageMarkers:
    spec = load_catalog()["languages"][code]
    return LanguageMarkers(
        match="word" if spec.get("match", "word") == "word" else "substring",
        negation_markers=tuple(spec.get("negationMarkers", ())),
        number_words=tuple(spec.get("numberWords", ())),
        thanks_words=tuple(spec.get("thanksWords", ())),
        spaced=spec.get("script") not in UNSPACED_SCRIPTS,
    )


def site(site_id: str) -> dict[str, Any] | None:
    return next((s for s in load_catalog()["sites"] if s["id"] == site_id), None)


def task(task_id: str) -> dict[str, Any] | None:
    return next((t for t in load_catalog()["tasks"] if t["id"] == task_id), None)


def reference_steps(task_id: str) -> list[dict[str, Any]]:
    found = task(task_id)
    return list(found["referenceSteps"]) if found else []


def reference_questions(task_id: str) -> list[dict[str, Any]]:
    found = task(task_id)
    return list(found["referenceQuestions"]) if found else []


def demo_script(script_id: str) -> dict[str, Any] | None:
    return next((d for d in load_catalog().get("demoScripts", []) if d["id"] == script_id), None)


def round_answers(task_id: str, turn: dict[str, Any]) -> list[dict[str, Any]]:
    """A demo round's scripted answers, `{questionId, answer, expected, own}`: its own first answer
    (`own` true) and its `followUps` (2026-10-16, one per further question), in the task's reference
    question order."""
    rank = {q["id"]: i for i, q in enumerate(reference_questions(task_id))}
    own = {k: turn[k] for k in ("questionId", "answer", "expected")}
    answers = [{**own, "own": True}, *({**f, "own": False} for f in turn.get("followUps", []))]
    return sorted(answers, key=lambda a: rank.get(a["questionId"], len(rank)))


def task_title(task_id: str, lang: str, fallback: str = "") -> str:
    found = task(task_id)
    if not found:
        return fallback
    titles = found["title"]
    return titles.get(lang) or titles.get("en") or next(iter(titles.values()), fallback)


def site_context(site_id: str) -> str:
    found = site(site_id)
    if not found:
        return ""
    return f"{found['name']}: {found['setting']}. {found.get('context', '')}".strip()
