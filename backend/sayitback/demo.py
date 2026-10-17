"""Default inputs for `adk web`: when a session's state is empty, every agent loads the catalog's
lead demo, the crane lifting zone (task `lifting-zone`, demo script `sg-lead`: Singapore, English
to Tamil), so the dev UI works without the API. `steps`, `questions` and `check_input` take another
task id, for tests built on that task's steps.
"""

from __future__ import annotations

from typing import Any

from sayitback import catalog
from sayitback.models import Question, Step
from sayitback.settings import Settings

TASK_ID = "lifting-zone"  # the lead demo
DEMO_SCRIPT = "sg-lead"
SITE_ID = "sg"
SUPERVISOR, WORKER = "en", "ta"
# DRAFT machine translation, pending native review: "Where will you be while the load is moving?"
# (the task's q1)
TAMIL_QUESTION = "லோடு நகரும்போது நீங்கள் எங்கே இருப்பீர்கள்?"
TAMIL_CLOSING = "நன்றி. உங்கள் மேற்பார்வையாளருக்காகக் காத்திருங்கள்."
REASONS = {
    "contradicted": "The answer states the action this step forbids.",
    "missed": "The answer does not mention this step.",
}


def _lang_fields(supervisor: str = SUPERVISOR, worker: str = WORKER) -> dict[str, Any]:
    return {
        "supervisor_lang": supervisor,
        "worker_lang": worker,
        "supervisor_lang_name": catalog.lang_name(supervisor),
        "worker_lang_name": catalog.lang_name(worker),
    }


def _task(task_id: str = TASK_ID) -> dict[str, Any]:
    found = catalog.task(task_id)
    assert found is not None
    return found


def steps(task_id: str = TASK_ID) -> list[dict[str, Any]]:
    return [
        Step.model_validate(s).model_dump(mode="json") for s in _task(task_id)["referenceSteps"]
    ]


def questions(task_id: str = TASK_ID) -> list[dict[str, Any]]:
    out = []
    for q in _task(task_id)["referenceQuestions"]:
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
        "site_context": catalog.site_context(SITE_ID),
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


def round_expected(script_id: str, index: int) -> dict[str, str]:
    """Every verdict a demo round's scripted answers expect: its own answer and its follow-ups."""
    script = catalog.demo_script(script_id)
    assert script is not None
    turn = script["rounds"][index]
    answers = catalog.round_answers(script["taskId"], turn)
    return {sid: v for a in answers for sid, v in a["expected"].items()}


def re_explain_input() -> dict[str, Any]:
    """The steps round 1 of the lead demo leaves open, with the verdicts its script expects
    (every question's answer, 2026-10-16)."""
    expected = round_expected(DEMO_SCRIPT, 0)
    open_steps = [s for s in steps() if expected.get(s["id"], "covered") != "covered"]
    for s in open_steps:
        verdict = expected[s["id"]]
        s.update(verdict=verdict, reason=REASONS.get(verdict, REASONS["missed"]))
    return {**_lang_fields(), "steps": open_steps, "sop_title": _task()["sop"]["title"]}


def transcribe_instruction_input() -> dict[str, Any]:
    return {
        "lang_name": catalog.lang_name(SUPERVISOR),
        "native": catalog.language_native(SUPERVISOR),
    }


def hazard_report_input() -> dict[str, Any]:
    return {
        "worker_lang_name": catalog.lang_name(WORKER),
        "worker_native": catalog.language_native(WORKER),
        "supervisor_lang_name": catalog.lang_name(SUPERVISOR),
        "lang_codes": list(catalog.lang_codes()),
    }


def check_input(task_id: str = TASK_ID) -> dict[str, Any]:
    return {
        **_lang_fields(),
        "steps": steps(task_id),
        "questions": questions(task_id),
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
