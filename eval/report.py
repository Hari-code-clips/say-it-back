"""Writers for eval/reports/latest.json (schema in docs/API.md, "Eval report") and latest.md."""

from __future__ import annotations

import json
from pathlib import Path

from config import PASS_EXACT_MIN, PASS_UNSAFE_MAX
from metrics import Row, group_summary, is_unsafe, passes_bar, summarize

METRIC_KEYS = (
    "exactAccuracy", "unsafeErrors", "unsafeDenominator", "unsafeUpperBound95",
    "catchRate", "overFlagRate", "unclearRate",
)
CAVEATS = [
    "## Caveats",
    "",
    "- The set is synthetic: TTS speech with mixed synthetic site noise. It is not the real-recording spike.",
    "- wrong_language and silence items are gold `unclear` on every step, because the right response is to abstain. "
    "An `unclear` rating is exact there, and a `covered` rating is an unsafe error.",
    "- `n` in the group tables counts step ratings. A ratio with no denominator shows as n/a.",
    "- With no unsafe error, the 95% bound is 3/N for N gold-miss ratings. At N = 40 that is 7.5%.",
    "",
]


def build_report(rows: list[Row], items: list[dict], meta: dict) -> dict:
    overall = summarize(rows)
    return {
        "generatedAt": meta["generatedAt"],
        "promptVersion": meta["promptVersion"],
        "models": meta["models"],
        "judgePasses": meta["judgePasses"],
        "nItems": len(items),
        "nStepRatings": len(rows),
        "metrics": {key: overall[key] for key in METRIC_KEYS},
        "passBar": {
            "exactAccuracyMin": PASS_EXACT_MIN,
            "unsafeErrorsMax": PASS_UNSAFE_MAX,
            "passed": passes_bar(overall),
        },
        "byLanguage": group_summary(rows, lambda r: r.worker_lang),
        "byPattern": group_summary(rows, lambda r: r.pattern),
        "items": [_item_entry(item, rows) for item in items],
    }


def _item_entry(item: dict, rows: list[Row]) -> dict:
    mine = [r for r in rows if r.item_id == item["id"]]
    return {
        "id": item["id"],
        "taskId": item["taskId"],
        "workerLang": item["workerLang"],
        "pattern": item["pattern"],
        "noise": item["noise"],
        "gold": {r.step_id: r.gold for r in mine},
        "pred": {r.step_id: r.pred for r in mine},
        "unsafe": any(is_unsafe(r) for r in mine),
        "flags": {r.step_id: list(r.flags) for r in mine},
    }


def write_reports(report: dict, rows: list[Row], meta: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "latest.json"
    md_path = out_dir / "latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report, rows, meta), encoding="utf-8")
    return json_path, md_path


def render_markdown(report: dict, rows: list[Row], meta: dict) -> str:
    metrics, bar = report["metrics"], report["passBar"]
    verdict = "PASS" if bar["passed"] else "FAIL"
    lines = [
        "# Say It Back eval report",
        "",
        f"**{verdict}**: exact accuracy {_pct(metrics['exactAccuracy'])} (bar {_pct(bar['exactAccuracyMin'])}); "
        f"unsafe errors {metrics['unsafeErrors']} of {metrics['unsafeDenominator']} gold-miss ratings "
        f"(bar {bar['unsafeErrorsMax']}).",
        "",
        f"Generated {report['generatedAt']} | prompt {report['promptVersion']} | models {_models(report)} | "
        f"judge passes {report['judgePasses']} | repeats {meta['repeat']} | items {report['nItems']} | "
        f"step ratings {report['nStepRatings']}",
    ]
    if meta["repeat"] > 1:
        lines.append(f"Repeat stability: {_pct(meta['stability'])} of step ratings unanimous across "
                     f"{meta['repeat']} runs.")
    lines += [""] + _overall_table(metrics)
    lines += _group_table("By language", "Language", report["byLanguage"])
    lines += _group_table("By pattern", "Pattern", report["byPattern"])
    lines += _group_table("By task", "Task", group_summary(rows, lambda r: r.task_id))
    lines += _group_table("By noise", "Noise", group_summary(rows, lambda r: r.noise))
    lines += _unsafe_section(rows)
    lines += CAVEATS
    return "\n".join(lines) + "\n"


def _overall_table(metrics: dict) -> list[str]:
    return [
        "## Overall", "",
        "| Metric | Value | Meaning |", "|---|---|---|",
        f"| exactAccuracy | {_pct(metrics['exactAccuracy'])} | predicted label equals gold; unclear counts only against unclear gold |",
        f"| unsafeErrors | {metrics['unsafeErrors']} of {metrics['unsafeDenominator']} | gold missed, contradicted or unclear, rated covered |",
        f"| unsafeUpperBound95 | {_pct(metrics['unsafeUpperBound95'])} | rule of three (3/N) when no error is seen |",
        f"| catchRate | {_pct(metrics['catchRate'])} | gold missed, contradicted or unclear, not rated covered |",
        f"| overFlagRate | {_pct(metrics['overFlagRate'])} | gold covered, not rated covered |",
        f"| unclearRate | {_pct(metrics['unclearRate'])} | predictions that are unclear |",
        "",
    ]


def _group_table(title: str, label: str, groups: dict[str, dict]) -> list[str]:
    body = [f"| {label} | step ratings (n) | exact | unsafe errors |", "|---|---|---|---|"]
    body += [f"| {name} | {g['n']} | {_pct(g['exactAccuracy'])} | {g['unsafeErrors']} |"
             for name, g in groups.items()]
    return [f"## {title}", "", *body, ""]


def _unsafe_section(rows: list[Row]) -> list[str]:
    unsafe = [r for r in rows if is_unsafe(r)]
    lines = ["## Unsafe errors", ""]
    if not unsafe:
        return lines + ["None. No gold-miss step was rated covered.", ""]
    lines += ["| Item | Step | Gold | Pred | Judge evidence |", "|---|---|---|---|---|"]
    lines += [f"| {r.item_id} | {r.step_id} | {r.gold} | {r.pred} | {_cell(r.evidence)} |" for r in unsafe]
    return lines + [""]


def _models(report: dict) -> str:
    return ", ".join(f"{name}={model}" for name, model in report["models"].items()) or "n/a"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _cell(text: str) -> str:
    return (text or "").replace("|", "/").replace("\n", " ")
