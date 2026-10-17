"""Catalog access shared by the testset build and the runner (backend/sayitback/data/catalog.json)."""

import json
import re
from pathlib import Path

from config import CATALOG_PATH, WORKER_LANGS


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def task_map(catalog: dict) -> dict[str, dict]:
    return {task["id"]: task for task in catalog["tasks"]}


def site_worker_langs(catalog: dict, task: dict) -> list[str]:
    """The task's site worker languages that the eval set covers (config.WORKER_LANGS). A site language the set has no
    items in yet (Telugu, 17 Oct) adds no question translation to the paid plan until it joins WORKER_LANGS."""
    site = next(s for s in catalog["sites"] if s["id"] == task["demoSite"])
    return [lang for lang in site["workerLanguages"] if lang in WORKER_LANGS]


def question_by_id(task: dict, question_id: str) -> dict:
    return next(q for q in task["referenceQuestions"] if q["id"] == question_id)


def round_answers(turn: dict) -> list[dict]:
    """A demo round's scripted answers: its own ({questionId, answer, expected}) and, since 16 Oct, its followUps."""
    return [turn, *turn.get("followUps", [])]


def demo_answer(turn: dict, question_id: str) -> dict | None:
    """The answer a demo round scripts for one question, or None if it scripts none."""
    return next((answer for answer in round_answers(turn) if answer["questionId"] == question_id), None)


def steps_for_question(task: dict, question_id: str) -> list[dict]:
    """Steps in scope for one question: the question's stepIds, in catalog order."""
    wanted = set(question_by_id(task, question_id)["stepIds"])
    return [step_payload(step, task) for step in task["referenceSteps"] if step["id"] in wanted]


def step_payload(step: dict, task: dict) -> dict:
    payload = {
        "id": step["id"],
        "text": step["text"],
        "hazard": step["hazard"],
        "essential": list(step["essential"]),
        "source": step["source"],
        "speakable": True,
    }
    if step["source"] in ("sop", "both"):
        payload["sopQuote"] = sop_line_for(task["sop"]["text"], step["text"])
    return payload


def question_payload(task: dict, question_id: str, worker_text: str) -> dict:
    question = question_by_id(task, question_id)
    return {
        "id": question_id,
        "text": worker_text,
        "backTranslation": question["text"],
        "stepIds": list(question["stepIds"]),
    }


def sop_line_for(sop_text: str, step_text: str) -> str:
    """The numbered SOP line that shares the most content words with the step (first wins ties)."""
    lines = [
        re.sub(r"^\d+\.\s*", "", line.strip())
        for line in sop_text.splitlines()
        if re.match(r"^\s*\d+\.", line)
    ]
    wanted = _content_words(step_text)
    return max(lines, key=lambda line: len(wanted & _content_words(line)))


def _content_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]+", text.lower()) if len(word) >= 4}
