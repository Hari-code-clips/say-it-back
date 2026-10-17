"""The evaluation set and reports written by eval/ (SIB_EVAL_DIR), for endpoints 16-19, and the
stored sample answers of endpoint 24.

Item ids are looked up in items.json and never joined into a path; an item's audio path is
resolved and must stay inside the testset folder.

An item's clip is served only when its file exists and the item does not list "audio" in its
`pending` list: eval/ marks a clip pending when the file on disk is stale (it voices an older
answer) or missing, and a stale clip must never be played or judged as if it said the item's
answer.

A sample answer (v0.4) is a catalog demo answer (`demoScripts[].rounds[]`, and since 2026-10-16
each round's `followUps`, one per further question) that has a stored synthetic clip: an eval item
of pattern `demo` keyed by (taskId, workerLang, demo.round + 1, questionId), its `demo` being
`{script, round}` with the round 0-based, as spec.json writes it. The item id is never parsed
(API.md, the 2026-10-14 eval line).
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
# Gold misses (API.md, "Eval report"): `unclear` is gold for silence and wrong-language items, where
# the right response is to ask again, so a `covered` there is an unsafe error too.
UNSAFE_GOLD = ("missed", "contradicted", "unclear")
PENDING_AUDIO = "audio"
DEMO_PATTERN = "demo"
SAMPLE_ROUNDS = 2  # round 2's answer serves every later round


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {k: item[k] for k in PUBLIC_FIELDS if k in item}


def reference_context(item: dict[str, Any]) -> dict[str, Any]:
    """Endpoint 17, v0.4: the catalog text an evaluator needs to read an item without the worker
    language. `steps` maps each gold step id to its reference step text, `questionText` is the
    reference question (both English)."""
    task_id, qid = item.get("taskId", ""), item.get("questionId", "")
    texts = {s["id"]: s["text"] for s in catalog.reference_steps(task_id)}
    question = next((q for q in catalog.reference_questions(task_id) if q["id"] == qid), None)
    return {
        "steps": {sid: texts[sid] for sid in item.get("gold", {}) if sid in texts},
        "questionText": question["text"] if question else "",
    }


def demo_round(item: dict[str, Any]) -> int | None:
    """The 1-based demo round a `demo` item voices (`demo.round` + 1), or None if it names none."""
    demo = item.get("demo")
    n = demo.get("round") if isinstance(demo, dict) else None
    return n + 1 if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None


def sample_round(n: int) -> int:
    """Round 1 has its own sample answer; every later round uses round 2's."""
    return 1 if n <= 1 else SAMPLE_ROUNDS


def demo_key(item: dict[str, Any]) -> tuple[Any, Any, int | None, Any]:
    """The demo answer a `demo` item voices: (taskId, workerLang, 1-based round, questionId)."""
    return (item.get("taskId"), item.get("workerLang"), demo_round(item), item.get("questionId"))


def _listed(
    key: tuple[str, str, int, str],
    answer: dict[str, Any],
    step_ids: list[str],
    item: dict[str, Any],
) -> dict[str, Any]:
    task_id, lang, n, qid = key
    gloss = item.get("answerGloss") or answer.get("answer", {}).get("en", "")
    return {
        "taskId": task_id,
        "workerLang": lang,
        "round": n,
        "questionId": qid,
        "stepIds": step_ids,
        "gloss": gloss,
        "own": answer["own"],
        "item": item,
    }


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
        """The item's clip, if it is current: inside the test set, on disk and not pending."""
        base = self.testset.resolve()
        path = (base / str(item.get("audio", ""))).resolve()
        pending = item.get("pending") or []
        stale = isinstance(pending, list) and PENDING_AUDIO in pending
        if base not in path.parents or not path.is_file() or stale:
            raise NotFound("The item's audio is not available.", code="no_audio")
        return path

    def has_audio(self, item: dict[str, Any]) -> bool:
        try:
            self.audio_path(item)
        except NotFound:
            return False
        return True

    def public_items(self) -> list[dict[str, Any]]:
        """Endpoint 17: each item's public fields, its reference text and whether its clip is
        here."""
        return [
            {**public_item(i), **reference_context(i), "hasAudio": self.has_audio(i)}
            for i in self.items_file().get("items", [])
        ]

    # Sample answers (endpoint 24) ---------------------------------------------------------------

    def _demo_items(self) -> list[dict[str, Any]]:
        try:
            items = self.items_file().get("items", [])
        except NotFound:
            return []  # no test set here: there are no stored clips to offer
        return [i for i in items if i.get("pattern") == DEMO_PATTERN and self.has_audio(i)]

    def demo_answers(self) -> list[dict[str, Any]]:
        """The catalog's demo answers that have a stored clip, in catalog order: `{taskId,
        workerLang, round, questionId, stepIds, gloss, own, item}` (round 1 or 2). `stepIds` are the
        reference question's steps, `own` marks the round's own first answer (the others are its
        `followUps`), and `item` is the eval item that holds the clip."""
        items = {demo_key(i): i for i in reversed(self._demo_items())}  # the first item of a key
        found: dict[tuple[str, str, int, str], dict[str, Any]] = {}
        for script in catalog.load_catalog().get("demoScripts", []):
            task_id, lang = script["taskId"], script["workerLang"]
            steps = {q["id"]: list(q["stepIds"]) for q in catalog.reference_questions(task_id)}
            for index, turn in enumerate(script.get("rounds", [])[:SAMPLE_ROUNDS]):
                for answer in catalog.round_answers(task_id, turn):
                    key = (task_id, lang, index + 1, answer["questionId"])
                    if key in items and key not in found:
                        found[key] = _listed(key, answer, steps.get(key[3], []), items[key])
        return list(found.values())

    def demo_answer_audio(
        self, task_id: str, worker_lang: str, n: int, question_id: str | None = None
    ) -> Path:
        """The clip of the answer to `question_id` in round `n` (2 serves every later round);
        without a question id, the round's own first answer, as before 2026-10-16. Else 404
        `no_demo_answer`."""
        if n >= 1:
            key = (task_id, worker_lang, sample_round(n))
            for a in self.demo_answers():
                wanted = a["own"] if question_id is None else a["questionId"] == question_id
                if (a["taskId"], a["workerLang"], a["round"]) == key and wanted:
                    return self.audio_path(a["item"])
        raise NotFound("There is no stored sample answer for this round.", code="no_demo_answer")

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
    """A gold miss (missed, contradicted or unclear) that was rated covered: the error that
    matters."""
    return any(v in UNSAFE_GOLD and predicted.get(sid) == "covered" for sid, v in gold.items())
