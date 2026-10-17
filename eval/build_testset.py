"""Regenerate the synthetic eval set from testset/spec.json.

Stages: translate (one batch per language) -> back-translate (separate calls) -> TTS (one call per clip)
-> local noise and mixing (ffmpeg + stdlib) -> testset/items.json.

The previous items.json is the ledger of model outputs, so only what is new or changed goes to Gemini:
- an item keeps its worker-language text while its English gloss (answerGloss) is unchanged;
- an item keeps its back-translation while its worker-language text is unchanged;
- a question keeps its worker-language text while the catalog's English question is unchanged
  (questionSources records the English each text came from);
- a clip is rendered only when it is missing or says other words than the item's answer
  (testset/audio/clips.json records what each clip says).
Reordering the catalog or adding an item therefore never re-translates or re-voices the rest. Whatever is
not final yet is listed in the item's `pending` (answer, backTranslation, audio).

Every Gemini result is cached under eval/.cache/gemini, every real call is logged in eval/gemini_calls.log,
and the whole project is capped at GEMINI_CALL_BUDGET calls (SIB_EVAL_CALL_BUDGET raises it).

Usage:
  uv run python build_testset.py                         # full build: everything pending is made
  uv run python build_testset.py --only lifting-zone     # render only pending clips whose id contains the text
  uv run python build_testset.py --skip-audio            # text stages only
  uv run python build_testset.py --spot-check            # also transcribe the spot-check clips back with Flash
  uv run python build_testset.py --skip-audio --offline  # regenerate items.json with no call; misses stay pending
  uv run python build_testset.py --plan                  # count the calls a full build would make; no call
  uv run python build_testset.py --rerender ITEM_ID      # voice one clip again, bypassing the cache (1 TTS call)
  uv run python build_testset.py --vendor-only           # render only the Sarvam-voiced clips; no Gemini call
  uv run python build_testset.py --rescore-spot-check    # rescore spotcheck.json from its own transcripts; no call
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field

from audio_tools import mix_at_snr, noise_bed, read_samples, scale_to_dbfs, speech_to_16k, write_samples
from catalog_io import demo_answer, load_catalog, task_map
from config import (
    AUDIO_DIR,
    BACK_BATCH,
    CLIPS_PATH,
    FLASH_MODEL,
    GEMINI_CALL_BUDGET,
    HELD_OUT_TASKS,
    ITEMS_PATH,
    PENDING_FIELDS,
    SILENCE_DBFS,
    SILENCE_SECONDS,
    SAMPLE_RATE,
    SNR_DB,
    SPEC_PATH,
    SPOTCHECK_PATH,
    TTS_MODEL,
    TTS_VOICES,
    WORK_DIR,
)
from gemini_client import GeminiCalls, ModelBlocked, OfflineMiss, backend_name, logged_call_count
from items_io import audio_path, clip_is_current, file_sha256, load_clip_manifest
from vendor_tts import SARVAM_LANGS, VendorCalls, cache_key, is_vendor_voice, parse_voice
from testset_text import (
    LANG_NAMES,
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
    "lifting-zone.q1.ta.demo.clean.r1",  # the lead demo's hard case: the clip evaluators hear first
    "confined-space.q2.hi.negation.clean",  # held out (v0.5): its gold depends on the negation surviving
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
CLIPS_ABOUT = (
    "What each clip in this folder says, written by build_testset.py when it renders the clip. An item's clip "
    "is current when its entry's text and voice equal the item's answer and voice and the file's SHA-256 "
    "equals sha256; any other item is pending 'audio' in items.json. render: interactions or generate_content "
    "(Gemini TTS), sarvam (a second vendor's TTS, vendor_tts.py) or local (silence, no model). cacheKey: the first "
    "12 characters of the TTS cache key, as gemini_calls.log or vendor_calls.log lists it."
)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="render only pending clips whose item id contains this text")
    parser.add_argument("--skip-audio", action="store_true", help="stop after the text stages")
    parser.add_argument("--spot-check", action="store_true", help="transcribe the spot-check clips back with Flash")
    parser.add_argument("--offline", action="store_true",
                        help="make no call: anything not in the ledger or the cache stays pending")
    parser.add_argument("--plan", action="store_true",
                        help="print the calls a full build (and the eval) would make; no call, nothing written")
    parser.add_argument("--vendor-only", action="store_true",
                        help="call only the second TTS vendor (Sarvam, SARVAM_API_KEY); Gemini stays offline")
    parser.add_argument("--rerender", metavar="ITEM_ID",
                        help="voice this one clip again with a new TTS call (after a failed spot-check)")
    parser.add_argument("--rescore-spot-check", action="store_true",
                        help="score spotcheck.json again from the transcripts it holds; no call, no other file")
    return parser.parse_args(argv)


def item_id(entry: dict) -> str:
    base = f"{entry['taskId']}.{entry['questionId']}.{entry['workerLang']}.{entry['pattern']}.{entry['noise']}"
    return f"{base}.{entry['variant']}" if entry.get("variant") else base


def voice_for(item: str) -> str:
    return TTS_VOICES[_digest_int(item) % len(TTS_VOICES)]


def rec_voice(rec: dict) -> str | None:
    """The clip's voice: spec.json's vendor `voice` when it names one (16 Oct), else the Gemini voice for the id."""
    if rec["pattern"] == "silence":
        return None
    return rec.get("voiceOverride") or voice_for(rec["id"])


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
        "demo": None,
        "heldOut": entry.get("heldOut"),
        "voiceOverride": entry.get("voice"),
    }
    if rec["voiceOverride"] is not None and not (is_vendor_voice(rec["voiceOverride"]) and spoken in SARVAM_LANGS):
        raise ValueError(f"{rec['id']}: voice must be sarvam/<model>/<speaker>, for a language Sarvam speaks")
    if entry["taskId"] not in tasks:
        raise ValueError(f"{rec['id']}: unknown task")
    if rec["heldOut"] is not (entry["taskId"] in HELD_OUT_TASKS):
        raise ValueError(f"{rec['id']}: heldOut must be true exactly for the held-out tasks {HELD_OUT_TASKS}")
    if entry["pattern"] == "demo":
        _fill_demo(rec, entry, demos)
    if entry["pattern"] == "silence":
        rec["text"] = ""
    rec["glossDisplay"] = _display_gloss(rec)
    return rec


def _fill_demo(rec: dict, entry: dict, demos: dict) -> None:
    """Text and gloss come from the catalog demo script: the round's own answer, or (16 Oct) the round's followUps
    answer to the item's question.

    demo.round is the 0-based index into the script's rounds, in spec.json and items.json alike; the round a
    supervisor sees (endpoint 24's round) is demo.round + 1.
    """
    script = demos.get(entry["demo"]["script"])
    if script is None:
        raise ValueError(f"{rec['id']}: unknown demo script {entry['demo']['script']}")
    index = entry["demo"]["round"]
    answer = demo_answer(script["rounds"][index], entry["questionId"])
    if answer is None or (script["taskId"], script["workerLang"]) != (entry["taskId"], entry["workerLang"]):
        raise ValueError(f"{rec['id']}: demo script does not match the item")
    if answer["expected"] != entry["gold"]:
        raise ValueError(f"{rec['id']}: gold differs from the catalog demo's expected labels")
    rec["gloss"] = answer["answer"]["en"]
    rec["text"] = answer["answer"][entry["workerLang"]]
    rec["demo"] = {"script": script["id"], "round": index}


def _display_gloss(rec: dict) -> str:
    if rec["spokenLang"] == rec["workerLang"]:
        return rec["gloss"]
    return f"[Spoken in {LANG_NAMES[rec['spokenLang']]}, expected {LANG_NAMES[rec['workerLang']]}] {rec['gloss']}"


class Ledger:
    """The previous items.json: model outputs that are kept while their source is unchanged."""

    def __init__(self, doc: dict | None) -> None:
        doc = doc or {}
        self.items = {item["id"]: item for item in doc.get("items", [])}
        self.questions = doc.get("questions", {})
        self.sources = doc.get("questionSources", {})

    def _final(self, item_id: str, name: str) -> dict | None:
        prev = self.items.get(item_id)
        if prev is None or name in prev.get("pending", []) or not prev.get(name):
            return None
        return prev

    def answer(self, rec: dict) -> str | None:
        prev = self._final(rec["id"], "answer")
        return prev["answer"] if prev and prev.get("answerGloss") == rec["glossDisplay"] else None

    def back(self, rec: dict, text: str) -> str | None:
        prev = self._final(rec["id"], "backTranslation")
        if prev and prev.get("answer") == text and prev.get("answerGloss") == rec["glossDisplay"]:
            return prev["backTranslation"]
        return None

    def question(self, key: str, lang: str, english: str) -> str | None:
        task_id, question_id = key.split(".")
        text = self.questions.get(task_id, {}).get(question_id, {}).get(lang)
        source = self.sources.get(task_id, {}).get(question_id, {}).get(lang)
        return text if text and source == english else None


@dataclass
class Texts:
    answers: dict[str, str] = field(default_factory=dict)            # id -> worker text ("" for silence)
    backs: dict[str, str] = field(default_factory=dict)              # id -> back-translation
    questions: dict[tuple[str, str], str] = field(default_factory=dict)   # (task.qid, lang) -> text
    sources: dict[tuple[str, str], str] = field(default_factory=dict)     # (task.qid, lang) -> English
    wanted_questions: list[tuple[str, str]] = field(default_factory=list)
    missed_languages: list[str] = field(default_factory=list)        # translate batches not made (offline)
    missed_backs: list[str] = field(default_factory=list)            # ids whose back-translation was not made
    calls_made: int = 0


def build_texts(calls: GeminiCalls, records: list[dict], catalog: dict, ledger: Ledger) -> Texts:
    out = Texts()
    to_translate: dict[str, list[dict]] = {}
    for rec in records:
        kept = rec["text"] if not rec["needsTranslation"] else ledger.answer(rec)
        if kept is None:
            to_translate.setdefault(rec["spokenLang"], []).append({"id": rec["id"], "en": rec["gloss"]})
        else:
            out.answers[rec["id"]] = kept
    q_to_translate: dict[str, list[dict]] = {}
    english: dict[str, str] = {}
    for lang, rows in questions_by_language(catalog).items():
        for row in rows:
            english[row["key"]] = row["en"]
            out.wanted_questions.append((row["key"], lang))
            kept = ledger.question(row["key"], lang, row["en"])
            if kept is None:
                q_to_translate.setdefault(lang, []).append(row)
            else:
                out.questions[(row["key"], lang)] = kept
                out.sources[(row["key"], lang)] = row["en"]
    texts, qtexts, out.missed_languages = translate_all(calls, to_translate, q_to_translate)
    out.answers.update(texts)
    out.questions.update(qtexts)
    out.sources.update({(key, lang): english[key] for key, lang in qtexts})
    to_back = []
    for rec in records:
        text = out.answers.get(rec["id"])
        if rec["pattern"] == "silence" or not text:
            continue
        kept = ledger.back(rec, text)
        if kept is None:
            to_back.append({"id": rec["id"], "lang": rec["spokenLang"], "text": text})
        else:
            out.backs[rec["id"]] = kept
    backs, out.missed_backs = back_translate_all(calls, to_back)
    out.backs.update(backs)
    return out


def apply_question_fixes(qtexts: dict[tuple[str, str], str], fixes: dict[str, str],
                         wanted: list[tuple[str, str]] | None = None) -> dict[tuple[str, str], str]:
    """Hand corrections from spec.json, keyed 'task.question.lang'. Each must name a catalog question.

    A fix for a question whose translation is still pending waits until the question is translated.
    """
    out = dict(qtexts)
    known = set(wanted) if wanted is not None else set(qtexts)
    for dotted, text in fixes.items():
        task_id, question_id, lang = dotted.split(".")
        key = (f"{task_id}.{question_id}", lang)
        if key not in known:
            raise ValueError(f"questionFixes names an unknown question: {dotted}")
        if key in out:
            out[key] = text
    return out


def previous_doc() -> dict | None:
    if not ITEMS_PATH.exists():
        return None
    return json.loads(ITEMS_PATH.read_text(encoding="utf-8"))


def keep_recorded(doc: dict, previous: dict | None) -> dict:
    """Consented recordings are added by hand with source 'recorded'. A rebuild must not drop them."""
    kept = [item for item in (previous or {}).get("items", []) if item.get("source") == "recorded"]
    return {**doc, "items": [*doc["items"], *kept]}


def _nested(pairs: dict[tuple[str, str], str]) -> dict:
    block: dict[str, dict[str, dict[str, str]]] = {}
    for (key, lang), text in pairs.items():
        task_id, question_id = key.split(".")
        block.setdefault(task_id, {}).setdefault(question_id, {})[lang] = text
    return {task: {qid: dict(sorted(langs.items())) for qid, langs in sorted(qs.items())}
            for task, qs in sorted(block.items())}


def question_block(qtexts: dict[tuple[str, str], str]) -> dict:
    return _nested(qtexts)


def write_clip_manifest(clips: dict[str, dict]) -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    doc = {"about": CLIPS_ABOUT, "clips": dict(sorted(clips.items()))}
    CLIPS_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _probe(rec: dict) -> dict:
    """The fields clip_is_current reads, for a record whose item is not written yet."""
    silent = rec["pattern"] == "silence"
    return {"id": rec["id"], "audio": f"audio/{rec['id']}.wav", "voice": None if silent else rec_voice(rec),
            "source": "synthetic_tts"}


def clips_to_render(records: list[dict], texts: dict[str, str], clips: dict[str, dict],
                    only: str | None = None) -> list[dict]:
    """Records whose clip is missing or says other words, and whose text exists. Current clips are left alone."""
    return [rec for rec in records
            if (only is None or only in rec["id"]) and rec["id"] in texts
            and not clip_is_current(_probe(rec), clips, text=texts[rec["id"]])]


def render_item(calls: GeminiCalls, rec: dict, text: str, fresh: bool = False, vendor: VendorCalls | None = None) -> dict:
    """Render one clip and return its manifest entry. fresh: a new TTS call even if one is cached."""
    out = AUDIO_DIR / f"{rec['id']}.wav"
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if rec["pattern"] == "silence":
        bed = WORK_DIR / f"{rec['id']}.bed.wav"
        noise_bed(bed, SILENCE_SECONDS, seed_for(rec["id"]))
        write_samples(out, scale_to_dbfs(read_samples(bed), SILENCE_DBFS))
        return {"text": "", "voice": None, "model": None, "render": "local", "cacheKey": None, "backend": None,
                "sha256": file_sha256(out)}
    voice = rec_voice(rec)
    if is_vendor_voice(voice):
        render, key, model, backend = "sarvam", cache_key(text, rec["spokenLang"], voice), parse_voice(voice)[0], "sarvam"
        raw = (vendor or VendorCalls()).tts_wav(f"tts {rec['id']}", text, rec["spokenLang"], voice, fresh=fresh)
    else:
        render, key = calls.tts_source(text, voice, fresh=fresh)
        model, backend = TTS_MODEL, backend_name("tts")
        raw = calls.tts_wav(purpose=f"tts {rec['id']}", text=text, voice=voice, fresh=fresh)
    src = WORK_DIR / f"{rec['id']}.24k.wav"
    src.write_bytes(raw)
    speech_path = WORK_DIR / f"{rec['id']}.16k.wav"
    speech_to_16k(src, speech_path)
    speech = read_samples(speech_path)
    if rec["noise"] == "clean":
        write_samples(out, speech)
    else:
        bed = WORK_DIR / f"{rec['id']}.bed.wav"
        noise_bed(bed, len(speech) / SAMPLE_RATE + 0.5, seed_for(rec["id"]))
        write_samples(out, mix_at_snr(speech, read_samples(bed), SNR_DB[rec["noise"]]))
    return {"text": text, "voice": voice, "model": model, "render": render, "cacheKey": key[:12],
            "backend": backend, "sha256": file_sha256(out)}


def render_pending(calls: GeminiCalls, records: list[dict], texts: dict[str, str], clips: dict[str, dict],
                   only: str | None, fresh: frozenset[str] = frozenset(), vendor: VendorCalls | None = None) -> list[str]:
    """Render what is pending; the manifest is written after each clip, so a stopped build keeps its progress.

    Ids in `fresh` get a new TTS call even when their text is cached (--rerender).
    """
    done = []
    for rec in clips_to_render(records, texts, clips, only):
        try:
            clips[rec["id"]] = render_item(calls, rec, texts[rec["id"]], fresh=rec["id"] in fresh, vendor=vendor)
        except OfflineMiss:
            print(f"not rendered (offline, not cached): {rec['id']}", flush=True)
            continue
        write_clip_manifest(clips)
        done.append(rec["id"])
        print(f"rendered {rec['id']}", flush=True)
    return done


def item_doc(rec: dict, texts: Texts, clips: dict[str, dict]) -> dict:
    silent = rec["pattern"] == "silence"
    answer = texts.answers.get(rec["id"])
    back = "" if silent else texts.backs.get(rec["id"], "")
    doc = {
        "id": rec["id"],
        "taskId": rec["taskId"],
        "questionId": rec["questionId"],
        "workerLang": rec["workerLang"],
        "pattern": rec["pattern"],
        "noise": rec["noise"],
        "source": "synthetic_tts",
        "answer": answer or "",
        "answerGloss": rec["glossDisplay"],
        "backTranslation": back,
        "fidelity": rec["fidelity"],
        "gold": rec["gold"],
        "audio": f"audio/{rec['id']}.wav",
        "voice": None if silent else rec_voice(rec),
        "demo": rec["demo"],
        "heldOut": rec["heldOut"],
    }
    pending = {
        "answer": answer is None,
        "backTranslation": not silent and not back,
        "audio": answer is None or not clip_is_current(doc, clips),
    }
    doc["pending"] = [name for name in PENDING_FIELDS if pending[name]]
    return doc


def build_doc(spec: dict, records: list[dict], texts: Texts, clips: dict[str, dict], previous: dict | None) -> dict:
    qtexts = apply_question_fixes(texts.questions, spec.get("questionFixes", {}), texts.wanted_questions)
    missing = sorted(f"{key}.{lang}" for key, lang in texts.wanted_questions if (key, lang) not in qtexts)
    return keep_recorded({
        "version": spec["version"],
        "questions": question_block(qtexts),
        "questionSources": _nested(texts.sources),
        "pendingQuestions": missing,
        "items": [item_doc(rec, texts, clips) for rec in records],
    }, previous)


def spot_check(calls: GeminiCalls, doc: dict) -> list[dict]:
    wanted = [item for item in doc["items"] if item["id"] in SPOTCHECK_IDS]
    not_ready = [item["id"] for item in wanted if "audio" in item["pending"]]
    if not_ready or len(wanted) != len(SPOTCHECK_IDS):
        raise RuntimeError(f"spot-check needs every spot-check clip rendered first; pending: {not_ready}")
    rows = []
    for item in wanted:
        wav = audio_path(item).read_bytes()
        try:
            got = calls.audio_json(
                purpose=f"spot-check {item['id']}", wav=wav, system=SPOT_SYSTEM, prompt=SPOT_PROMPT,
                schema=SPOT_SCHEMA, validate=_check_spot,
            )
        except ModelBlocked as exc:  # recorded, not cached: a later call may answer
            rows.append({"id": item["id"], "answer": item["answer"], "transcript": "", "language": "none",
                         "similarity": 0.0, "tolerantSimilarity": 0.0, "tolerated": [], "match": False,
                         "blocked": str(exc)})
            continue
        rows.append(spot_row(item, got["transcript"], got["language"]))
    SPOTCHECK_PATH.write_text(json.dumps({"model": FLASH_MODEL, "items": rows}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    return rows


def spot_material(wav: bytes) -> dict:
    return {"kind": "audio_json", "model": FLASH_MODEL, "system": SPOT_SYSTEM, "prompt": SPOT_PROMPT,
            "schema": SPOT_SCHEMA, "audioSha256": hashlib.sha256(wav).hexdigest()}


def similarity(expected: str, heard: str) -> float:
    return difflib.SequenceMatcher(None, _squash(expected), _squash(heard)).ratio()


LOAN = ""  # stands in for one Latin loanword of the answer
LOAN_MAX = 12  # squashed characters a loanword may be heard as
SPOT_GAP_MAX = 15  # squashed characters of unexplained extra or missing speech that fail a match, whatever the ratio
_ZH_DIGITS = "零一二三四五六七八九"


@dataclass
class Tolerant:
    """The spot-check's tolerant comparison (v0.5.1). score: a SequenceMatcher-style ratio with loanword spans
    excused; tolerated: what was excused, for a human to read; gap: the longest unexplained run of extra or missing
    speech (squashed characters)."""

    score: float
    tolerated: list[dict]
    gap: int


def tolerant_similarity(expected: str, heard: str, lang: str) -> Tolerant:
    """Like similarity(), but a correct clip of a code-switched answer is not flagged.

    - A Latin loanword of the answer ("breaker", "load") may be heard in the worker's script (பிரேக்கர, လုပ်) or in
      Latin: the span heard in its place is excused, if something was heard there and it is at most LOAN_MAX
      characters per loanword.
    - Chinese: digits heard are written as Chinese numerals first, so 30 must equal 三十. A wrong number still differs.
    - Anything else heard or missing counts in full, and gap reports its longest run, so a spoken style prefix or a
      dropped phrase fails a match even when the answer is long enough to keep the ratio high.
    """
    if lang == "zh":
        heard = re.sub(r"\d+", lambda m: zh_numeral(int(unicodedata.normalize("NFKC", m.group()))), heard)
    a, b = _squash(expected), _squash(heard)
    loanwords = re.findall(r"[a-z]+", a)
    a = re.sub(r"[a-z]+", LOAN, a)
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    matched = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag == "equal")
    size_a, size_b, tolerated, gap = len(a), len(b), [], 0
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        span, loans = a[i1:i2], a[i1:i2].count(LOAN)
        if loans and loans <= j2 - j1 <= loans * LOAN_MAX + (len(span) - loans) + 2:
            size_a, size_b = size_a - (i2 - i1), size_b - (j2 - j1)
            first = a[:i1].count(LOAN)
            tolerated.append({"loanwords": loanwords[first:first + loans], "heard": b[j1:j2]})
        else:
            gap = max(gap, i2 - i1, j2 - j1)
    score = 2 * matched / (size_a + size_b) if size_a + size_b else 1.0
    return Tolerant(score, tolerated, gap)


def zh_numeral(n: int) -> str:
    """A whole number below 10000 in Chinese numerals, as it is said: 15 十五, 30 三十, 105 一百零五."""
    if n < 10:
        return _ZH_DIGITS[n]
    out = ""
    for value, unit in ((1000, "千"), (100, "百"), (10, "十")):
        digit, n = divmod(n, value)
        if digit:
            out += ("" if unit == "十" and digit == 1 and not out else _ZH_DIGITS[digit]) + unit
        elif out and n and not out.endswith("零"):
            out += "零"
    return out + (_ZH_DIGITS[n] if n else "")


def spot_match(tolerant: Tolerant) -> bool:
    return tolerant.score >= SPOT_SIMILARITY_MATCH and tolerant.gap <= SPOT_GAP_MAX


def spot_row(item: dict, transcript: str, language: str) -> dict:
    """One spot-check row. similarity is the raw score, kept for comparison; match uses the tolerant one and the
    gap (v0.5.1), and tolerated lists every loanword span it excused, so a human can read what was let through."""
    tolerant = tolerant_similarity(item["answer"], transcript, item.get("workerLang", ""))
    return {"id": item["id"], "answer": item["answer"], "transcript": transcript, "language": language,
            "similarity": round(similarity(item["answer"], transcript), 3),
            "tolerantSimilarity": round(tolerant.score, 3), "tolerated": tolerant.tolerated, "gap": tolerant.gap,
            "match": spot_match(tolerant)}


def _squash(text: str) -> str:
    """Casefold and drop punctuation, symbols and spaces. Vowel signs (marks) are kept."""
    return "".join(ch.casefold() for ch in text if unicodedata.category(ch)[0] not in "PZS" and not ch.isspace())


def _check_spot(data: dict) -> None:
    if not isinstance(data.get("transcript"), str) or not isinstance(data.get("language"), str):
        raise ValueError("spot-check response is missing transcript or language")


def _tts_needs_call(rec: dict, texts: Texts, calls: GeminiCalls, vendor: VendorCalls) -> bool:
    """A clip to render that no cache holds: its text is not made yet, or no cached clip says it in its voice."""
    if rec["id"] not in texts.answers:
        return True
    text, voice = texts.answers[rec["id"]], rec_voice(rec)
    if is_vendor_voice(voice):
        return not vendor.is_cached(text, rec["spokenLang"], voice)
    return not calls.is_cached_tts(text, voice)


def call_plan(calls: GeminiCalls, records: list[dict], texts: Texts, clips: dict[str, dict],
              vendor: VendorCalls | None = None) -> dict:
    """The model calls a full build would make now, counted from the same stages (offline texts)."""
    vendor = vendor or VendorCalls(offline=True)
    pending_answers = [rec for rec in records if rec["id"] not in texts.answers]
    back_rows = len(texts.missed_backs) + sum(rec["pattern"] != "silence" for rec in pending_answers)
    renders = clips_to_render(records, texts.answers, clips) + pending_answers
    tts_all = [rec for rec in renders if rec["pattern"] != "silence" and _tts_needs_call(rec, texts, calls, vendor)]
    tts = [rec for rec in tts_all if not is_vendor_voice(rec_voice(rec))]
    vendor_tts = [rec for rec in tts_all if is_vendor_voice(rec_voice(rec))]
    spot = 0
    for rec in records:
        if rec["id"] not in SPOTCHECK_IDS:
            continue
        current = rec["id"] in texts.answers and clip_is_current(_probe(rec), clips, text=texts.answers[rec["id"]])
        spot += not (current and calls.is_cached(spot_material(audio_path(_probe(rec)).read_bytes())))
    return {
        "translate": len(texts.missed_languages), "translateLanguages": texts.missed_languages,
        "backTranslate": math.ceil(back_rows / BACK_BATCH), "backRows": back_rows,
        "tts": len(tts), "ttsIds": [rec["id"] for rec in tts],
        "vendorTts": len(vendor_tts), "vendorIds": [rec["id"] for rec in vendor_tts],
        "vendorChars": sum(len(texts.answers.get(rec["id"], "")) for rec in vendor_tts),
        "localRenders": sum(rec["pattern"] == "silence" for rec in renders),
        "spotCheck": spot,
    }


def print_plan(plan: dict, n_items: int) -> None:
    build = plan["translate"] + plan["backTranslate"] + plan["tts"] + plan["spotCheck"]
    used = logged_call_count()
    print("Calls a full build would make now (cache hits and kept texts make none):")
    print(f"  translate (Flash):       {plan['translate']}  languages {', '.join(plan['translateLanguages']) or '-'}")
    print(f"  back-translate (Flash):  {plan['backTranslate']}  for {plan['backRows']} answers")
    print(f"  TTS (one per clip):      {plan['tts']}  (+{plan['localRenders']} silence clips made locally, no call)")
    print(f"  TTS, Sarvam (vendor):    {plan['vendorTts']}  ({plan['vendorChars']} characters; vendor_calls.log, "
          f"SIB_VENDOR_CALL_BUDGET; not Gemini)")
    print(f"  spot-check (Flash):      {plan['spotCheck']}  (--spot-check)")
    print(f"  build total:             {build}; each may add one logged retry after a 429 or 503")
    print(f"  project cap:             {used} logged so far + {build} = {used + build} of {GEMINI_CALL_BUDGET}"
          f" ({'fits' if used + build <= GEMINI_CALL_BUDGET else 'over: raise SIB_EVAL_CALL_BUDGET'};"
          f" with every retry {used + 2 * build})")
    passes = _judge_passes()
    print(f"  eval (run_eval.py):      {n_items} items x (1 + {passes} judge passes) = {n_items * (1 + passes)}"
          " model calls through the backend; not counted in gemini_calls.log")
    for item in plan["ttsIds"]:
        print(f"    tts {item}")
    for item in plan["vendorIds"]:
        print(f"    sarvam {item}")


def _judge_passes() -> int:
    try:
        from sayitback.settings import Settings
        return Settings.from_env().judge_passes
    except Exception:  # noqa: BLE001 - the plan still prints with the backend's default
        return 2


def rescore_spot_check(doc: dict, path=None) -> list[dict]:
    """Score the stored spot-check transcripts again with the current comparison: no model call, and no file but
    spotcheck.json is written. A blocked row stays as it is (it holds no transcript)."""
    path = path or SPOTCHECK_PATH
    stored = json.loads(path.read_text(encoding="utf-8"))
    items = {item["id"]: item for item in doc["items"]}
    rows = [row if row.get("blocked") else spot_row(items[row["id"]], row["transcript"], row["language"])
            for row in stored["items"]]
    path.write_text(json.dumps({**stored, "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def run_build(args: argparse.Namespace) -> int:
    if args.rescore_spot_check:
        for row in rescore_spot_check(json.loads(ITEMS_PATH.read_text(encoding="utf-8"))):
            print(f"spot {row['id']}: similarity {row['similarity']} tolerant {row.get('tolerantSimilarity')} "
                  f"match={row['match']}", flush=True)
        return 0
    catalog = load_catalog()
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    records = resolve_records(spec, catalog)
    if args.rerender and (args.rerender not in {rec["id"] for rec in records}
                          or args.skip_audio or args.offline or args.plan):
        raise ValueError("--rerender needs an exact item id, and audio on (not --skip-audio, --offline or --plan)")
    previous = previous_doc()
    calls = GeminiCalls(offline=args.offline or args.plan or args.vendor_only)
    vendor = VendorCalls(offline=args.offline or args.plan)
    texts = build_texts(calls, records, catalog, Ledger(previous))
    clips = load_clip_manifest()
    if args.plan:
        print_plan(call_plan(calls, records, texts, clips, vendor), len(records))
        return 0
    fresh: frozenset[str] = frozenset()
    if args.rerender:
        clips.pop(args.rerender, None)  # the clip is no longer current, so it is rendered again
        fresh = frozenset({args.rerender})
        args.only = args.only or args.rerender
    if not args.skip_audio:
        render_pending(calls, records, texts.answers, clips, args.only, fresh, vendor)
    doc = build_doc(spec, records, texts, clips, previous)
    ITEMS_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {name: sum(name in item["pending"] for item in doc["items"]) for name in PENDING_FIELDS}
    print(f"wrote {ITEMS_PATH.name}: {len(doc['items'])} items; pending "
          + ", ".join(f"{name} {n}" for name, n in counts.items())
          + f"; questions pending {len(doc['pendingQuestions'])}", flush=True)
    if args.skip_audio:
        print("audio not rendered (--skip-audio)", flush=True)
    elif args.spot_check:
        for row in spot_check(calls, doc):
            blocked = f" BLOCKED ({row['blocked']})" if row.get("blocked") else ""
            print(f"spot {row['id']}: similarity {row['similarity']} tolerant {row['tolerantSimilarity']} "
                  f"match={row['match']}{blocked}", flush=True)
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
