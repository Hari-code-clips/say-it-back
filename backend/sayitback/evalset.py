"""The evaluation set and reports written by eval/ (SIB_EVAL_DIR), for endpoints 16-19.

Item ids are looked up in items.json and never joined into a path; an item's audio path is
resolved and must stay inside the testset folder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sayitback import catalog
from sayitback.errors import NotFound
from sayitback.models import Question, Step

PUBLIC_FIELDS = (
    "id",
    "taskId",
    "questionId",
    "workerLang",
    "pattern",
    "noise",
    "source",
    "answerGloss",
    "gold",
)
EVAL_SUPERVISOR_LANG = "en"
UNSAFE_GOLD = ("missed", "contradicted")


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {k: item[k] for k in PUBLIC_FIELDS if k in item}


class EvalData:
    def __init__(self, root: Path) -> None:
        self.testset = root / "testset"
        self.report = root / "reports" / "latest.json"

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, NotADirectoryError):
            return None

    def latest_report(self) -> dict[str, Any]:
        report = self._read(self.report)
        if report is None:
            raise NotFound("No evaluation report has been generated yet.", code="no_report")
        return report

    def items_file(self) -> dict[str, Any]:
        data = self._read(self.testset / "items.json")
        if data is None:
            raise NotFound("No evaluation test set is available.", code="no_testset")
        return data

    def item(self, item_id: str) -> dict[str, Any]:
        found = next(
            (i for i in self.items_file().get("items", []) if i.get("id") == item_id), None
        )
        if found is None:
            raise NotFound("Unknown evaluation item.", code="no_item")
        return found

    def audio_path(self, item: dict[str, Any]) -> Path:
        base = self.testset.resolve()
        path = (base / item.get("audio", "")).resolve()
        if base not in path.parents or not path.is_file():
            raise NotFound("The item's audio is not available.", code="no_audio")
        return path

    def check_inputs(self, item: dict[str, Any]) -> tuple[list[Step], list[Question]]:
        """Reference steps and the item's question (worker-language text), supervisor in English."""
        task_id, qid, lang = item["taskId"], item["questionId"], item["workerLang"]
        reference = next((q for q in catalog.reference_questions(task_id) if q["id"] == qid), None)
        text = self.items_file().get("questions", {}).get(task_id, {}).get(qid, {}).get(lang)
        if reference is None or not text:
            raise NotFound("The item's question is not in the test set.", code="no_item")
        scope = set(reference["stepIds"])
        steps = [
            Step.model_validate(s) for s in catalog.reference_steps(task_id) if s["id"] in scope
        ]
        question = Question(
            id=qid, text=text, back_translation=reference["text"], step_ids=reference["stepIds"]
        )
        return steps, [question]


def agreement(gold: dict[str, str], predicted: dict[str, str]) -> dict[str, bool]:
    return {sid: predicted.get(sid) == verdict for sid, verdict in gold.items()}


def is_unsafe(gold: dict[str, str], predicted: dict[str, str]) -> bool:
    """A gold missed or contradicted step that was rated covered: the error that matters."""
    return any(v in UNSAFE_GOLD and predicted.get(sid) == "covered" for sid, v in gold.items())
