"""Load and validate the eval item set (testset/items.json) against the catalog, and the clip manifest."""

import hashlib
import json
import re
from pathlib import Path

from catalog_io import demo_answer, question_by_id, question_payload, steps_for_question, task_map
from config import (
    ABSTAIN_PATTERNS,
    CLIPS_PATH,
    GOLD_LABELS,
    HELD_OUT_TASKS,
    ITEMS_PATH,
    NOISES,
    PATTERNS,
    PENDING_FIELDS,
    SOURCES,
    TESTSET_DIR,
    WORKER_LANGS,
)
from site_noise import NOISE_NAMES as SITE_NOISES

ITEM_KEYS = (
    "id", "taskId", "questionId", "workerLang", "pattern", "noise", "source", "answer",
    "answerGloss", "backTranslation", "fidelity", "gold", "audio", "voice", "demo", "heldOut", "pending",
)
# 72 since 16 Oct: the eight breadth demo answers (build-notes/34-breadth.md); 88 since 17 Oct: the sixteen answers of the
# four demo suites (build-notes/37-domain-suites.md)
MIN_ITEMS, MAX_ITEMS = 36, 88
SPEAKER_CODE = re.compile(r"^V\d{2}$")  # recorded items (v0.5.1): a code, never a name
RECORDED_EXCLUDED_PATTERNS = ("demo", "silence", "wrong_language")


def load_items(path: Path = ITEMS_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def problems(doc: dict, catalog: dict) -> list[str]:
    """Contract problems in the item set. An empty list means the set is valid (pending items included)."""
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
    out.extend(_demo_problems(items, catalog))
    out.extend(_held_out_task_problems(catalog))
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
    if item["noise"] not in (SITE_NOISES if "augmentedFrom" in item else NOISES):
        out.append(f"{item_id}: noise {item['noise']}")
    if "augmentedFrom" in item and item["source"] != "recorded":
        out.append(f"{item_id}: only a recorded item has site-noise copies (augmentedFrom)")
    if item["source"] not in SOURCES:
        out.append(f"{item_id}: source {item['source']}")
    if item["heldOut"] is not (item["taskId"] in HELD_OUT_TASKS):
        out.append(f"{item_id}: heldOut must be true exactly for the held-out tasks {HELD_OUT_TASKS}")
    out.extend(_gold_problems(item, task))
    out.extend(_pending_problems(item))
    out.extend(_question_problems(item, doc))
    if item["source"] == "recorded":
        out.extend(_recorded_problems(item, doc))
    elif "ambient" in item:
        out.append(f"{item_id}: only a recording has an ambient note")
    return out


def _recorded_problems(item: dict, doc: dict) -> list[str]:
    """v0.5.1, a consented human recording (record_clips.py): a speaker code and never a name, explicit consent,
    review until a native speaker has listened, its clip under audio/recorded/, and the task, question, language,
    pattern and gold of the synthetic item it re-voices (recordedFrom), so its gold labels stay true."""
    item_id = item["id"]
    out = []
    if item.get("consent") is not True:
        out.append(f"{item_id}: a recorded item needs consent: true")
    if not isinstance(item["voice"], str) or not SPEAKER_CODE.match(item["voice"]):
        out.append(f"{item_id}: voice must be a speaker code V01-V99, never a name")
    if item["fidelity"] not in ("review", "ok"):
        out.append(f"{item_id}: fidelity must be review or ok")
    if item["pattern"] in RECORDED_EXCLUDED_PATTERNS:
        out.append(f"{item_id}: {item['pattern']} items are not recorded")
    if "ambient" in item and ("augmentedFrom" in item or not isinstance(item["ambient"], str)
                              or not item["ambient"].strip()):
        out.append(f"{item_id}: ambient is a non-empty note of the real noise in an as-recorded clip, never a copy")
    if "augmentedFrom" in item:
        out.extend(_augmented_problems(item, doc))
    elif item["noise"] != "clean":
        out.append(f"{item_id}: a recording is noise clean; site noise goes on a copy (augment_recorded.py)")
    source = next((i for i in doc["items"] if i["id"] == item.get("recordedFrom")), None)
    if source is None or source["source"] != "synthetic_tts":
        return out + [f"{item_id}: recordedFrom must name a synthetic item"]
    recording_id = item.get("augmentedFrom", item_id)
    if recording_id != f"{source['id']}.rec.{item['voice']}" or item["audio"] != f"audio/recorded/{item_id}.wav":
        out.append(f"{item_id}: a recording is <item id>.rec.<speaker>, its clip audio/recorded/<id>.wav")
    same = ("taskId", "questionId", "workerLang", "pattern", "gold", "heldOut", "answerGloss")
    if any(item[key] != source[key] for key in same):
        out.append(f"{item_id}: task, question, language, pattern, gold and gloss must match {source['id']}")
    return out


# A site-noise copy (augment_recorded.py, 16 Oct) is the same speech as its recording, with noise added.
AUGMENTED_SAME = ("taskId", "questionId", "workerLang", "pattern", "gold", "heldOut", "answerGloss", "voice",
                  "recordedFrom", "answer", "backTranslation", "fidelity", "pending", "consent")


def _augmented_problems(item: dict, doc: dict) -> list[str]:
    """A site-noise copy names a clean recording (augmentedFrom), is <recording id>.<profile>.<snr>, and keeps that
    recording's fields and texts; a copy left behind when its recording changed is a problem until the tool reruns."""
    item_id = item["id"]
    recording = next((i for i in doc["items"] if i["id"] == item["augmentedFrom"]), None)
    if recording is None or recording["source"] != "recorded" or "augmentedFrom" in recording:
        return [f"{item_id}: augmentedFrom must name a clean recorded item"]
    out = []
    if recording.get("ambient"):
        out.append(f"{item_id}: site noise is added only to a quiet-room recording, not to {recording['id']}")
    if item_id != f"{recording['id']}.{item['noise']}":
        out.append(f"{item_id}: a site-noise copy is <recording id>.<noise>, noise one of {', '.join(SITE_NOISES)}")
    if any(item.get(key) != recording.get(key) for key in AUGMENTED_SAME):
        out.append(f"{item_id}: a site-noise copy keeps {recording['id']}'s fields and texts "
                   "(run augment_recorded.py again)")
    return out


def question_text(item: dict, doc: dict) -> str | None:
    """The item's question in its worker language, or None while that translation is pending."""
    return doc["questions"].get(item["taskId"], {}).get(item["questionId"], {}).get(item["workerLang"]) or None


def _question_problems(item: dict, doc: dict) -> list[str]:
    """A missing question text is allowed only while it is listed in pendingQuestions, and then the item cannot
    have a current clip either: an item is never runnable without the question it answers."""
    if question_text(item, doc) is not None:
        return []
    key = f"{item['taskId']}.{item['questionId']}.{item['workerLang']}"
    if key not in doc.get("pendingQuestions", []):
        return [f"{item['id']}: no worker-language question text"]
    if "audio" not in item["pending"]:
        return [f"{item['id']}: its question is pending, so its clip must be pending too"]
    return []


def _held_out_task_problems(catalog: dict) -> list[str]:
    """A held-out task is a catalog task with no demo script (nothing scripted about it is shown to anyone)."""
    tasks = task_map(catalog)
    scripted = {script["taskId"] for script in catalog["demoScripts"]}
    return ([f"held-out task {task_id} is not in the catalog" for task_id in HELD_OUT_TASKS if task_id not in tasks]
            + [f"held-out task {task_id} has a demo script" for task_id in HELD_OUT_TASKS if task_id in scripted])


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


def _pending_problems(item: dict) -> list[str]:
    """A pending field holds no text, and an empty text that should exist is always marked pending."""
    item_id, pending = item["id"], item["pending"]
    if not isinstance(pending, list) or not set(pending) <= set(PENDING_FIELDS) or len(set(pending)) != len(pending):
        return [f"{item_id}: pending must list fields from {PENDING_FIELDS}"]
    out = []
    silent = item["pattern"] == "silence"
    if "answer" in pending:
        if item["answer"]:
            out.append(f"{item_id}: answer is pending but holds text")
        if item["source"] == "recorded":  # the clip came first: only its transcript waits
            if "backTranslation" not in pending:
                out.append(f"{item_id}: a pending transcript leaves its back-translation pending too")
        elif not {"backTranslation", "audio"} <= set(pending):
            out.append(f"{item_id}: a pending answer leaves its back-translation and clip pending too")
    elif not item["answer"] and not silent:
        out.append(f"{item_id}: answer is empty but not marked pending")
    if "backTranslation" in pending and item["backTranslation"]:
        out.append(f"{item_id}: backTranslation is pending but holds text")
    if not item["backTranslation"] and not silent and "backTranslation" not in pending:
        out.append(f"{item_id}: backTranslation is empty but not marked pending")
    return out


def _demo_problems(items: list[dict], catalog: dict) -> list[str]:
    """Demo items carry demo = {script, round}: the catalog demoScripts id and the 0-based index into its
    rounds (endpoint 24's round is round + 1). The item's questionId names the round's own answer or, since 16 Oct,
    one of its followUps, and (taskId, workerLang, round, questionId) is unique."""
    scripts = {script["id"]: script for script in catalog["demoScripts"]}
    out, seen = [], set()
    for item in items:
        demo = item.get("demo")
        if item["pattern"] != "demo":
            if demo is not None:
                out.append(f"{item['id']}: only demo items carry demo")
            continue
        script = scripts.get((demo or {}).get("script"))
        n = (demo or {}).get("round")
        if script is None or not isinstance(n, int) or isinstance(n, bool) or not 0 <= n < len(script["rounds"]):
            out.append(f"{item['id']}: demo must name a catalog demo script and an index into its rounds")
            continue
        if (script["taskId"], script["workerLang"]) != (item["taskId"], item["workerLang"]):
            out.append(f"{item['id']}: demo script {script['id']} is for another task or language")
        if demo_answer(script["rounds"][n], item["questionId"]) is None:
            out.append(f"{item['id']}: round {n + 1} of {script['id']} scripts no answer to {item['questionId']}")
        key = (item["taskId"], item["workerLang"], n, item["questionId"])
        if key in seen:
            out.append(f"{item['id']}: a second demo item for {key}")
        seen.add(key)
    return out


def pending_items(doc: dict, field: str | None = None) -> list[dict]:
    """Items with anything pending, or with that one field pending."""
    return [item for item in doc["items"] if (field in item["pending"] if field else item["pending"])]


def audio_path(item: dict) -> Path:
    return TESTSET_DIR / item["audio"]


def load_clip_manifest(path: Path = CLIPS_PATH) -> dict[str, dict]:
    """Clip id -> {text, voice, model, render, cacheKey, sha256}: what the clip on disk says."""
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))["clips"]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clip_is_current(item: dict, clips: dict[str, dict], text: str | None = None) -> bool:
    """The item's clip exists and says the item's answer in the item's voice (manifest and file hash agree).

    `text` overrides item["answer"] (the build checks a record before its item is written). A consented
    recording is not rendered, so it is current when its file exists.
    """
    entry = clips.get(item["id"])
    path = audio_path(item)
    if item.get("source") == "recorded":
        return path.is_file()
    if entry is None or not path.is_file():
        return False
    wanted = item["answer"] if text is None else text
    return entry["text"] == wanted and entry["voice"] == item["voice"] and entry["sha256"] == file_sha256(path)


def item_is_ready(item: dict, doc: dict, clips: dict[str, dict]) -> bool:
    """The item can run: its clip is current and its question has a worker-language text."""
    return clip_is_current(item, clips) and question_text(item, doc) is not None


def items_sha256(path: Path = ITEMS_PATH) -> str:
    """The report's testsetSha256: the SHA-256 of the items.json bytes the run read."""
    return file_sha256(path)


def build_check_payload(item: dict, doc: dict, catalog: dict) -> dict:
    """Keyword arguments for run_check: steps and questions from the catalog, the clip, the languages.

    Steps are exactly the item's question's stepIds (catalog order), and the question is the only one
    passed, so no step is in scope without a question (guard rule 6, not_asked, never fires here).
    """
    task = task_map(catalog)[item["taskId"]]
    worker_text = doc["questions"][item["taskId"]][item["questionId"]][item["workerLang"]]
    return {
        "steps": steps_for_question(task, item["questionId"]),
        "questions": [question_payload(task, item["questionId"], worker_text)],
        "clips": {item["questionId"]: audio_path(item).read_bytes()},
        "worker_lang": item["workerLang"],
        "supervisor_lang": "en",
    }
