"""Run the Say It Back check over the eval set and write reports/latest.json and reports/latest.md.

Each item is one run_check call: the catalog steps in scope of its question (exactly the question's
stepIds), that one question's text in the worker's language, the item's clip, and supervisor language en.
Steps outside the question are never passed, so no step is marked not_asked and a step a task gains
(lifting-zone s4, asked only by q3) cannot enter another item's ratings. Only the item's gold steps are
scored; any other rating the check returns is ignored.

An item runs only when its clip is current (testset/audio/clips.json says the file holds the item's
answer) and its question has a worker-language text. A real run stops if a selected item is not ready,
unless --ready-only is given; that report is marked incomplete ("complete": false) and its headline says
not to quote it.

v0.5: the report also splits held-out from in-set items (byHeldOut), leaves out the abstain patterns
(modelOnly), records the SHA-256 of items.json (testsetSha256), and scores a keyword baseline on the
same translations (baseline_keyword.py).

v0.5.1, a run that survives failures:
- every finished item is appended at once to <out>/progress.jsonl (checkpoint.py), with the run's settings
  (models, prompt version, judge passes, thinking levels, items.json SHA-256, repeats); --resume reuses the lines
  written under the same settings and runs the rest, and refuses a file written under other settings;
- a check that raises is tried once more after RETRY_WAIT_S; if it fails again the item is recorded as an error
  (its class and message, no content), the run goes on, and the report lists it in `errors` and is
  "complete": false. The exit code is then 1, and progress.jsonl is kept so --resume can retry those items;
- the report records those settings in `settings`, so runs with other thinking levels can be told apart.

Usage:
  uv run python run_eval.py                 # all items, one run each
  uv run python run_eval.py --lang ta       # one worker language
  uv run python run_eval.py --limit 5       # the first N items after filtering
  uv run python run_eval.py --repeat 3      # each item 3 times; unsafe if any run rates a gold miss covered
  uv run python run_eval.py --ready-only    # skip items whose clip is pending (an incomplete report)
  uv run python run_eval.py --limit 2 --out reports/smoke   # a smoke run that leaves reports/latest.* alone
  uv run python run_eval.py --dry-run       # validate and print the plan; makes no calls
  uv run python run_eval.py --resume        # after a crash or a stop: run only the items not in progress.jsonl
  uv run python run_eval.py --restart       # discard progress.jsonl and run everything again
  uv run python run_eval.py --source recorded   # only the real voices and their site-noise copies (16 Oct), into
                                                # reports/recorded/ unless --out says otherwise
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import checkpoint
from baseline_keyword import all_baselines
from catalog_io import load_catalog
from check_adapter import RunCheck, backend_run_check, call_check
from config import FLASH_MODEL, REPORTS_DIR, SOURCES, VERDICTS, WORKER_LANGS
from items_io import build_check_payload, item_is_ready, items_sha256, load_clip_manifest, load_items, problems
from metrics import Row, RunRating
from report import build_report, write_reports


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=WORKER_LANGS, help="only items with this worker language")
    parser.add_argument("--source", choices=SOURCES,
                        help="only items of this source (recorded: the real voices and their site-noise copies); "
                             "the report goes to reports/<source>/ unless --out says otherwise")
    parser.add_argument("--limit", type=int, help="only the first N items after filtering")
    parser.add_argument("--repeat", type=int, default=1, help="runs per item (default 1)")
    parser.add_argument("--ready-only", action="store_true",
                        help="skip items whose clip is pending; the report is marked incomplete")
    parser.add_argument("--dry-run", action="store_true", help="validate and print the plan; make no calls")
    parser.add_argument("--out", type=Path,
                        help="write latest.json and latest.md here instead of reports/ (a smoke run)")
    parser.add_argument("--resume", action="store_true",
                        help="reuse the finished items in <out>/progress.jsonl (same settings only)")
    parser.add_argument("--restart", action="store_true", help="discard <out>/progress.jsonl and start again")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.resume and args.restart:
        parser.error("--resume and --restart cannot be combined")
    return args


def select_items(items: list[dict], lang: str | None, limit: int | None,
                 ready: set[str] | None = None, source: str | None = None) -> list[dict]:
    chosen = [item for item in items
              if (lang is None or item["workerLang"] == lang) and (ready is None or item["id"] in ready)
              and (source is None or item["source"] == source)]
    return chosen if limit is None else chosen[:limit]


def judge_passes() -> int:
    """The backend's SIB_JUDGE_PASSES (default 2), read the way the service reads it."""
    try:
        return importlib.import_module("sayitback.settings").Settings.from_env().judge_passes
    except (ImportError, AttributeError):
        return 2


def print_plan(items: list[dict], repeat: int, not_ready: list[str]) -> None:
    steps = sum(len(item["gold"]) for item in items)
    passes = judge_passes()
    checks = len(items) * repeat
    print(f"dry run: {len(items)} items, {steps} step ratings, {checks} run_check calls = "
          f"{checks * (1 + passes)} model calls (transcriber + {passes} judge passes each; none made)")
    for name, key in (("language", "workerLang"), ("pattern", "pattern"), ("noise", "noise"), ("source", "source")):
        counted = Counter(item[key] for item in items)
        print(f"  {name}: " + ", ".join(f"{k} {v}" for k, v in sorted(counted.items())))
    held = [item for item in items if item.get("heldOut")]
    held_tasks = Counter(item["taskId"] for item in held)
    print(f"  held out: {len(held)} items, {sum(len(item['gold']) for item in held)} step ratings ("
          + (", ".join(f"{k} {v}" for k, v in sorted(held_tasks.items())) or "none") + ")")
    if not_ready:
        print(f"  not ready (clip pending, or question not translated): {len(not_ready)}; a real run stops on them "
              "(render first, eval/RUN_PAID.md, or pass --ready-only)")


CHECK_AGENTS = ("blind_transcriber", "judge_a", "judge_b")  # the agents run_check runs (SIB_THINKING_<AGENT>)
RETRY_WAIT_S = 20.0  # before the one retry of a check that raised
ERROR_MESSAGE_MAX = 200


def run_settings(testset_sha256: str, repeat: int) -> dict:
    """The run's fingerprint, read the way the service reads its settings: what makes two runs comparable."""
    settings = importlib.import_module("sayitback.settings").Settings.from_env()
    passes = settings.judge_passes
    return {
        "promptVersion": _prompt_version(),
        "models": {"flash": settings.flash_model, "judgeB": settings.judge_b_model_id if passes == 2 else None},
        "judgePasses": passes,
        "thinking": {agent: settings.thinking[agent] for agent in CHECK_AGENTS},
        "testsetSha256": testset_sha256,
        "repeat": repeat,
    }


def run_items(items: list[dict], doc: dict, catalog: dict, run_check: RunCheck, repeat: int,
              progress: Path | None = None, settings: dict | None = None,
              done: dict[str, list[dict]] | None = None) -> tuple[dict[str, list[dict]], list[dict]]:
    """(item id -> its runs, errors). Items in `done` are not run again. Each finished item, or its error, is
    appended to `progress` before the next one starts."""
    runs: dict[str, list[dict]] = {}
    errors: list[dict] = []
    for item in items:
        if done and item["id"] in done:
            runs[item["id"]] = done[item["id"]]
            print(f"kept {item['id']} (progress.jsonl)", flush=True)
            continue
        try:
            results = [_check_with_retry(run_check, build_check_payload(item, doc, catalog)) for _ in range(repeat)]
        except Exception as exc:  # noqa: BLE001 - recorded and the run goes on; a report can never be lost
            error = {"class": type(exc).__name__, "message": str(exc)[:ERROR_MESSAGE_MAX]}
            errors.append({"id": item["id"], **error})
            if progress is not None:
                checkpoint.append(progress, item["id"], settings or {}, error=error)
            print(f"ERROR {item['id']}: {error['class']}: {error['message']}", flush=True)
            continue
        runs[item["id"]] = results
        if progress is not None:
            checkpoint.append(progress, item["id"], settings or {}, runs=results)
        print(f"ran {item['id']} x{repeat}", flush=True)
    return runs, errors


def _check_with_retry(run_check: RunCheck, payload: dict) -> dict:
    try:
        return call_check(run_check, payload)
    except Exception as exc:  # noqa: BLE001 - one more try for any failure, then the caller records it
        print(f"  check failed ({type(exc).__name__}); trying once more in {RETRY_WAIT_S:g} s", flush=True)
        time.sleep(RETRY_WAIT_S)
        return call_check(run_check, payload)


def aggregate(items: list[dict], runs: dict[str, list[dict]]) -> tuple[list[Row], float]:
    """One Row per (item, gold step). pred is the unanimous verdict, or unclear when repeats disagree.

    Only the gold steps (= the question's stepIds) are read from each run; other ratings are ignored. The row keeps
    the first run's English translation of the answer (the keyword baseline reads it), its worker-language text, and
    the step's final rating in that run (v0.5.1: the report's items[].original and items[].ratings).
    """
    rows: list[Row] = []
    unanimous = 0
    for item in items:
        first = runs[item["id"]][0]
        translation = first.get("transcripts", {}).get(item["questionId"], "")
        original = first.get("originals", {}).get(item["questionId"], "")
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
                held_out=bool(item.get("heldOut", False)),
                translation=translation,
                source=item.get("source", "synthetic_tts"),
                original=original,
                rating=_run_rating(step_id, per_run[0]),
            ))
    return rows, (unanimous / len(rows) if rows else 1.0)


def _verdict(rating: dict | None) -> str:
    verdict = rating.get("verdict") if rating else None
    return verdict if verdict in VERDICTS else "unclear"


def _run_rating(step_id: str, rating: dict | None) -> RunRating | None:
    if rating is None:
        return None
    return RunRating(step_id=step_id, verdict=_verdict(rating), quote=rating.get("quote"),
                     quote_translation=rating.get("quoteTranslation"), reason=rating.get("reason"),
                     flags=tuple(rating.get("flags", ())))


def _evidence(per_run: list[dict | None], verdicts: list[str]) -> str:
    for rating, verdict in zip(per_run, verdicts):
        if rating and verdict == "covered" and rating["evidence"]:
            return rating["evidence"]
    return next((rating["evidence"] for rating in per_run if rating and rating["evidence"]), "")


def run_models(runs: dict[str, list[dict]]) -> dict[str, str]:
    """flash: the transcriber's (and judge A's) model; judgeB: judge B's, when a second pass ran."""
    results = [run for group in runs.values() for run in group]
    ids = next((run["modelIds"] for run in results if run["modelIds"]), {})
    models = {"flash": ids.get("transcribe") or ids.get("judge_a") or next(iter(ids.values()), FLASH_MODEL)}
    if any(run["passB"] for run in results) and ids.get("judge_b"):
        models["judgeB"] = ids["judge_b"]
    return models


def testset_info(doc: dict, clips: dict[str, dict], items: list[dict]) -> dict:
    sources = Counter(item["source"] for item in doc["items"])
    tts = sorted({clips[item["id"]]["model"] for item in items
                  if item["id"] in clips and clips[item["id"]].get("model")})
    return {"version": doc["version"], "nItems": len(doc["items"]),
            "synthetic": sources.get("synthetic_tts", 0), "recorded": sources.get("recorded", 0),
            "ttsModels": tts}


def run_meta(runs: dict[str, list[dict]], repeat: int, stability: float, testset: dict, complete: bool,
             testset_sha256: str | None = None, settings: dict | None = None, selection: dict | None = None) -> dict:
    results = [run for group in runs.values() for run in group]
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "promptVersion": _prompt_version(),
        "models": run_models(runs),
        "judgePasses": 2 if any(run["passB"] for run in results) else 1,
        "repeat": repeat,
        "stability": stability,
        "testset": testset,
        "complete": complete,
        "testsetSha256": testset_sha256,
        "settings": settings,
        "selection": selection,
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
    testset_sha256 = items_sha256()
    found = problems(doc, catalog)
    if found:
        for line in found:
            print(f"PROBLEM: {line}", file=sys.stderr)
        return 1
    clips = load_clip_manifest()
    ready = {item["id"] for item in doc["items"] if item_is_ready(item, doc, clips)}
    items = select_items(doc["items"], args.lang, args.limit, ready if args.ready_only else None, args.source)
    if not items:
        print("no items selected", file=sys.stderr)
        return 1
    not_ready = [item["id"] for item in items if item["id"] not in ready]
    if args.dry_run:
        print_plan(items, args.repeat, not_ready)
        return 0
    if not_ready:
        print(f"STOPPED: {len(not_ready)} selected items are not ready (clip not current, or question not "
              f"translated): {', '.join(not_ready[:5])}{' ...' if len(not_ready) > 5 else ''}. Render them first "
              "(eval/RUN_PAID.md), or pass --ready-only for an incomplete report.", file=sys.stderr)
        return 1
    # A --source run goes to reports/<source>/, so a subset never overwrites the whole set's reports/latest.*.
    out = out_dir or args.out or (REPORTS_DIR / args.source if args.source else REPORTS_DIR)
    progress = out / checkpoint.PROGRESS_NAME
    settings = run_settings(testset_sha256, args.repeat)
    done: dict[str, list[dict]] = {}
    if progress.exists() and args.restart:
        progress.unlink()
    elif progress.exists() and not args.resume:
        print(f"STOPPED: {progress} holds an earlier run's finished items. Pass --resume to continue it, or "
              "--restart to discard it.", file=sys.stderr)
        return 1
    elif args.resume:
        try:
            done = checkpoint.load(progress, settings)
        except checkpoint.ResumeRefused as exc:
            print(f"STOPPED: cannot resume: {exc}", file=sys.stderr)
            return 1
        print(f"resuming: {sum(item['id'] in done for item in items)} of {len(items)} items already done", flush=True)
    check: Any = run_check or backend_run_check()
    runs, errors = run_items(items, doc, catalog, check, args.repeat, progress, settings, done)
    finished = [item for item in items if item["id"] in runs]
    complete = not errors and len(finished) == len(doc["items"])
    scope = [item for item in doc["items"] if item["source"] == args.source]
    selection = None if args.source is None else {
        "source": args.source, "nItems": len(scope), "complete": not errors and len(finished) == len(scope)}
    rows, stability = aggregate(finished, runs)
    meta = run_meta(runs, args.repeat, stability, testset_info(doc, clips, finished), complete, testset_sha256,
                    settings, selection)
    report = build_report(rows, finished, meta, baseline=all_baselines(rows, catalog), errors=errors)
    json_path, md_path = write_reports(report, rows, meta, out)
    if not errors:
        progress.unlink(missing_ok=True)  # everything is in the report; a later run starts clean
    status = "PASS" if report["passBar"]["passed"] else "FAIL"
    print(f"{status}: exact accuracy {report['metrics']['exactAccuracy']}, "
          f"unsafe errors {report['metrics']['unsafeErrors']}, "
          f"correct pass rate {report['metrics']['correctPassRate']} -> {json_path.name}, {md_path.name}")
    print(report["headline"])
    held, keyword = report["byHeldOut"]["heldOut"], report["baseline"]["keywordNegation"]
    print(f"held out: {held['unsafeErrors']} false passes of {held['unsafeDenominator']} gold-miss ratings "
          f"({held['nItems']} items), exact {held['exactAccuracy']}; keyword + negation baseline: "
          f"{keyword['unsafeErrors']} false passes, exact {keyword['exactAccuracy']}")
    real, noisy = report["bySource"]["recorded"], report["recordedNoise"]["siteNoise"]
    if real["nItems"]:
        print(f"real voices: {real['unsafeErrors']} false passes of {real['unsafeDenominator']} gold-miss ratings "
              f"({real['nItems']} items); with site noise: {noisy['unsafeErrors']} of {noisy['unsafeDenominator']} "
              f"({noisy['nItems']} items)")
    if errors:
        print(f"ERRORS: {len(errors)} of {len(items)} items errored twice and are not in the report "
              f"({', '.join(e['id'] for e in errors[:5])}{' ...' if len(errors) > 5 else ''}). The report is "
              f"incomplete; {progress.name} is kept: rerun with --resume to retry only them.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
