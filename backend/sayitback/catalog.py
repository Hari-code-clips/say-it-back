"""The task catalog (sayitback/data/catalog.json) and its public view.

The catalog file is read-only data. The public view never carries `referenceSteps`,
`referenceQuestions`, `demoScripts` or the design notes, which are the answers to the demo.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sayitback.errors import Unprocessable

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog.json"
CUSTOM_TASK_ID = "custom"
PUBLIC_TASK_FIELDS = ("id", "icon", "title", "demoSite", "demoPair", "sop", "sampleInstruction")
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
