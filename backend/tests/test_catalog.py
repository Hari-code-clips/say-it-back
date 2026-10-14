"""The catalog and its public view: no reference answers leak (API.md endpoint 2)."""

from __future__ import annotations

import json

import pytest

from sayitback import catalog
from sayitback.errors import Unprocessable

SECRET_KEYS = ("referenceSteps", "referenceQuestions", "demoScripts", "designNote")


def test_public_view_has_the_documented_shape():
    view = catalog.public_view()
    assert set(view) == {"version", "languages", "sites", "tasks"}
    assert set(view["languages"]) == {"en", "zh", "ta", "bn", "my", "hi", "or"}
    assert {t["id"] for t in view["tasks"]} == {t["id"] for t in catalog.load_catalog()["tasks"]}


def test_public_tasks_carry_exactly_the_documented_fields():
    for task in catalog.public_view()["tasks"]:
        assert set(task) == {
            "id",
            "icon",
            "title",
            "demoSite",
            "demoPair",
            "sop",
            "sampleInstruction",
        }


def test_no_reference_answer_leaks_anywhere_in_the_public_json():
    text = json.dumps(catalog.public_view(), ensure_ascii=False)
    for key in SECRET_KEYS:
        assert key not in text
    # nor the content of one reference step
    assert "Switch off (isolate) the supply at the breaker" not in text
    assert "Check that the shoring is in place before going in" not in text


def test_the_catalog_file_itself_still_has_the_answers():
    raw = catalog.load_catalog()
    assert "demoScripts" in raw
    assert all("referenceSteps" in t for t in raw["tasks"])


def test_unicode_ranges_come_from_the_catalog():
    assert catalog.unicode_ranges("or") == ((0x0B00, 0x0B7F),)
    assert catalog.unicode_ranges("ta") == ((0x0B80, 0x0BFF),)
    assert catalog.unicode_ranges("hi") == ((0x0900, 0x097F),)


def test_language_validation_names_the_field():
    assert catalog.require_lang("ta") == "ta"
    with pytest.raises(Unprocessable) as err:
        catalog.require_lang("xx", "workerLang")
    assert "workerLang" in err.value.message
    assert err.value.code == "unsupported_language"


def test_task_title_falls_back_to_english():
    assert catalog.task_title("panel-isolation", "ta").startswith("டிஸ்ட்ரிபியூஷன்")
    assert catalog.task_title("panel-isolation", "zh") == "Open a distribution panel"
    assert catalog.task_title("custom", "en", fallback="My SOP") == "My SOP"
