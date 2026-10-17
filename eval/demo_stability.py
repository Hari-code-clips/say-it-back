"""Demo stability (review P0-16, 17 Oct 2026): each stored demo answer checked N times on its own clip, labels counted.

On 15 Oct identical audio came back "Ask again" in one run and "Got it" in another. This runs the real check
(sayitback.pipeline.run_check) N times (default 10) on each chosen item's clip, the way run_eval.py does (the question's
steps, that one question in the worker's language, the clip, supervisor language en), and counts per item and step how
often each label came back. A gold-miss step (gold missed, contradicted or unclear) rated covered ("Got it") in any run
is a false pass: the release is blocked. Items: every stored answer of the lead demo script sg-lead (both rounds, q1 to
q3: 6 items), or --script ID ..., or --items ID .... Run n of every item comes before run n+1, so a stopped run leaves
the items with about the same count.

Calls: a check is 1 + judge passes model calls (3 by default). Before each check its calls go to gemini_calls.log, one
line per model call in the build's format (gemini_client), capped by SIB_EVAL_CALL_BUDGET, which must be set: a real run
does not start without it, nor when the log plus the plan would pass it. A check that raises is tried once more after
RETRY_WAIT_S, logged again. The backend's own retries of one model call (SIB_RETRY_ATTEMPTS) stay inside its line, as in
run_eval.py. --dry-run prints the plan and makes no call.

Writes reports/stability/<date>.json and .md (a second run that day: <date>-2, ...; a report is never overwritten).
Exit codes: 0, every run done and no false pass; 1, a false pass (block the release); 2, no verdict (refused, or the
counts are short: a check failed twice, the budget ran out, or Ctrl-C).

Usage:
  uv run python demo_stability.py --dry-run                 # the plan; no call, nothing written
  SIB_EVAL_CALL_BUDGET=... uv run python demo_stability.py  # paid: 6 items x 10 runs x 3 = 180 model calls
  uv run python demo_stability.py --script chennai-second --repeat 5
  uv run python demo_stability.py --items lifting-zone.q1.ta.demo.clean.r1 --repeat 20
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import gemini_client
from catalog_io import load_catalog
from check_adapter import RunCheck, backend_run_check, call_check
from config import REPORTS_DIR, VERDICTS
from items_io import build_check_payload, item_is_ready, items_sha256, load_clip_manifest, load_items, problems
from metrics import is_gold_miss
from report import _cell
from run_eval import ERROR_MESSAGE_MAX, RETRY_WAIT_S, _verdict, run_models, run_settings

DEFAULT_SCRIPTS = ("sg-lead",)  # the lead demo: lifting-zone, en -> ta
DEFAULT_REPEAT = REVIEW_MIN_REPEAT = 10  # the review asks for at least 10 runs of each lead answer
STABILITY_DIR = REPORTS_DIR / "stability"
LABELS = {"covered": "Got it", "missed": "Missed", "contradicted": "Wrong", "unclear": "Ask again"}  # web verdict.*
EXIT_OK, EXIT_FALSE_PASS, EXIT_NO_VERDICT = 0, 1, 2

Outcome = tuple[dict[str, list[dict]], list[dict], str | None]  # runs per item id, errors, why the run stopped early


class Refused(Exception):
    """The run cannot start; nothing was called."""


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    chosen = parser.add_mutually_exclusive_group()
    chosen.add_argument("--items", nargs="+", metavar="ID", help="these eval item ids, in this order")
    chosen.add_argument("--script", nargs="+", metavar="ID",
                        help="every stored answer of these demo scripts (default: sg-lead)")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT,
                        help=f"checks per item on its one clip (default {DEFAULT_REPEAT})")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; make no call, write nothing")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    return args


def select_items(doc: dict, catalog: dict, item_ids: list[str] | None, scripts: list[str] | None) -> list[dict]:
    """Those item ids in the order given, or every stored answer of the demo scripts, by round, then by question."""
    by_id = {item["id"]: item for item in doc["items"]}
    if item_ids:
        unknown = [item_id for item_id in item_ids if item_id not in by_id]
        if unknown:
            raise Refused(f"unknown item ids: {', '.join(unknown)}.")
        return [by_id[item_id] for item_id in dict.fromkeys(item_ids)]
    wanted = list(dict.fromkeys(scripts or DEFAULT_SCRIPTS))
    known = sorted(script["id"] for script in catalog["demoScripts"])
    unknown = [script for script in wanted if script not in known]
    if unknown:
        raise Refused(f"unknown demo scripts: {', '.join(unknown)} (the catalog has {', '.join(known)}).")
    chosen = [item for item in doc["items"] if item["pattern"] == "demo" and item["demo"]["script"] in wanted]
    empty = [script for script in wanted if not any(item["demo"]["script"] == script for item in chosen)]
    if empty:
        raise Refused(f"no stored answer in the test set for: {', '.join(empty)}.")
    return sorted(chosen, key=lambda i: (wanted.index(i["demo"]["script"]), i["demo"]["round"], i["questionId"]))


def call_lines(settings: dict) -> list[tuple[str, str]]:
    """(agent, model) of each model call in one check: the blind transcriber and judge A on Flash, then judge B on its
    own model when a second pass runs (the check_answer Workflow)."""
    flash = settings["models"]["flash"]
    lines = [("blind_transcriber", flash), ("judge_a", flash)]
    return lines + ([("judge_b", settings["models"]["judgeB"])] if settings["judgePasses"] == 2 else [])


def budget_cap() -> int | None:
    """The cap when SIB_EVAL_CALL_BUDGET is set for this run, else None: a stability run never runs on the default cap.
    The cap is the build's own (gemini_client.GEMINI_CALL_BUDGET, read from that variable at start-up)."""
    return gemini_client.GEMINI_CALL_BUDGET if os.environ.get("SIB_EVAL_CALL_BUDGET", "").strip() else None


def check_can_start(not_ready: list[str], cap: int | None, calls: int) -> None:
    """Raises Refused before any call: a selected clip that is not current, no budget set, or a plan past the cap."""
    if not_ready:
        raise Refused(f"{len(not_ready)} selected items are not ready (clip not current, or question not translated): "
                      f"{', '.join(not_ready)}. Render them first (eval/RUN_PAID.md).")
    used = gemini_client.logged_call_count()
    if cap is None:
        raise Refused(f"SIB_EVAL_CALL_BUDGET is not set. This run logs {calls} model calls to gemini_calls.log "
                      f"({used} lines there now), so set it to at least {used + calls}, with room for retries "
                      "(eval/RUN_PAID.md, \"Demo stability\").")
    if used + calls > cap:
        raise Refused(f"SIB_EVAL_CALL_BUDGET={cap} is too low: gemini_calls.log holds {used} lines and this run logs "
                      f"{calls} more ({used + calls}). Raise it (eval/RUN_PAID.md, \"Demo stability\").")


def print_plan(items: list[dict], repeat: int, settings: dict, not_ready: list[str], cap: int | None) -> None:
    lines = call_lines(settings)
    checks, used = len(items) * repeat, gemini_client.logged_call_count()
    calls = checks * len(lines)
    print(f"dry run: {len(items)} items x {repeat} runs = {checks} checks x {len(lines)} model calls "
          f"({' + '.join(agent for agent, _ in lines)}) = {calls} model calls; none made")
    print(f"  prompt {settings['promptVersion']}, models {_models(settings['models'])}, judge passes "
          f"{settings['judgePasses']}, thinking {_thinking(settings)}")
    for item in items:
        gold = ", ".join(f"{step} {label}" for step, label in item["gold"].items())
        print(f"  {item['id']}: gold {gold}{'' if item['id'] not in not_ready else ' (NOT READY)'}")
    misses = sum(is_gold_miss(label) for item in items for label in item["gold"].values())
    print(f"  gold-miss steps: {misses}; one rated covered (Got it) in any run blocks the release (exit 1)")
    print(f"  gemini_calls.log: {used} lines now, {used + calls} after this run ({used + 2 * calls} if every check is "
          "retried once)")
    if cap is None:
        print("  SIB_EVAL_CALL_BUDGET is not set: a real run refuses to start (eval/RUN_PAID.md, \"Demo stability\")")
    else:
        print(f"  SIB_EVAL_CALL_BUDGET={cap}: {'fits' if used + calls <= cap else 'too low, a real run refuses'}")


def run_all(items: list[dict], payloads: dict[str, dict], run_check: RunCheck, repeat: int,
            lines: list[tuple[str, str]]) -> Outcome:
    """(item id -> its finished runs, errors, why the run stopped early or None). Run n of every item before run n+1."""
    runs: dict[str, list[dict]] = {item["id"]: [] for item in items}
    errors: list[dict] = []
    try:
        for n in range(1, repeat + 1):
            for item in items:
                payload, label = payloads[item["id"]], f"{item['id']} run {n}/{repeat}"
                try:
                    runs[item["id"]].append(_check_with_retry(run_check, payload, lines, label))
                except gemini_client.BudgetExceeded as exc:
                    print(f"STOPPED: {exc}", file=sys.stderr)
                    return runs, errors, "budget"
                except Exception as exc:  # noqa: BLE001 - recorded: the counts are short, and the run goes on
                    errors.append({"id": item["id"], "run": n, "class": type(exc).__name__,
                                   "message": str(exc)[:ERROR_MESSAGE_MAX]})
                    print(f"ERROR {label}: {type(exc).__name__}", flush=True)
                    continue
                print(f"ran {label}", flush=True)
    except KeyboardInterrupt:  # Ctrl-C: keep what was paid for, a false pass above all
        print("STOPPED: interrupted; writing the runs that finished", file=sys.stderr)
        return runs, errors, "interrupted"
    return runs, errors, None


def _check_with_retry(run_check: RunCheck, payload: dict, lines: list[tuple[str, str]], label: str) -> dict:
    try:
        return _logged_check(run_check, payload, lines, label, attempt=1)
    except gemini_client.BudgetExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 - one more try for any failure, as run_eval.py does
        print(f"  check failed ({type(exc).__name__}); trying once more in {RETRY_WAIT_S:g} s", flush=True)
        time.sleep(RETRY_WAIT_S)
        return _logged_check(run_check, payload, lines, label, attempt=2)


def _logged_check(run_check: RunCheck, payload: dict, lines: list[tuple[str, str]], label: str, attempt: int) -> dict:
    """Write one log line per model call of this check, refusing first if they do not all fit under the cap."""
    used, cap = gemini_client.logged_call_count(), gemini_client.GEMINI_CALL_BUDGET
    if used + len(lines) > cap:
        raise gemini_client.BudgetExceeded(f"Gemini call budget reached ({used} logged + {len(lines)} > {cap}); "
                                           "not calling")
    key = _clip_sha256(payload)
    for agent, model in lines:
        gemini_client._record_call(f"stability {label} {agent}", model, key, attempt)
    return call_check(run_check, payload)


def _clip_sha256(payload: dict) -> str:
    (clip,) = payload["clips"].values()
    return hashlib.sha256(clip).hexdigest()


def step_counts(item: dict, item_runs: list[dict]) -> list[dict]:
    """Per gold step: each label's count over the runs, the labels in run order, and the guard flags counted
    (not_rated when a run returned no rating, which counts as unclear, as in run_eval.py)."""
    out = []
    for step_id, gold in item["gold"].items():
        ratings = [run["ratings"].get(step_id) for run in item_runs]
        sequence = [_verdict(rating) for rating in ratings]
        counted = Counter(sequence)
        flags = Counter(flag for rating in ratings if rating for flag in rating["flags"])
        flags.update(["not_rated"] * sum(rating is None for rating in ratings))
        out.append({"stepId": step_id, "gold": gold, "counts": {v: counted[v] for v in VERDICTS},
                    "sequence": sequence, "flags": dict(sorted(flags.items())),
                    "falsePass": is_gold_miss(gold) and counted["covered"] > 0, "stable": len(set(sequence)) == 1})
    return out


def item_entry(item: dict, item_runs: list[dict], clip_sha256: str) -> dict:
    heard = {run.get("originals", {}).get(item["questionId"], "") for run in item_runs}
    return {"id": item["id"], "taskId": item["taskId"], "questionId": item["questionId"],
            "workerLang": item["workerLang"], "demo": item.get("demo"), "voice": item["voice"],
            "clipSha256": clip_sha256, "runs": len(item_runs), "distinctTranscripts": len(heard),
            "steps": step_counts(item, item_runs)}


def build_report(items: list[dict], payloads: dict[str, dict], outcome: Outcome, settings: dict, *, repeat: int,
                 selection: dict, day: date, log_lines: tuple[int, int]) -> dict:
    """log_lines: gemini_calls.log's line count before and after the run (retries and failed checks included)."""
    runs, errors, stopped = outcome
    entries = [item_entry(item, runs[item["id"]], _clip_sha256(payloads[item["id"]])) for item in items]
    steps = [step for entry in entries for step in entry["steps"]]
    false_passes = sum(step["counts"]["covered"] for step in steps if is_gold_miss(step["gold"]))
    checks = sum(entry["runs"] for entry in entries)
    complete = not errors and stopped is None and checks == len(items) * repeat
    return {
        "kind": "demo-stability", "day": day.isoformat(),
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": "blocked" if false_passes else ("pass" if complete else "incomplete"),
        "complete": complete, "stopped": stopped,
        "falsePasses": false_passes, "goldMissSteps": sum(is_gold_miss(step["gold"]) for step in steps),
        "repeat": repeat, "nItems": len(items), "itemIds": [item["id"] for item in items], "selection": selection,
        "checksPlanned": len(items) * repeat, "checksRun": checks, "callsPerCheck": len(call_lines(settings)),
        "callsLogged": log_lines[1] - log_lines[0], "logLines": log_lines[1],
        "promptVersion": settings["promptVersion"], "models": run_models(runs), "settings": settings,
        "errors": errors, "items": entries,
    }


def report_paths(out_dir: Path, day: date) -> tuple[Path, Path]:
    """<day>.json and .md, or <day>-2, -3, ... when that day has one already: a paid run is never overwritten."""
    stem, n = day.isoformat(), 1
    while (out_dir / f"{stem}.json").exists() or (out_dir / f"{stem}.md").exists():
        n += 1
        stem = f"{day.isoformat()}-{n}"
    return out_dir / f"{stem}.json", out_dir / f"{stem}.md"


def verdict_line(report: dict) -> str:
    checks, n, repeat = report["checksRun"], report["nItems"], report["repeat"]
    if report["verdict"] == "blocked":
        where = "; ".join(f"{e['id']} {s['stepId']} (gold {s['gold']}) in {s['counts']['covered']} of {e['runs']} runs"
                          for e in report["items"] for s in e["steps"] if s["falsePass"])
        noun = "false pass" if report["falsePasses"] == 1 else "false passes"
        return f"BLOCKED: {report['falsePasses']} {noun}, a gold-miss step rated Got it: {where}. Do not release."
    if report["verdict"] == "incomplete":
        why = {"budget": "the call budget ran out", "interrupted": "stopped by Ctrl-C"}.get(
            report["stopped"], f"{len(report['errors'])} checks failed twice")
        return (f"NO VERDICT: {checks} of {report['checksPlanned']} checks ran ({why}); none of them rated a gold-miss "
                "step Got it. Fix the cause and run it again.")
    short = "" if repeat >= REVIEW_MIN_REPEAT else (f" Fewer than the review's {REVIEW_MIN_REPEAT} runs per answer: "
                                                     "not the release check.")
    return f"PASS: no gold-miss step was rated Got it in {checks} checks ({n} items x {repeat} runs).{short}"


def render_markdown(report: dict) -> str:
    s = report["settings"]
    lines = [
        f"# Demo stability, {report['day']}", "", f"> {verdict_line(report)}", "",
        f"Generated {report['generatedAt']} | prompt {report['promptVersion']} | models {_models(report['models'])} | "
        f"judge passes {s['judgePasses']} | thinking {_thinking(s)} | max output tokens {s['maxOutputTokens']} | "
        f"backend {s['backend']} | items.json SHA-256 {s['testsetSha256'][:12]} | {report['repeat']} runs per item | "
        f"{report['checksRun']} checks | {report['callsLogged']} model calls logged (gemini_calls.log now "
        f"{report['logLines']} lines)", "",
        "## Items", "",
        "| Item | Demo | Voice | Clip SHA-256 | Runs | Distinct transcripts |", "|---|---|---|---|---|---|",
    ]
    lines += [f"| {e['id']} | {_demo(e['demo'])} | {e['voice']} | {e['clipSha256'][:12]} | {e['runs']} | "
              f"{e['distinctTranscripts']} |" for e in report["items"]]
    lines += ["", "## Labels per step", "",
              "| Item | Step | Gold | " + " | ".join(LABELS.values()) + " | Result |", "|---" * 8 + "|"]
    lines += [f"| {e['id']} | {st['stepId']} | {st['gold']} | " + " | ".join(str(st["counts"][v]) for v in LABELS)
              + f" | {_result(st)} |"
              for e in report["items"] for st in e["steps"]]
    flagged = [f"- {e['id']} {st['stepId']}: " + ", ".join(f"{flag} {k}" for flag, k in st["flags"].items())
               for e in report["items"] for st in e["steps"] if st["flags"]]
    lines += ["", "## Flags, counted over the runs", "", *(flagged or ["None."]), ""]
    if report["errors"]:
        lines += ["## Errors", "", "| Item | Run | Error | Message |", "|---|---|---|---|"]
        lines += [f"| {x['id']} | {x['run']} | {x['class']} | {_cell(x['message'])} |" for x in report["errors"]] + [""]
    return "\n".join(lines + _reading()) + "\n"


def _reading() -> list[str]:
    return [
        "## How to read this", "",
        "- Each item is one stored demo answer, its own clip (SHA-256 above), checked again and again with the same "
        "steps, question and languages, the way run_eval.py checks it (pipeline.run_check). What varies is the "
        "models' output (blind transcriber, judge A, judge B), not the input; distinct transcripts counts the "
        "different texts the transcriber heard.",
        "- Stop rule (review P0-16, eval/RUN_PAID.md): a gold-miss step (gold missed, contradicted or unclear) rated "
        "Got it in any run blocks the release. Missed, Wrong and Ask again on a gold miss are safe; Ask again on a "
        "gold Got it step costs a re-ask, not safety.",
        "- These are counts over a few runs of one synthetic clip per answer, not rates; a clean run here says "
        "nothing about real workers' answers.",
        "",
    ]


def _result(step: dict) -> str:
    if step["falsePass"]:
        return "FALSE PASS"
    return "no run" if not step["sequence"] else "same every run" if step["stable"] else "varies"


def _models(models: dict) -> str:
    return ", ".join(f"{name}={model}" for name, model in models.items() if model) or "n/a"


def _thinking(settings: dict) -> str:
    return ", ".join(f"{agent} {level}" for agent, level in settings["thinking"].items())


def _demo(demo: dict | None) -> str:
    return f"{demo['script']} round {demo['round'] + 1}" if demo else "-"


def stability_settings(repeat: int) -> dict:
    """run_eval.py's fingerprint (prompt version, models, judge passes, thinking levels, items.json SHA-256, repeats),
    plus the Flash output cap and the Gemini backend, so the run can be compared with the deployed service."""
    from sayitback.settings import Settings  # lazy, as in run_eval.run_settings

    return {**run_settings(items_sha256(), repeat), "maxOutputTokens": Settings.from_env().max_output_tokens,
            "backend": gemini_client.backend_name("flash")}


def main(argv: list[str] | None = None, *, run_check: RunCheck | None = None, out_dir: Path | None = None,
         today: date | None = None) -> int:
    args = parse_args(argv)
    doc, catalog = load_items(), load_catalog()
    try:
        found = problems(doc, catalog)
        if found:
            raise Refused("the test set breaks its contract: " + "; ".join(found[:5]) + ".")
        items = select_items(doc, catalog, args.items, args.script)
        clips = load_clip_manifest()
        not_ready = [item["id"] for item in items if not item_is_ready(item, doc, clips)]
        settings, cap = stability_settings(args.repeat), budget_cap()
        if args.dry_run:
            print_plan(items, args.repeat, settings, not_ready, cap)
            return EXIT_OK
        check_can_start(not_ready, cap, len(items) * args.repeat * len(call_lines(settings)))
    except Refused as exc:
        print(f"STOPPED: {exc} Nothing was called.", file=sys.stderr)
        return EXIT_NO_VERDICT
    payloads = {item["id"]: build_check_payload(item, doc, catalog) for item in items}  # each clip read once
    before = gemini_client.logged_call_count()
    outcome = run_all(items, payloads, run_check or backend_run_check(), args.repeat, call_lines(settings))
    day = today or date.today()
    report = build_report(
        items, payloads, outcome, settings, repeat=args.repeat, day=day,
        selection={"items": list(args.items)} if args.items else {"scripts": list(args.script or DEFAULT_SCRIPTS)},
        log_lines=(before, gemini_client.logged_call_count()))
    json_path = write_report(report, out_dir or STABILITY_DIR, day)
    print(f"{verdict_line(report)} -> {json_path} and .md")
    for entry in report["items"]:
        for step in entry["steps"]:
            counted = ", ".join(f"{LABELS[v]} {k}" for v, k in step["counts"].items() if k) or "no run"
            print(f"  {entry['id']} {step['stepId']} (gold {step['gold']}): {counted}")
    return EXIT_FALSE_PASS if report["falsePasses"] else EXIT_OK if report["complete"] else EXIT_NO_VERDICT


def write_report(report: dict, out_dir: Path, day: date) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = report_paths(out_dir, day)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path


if __name__ == "__main__":
    sys.exit(main())
