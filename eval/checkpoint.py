"""The run's checkpoint (v0.5.1): run_eval.py appends every finished item to <out>/progress.jsonl at once, so a
crash or a stopped run keeps what was paid for, and --resume runs only what is left.

Each line is one item:
- {"itemId", "settings", "runs": [normalized check results, one per repeat]}, or
- {"itemId", "settings", "error": {"class", "message"}} when its check failed twice.

settings is the run's fingerprint (run_eval.run_settings: prompt version, models, judge passes, thinking levels,
items.json SHA-256, repeats). A resume refuses a file written under other settings, so two configurations are never
mixed in one report. Error lines are not reused: a resume runs those items again. A last line cut off by a crash is
skipped; any other line that is not JSON stops the resume.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROGRESS_NAME = "progress.jsonl"


class ResumeRefused(Exception):
    """The progress file cannot be resumed under the current settings."""


def load(path: Path, settings: dict) -> dict[str, list[dict]]:
    """item id -> its stored runs, for every finished item; raises ResumeRefused on a settings mismatch."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done: dict[str, list[dict]] = {}
    for n, line in enumerate(lines, start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            if n == len(lines):
                continue  # cut off by the crash: that item runs again
            raise ResumeRefused(f"{path.name} line {n} is not JSON") from None
        if entry.get("settings") != settings:
            changed = differences(entry.get("settings") or {}, settings)
            raise ResumeRefused(f"{path.name} line {n} was written under other settings ({', '.join(changed)}); "
                                "run with --restart to discard it, or restore those settings")
        if "runs" in entry:
            done[entry["itemId"]] = entry["runs"]
    return done


def append(path: Path, item_id: str, settings: dict, *, runs: list[dict] | None = None,
           error: dict | None = None) -> None:
    """One line, flushed and synced before the next item starts."""
    entry = {"itemId": item_id, "settings": settings, **({"runs": runs} if error is None else {"error": error})}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(entry, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())


def differences(old: dict, new: dict) -> list[str]:
    """The fingerprint keys whose values differ, nested ones dotted (thinking.judge_a)."""
    out = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            out += [f"{key}.{sub}" for sub in differences(a, b)]
        elif a != b:
            out.append(key)
    return out
