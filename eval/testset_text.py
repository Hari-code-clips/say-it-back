"""Translation and back-translation for the synthetic set.

Only the rows given are sent: the build passes the answers and questions that its ledger (the previous
items.json) cannot supply. Forward translation is one batch per spoken language (answers plus that
language's question texts). Back-translation is a separate call per BACK_BATCH rows and never sees the
English gloss. In an offline run a batch that is not cached is skipped and its rows stay pending.
"""

import json

from catalog_io import site_worker_langs
from config import BACK_BATCH
from gemini_client import GeminiCalls, OfflineMiss

LANG_NAMES = {
    "ta": "Tamil", "bn": "Bengali", "zh": "Simplified Chinese (Mandarin)",
    "my": "Burmese", "hi": "Hindi", "or": "Odia", "te": "Telugu",
}
SITE_TERMS = (
    "breaker, lock, tag, tester, harness, buckle, lanyard, lifeline, scaffold, ladder, shoring, "
    "trench, barrier, signalman, extinguisher, fire watcher, hook, crane, load"
)
TRANSLATE_SYSTEM = (
    "You write the spoken answers a construction worker would give in a safety check, for a synthetic "
    "test set. Translate each English draft into {lang} as the worker would say it aloud on site: natural "
    "spoken register, short sentences, numbers written out as words. Keep site loanwords as they are said "
    "on site ({terms}).\n"
    "Rules:\n"
    "1. Keep everything the draft says: omissions, hedges, wrong numbers, wrong order and wrong actions. "
    "Never add a safety step, never correct a mistake and never complete a missing part.\n"
    "2. Keep the stance: a negation stays a negation, a refusal stays a refusal.\n"
    "3. A draft such as 'OK, understood.' or a question repeated back stays that kind of line.\n"
    "4. Translate each interviewer question as a supervisor would ask it aloud in {lang}, keeping its "
    "meaning and key words.\n"
    "Return only the JSON requested."
)
TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["id", "text"]}},
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {"key": {"type": "string"}, "text": {"type": "string"}},
            "required": ["key", "text"]}},
    },
    "required": ["answers", "questions"],
}
BACK_SYSTEM = (
    "You translate spoken worker answers from a construction-site safety check into English, for an audit. "
    "Translate literally and faithfully, as an independent translator who has not seen any English source. "
    "Keep omissions, hedges, wrong numbers and wrong actions. Do not add, infer or improve anything. "
    "Each item names its language. Return only the JSON requested."
)
BACK_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "en": {"type": "string"}},
        "required": ["id", "en"]}}},
    "required": ["items"],
}


def answers_by_language(records: list[dict]) -> dict[str, list[dict]]:
    """English drafts to translate, grouped by the language they are spoken in."""
    out: dict[str, list[dict]] = {}
    for rec in records:
        if rec["needsTranslation"]:
            out.setdefault(rec["spokenLang"], []).append({"id": rec["id"], "en": rec["gloss"]})
    return out


def questions_by_language(catalog: dict) -> dict[str, list[dict]]:
    """Every catalog question, once per site worker language of its task."""
    out: dict[str, list[dict]] = {}
    for task in catalog["tasks"]:
        for lang in site_worker_langs(catalog, task):
            for question in task["referenceQuestions"]:
                out.setdefault(lang, []).append({"key": f"{task['id']}.{question['id']}", "en": question["text"]})
    return out


def translate_all(calls: GeminiCalls, answers: dict[str, list[dict]], questions: dict[str, list[dict]],
                  ) -> tuple[dict[str, str], dict[tuple[str, str], str], list[str]]:
    """Returns (answer id -> worker text, (question key, lang) -> worker text, languages left pending).

    A language with no rows makes no call. A language whose batch an offline run has not cached is
    returned in the third list and none of its rows is filled.
    """
    texts: dict[str, str] = {}
    qtexts: dict[tuple[str, str], str] = {}
    missed: list[str] = []
    for lang in sorted(set(answers) | set(questions)):
        rows_a, rows_q = answers.get(lang, []), questions.get(lang, [])
        if not rows_a and not rows_q:
            continue
        try:
            answer_map, question_map = translate_language(calls, lang, rows_a, rows_q)
        except OfflineMiss:
            missed.append(lang)
            continue
        texts.update(answer_map)
        qtexts.update({(key, lang): text for key, text in question_map.items()})
    return texts, qtexts, missed


def translate_language(calls: GeminiCalls, lang: str, answers: list[dict], questions: list[dict],
                       ) -> tuple[dict[str, str], dict[str, str]]:
    prompt = _translate_prompt(answers, questions)
    data = calls.text_json(
        purpose=f"translate {lang}: {len(answers)} answers, {len(questions)} questions",
        system=TRANSLATE_SYSTEM.format(lang=LANG_NAMES[lang], terms=SITE_TERMS),
        prompt=prompt,
        schema=TRANSLATE_SCHEMA,
        validate=lambda d: _check_translation(d, answers, questions),
    )
    return ({row["id"]: row["text"] for row in data["answers"]},
            {row["key"]: row["text"] for row in data["questions"]})


def back_translate_all(calls: GeminiCalls, spoken: list[dict]) -> tuple[dict[str, str], list[str]]:
    """spoken: [{id, lang, text}], in batches of BACK_BATCH. Returns (id -> English, ids left pending)."""
    out: dict[str, str] = {}
    missed: list[str] = []
    batches = [spoken[i:i + BACK_BATCH] for i in range(0, len(spoken), BACK_BATCH)]
    for part, batch in enumerate(batches, start=1):
        try:
            out.update(_back_batch(calls, part, batch))
        except OfflineMiss:
            missed.extend(row["id"] for row in batch)
    return out, missed


def _back_batch(calls: GeminiCalls, part: int, batch: list[dict]) -> dict[str, str]:
    payload = [{"id": row["id"], "language": LANG_NAMES[row["lang"]], "text": row["text"]} for row in batch]
    prompt = "Translate each item into English. Return every id exactly as given.\n" + _dump(payload)
    data = calls.text_json(
        purpose=f"back-translate part {part}: {len(batch)} answers",
        system=BACK_SYSTEM,
        prompt=prompt,
        schema=BACK_SCHEMA,
        validate=lambda d: _check_back(d, batch),
    )
    return {row["id"]: row["en"] for row in data["items"]}


def _translate_prompt(answers: list[dict], questions: list[dict]) -> str:
    payload = {
        "answers": [{"id": a["id"], "draft": a["en"]} for a in answers],
        "questions": [{"key": q["key"], "draft": q["en"]} for q in questions],
    }
    return "Translate the drafts below. Return every id and key exactly as given.\n" + _dump(payload)


def _check_translation(data: dict, answers: list[dict], questions: list[dict]) -> None:
    _same_keys([row["id"] for row in data["answers"]], [a["id"] for a in answers], "answer ids")
    _same_keys([row["key"] for row in data["questions"]], [q["key"] for q in questions], "question keys")
    if any(not row["text"].strip() for row in data["answers"] + data["questions"]):
        raise ValueError("empty translation returned")


def _check_back(data: dict, batch: list[dict]) -> None:
    _same_keys([row["id"] for row in data["items"]], [row["id"] for row in batch], "back-translation ids")
    if any(not row["en"].strip() for row in data["items"]):
        raise ValueError("empty back-translation returned")


def _same_keys(got: list[str], want: list[str], label: str) -> None:
    if len(set(got)) != len(got) or sorted(got) != sorted(want):
        raise ValueError(f"{label} do not match the batch")


def _dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
