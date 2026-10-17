"""Record consented human voices for the eval set (v0.5.1): a real person saying an existing item's answer.

Each recording becomes a new item beside the synthetic one, with the same task, question, language, pattern and
gold, and `source: "recorded"`. The judges then hear a real voice, a real room and a real microphone instead of
Gemini TTS, which is the eval's biggest known bias.

For each chosen item the tool shows the question, the English gloss and the worker-language text, and asks the
volunteer to say it in their own words with the same meaning: no step added or left out, and every "not" or
"never" kept, because the gold labels depend on it. It records from the Mac microphone (ffmpeg avfoundation,
16 kHz mono 16-bit WAV; Enter stops; at most 30 s), lets the volunteer play it back or redo it, and saves it as
`<item id>.rec.<speaker>` with the clip in testset/audio/recorded/. Every recorded item is `fidelity: "review"`.

Consent and privacy:
- The speaker is a code (V01, V02, ...), never a name. Keep the list of who is who outside the repo.
- Nothing is recorded until the volunteer types "yes" to CONSENT_TEXT, and every saved item says `consent: true`.
- `--forget V01` deletes that speaker's clips and items when they ask, their site-noise copies included
  (augment_recorded.py). Copies already committed or deployed must be removed there as well.

Not recordable: demo items (keyed for the Sample page, endpoint 24), silence and wrong_language items, and items
whose worker-language text or question is still pending translation.

Usage, from say-it-back/eval (never while build_testset.py runs: both write testset/items.json):
  uv run python record_clips.py --list-devices
  uv run python record_clips.py --speaker V01 --lang ta --dry-run     # what would be recorded; no mic, no write
  uv run python record_clips.py --speaker V01 --lang ta --limit 5
  uv run python record_clips.py --speaker V01 --item trench-entry.q1.or.complete.clean --device :1
  uv run python record_clips.py --forget V01
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from audio_tools import mean_square, read_samples
from catalog_io import load_catalog, question_by_id, task_map
from config import SAMPLE_RATE, TESTSET_DIR
from items_io import RECORDED_EXCLUDED_PATTERNS, SPEAKER_CODE, question_text
from testset_text import LANG_NAMES

RECORDED_DIR = "audio/recorded"
MAX_SECONDS = 30.0
MIN_SECONDS = 0.5
MIN_RMS_DBFS = -45.0  # the set's silence clips sit at -50 dBFS; a take this quiet holds no speech
CONSENT_TEXT = (
    "Before we record, please read this.\n"
    "- Your recording is used only to test Say It Back, a safety-briefing prototype.\n"
    "- It is stored in the project's code repository, which is public, and it can be played on the project's\n"
    "  public evaluation page.\n"
    "- No name is stored. You are recorded as {speaker}.\n"
    "- Ask at any time and your recordings are deleted from the project.\n"
    'Type "yes" to agree, or anything else to stop.'
)


class Quit(Exception):
    """The volunteer asked to stop: everything kept so far is already saved."""


class Recorder(Protocol):
    def record(self, dst: Path, max_seconds: float, wait_for_stop: Callable[[], object]) -> None: ...

    def play(self, path: Path) -> None: ...


@dataclass
class FfmpegRecorder:
    """The Mac microphone through ffmpeg's avfoundation input. device is ":<audio index>" (--list-devices)."""

    device: str = ":0"

    def input_args(self) -> list[str]:
        return ["-f", "avfoundation", "-i", self.device]

    def command(self, dst: Path, max_seconds: float) -> list[str]:
        return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *self.input_args(),
                "-t", f"{max_seconds:g}", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(dst)]

    def record(self, dst: Path, max_seconds: float, wait_for_stop: Callable[[], object]) -> None:
        proc = subprocess.Popen(self.command(dst, max_seconds), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        wait_for_stop()
        if proc.poll() is None and proc.stdin is not None:
            proc.stdin.write(b"q")  # ffmpeg's own key to stop and finish the file
            proc.stdin.flush()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait()
        if not dst.is_file():
            err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"ffmpeg wrote no recording: {err.strip()[-300:]} (check the microphone "
                               "permission in System Settings, and --device)")

    def play(self, path: Path) -> None:
        subprocess.run(["afplay", str(path)], check=False)


def list_devices() -> str:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                          capture_output=True, text=True, check=False)
    return proc.stderr


@dataclass
class Io:
    ask: Callable[[str], str] = input
    say: Callable[[str], None] = print


@dataclass
class Session:
    speaker: str
    doc: dict
    catalog: dict
    testset_dir: Path
    recorder: Recorder
    io: Io = field(default_factory=Io)


def recorded_id(source_id: str, speaker: str) -> str:
    return f"{source_id}.rec.{speaker}"


def recordable(doc: dict, speaker: str, item_ids: list[str] | None = None, tasks: list[str] | None = None,
               langs: list[str] | None = None) -> list[dict]:
    """Synthetic items a volunteer can say: text and question translated, not a demo, silence or wrong-language
    item, and not recorded by this speaker yet. Filters of different kinds must all match."""
    have = {item["id"] for item in doc["items"]}
    return [item for item in doc["items"]
            if item["source"] == "synthetic_tts" and item["pattern"] not in RECORDED_EXCLUDED_PATTERNS
            and item["answer"] and "answer" not in item["pending"] and question_text(item, doc) is not None
            and recorded_id(item["id"], speaker) not in have
            and (not item_ids or item["id"] in item_ids) and (not tasks or item["taskId"] in tasks)
            and (not langs or item["workerLang"] in langs)]


def check_clip(path: Path) -> tuple[list[str], str]:
    """(problems, a short description). A take with any problem is not kept."""
    with wave.open(str(path), "rb") as wav:
        fmt = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
    if fmt != (SAMPLE_RATE, 1, 2):
        return [f"the file is {fmt[0]} Hz, {fmt[1]} channel(s), {8 * fmt[2]}-bit; it must be 16 kHz mono 16-bit"], ""
    samples = read_samples(path)
    seconds = len(samples) / SAMPLE_RATE
    power = mean_square(samples)
    level = 10 * math.log10(power / 32768 ** 2) if power else -120.0
    problems = []
    if seconds < MIN_SECONDS:
        problems.append(f"it is only {seconds:.1f} s long")
    if level < MIN_RMS_DBFS:
        problems.append(f"it is nearly silent ({level:.0f} dBFS): check the microphone and speak closer")
    clipped = sum(abs(x) >= 32767 for x in samples)
    note = " (some peaks clipped: speak a little further from the microphone)" if clipped > SAMPLE_RATE // 100 else ""
    return problems, f"{seconds:.1f} s, {level:.0f} dBFS{note}"


def consent(session: Session) -> bool:
    session.io.say(CONSENT_TEXT.format(speaker=session.speaker))
    return session.io.ask("> ").strip().lower() == "yes"


def record_item(session: Session, item: dict, n: int, total: int, work: Path) -> dict | None:
    """Record one take the volunteer keeps, and return its new item; None when skipped. Raises Quit."""
    io, lang = session.io, LANG_NAMES[item["workerLang"]]
    task = task_map(session.catalog)[item["taskId"]]
    new_id = recorded_id(item["id"], session.speaker)
    io.say(f"\n[{n} of {total}] {item['id']}\n"
           f"Question:  {question_by_id(task, item['questionId'])['text']}\n"
           f"           {question_text(item, session.doc)}\n"
           f"English:   {item['answerGloss']}\n"
           f"{lang}:  {item['answer']}\n"
           "Say this answer in your own words. Keep the same meaning: add no step, leave none out, and keep "
           "every 'not' and 'never'.")
    take = work / f"{new_id}.wav"
    while True:
        choice = io.ask("Enter to record, s to skip, q to quit: ").strip().lower()
        if choice == "q":
            raise Quit
        if choice == "s":
            return None
        session.recorder.record(take, MAX_SECONDS,
                                lambda: io.ask(f"Recording. Press Enter to stop (at most {MAX_SECONDS:g} s). "))
        problems, info = check_clip(take)
        if problems:
            io.say("Not usable: " + "; ".join(problems) + ". Record it again.")
            continue
        io.say(f"Recorded {info}.")
        while (choice := io.ask("p play, r redo, k keep, s skip: ").strip().lower()) == "p":
            session.recorder.play(take)
        if choice == "s":
            return None
        if choice != "k":
            continue
        if io.ask("Same meaning as the English, with no step added or left out and every 'not' kept? (y/n) "
                  ).strip().lower() != "y":
            io.say("Not kept: the gold labels would not fit it. Record it again, or skip.")
            continue
        return _keep(session, item, new_id, take, lang)


def _keep(session: Session, item: dict, new_id: str, take: Path, lang: str) -> dict:
    io = session.io
    if io.ask("Was it the text shown, word for word? (y/n) ").strip().lower() == "y":
        answer, back = item["answer"], item["backTranslation"]
    else:
        answer = io.ask(f"Type what was said, in {lang} (or press Enter to leave the transcript for later): ").strip()
        back = ""
    pending = [name for name, missing in (("answer", not answer), ("backTranslation", not back)) if missing]
    dst = session.testset_dir / RECORDED_DIR / f"{new_id}.wav"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(take), dst)
    return {
        "id": new_id,
        "taskId": item["taskId"],
        "questionId": item["questionId"],
        "workerLang": item["workerLang"],
        "pattern": item["pattern"],
        "noise": "clean",  # no synthetic noise mixed in; the room's own noise is in the recording
        "source": "recorded",
        "answer": answer,
        "answerGloss": item["answerGloss"],
        "backTranslation": back,
        "fidelity": "review",
        "gold": dict(item["gold"]),
        "audio": f"{RECORDED_DIR}/{new_id}.wav",
        "voice": session.speaker,
        "demo": None,
        "heldOut": item["heldOut"],
        "consent": True,
        "recordedFrom": item["id"],
        "pending": pending,
    }


def write_doc(doc: dict, testset_dir: Path) -> None:
    """items.json, written whole through a temporary file so a stopped session never leaves half a file."""
    path = testset_dir / "items.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_session(session: Session, chosen: list[dict]) -> list[str]:
    """Record each chosen item; items.json is written after every kept take. Returns the new item ids."""
    if not consent(session):
        session.io.say("No consent was given, so nothing was recorded.")
        return []
    saved: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sib-takes-") as work:
        for n, item in enumerate(chosen, start=1):
            try:
                new = record_item(session, item, n, len(chosen), Path(work))
            except Quit:
                break
            if new is not None:
                session.doc["items"].append(new)
                write_doc(session.doc, session.testset_dir)
                saved.append(new["id"])
                session.io.say(f"Saved {new['id']}.")
    return saved


def forget(doc: dict, speaker: str, testset_dir: Path) -> list[str]:
    """Delete a speaker's recorded items, their site-noise copies (augment_recorded.py: augmentedFrom), and every
    clip of theirs under audio/recorded/, a stray one with no item too (a stopped run). Returns the removed ids."""
    ids = {item["id"] for item in doc["items"] if item["source"] == "recorded" and item["voice"] == speaker}
    ids |= {item["id"] for item in doc["items"] if item.get("augmentedFrom") in ids}
    gone = [item for item in doc["items"] if item["id"] in ids]
    for item in gone:
        (testset_dir / item["audio"]).unlink(missing_ok=True)
    clips = testset_dir / RECORDED_DIR
    for stray in [*clips.glob(f"*.rec.{speaker}.wav"), *clips.glob(f"*.rec.{speaker}.*.wav")]:
        stray.unlink(missing_ok=True)
    doc["items"] = [item for item in doc["items"] if item["id"] not in ids]
    if gone:
        write_doc(doc, testset_dir)
    return [item["id"] for item in gone]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--speaker", help="speaker code, V01 to V99 (never a name)")
    parser.add_argument("--item", action="append", help="an exact item id (repeatable)")
    parser.add_argument("--task", action="append", help="a task id (repeatable)")
    parser.add_argument("--lang", action="append", help="a worker language (repeatable)")
    parser.add_argument("--limit", type=int, help="at most this many items")
    parser.add_argument("--device", default=":0", help='avfoundation audio input, ":<index>" (default ":0")')
    parser.add_argument("--dry-run", action="store_true", help="list what would be recorded; no mic, no write")
    parser.add_argument("--list-devices", action="store_true", help="list the Mac's audio inputs and stop")
    parser.add_argument("--forget", metavar="SPEAKER", help="delete this speaker's recordings and items")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, recorder: Recorder | None = None, io: Io | None = None,
         testset_dir: Path = TESTSET_DIR, catalog: dict | None = None) -> int:
    args = parse_args(argv)
    io = io or Io()
    if args.list_devices:
        io.say(list_devices())
        return 0
    doc = json.loads((testset_dir / "items.json").read_text(encoding="utf-8"))
    speaker = args.forget or args.speaker
    if not speaker or not SPEAKER_CODE.match(speaker):
        io.say("Give a speaker code from V01 to V99 (--speaker or --forget), never a name.")
        return 2
    if args.forget:
        removed = forget(doc, speaker, testset_dir)
        io.say(f"Deleted {len(removed)} items of {speaker} (recordings and their site-noise copies) and every clip "
               "of theirs." + "".join(f"\n  {i}" for i in removed))
        return 0
    chosen = recordable(doc, speaker, args.item, args.task, args.lang)[:args.limit]
    if not chosen:
        io.say("No recordable item matches (demo, silence, wrong-language and untranslated items are left out).")
        return 1
    if args.dry_run:
        io.say(f"dry run: {len(chosen)} items for {speaker}; nothing recorded or written")
        for item in chosen:
            io.say(f"  {recorded_id(item['id'], speaker)}  <-  {item['answerGloss']}")
        return 0
    session = Session(speaker, doc, catalog or load_catalog(), testset_dir, recorder or FfmpegRecorder(args.device), io)
    saved = run_session(session, chosen)
    io.say(f"{len(saved)} recordings saved for {speaker}. Next: uv run pytest tests/test_items.py")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
