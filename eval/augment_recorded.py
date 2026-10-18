"""Site-noise copies of the consented real recordings (16 Oct): real voices at the noise levels of a site.

For each recording record_clips.py saved (source "recorded", consent true, noise clean), this writes one copy per
site-noise profile and SNR (site_noise.py: drone, hammer, beeper and babble, at 10, 5 and 0 dB measured over the
speech) as a new item `<recording id>.<profile>.<snr>`, its clip in testset/audio/recorded/ (16 kHz mono 16-bit).
A copy keeps the recording's task, question, language, pattern, gold, gloss, texts, fidelity, pending, speaker code,
consent and recordedFrom (the synthetic item it re-voices), and adds `augmentedFrom` (the recording) and `noise` (the
profile and SNR). Synthetic items are never read or changed.

The noise is seeded by the recording id and the profile, so a rerun writes the same bytes and the three SNRs of a
profile differ only in level. A rerun adds what is missing, brings a copy back in line with its recording (a
transcript typed in later), and mixes again a copy whose clip is gone. items.json is written the way record_clips.py
writes it (record_clips.write_doc), after each recording's copies. `record_clips.py --forget V01` deletes the copies
with the recordings. What the numbers mean: real voices with synthetic site noise, not a field trial (README.md).

Usage, from say-it-back/eval (never while build_testset.py or record_clips.py runs: all three write items.json):
  uv run python augment_recorded.py --dry-run          # what would be written; nothing is
  uv run python augment_recorded.py                    # every recording, every profile at every SNR
  uv run python augment_recorded.py --speaker V01 --profile site-hammer --snr snr0
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from audio_tools import read_samples, write_samples
from config import TESTSET_DIR
from items_io import SPEAKER_CODE
from record_clips import RECORDED_DIR, check_clip, write_doc
from site_noise import PROFILES, SNR_LEVELS, make, mix_over_speech, seed_for


@dataclass(frozen=True)
class Job:
    item: dict  # the copy as it should be
    recording: dict
    change: str  # "new"; "update": its fields follow the recording again; "clip": its clip is missing


def recordings(doc: dict, speakers: list[str] | None = None) -> list[dict]:
    """The consented recordings themselves (never a copy, never a synthetic item), optionally of some speakers."""
    return [item for item in doc["items"]
            if item["source"] == "recorded" and item.get("consent") is True and "augmentedFrom" not in item
            and item["noise"] == "clean" and not item.get("ambient")  # real noise already: no synthetic noise on top
            and (not speakers or item["voice"] in speakers)]


def copy_item(recording: dict, profile: str, snr: str) -> dict:
    noise = f"{profile}.{snr}"
    new_id = f"{recording['id']}.{noise}"
    return {**recording, "id": new_id, "noise": noise, "audio": f"{RECORDED_DIR}/{new_id}.wav",
            "gold": dict(recording["gold"]), "pending": list(recording["pending"]), "augmentedFrom": recording["id"]}


def plan(doc: dict, testset_dir: Path, speakers: list[str] | None = None, profiles: list[str] | None = None,
         snrs: list[str] | None = None) -> tuple[list[Job], list[str]]:
    """(the copies to write, the recordings skipped and why). A copy already in line, with its clip, is left alone."""
    have = {item["id"]: item for item in doc["items"]}
    jobs, skipped = [], []
    for recording in recordings(doc, speakers):
        clip = testset_dir / recording["audio"]
        problems = check_clip(clip)[0] if clip.is_file() else ["its clip is missing"]
        if problems:
            skipped.append(f"{recording['id']}: {'; '.join(problems)}")
            continue
        for profile in profiles or PROFILES:
            for snr in snrs or SNR_LEVELS:
                wanted = copy_item(recording, profile, snr)
                old = have.get(wanted["id"])
                if old is None:
                    jobs.append(Job(wanted, recording, "new"))
                elif old != wanted:
                    jobs.append(Job(wanted, recording, "update"))
                elif not (testset_dir / wanted["audio"]).is_file():
                    jobs.append(Job(wanted, recording, "clip"))
    return jobs, skipped


def render(recording: dict, jobs: list[Job], testset_dir: Path) -> None:
    """Mix the clips of one recording's copies: one noise per profile, seeded by the recording and profile."""
    speech = read_samples(testset_dir / recording["audio"])
    noises: dict[str, list[float]] = {}
    for job in jobs:
        profile, snr = job.item["noise"].split(".")
        if profile not in noises:
            noises[profile] = make(profile, len(speech), seed_for(f"{recording['id']}.{profile}"))
        write_samples(testset_dir / job.item["audio"], mix_over_speech(speech, noises[profile], SNR_LEVELS[snr]))


def apply(doc: dict, jobs: list[Job], testset_dir: Path) -> None:
    """Each recording's clips first, then its items (new ones appended, changed ones in place), then items.json."""
    groups: dict[str, list[Job]] = {}
    for job in jobs:
        groups.setdefault(job.recording["id"], []).append(job)
    for group in groups.values():
        render(group[0].recording, [job for job in group if job.change != "update"
                                    or not (testset_dir / job.item["audio"]).is_file()], testset_dir)
        index = {item["id"]: n for n, item in enumerate(doc["items"])}
        for job in group:
            if job.item["id"] in index:
                doc["items"][index[job.item["id"]]] = job.item
            else:
                doc["items"].append(job.item)
        write_doc(doc, testset_dir)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--speaker", action="append", help="only this speaker's recordings, V01 to V99 (repeatable)")
    parser.add_argument("--profile", action="append", choices=list(PROFILES), help="only this profile (repeatable)")
    parser.add_argument("--snr", action="append", choices=list(SNR_LEVELS), help="only this SNR (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="list what would be written; write nothing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, testset_dir: Path = TESTSET_DIR) -> int:
    args = parse_args(argv)
    if any(not SPEAKER_CODE.match(speaker) for speaker in args.speaker or []):
        print("A speaker is a code from V01 to V99, never a name.")
        return 2
    doc = json.loads((testset_dir / "items.json").read_text(encoding="utf-8"))
    if not recordings(doc, args.speaker):
        print("No consented recording to add site noise to: record_clips.py records them.")
        return 1
    jobs, skipped = plan(doc, testset_dir, args.speaker, args.profile, args.snr)
    for line in skipped:
        print(f"skipped {line}")
    changes = Counter(job.change for job in jobs)
    summary = ", ".join(f"{changes[name]} {name}" for name in ("new", "update", "clip") if changes[name]) or "none"
    if args.dry_run:
        print(f"dry run: {len(jobs)} site-noise copies to write ({summary}); nothing written")
        for job in jobs:
            print(f"  {job.change:6} {job.item['id']}")
        return 1 if skipped else 0
    apply(doc, jobs, testset_dir)
    print(f"wrote {len(jobs)} site-noise copies ({summary}). Next: uv run pytest -q")
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
