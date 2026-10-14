"""Default inputs for `adk web`: when a session's state is empty, every agent loads the catalog's
panel-isolation demo (the `sg-lead` task) so the dev UI works without the API.
"""

from __future__ import annotations

from typing import Any

from sayitback import catalog
from sayitback.models import Question, Step
from sayitback.settings import Settings

TASK_ID = "panel-isolation"
SUPERVISOR, WORKER = "en", "ta"
TAMIL_QUESTION = "பேனலைத் திறப்பதற்கு முன் நீங்கள் என்ன செய்வீர்கள்?"
TAMIL_CLOSING = "நன்றி. உங்கள் மேற்பார்வையாளருக்காகக் காத்திருங்கள்."


def _lang_fields(supervisor: str = SUPERVISOR, worker: str = WORKER) -> dict[str, Any]:
    return {
        "supervisor_lang": supervisor,
        "worker_lang": worker,
        "supervisor_lang_name": catalog.lang_name(supervisor),
        "worker_lang_name": catalog.lang_name(worker),
    }


def _task() -> dict[str, Any]:
    found = catalog.task(TASK_ID)
    assert found is not None
    return found


def steps() -> list[dict[str, Any]]:
    return [Step.model_validate(s).model_dump(mode="json") for s in _task()["referenceSteps"]]


def questions() -> list[dict[str, Any]]:
    out = []
    for q in _task()["referenceQuestions"]:
        out.append(
            Question(id=q["id"], text=q["text"], back_translation=q["text"], step_ids=q["stepIds"])
        )
    return [q.model_dump(mode="json") for q in out]


def extract_input() -> dict[str, Any]:
    task = _task()
    return {
        **_lang_fields(),
        "instruction": task["sampleInstruction"][SUPERVISOR],
        "sop": task["sop"],
        "max_steps": 6,
    }


def script_input() -> dict[str, Any]:
    limits = Settings()  # the dev UI has no configured runtime: the defaults
    return {
        **_lang_fields(),
        "steps": steps(),
        "basis": _task()["sampleInstruction"][SUPERVISOR],
        "round_kind": "initial",
        "site_context": catalog.site_context("sg"),
        "questions_min": 2,
        "questions_max": 3,
        "max_sentences_per_step": limits.max_sentences_per_step,
        "max_line_chars": limits.max_line_chars,
        "previous_questions": [],
    }


def back_translate_input() -> dict[str, Any]:
    return {
        **_lang_fields(),
        "sentences": [_task()["sampleInstruction"][WORKER]],
        "questions": [{"id": "q1", "text": TAMIL_QUESTION}],
        "closing": TAMIL_CLOSING,
    }


def re_explain_input() -> dict[str, Any]:
    open_steps = [s for s in steps() if s["id"] in ("s2", "s3")]
    for s in open_steps:
        s.update(verdict="missed", reason="The answer does not mention this step.")
    return {**_lang_fields(), "steps": open_steps, "sop_title": _task()["sop"]["title"]}


def transcribe_instruction_input() -> dict[str, Any]:
    return {
        "lang_name": catalog.lang_name(SUPERVISOR),
        "native": catalog.language_native(SUPERVISOR),
    }


def check_input() -> dict[str, Any]:
    return {
        **_lang_fields(),
        "steps": steps(),
        "questions": questions(),
        "script": None,
        "clip_ids": ["q1"],
        "lang_codes": list(catalog.lang_codes()),
        "clip_stats": {},
    }


def briefer_input() -> dict[str, Any]:
    return {
        "lang_name": catalog.lang_name(WORKER),
        "instruction": _task()["sampleInstruction"][WORKER],
        "questions": [{"id": "q1", "text": TAMIL_QUESTION}],
        "closing": TAMIL_CLOSING,
    }
