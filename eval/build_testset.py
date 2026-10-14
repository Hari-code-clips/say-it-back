"""Regenerate the synthetic eval set from testset/spec.json.

Stages: translate (one batch per language) -> back-translate (separate calls) -> TTS (one call per clip)
-> local noise and mixing (ffmpeg + stdlib) -> testset/items.json. Every Gemini result is cached under
eval/.cache/gemini, so a re-run with unchanged inputs makes no calls. Every real call is logged in
eval/gemini_calls.log, and the whole project is capped at GEMINI_CALL_BUDGET calls.

Usage:
  uv run python build_testset.py                    # full build
  uv run python build_testset.py --only hot-work    # only render clips whose id contains the text
  uv run python build_testset.py --skip-audio       # text stage only (translations, back-translations)
  uv run python build_testset.py --spot-check       # transcribe 5 clips back with Flash (5 calls)
"""

import argparse
import difflib
import hashlib
import json
import sys
import unicodedata

from audio_tools import mix_at_snr, noise_bed, read_samples, scale_to_dbfs, speech_to_16k, write_samples
from catalog_io import load_catalog, task_map
from config import (
    AUDIO_DIR,
    FLASH_MODEL,
    ITEMS_PATH,
    SILENCE_DBFS,
    SILENCE_SECONDS,
    SAMPLE_RATE,
    SNR_DB,
    SPEC_PATH,
    SPOTCHECK_PATH,
    TTS_VOICES,
    WORK_DIR,
)
from gemini_client import GeminiCalls
from items_io import audio_path
from testset_text import (
    LANG_NAMES,
    answers_by_language,
    back_translate_all,
    questions_by_language,
    translate_all,
)

SPOTCHECK_IDS = (
    "panel-isolation.q1.ta.code_switch.clean",
    "hot-work.q2.zh.numbers.snr5",
    "trench-entry.q1.or.complete.clean",
    "lifting-zone.q1.my.negation.clean",
    "panel-isolation.q1.bn.two_missing.snr10",
)
SPOT_SIMILARITY_MATCH = 0.90
SPOT_SYSTEM = (
    "You transcribe short spoken answers from a construction-site safety check. Transcribe exactly what is "
    "said, in the language and script it is spoken in. Do not translate, correct or add anything."
)
SPOT_PROMPT = "Transcribe this audio. Return JSON: transcript (verbatim) and language (English name)."
SPOT_SCHEMA = {
    "type": "object",
    "properties": {"transcript": {"type": "string"}, "language": {"type": "string"}},
    "required": ["transcript", "language"],
}


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="render audio only for item ids containing this text")
    parser.add_argument("--skip-audio", action="store_true", help="stop after the translation stage")
    parser.add_argument("--spot-check", action="store_true", help="transcribe 5 clips back with Flash")
    parser.add_argument("--offline", action="store_true",
                        help="regenerate items.json from the cache only; a cache miss stops the run, no call is made")
    return parser.parse_args(argv)


def item_id(entry: dict) -> str:
    base = f"{entry['taskId']}.{entry['questionId']}.{entry['workerLang']}.{entry['pattern']}.{entry['noise']}"
    return f"{base}.{entry['variant']}" if entry.get("variant") else base


def voice_for(item: str) -> str:
    return TTS_VOICES[_digest_int(item) % len(TTS_VOICES)]


def seed_for(item: str) -> int:
    return _digest_int(item) % 100000


def _digest_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def resolve_records(spec: dict, catalog: dict) -> list[dict]:
    tasks = task_map(catalog)
    demos = {script["id"]: script for script in catalog["demoScripts"]}
    records = [_resolve(entry, tasks, demos) for entry in spec["items"]]
    ids = [rec["id"] for rec in records]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate item ids in spec.json (add a variant)")
    return records


def _resolve(entry: dict, tasks: dict, demos: dict) -> dict:
    spoken = entry.get("spokenLang", entry["workerLang"])
    rec = {
        "id": item_id(entry),
        "taskId": entry["taskId"],
        "questionId": entry["questionId"],
        "workerLang": entry["workerLang"],
        "spokenLang": spoken,
        "pattern": entry["pattern"],
        "noise": entry["noise"],
        "gold": dict(entry["gold"]),
        "fidelity": entry.get("fidelity", "ok"),
        "needsTranslation": entry["pattern"] not in ("demo", "silence"),
        "gloss": entry["gloss"] if entry["pattern"] != "demo" else "",
        "text": "",
    }
    if entry["taskId"] not in tasks:
        raise ValueError(f"{rec['id']}: unknown task")
    if entry["pattern"] == "demo":
        _fill_demo(rec, entry, demos)
    if entry["pattern"] == "silence":
        rec["text"] = ""
    rec["glossDisplay"] = _display_gloss(rec)
    return rec


def _fill_demo(rec: dict, entry: dict, demos: dict) -> None:
    script = demos[entry["demo"]["script"]]
    turn = script["rounds"][entry["demo"]["round"]]
    if (script["taskId"], script["workerLang"], turn["questionId"]) != (
            entry["taskId"], entry["workerLang"], entry["questionId"]):
        raise ValueError(f"{rec['id']}: demo script does not match the item")
    if turn["expected"] != entry["gold"]:
        raise ValueError(f"{rec['id']}: gold differs from the catalog demo's expected labels")
    rec["gloss"] = turn["answer"]["en"]
    rec["text"] = turn["answer"][entry["workerLang"]]


def _display_gloss(rec: dict) -> str:
    if rec["spokenLang"] == rec["workerLang"]:
        return rec["gloss"]
    return f"[Spoken in {LANG_NAMES[rec['spokenLang']]}, expected {LANG_NAMES[rec['workerLang']]}] {rec['gloss']}"


def build_texts(calls: GeminiCalls, records: list[dict], catalog: dict,
                ) -> tuple[dict[str, str], dict[tuple[str, str], str], dict[str, str]]:
    """Returns (answer id -> worker text, (question key, lang) -> question text, answer id -> back-translation)."""
    texts = {rec["id"]: rec["text"] for rec in records if not rec["needsTranslation"]}
    translated, qtexts = translate_all(calls, answers_by_language(records), questions_by_language(catalog))
    texts.update(translated)
    spoken = [{"id": rec["id"], "lang": rec["spokenLang"], "text": texts[rec["id"]]}
              for rec in records if rec["pattern"] != "silence"]
    backs = back_translate_all(calls, spoken)
    return texts, qtexts, backs


def apply_question_fixes(qtexts: dict[tuple[str, str], str], fixes: dict[str, str]) -> dict[tuple[str, str], str]:
    """Hand corrections from spec.json, keyed 'task.question.lang'. Each must name a real question."""
    out = dict(qtexts)
    for dotted, text in fixes.items():
        task_id, question_id, lang = dotted.split(".")
        key = (f"{task_id}.{question_id}", lang)
        if key not in out:
            raise ValueError(f"questionFixes names an unknown question: {dotted}")
        out[key] = text
    return out


def keep_recorded(doc: dict) -> dict:
    """Consented recordings are added by hand with source 'recorded'. A rebuild must not drop them."""
    if not ITEMS_PATH.exists():
        return doc
    previous = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    kept = [item for item in previous.get("items", []) if item.get("source") == "recorded"]
    return {**doc, "items": [*doc["items"], *kept]}


def question_block(qtexts: dict[tuple[str, str], str]) -> dict:
    block: dict[str, dict[str, dict[str, str]]] = {}
    for (key, lang), text in qtexts.items():
        task_id, question_id = key.split(".")
        block.setdefault(task_id, {}).setdefault(question_id, {})[lang] = text
    return {task: {qid: dict(sorted(langs.items())) for qid, langs in sorted(qs.items())}
            for task, qs in sorted(block.items())}


def render_item(calls: GeminiCalls, rec: dict, text: str) -> None:
    out = AUDIO_DIR / f"{rec['id']}.wav"
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if rec["pattern"] == "silence":
        bed = WORK_DIR / f"{rec['id']}.bed.wav"
        noise_bed(bed, SILENCE_SECONDS, seed_for(rec["id"]))
        write_samples(out, scale_to_dbfs(read_samples(bed), SILENCE_DBFS))
        return
    raw = calls.tts_wav(purpose=f"tts {rec['id']}", text=text, voice=voice_for(rec["id"]))
    src = WORK_DIR / f"{rec['id']}.24k.wav"
    src.write_bytes(raw)
    speech_path = WORK_DIR / f"{rec['id']}.16k.wav"
    speech_to_16k(src, speech_path)
    speech = read_samples(speech_path)
    if rec["noise"] == "clean":
        write_samples(out, speech)
        return
    bed = WORK_DIR / f"{rec['id']}.bed.wav"
    noise_bed(bed, len(speech) / SAMPLE_RATE + 0.5, seed_for(rec["id"]))
    write_samples(out, mix_at_snr(speech, read_samples(bed), SNR_DB[rec["noise"]]))


def item_doc(rec: dict, texts: dict[str, str], backs: dict[str, str]) -> dict:
    silent = rec["pattern"] == "silence"
    return {
        "id": rec["id"],
        "taskId": rec["taskId"],
        "questionId": rec["questionId"],
        "workerLang": rec["workerLang"],
        "pattern": rec["pattern"],
        "noise": rec["noise"],
        "source": "synthetic_tts",
        "answer": texts.get(rec["id"], ""),
        "answerGloss": rec["glossDisplay"],
        "backTranslation": backs.get(rec["id"], ""),
        "fidelity": rec["fidelity"],
        "gold": rec["gold"],
        "audio": f"audio/{rec['id']}.wav",
        "voice": None if silent else voice_for(rec["id"]),
    }


def spot_check(calls: GeminiCalls, doc: dict) -> list[dict]:
    wanted = [item for item in doc["items"] if item["id"] in SPOTCHECK_IDS]
    rows = []
    for item in wanted:
        wav = audio_path(item).read_bytes()
        got = calls.audio_json(
            purpose=f"spot-check {item['id']}", wav=wav, system=SPOT_SYSTEM, prompt=SPOT_PROMPT,
            schema=SPOT_SCHEMA, validate=_check_spot,
        )
        ratio = similarity(item["answer"], got["transcript"])
        rows.append({"id": item["id"], "answer": item["answer"], "transcript": got["transcript"],
                     "language": got["language"], "similarity": round(ratio, 3),
                     "match": ratio >= SPOT_SIMILARITY_MATCH})
    SPOTCHECK_PATH.write_text(json.dumps({"model": FLASH_MODEL, "items": rows}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    return rows


def similarity(expected: str, heard: str) -> float:
    return difflib.SequenceMatcher(None, _squash(expected), _squash(heard)).ratio()


def _squash(text: str) -> str:
    """Casefold and drop punctuation, symbols and spaces. Vowel signs (marks) are kept."""
    return "".join(ch.casefold() for ch in text if unicodedata.category(ch)[0] not in "PZS" and not ch.isspace())


def _check_spot(data: dict) -> None:
    if not isinstance(data.get("transcript"), str) or not isinstance(data.get("language"), str):
        raise ValueError("spot-check response is missing transcript or language")


def run_build(args: argparse.Namespace) -> int:
    catalog = load_catalog()
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    records = resolve_records(spec, catalog)
    calls = GeminiCalls(offline=args.offline)
    texts, qtexts, backs = build_texts(calls, records, catalog)
    qtexts = apply_question_fixes(qtexts, spec.get("questionFixes", {}))
    if not args.skip_audio:
        for rec in records:
            if args.only is None or args.only in rec["id"]:
                render_item(calls, rec, texts.get(rec["id"], ""))
                print(f"rendered {rec['id']}", flush=True)
    doc = keep_recorded({
        "version": spec["version"],
        "questions": question_block(qtexts),
        "items": [item_doc(rec, texts, backs) for rec in records],
    })
    ITEMS_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {ITEMS_PATH.name}: {len(doc['items'])} items", flush=True)
    if args.skip_audio:
        print("audio not rendered (--skip-audio)", flush=True)
    elif args.spot_check:
        for row in spot_check(calls, doc):
            print(f"spot {row['id']}: similarity {row['similarity']} match={row['match']}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_build(args)
    except Exception as exc:  # noqa: BLE001 - the build stops and reports; no traceback with request details
        print(f"STOPPED: {type(exc).__name__}: {str(exc)[:400]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
