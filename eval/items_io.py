"""Load and validate the eval item set (testset/items.json) against the catalog."""

import json
from pathlib import Path

from catalog_io import question_by_id, question_payload, steps_for_question, task_map
from config import (
    ABSTAIN_PATTERNS,
    GOLD_LABELS,
    ITEMS_PATH,
    NOISES,
    PATTERNS,
    SOURCES,
    TESTSET_DIR,
    WORKER_LANGS,
)

ITEM_KEYS = (
    "id", "taskId", "questionId", "workerLang", "pattern", "noise", "source", "answer",
    "answerGloss", "backTranslation", "fidelity", "gold", "audio", "voice",
)
MIN_ITEMS, MAX_ITEMS = 36, 42


def load_items(path: Path = ITEMS_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def problems(doc: dict, catalog: dict) -> list[str]:
    """Contract problems in the item set. An empty list means the set is valid."""
    tasks = task_map(catalog)
    items = doc["items"]
    synthetic = [item for item in items if item.get("source") == "synthetic_tts"]
    out: list[str] = []
    if not MIN_ITEMS <= len(synthetic) <= MAX_ITEMS:
        out.append(f"synthetic item count {len(synthetic)} outside {MIN_ITEMS}-{MAX_ITEMS}")
    dupes = {i["id"] for i in items if sum(j["id"] == i["id"] for j in items) > 1}
    out.extend(f"duplicate id {item_id}" for item_id in sorted(dupes))
    for item in items:
        out.extend(_item_problems(item, doc, tasks))
    return out


def _item_problems(item: dict, doc: dict, tasks: dict) -> list[str]:
    item_id = item.get("id", "?")
    missing = [key for key in ITEM_KEYS if key not in item]
    if missing:
        return [f"{item_id}: missing keys {missing}"]
    task = tasks.get(item["taskId"])
    if task is None:
        return [f"{item_id}: unknown taskId {item['taskId']}"]
    out: list[str] = []
    if item["workerLang"] not in WORKER_LANGS:
        out.append(f"{item_id}: workerLang {item['workerLang']}")
    if item["pattern"] not in PATTERNS:
        out.append(f"{item_id}: pattern {item['pattern']}")
    if item["noise"] not in NOISES:
        out.append(f"{item_id}: noise {item['noise']}")
    if item["source"] not in SOURCES:
        out.append(f"{item_id}: source {item['source']}")
    out.extend(_gold_problems(item, task))
    if item["workerLang"] not in doc["questions"].get(item["taskId"], {}).get(item["questionId"], {}):
        out.append(f"{item_id}: no worker-language question text")
    return out


def _gold_problems(item: dict, task: dict) -> list[str]:
    item_id = item["id"]
    try:
        step_ids = set(question_by_id(task, item["questionId"])["stepIds"])
    except StopIteration:
        return [f"{item_id}: unknown questionId {item['questionId']}"]
    out = []
    if set(item["gold"]) != step_ids:
        out.append(f"{item_id}: gold keys {sorted(item['gold'])} != question steps {sorted(step_ids)}")
    labels = set(item["gold"].values())
    if not labels <= set(GOLD_LABELS):
        out.append(f"{item_id}: gold labels must be covered, missed, contradicted or unclear")
    abstains = item["pattern"] in ABSTAIN_PATTERNS
    if "unclear" in labels and not abstains:
        out.append(f"{item_id}: gold unclear is only for silence and wrong_language items")
    if abstains and labels != {"unclear"}:
        out.append(f"{item_id}: {item['pattern']} items are gold unclear on every step")
    return out


def audio_path(item: dict) -> Path:
    return TESTSET_DIR / item["audio"]


def build_check_payload(item: dict, doc: dict, catalog: dict) -> dict:
    """Keyword arguments for run_check: steps and questions from the catalog, the clip, the languages."""
    task = task_map(catalog)[item["taskId"]]
    worker_text = doc["questions"][item["taskId"]][item["questionId"]][item["workerLang"]]
    return {
        "steps": steps_for_question(task, item["questionId"]),
        "questions": [question_payload(task, item["questionId"], worker_text)],
        "clips": {item["questionId"]: audio_path(item).read_bytes()},
        "worker_lang": item["workerLang"],
        "supervisor_lang": "en",
    }
