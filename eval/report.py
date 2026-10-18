"""Writers for eval/reports/latest.json (schema in docs/API.md, "Eval report") and latest.md."""

from __future__ import annotations

import json
import math
from pathlib import Path

from config import ABSTAIN_PATTERNS, PASS_CORRECT_MIN, PASS_EXACT_MIN, PASS_UNSAFE_MAX, SOURCES
from metrics import Row, RunRating, counts, group_summary, is_unsafe, passes_bar, summarize
from site_noise import NOISE_NAMES, SNR_LEVELS

METRIC_KEYS = (
    "exactAccuracy", "unsafeErrors", "unsafeDenominator", "unsafeUpperBound95",
    "catchRate", "overFlagRate", "unclearRate",
    "correctPassRate", "unsafeUpperBound95Items", "unsafeItemDenominator",  # v0.5, additive
)
BASELINE_NAMES = {"keyword": "keyword baseline", "keywordNegation": "keyword + negation baseline"}
SOURCE_NAMES = {"synthetic_tts": "Synthetic TTS voices", "recorded": "Recorded human voices"}
# 17 Oct: who made the voice. The judges are Gemini, so Gemini-voiced items share their model family; Sarvam-voiced
# items (spec.json `voice: "sarvam/..."`) do not, though they are still synthetic; recorded items are people.
VOICE_GROUPS = ("gemini", "otherVendor", "recorded")
VOICE_NAMES = {"gemini": "Gemini TTS voices", "otherVendor": "Another vendor's TTS voices (Sarvam)",
               "recorded": "Recorded human voices"}


def voice_group(item: dict) -> str:
    """The item's voice: a person (source recorded), another TTS vendor (a vendor voice id), or Gemini TTS."""
    if item.get("source") == "recorded":
        return "recorded"
    return "otherVendor" if str(item.get("voice") or "").startswith("sarvam/") else "gemini"
REPORT_TEXT_MAX = 600  # characters of one original, quote or reason in items[]: keeps the served report small


def build_report(rows: list[Row], items: list[dict], meta: dict,
                 baseline: dict[str, list[Row]] | None = None, errors: list[dict] | None = None) -> dict:
    """meta: generatedAt, promptVersion, models, judgePasses, repeat, stability, testset, complete, and
    testsetSha256 (v0.5). baseline: the keyword baselines' rows on the same items (baseline_keyword.all_baselines).

    v0.5 adds, without renaming anything: correctPassRate, unsafeUpperBound95Items and unsafeItemDenominator in
    metrics; passBar.correctPassMin; byHeldOut; modelOnly; testsetSha256; baseline; heldOut and translation per item.
    v0.5.1 adds bySource (synthetic_tts, recorded), and per item source, original and ratings; `settings` (the run's
    fingerprint: models, prompt version, judge passes, thinking levels, items.json SHA-256, repeats); and `errors`
    ([{id, class, message}], items whose check failed twice: they are not in items, and the run is incomplete).
    16 Oct adds recordedNoise (recorded_noise) and selection (null, or {source, nItems, complete} for a --source run).
    """
    overall = summarize(rows)
    report = {
        "generatedAt": meta["generatedAt"],
        "promptVersion": meta["promptVersion"],
        "models": meta["models"],
        "judgePasses": meta["judgePasses"],
        "repeat": meta["repeat"],
        "nItems": len(items),
        "nStepRatings": len(rows),
        "complete": meta["complete"],
        "testset": meta["testset"],
        "testsetSha256": meta.get("testsetSha256"),
        "settings": meta.get("settings"),
        "selection": meta.get("selection"),
        "errors": list(errors or []),
        "metrics": {key: overall[key] for key in METRIC_KEYS},
        "counts": counts(rows),
        "passBar": {
            "exactAccuracyMin": PASS_EXACT_MIN,
            "unsafeErrorsMax": PASS_UNSAFE_MAX,
            "correctPassMin": PASS_CORRECT_MIN,
            "passed": passes_bar(overall),
        },
        "byLanguage": group_summary(rows, lambda r: r.worker_lang),
        "byPattern": group_summary(rows, lambda r: r.pattern),
        "byHeldOut": {
            "heldOut": group_metrics([r for r in rows if r.held_out]),
            "inSet": group_metrics([r for r in rows if not r.held_out]),
        },
        "modelOnly": {"excludedPatterns": list(ABSTAIN_PATTERNS),
                      **group_metrics([r for r in rows if r.pattern not in ABSTAIN_PATTERNS])},
        "bySource": {source: group_metrics([r for r in rows if r.source == source]) for source in SOURCES},
        "byVoice": _by_voice(rows, items),
        "recordedNoise": recorded_noise(rows, items),
        "items": [_item_entry(item, rows) for item in items],
    }
    if baseline is not None:
        report["baseline"] = {name: group_metrics(baseline_rows) for name, baseline_rows in baseline.items()}
    report["headline"] = headline(report)
    return report


def group_metrics(rows: list[Row]) -> dict:
    """Every metric of `metrics` for a subset, with its size: n step ratings and nItems items."""
    summary = summarize(rows)
    return {"n": len(rows), "nItems": len({r.item_id for r in rows}), **{key: summary[key] for key in METRIC_KEYS}}


def recorded_noise(rows: list[Row], items: list[dict] | None = None) -> dict:
    """16 Oct, the recorded items by noise: as recorded in a quiet room (clean), every site-noise copy
    (augment_recorded.py), each SNR over every profile, and each profile at each SNR present. 17 Oct, additive:
    ambient, the recordings made where real noise was present (the item's `ambient` note, for example rain); they
    are not in clean, and no synthetic noise is mixed into them."""
    ambient_ids = {item["id"] for item in items or [] if item.get("ambient")}
    recorded = [r for r in rows if r.source == "recorded"]
    copies = [r for r in recorded if r.noise in NOISE_NAMES]
    return {
        "clean": group_metrics([r for r in recorded if r.noise == "clean" and r.item_id not in ambient_ids]),
        "ambient": group_metrics([r for r in recorded if r.item_id in ambient_ids]),
        "siteNoise": group_metrics(copies),
        "bySnr": {snr: group_metrics([r for r in copies if r.noise.endswith(f".{snr}")]) for snr in SNR_LEVELS},
        "byNoise": {noise: group_metrics([r for r in copies if r.noise == noise])
                    for noise in sorted({r.noise for r in copies})},
    }


def headline(report: dict) -> str:
    """One sentence a judge can quote. The bound is rounded up, so it is never understated, and (17 Oct, review P0-8)
    it names its method and the independence it assumes, so it is never quoted without them."""
    m, c, ts = report["metrics"], report["counts"], report["testset"]
    false_passes = c["falsePasses"]
    noun = "false pass" if false_passes == 1 else "false passes"
    sentence = (
        f"{false_passes} {noun} in {c['goldMiss']} gold-miss step ratings "
        f"(95% upper bound {_pct_up(m['unsafeUpperBound95'])} by {_bound_method(false_passes)} over those ratings, "
        f"which assumes independent ratings); exact {_pct(m['exactAccuracy'])}; "
        f"correct passes {c['correctPasses']} of {c['goldCovered']}; asked again {_pct(m['unclearRate'])}. "
        f"{report['nItems']} answers {_voices(report)}, judged by Gemini ({_judges(report)})."
    )
    selection = report.get("selection") or {}
    if not report["complete"] and selection.get("complete"):
        sentence = (f"{SOURCE_NAMES[selection['source']]} only ({report['nItems']} of the {ts['nItems']} items in "
                    "the set): " + sentence)
    elif not report["complete"]:
        sentence = f"Incomplete run ({report['nItems']} of {ts['nItems']} items, not for quoting): " + sentence
    return sentence


def _bound_method(errors: int) -> str:
    """How metrics.unsafe_upper_bound made the bound: the rule of three (3/N) with no error, a Wilson interval else."""
    return "the rule of three" if errors == 0 else "the Wilson score interval"


def _recorded_counts(report: dict) -> tuple[int, int]:
    """(recorded items run, of which site-noise copies), from the items run."""
    recorded = [entry for entry in report["items"] if entry.get("source") == "recorded"]
    return len(recorded), sum(entry["noise"] in NOISE_NAMES for entry in recorded)


def _voices(report: dict) -> str:
    """The voices of the items run (16 Oct: counted over them, so a copy with site noise is never a recording)."""
    tts = ", ".join(report["testset"].get("ttsModels") or []) or "Gemini TTS"
    recorded, copies = _recorded_counts(report)
    noisy = f" ({copies} of them with synthetic site noise)" if copies else ""
    if not recorded:
        return f"in synthetic Gemini TTS voices ({tts})"
    if recorded == len(report["items"]):
        return f"from consented human recordings{noisy}"
    return f"in synthetic Gemini TTS voices ({tts}) and {recorded} consented recordings{noisy}"


def _judges(report: dict) -> str:
    models = report["models"]
    flash = models.get("flash", "n/a")
    judge_b = models.get("judgeB")
    if report["judgePasses"] < 2 or not judge_b:
        return f"{flash}, one judge pass"
    if judge_b == flash:
        return f"{flash} for both judges"
    return f"{flash}; judge B {judge_b}"


def _by_voice(rows: list[Row], items: list[dict]) -> dict:
    """17 Oct, additive: the metrics per voice group (VOICE_GROUPS), each item's group read from the item itself."""
    group_of = {item["id"]: voice_group(item) for item in items}
    return {group: group_metrics([r for r in rows if group_of.get(r.item_id) == group]) for group in VOICE_GROUPS}


def _item_entry(item: dict, rows: list[Row]) -> dict:
    """translation (v0.5): the blind transcriber's English translation of the answer (first run), the keyword
    baseline's input, so the baseline can be recomputed from the report alone. original and ratings (v0.5.1): its
    text in the worker's language, and each gold step's final (guarded) rating in that run, so a stored result shows
    the worker's own words and the quote behind each verdict. Free text is cut at REPORT_TEXT_MAX characters."""
    mine = [r for r in rows if r.item_id == item["id"]]
    return {
        "id": item["id"],
        "taskId": item["taskId"],
        "workerLang": item["workerLang"],
        "pattern": item["pattern"],
        "noise": item["noise"],
        "source": item.get("source", "synthetic_tts"),
        "heldOut": bool(item.get("heldOut", False)),
        "gold": {r.step_id: r.gold for r in mine},
        "pred": {r.step_id: r.pred for r in mine},
        "unsafe": any(is_unsafe(r) for r in mine),
        "flags": {r.step_id: list(r.flags) for r in mine},
        "translation": mine[0].translation if mine else "",
        "original": _clip(mine[0].original) if mine else "",
        "ratings": [_rating_json(r.rating) for r in mine if r.rating is not None],
    }


def _rating_json(rating: RunRating) -> dict:
    """{stepId, verdict} plus quote, quoteTranslation, reason and flags when the rating has them."""
    out: dict = {"stepId": rating.step_id, "verdict": rating.verdict}
    for key, value in (("quote", rating.quote), ("quoteTranslation", rating.quote_translation),
                       ("reason", rating.reason)):
        if value:
            out[key] = _clip(value)
    if rating.flags:
        out["flags"] = list(rating.flags)
    return out


def _clip(text: str) -> str:
    return text if len(text) <= REPORT_TEXT_MAX else text[:REPORT_TEXT_MAX - 1] + "…"


def write_reports(report: dict, rows: list[Row], meta: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "latest.json"
    md_path = out_dir / "latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report, rows, meta), encoding="utf-8")
    return json_path, md_path


def render_markdown(report: dict, rows: list[Row], meta: dict) -> str:
    metrics, bar = report["metrics"], report["passBar"]
    selection = report.get("selection") or {}
    scope = ("" if report["complete"] else f" ({SOURCE_NAMES[selection['source']].lower()} only, not the whole set)"
             if selection.get("complete") else " (incomplete run, not for quoting)")
    verdict = ("PASS" if bar["passed"] else "FAIL") + scope
    lines = [
        "# Say It Back eval report",
        "",
        f"> {report['headline']}",
        "",
        f"**{verdict}**: exact accuracy {_pct(metrics['exactAccuracy'])} (bar {_pct(bar['exactAccuracyMin'])}); "
        f"unsafe errors {metrics['unsafeErrors']} of {metrics['unsafeDenominator']} gold-miss ratings "
        f"(bar {bar['unsafeErrorsMax']}); correct passes {_pct(metrics['correctPassRate'])} "
        f"(bar {_pct(bar['correctPassMin'])}).",
        "",
        f"Generated {report['generatedAt']} | prompt {report['promptVersion']} | models {_models(report)} | "
        f"judge passes {report['judgePasses']} | repeats {meta['repeat']} | items {report['nItems']} of "
        f"{report['testset']['nItems']} (test set {report['testset']['version']}, items.json SHA-256 "
        f"{(report.get('testsetSha256') or 'n/a')[:12]}) | step ratings {report['nStepRatings']}"
        + _thinking(report),
    ]
    if meta["repeat"] > 1:
        lines.append(f"Repeat stability: {_pct(meta['stability'])} of step ratings unanimous across "
                     f"{meta['repeat']} runs.")
    lines += [""] + _about(report)
    lines += _overall_table(metrics, report["counts"])
    lines += _subsets_table(report)
    lines += _recorded_noise_section(report)
    lines += _group_table("By language", "Language", report["byLanguage"])
    lines += _group_table("By pattern", "Pattern", report["byPattern"])
    lines += _group_table("By task", "Task", group_summary(rows, lambda r: r.task_id))
    lines += _group_table("By noise", "Noise", group_summary(rows, lambda r: r.noise))
    lines += _unsafe_section(rows)
    lines += _errors_section(report)
    lines += _caveats(report)
    return "\n".join(lines) + "\n"


def _thinking(report: dict) -> str:
    thinking = (report.get("settings") or {}).get("thinking") or {}
    return (" | thinking " + ", ".join(f"{agent} {level}" for agent, level in thinking.items())) if thinking else ""


def _errors_section(report: dict) -> list[str]:
    errors = report.get("errors") or []
    if not errors:
        return []
    lines = ["## Errors", "", f"{len(errors)} items failed twice and are not scored, so this run is incomplete. "
             "Rerun with `--resume` to retry only them.", "", "| Item | Error | Message |", "|---|---|---|"]
    lines += [f"| {e['id']} | {e['class']} | {_cell(e['message'])} |" for e in errors]
    return lines + [""]


def _about(report: dict) -> list[str]:
    ts = report["testset"]
    tts = ", ".join(ts.get("ttsModels") or []) or "Gemini TTS"
    recorded, copies = _recorded_counts(report)
    synthetic = [
        f"- **The answers are synthetic.** They were written by the team as English glosses, translated by "
        f"Gemini, and voiced by Gemini TTS ({tts}), about a third with synthetic site noise. "
        + ("No real worker was recorded." if not recorded else f"{recorded} answers are consented recordings."),
        f"- **Known bias: the same model family speaks and judges.** Gemini models ({_judges(report)}) grade "
        "speech that a Gemini model produced: clean, fluent and without accent. That is probably easier than a "
        "real worker on a phone at a site, so treat these numbers as a check of the logic, not a measure of "
        "real-world accuracy.",
    ] if recorded < len(report["items"]) or not recorded else []
    real = [
        f"- **Real voices, synthetic site noise: not a field trial.** {recorded - copies} answers are consented "
        "recordings (speaker codes, never names) re-voicing synthetic items with the same gold, made in a quiet "
        f"room; {copies} are copies of them with procedural site noise (machinery drone, hammering, a reversing "
        "beeper, distant babble) mixed in at 10, 5 and 0 dB SNR over the speech (eval/site_noise.py). A site adds "
        "distance, wind, echo and accents this does not, and the speakers are few: read the bound, not the rate.",
    ] if recorded else []
    lines = [
        "## What these numbers are",
        "",
        *synthetic,
        *real,
        "- **Gold labels are the authors' judgement**, from the rubric in docs/API.md; items marked "
        "`fidelity: review` still need a native speaker's check.",
        "",
    ]
    selection = report.get("selection") or {}
    if not report["complete"] and selection.get("complete"):
        lines[2:2] = [f"- **{SOURCE_NAMES[selection['source']]} only:** {report['nItems']} of the {ts['nItems']} "
                      f"items in the set (`run_eval.py --source {selection['source']}`). Quote them as that subset, "
                      "beside the whole set's run (reports/latest.md), never as the whole set."]
    elif not report["complete"]:
        lines[2:2] = [f"- **Incomplete run:** {report['nItems']} of {ts['nItems']} items. Do not quote these "
                      "numbers; run the whole set (eval/RUN_PAID.md)."]
    return lines


def _overall_table(metrics: dict, c: dict) -> list[str]:
    return [
        "## Overall", "",
        "| Metric | Value | Meaning |", "|---|---|---|",
        f"| exactAccuracy | {_pct(metrics['exactAccuracy'])} | predicted label equals gold; unclear counts only against unclear gold |",
        f"| unsafeErrors | {metrics['unsafeErrors']} | false passes: gold missed, contradicted or unclear, rated covered |",
        f"| unsafeDenominator | {metrics['unsafeDenominator']} | gold-miss ratings (gold missed, contradicted or unclear) |",
        f"| unsafeUpperBound95 | {_pct_up(metrics['unsafeUpperBound95'])} | 95% upper bound on false passes over the gold-miss ratings: rule of three (3/N) when no error is seen, Wilson 95% otherwise; assumes independent ratings; rounded up |",
        f"| catchRate | {_pct(metrics['catchRate'])} | gold missed, contradicted or unclear, not rated covered |",
        f"| overFlagRate | {_pct(metrics['overFlagRate'])} | gold covered, not rated covered |",
        f"| unclearRate | {_pct(metrics['unclearRate'])} | predictions that are unclear (asked again: {c['askedAgain']} of {c['stepRatings']}) |",
        f"| correct passes | {c['correctPasses']} of {c['goldCovered']} | gold covered, rated covered |",
        f"| correctPassRate | {_pct(metrics['correctPassRate'])} | gold covered, rated covered, as a share |",
        f"| unsafeItemDenominator | {metrics['unsafeItemDenominator']} | items with at least one gold-miss step |",
        f"| unsafeUpperBound95Items | {_pct_up(metrics['unsafeUpperBound95Items'])} | the same bound over those items (an item is an error if any of its gold-miss steps is rated covered); assumes independent items; rounded up |",
        "",
    ]


def _subsets_table(report: dict) -> list[str]:
    """Held-out against in-set items, the model alone (no abstain items), and the keyword baselines."""
    held, model_only = report["byHeldOut"], report["modelOnly"]
    rows = [("All items", report["metrics"] | {"n": report["nStepRatings"], "nItems": report["nItems"]}),
            ("In-set tasks", held["inSet"]), ("Held-out tasks", held["heldOut"]),
            ("Model only (no silence or wrong_language)", model_only),
            ("Synthetic TTS voices", report["bySource"]["synthetic_tts"])]
    voices = report.get("byVoice")
    if voices:  # 17 Oct: a report from before then has no voice split
        rows += [(VOICE_NAMES[group], voices[group]) for group in ("gemini", "otherVendor")]
    rows += [("Recorded human voices", report["bySource"]["recorded"])]
    rows += [(BASELINE_NAMES.get(name, name).capitalize(), group) for name, group in report.get("baseline", {}).items()]
    body = _subset_lines(rows)
    return [
        "## Held-out tasks, the model alone, and a keyword baseline", "",
        "- **Held-out tasks** (confined-space entry, fragile roofs) have no demo script, and no prompt example uses "
        "their words, so these items test judgement, not recall. They are few: read their bound, not their rate.",
        "- **Model only** leaves out the silence and wrong_language items, which the code guards (no speech, wrong "
        "language) catch before any judgement matters.",
        "- **Gemini TTS voices** share the judges' model family; **another vendor's TTS voices** (Sarvam Bulbul) do "
        "not, so the gap between the two rows is a first look at that bias, although both are synthetic: clean, "
        "fluent and without a site accent.",
        "- **Recorded human voices** are consented volunteers (speaker codes, no names) re-voicing synthetic items "
        "with the same gold (eval/record_clips.py); the gap to the synthetic row is the first sign of real speech.",
        "- **Keyword baselines** rate each step from the same English translation of the answer that the judges "
        "read: covered when every content word of every essential phrase appears, missed when none does, unclear "
        "otherwise; the negation variant also says contradicted when the matching clause and the essential phrase "
        "disagree on negation (eval/baseline_keyword.py).",
        "", *body, "",
    ]


BOUND_NOTE = ("95% bound: the rule of three (3/N) over the row's gold-miss ratings (steps) or over its items with a "
              "gold miss (items) when the row has no false pass, else the Wilson score interval; it assumes those "
              "ratings (or items) are independent, and is rounded up.")


def _subset_lines(rows: list[tuple[str, dict]]) -> list[str]:
    """The subsets table, then the note that says how its 95% bounds are made and what they assume."""
    body = ["| Subset | items | step ratings | exact | false passes | 95% bound (steps) | 95% bound (items) | "
            "correct passes | asked again |", "|---|---|---|---|---|---|---|---|---|"]
    return body + [f"| {name} | {g['nItems']} | {g['n']} | {_pct(g['exactAccuracy'])} | {g['unsafeErrors']} of "
                   f"{g['unsafeDenominator']} | {_pct_up(g['unsafeUpperBound95'])} | "
                   f"{_pct_up(g['unsafeUpperBound95Items'])} | {_pct(g['correctPassRate'])} | "
                   f"{_pct(g['unclearRate'])} |" for name, g in rows] + ["", BOUND_NOTE]


def _recorded_noise_section(report: dict) -> list[str]:
    """16 Oct: the recorded items as recorded, then their site-noise copies; nothing when no recording ran."""
    split = report["recordedNoise"]
    ambient = split.get("ambient") or {"nItems": 0}  # a report from before 17 Oct has none
    if not split["clean"]["nItems"] and not split["siteNoise"]["nItems"] and not ambient["nItems"]:
        return []
    rows = [("As recorded (quiet room)", split["clean"])]
    rows += [("As recorded in real background noise", ambient)] if ambient["nItems"] else []
    rows += [("All site noise", split["siteNoise"])]
    rows += [(f"Site noise at {SNR_LEVELS[snr]:g} dB SNR", group) for snr, group in split["bySnr"].items()
             if group["nItems"]]
    rows += list(split["byNoise"].items())
    return [
        "## Real voices by noise", "",
        "- Consented recordings (eval/record_clips.py), and copies of them with procedural site noise mixed in "
        "(eval/augment_recorded.py): machinery drone, hammering, a reversing beeper and distant babble, at an SNR "
        "measured over the speech. Real voices with synthetic noise: not a field trial. Recordings made in real noise "
        "(the item's ambient note) get no synthetic noise.",
        "", *_subset_lines(rows), "",
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


def _caveats(report: dict) -> list[str]:
    n = report["metrics"]["unsafeDenominator"]
    n_items = report["metrics"]["unsafeItemDenominator"]
    bound = f"At N = {n} that is {_pct_up(3 / n)}." if n else ""
    item_bound = (f"Over the {n_items} items with a gold miss it is {_pct_up(3 / n_items)}, which assumes the items "
                  "independent." if n_items else "")
    return [
        "## Caveats",
        "",
        "- This is not the real-recording spike: synthetic speech flatters the judges (see above).",
        "- wrong_language and silence items are gold `unclear` on every step, because the right response is to "
        "abstain. An `unclear` rating is exact there, and a `covered` rating is an unsafe error.",
        "- `n` in the group tables counts step ratings. A ratio with no denominator shows as n/a.",
        "- With no unsafe error, the 95% upper bound is the rule of three, 3/N for N gold-miss ratings, and it assumes "
        f"the N ratings are independent. {bound} {item_bound}".rstrip(),
        "- They are not: the ratings of one answer share its clip, and answers share tasks, voices and labellers. So "
        "the bound over items is the more cautious number, and neither is a false-pass probability for real workers.",
        "",
    ]


def _models(report: dict) -> str:
    return ", ".join(f"{name}={model}" for name, model in report["models"].items()) or "n/a"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _pct_up(value: float | None) -> str:
    """A bound as a percentage rounded up to 0.1 (3/76 = 3.947% -> 4.0%)."""
    return "n/a" if value is None else f"{math.ceil(round(value * 1000, 6)) / 10:.1f}%"


def _cell(text: str) -> str:
    return (text or "").replace("|", "/").replace("\n", " ")
