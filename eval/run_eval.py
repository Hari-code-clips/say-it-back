"""Run the Say It Back check over the eval set and write reports/latest.json and reports/latest.md.

Each item is one run_check call: the catalog steps in scope of its question, the question text in the
worker's language, the item's clip, and supervisor language en. Steps outside the question are not
passed, so no step is marked not_asked.

Usage:
  uv run python run_eval.py                 # all items, one run each
  uv run python run_eval.py --lang ta       # one worker language
  uv run python run_eval.py --limit 5       # the first N items after filtering
  uv run python run_eval.py --repeat 3      # each item 3 times; unsafe if any run rates a gold miss covered
  uv run python run_eval.py --dry-run       # validate and print the plan; makes no calls
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from catalog_io import load_catalog
from check_adapter import RunCheck, backend_run_check, call_check
from config import FLASH_MODEL, REPORTS_DIR, VERDICTS, WORKER_LANGS
from items_io import build_check_payload, load_items, problems
from metrics import Row
from report import build_report, write_reports


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=WORKER_LANGS, help="only items with this worker language")
    parser.add_argument("--limit", type=int, help="only the first N items after filtering")
    parser.add_argument("--repeat", type=int, default=1, help="runs per item (default 1)")
    parser.add_argument("--dry-run", action="store_true", help="validate and print the plan; make no calls")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def select_items(items: list[dict], lang: str | None, limit: int | None) -> list[dict]:
    chosen = [item for item in items if lang is None or item["workerLang"] == lang]
    return chosen if limit is None else chosen[:limit]


def print_plan(items: list[dict], repeat: int) -> None:
    steps = sum(len(item["gold"]) for item in items)
    print(f"dry run: {len(items)} items, {steps} step ratings, {len(items) * repeat} run_check calls (none made)")
    for name, key in (("language", "workerLang"), ("pattern", "pattern"), ("noise", "noise")):
        counts = Counter(item[key] for item in items)
        print(f"  {name}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


def run_items(items: list[dict], doc: dict, catalog: dict, run_check: RunCheck,
              repeat: int) -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = {}
    for item in items:
        runs[item["id"]] = [call_check(run_check, build_check_payload(item, doc, catalog)) for _ in range(repeat)]
        print(f"ran {item['id']} x{repeat}", flush=True)
    return runs


def aggregate(items: list[dict], runs: dict[str, list[dict]]) -> tuple[list[Row], float]:
    """One Row per (item, gold step). pred is the unanimous verdict, or unclear when repeats disagree."""
    rows: list[Row] = []
    unanimous = 0
    for item in items:
        for step_id, gold in item["gold"].items():
            per_run = [run["ratings"].get(step_id) for run in runs[item["id"]]]
            verdicts = [_verdict(rating) for rating in per_run]
            agreed = len(set(verdicts)) == 1
            unanimous += agreed
            flags = {flag for rating in per_run if rating for flag in rating["flags"]}
            if any(rating is None for rating in per_run):
                flags.add("not_rated")
            rows.append(Row(
                item_id=item["id"], task_id=item["taskId"], worker_lang=item["workerLang"],
                pattern=item["pattern"], noise=item["noise"], step_id=step_id, gold=gold,
                pred=verdicts[0] if agreed else "unclear",
                any_covered="covered" in verdicts,
                flags=tuple(sorted(flags)),
                evidence=_evidence(per_run, verdicts),
            ))
    return rows, (unanimous / len(rows) if rows else 1.0)


def _verdict(rating: dict | None) -> str:
    verdict = rating.get("verdict") if rating else None
    return verdict if verdict in VERDICTS else "unclear"


def _evidence(per_run: list[dict | None], verdicts: list[str]) -> str:
    for rating, verdict in zip(per_run, verdicts):
        if rating and verdict == "covered" and rating["evidence"]:
            return rating["evidence"]
    return next((rating["evidence"] for rating in per_run if rating and rating["evidence"]), "")


def run_meta(runs: dict[str, list[dict]], repeat: int, stability: float) -> dict:
    results = [run for group in runs.values() for run in group]
    model_ids = next((run["modelIds"] for run in results if run["modelIds"]), {})
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "promptVersion": _prompt_version(),
        "models": {"flash": next((m for m in model_ids.values() if m), FLASH_MODEL)},
        "judgePasses": 2 if any(run["passB"] for run in results) else 1,
        "repeat": repeat,
        "stability": stability,
    }


def _prompt_version() -> str:
    try:
        return str(importlib.import_module("sayitback.prompts").PROMPT_VERSION)
    except (ImportError, AttributeError):
        return "unknown"


def main(argv: list[str] | None = None, *, run_check: RunCheck | None = None,
         out_dir: Path | None = None) -> int:
    args = parse_args(argv)
    doc, catalog = load_items(), load_catalog()
    found = problems(doc, catalog)
    if found:
        for line in found:
            print(f"PROBLEM: {line}", file=sys.stderr)
        return 1
    items = select_items(doc["items"], args.lang, args.limit)
    if not items:
        print("no items selected", file=sys.stderr)
        return 1
    if args.dry_run:
        print_plan(items, args.repeat)
        return 0
    check: Any = run_check or backend_run_check()
    runs = run_items(items, doc, catalog, check, args.repeat)
    rows, stability = aggregate(items, runs)
    meta = run_meta(runs, args.repeat, stability)
    report = build_report(rows, items, meta)
    json_path, md_path = write_reports(report, rows, meta, out_dir or REPORTS_DIR)
    status = "PASS" if report["passBar"]["passed"] else "FAIL"
    print(f"{status}: exact accuracy {report['metrics']['exactAccuracy']}, "
          f"unsafe errors {report['metrics']['unsafeErrors']} -> {json_path.name}, {md_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
