"""The report's quotable headline, its counts and its plain statement of what the numbers are."""

import pytest

from metrics import Row, RunRating, counts
from report import BOUND_NOTE, METRIC_KEYS, REPORT_TEXT_MAX, _pct_up, build_report, render_markdown

TESTSET = {"version": "2026-10-14", "nItems": 46, "synthetic": 46, "recorded": 0,
           "ttsModels": ["gemini-3.8-flash-tts"]}


def row(gold: str, pred: str, n: int) -> Row:
    return Row(item_id=f"item-{n}", task_id="lifting-zone", worker_lang="ta", pattern="complete",
               noise="clean", step_id="s1", gold=gold, pred=pred, any_covered=pred == "covered")


def meta(complete: bool = True, judge_b: str | None = "gemini-3.1-flash-lite") -> dict:
    models = {"flash": "gemini-3.8-flash", **({"judgeB": judge_b} if judge_b else {})}
    return {"generatedAt": "2026-10-14T12:00:00Z", "promptVersion": "p", "models": models,
            "judgePasses": 2 if judge_b else 1, "repeat": 1, "stability": 1.0, "testset": TESTSET,
            "complete": complete}


def report_for(rows: list[Row], **kwargs) -> dict:
    items = [{"id": r.item_id, "taskId": r.task_id, "workerLang": r.worker_lang, "pattern": r.pattern,
              "noise": r.noise} for r in rows]
    return build_report(rows, items, meta(**kwargs))


def _set(misses: int = 76, covered_ok: int = 40, covered_unclear: int = 5, false_passes: int = 0) -> list[Row]:
    rows = [row("missed", "missed", n) for n in range(misses - false_passes)]
    rows += [row("missed", "covered", 1000 + n) for n in range(false_passes)]
    rows += [row("covered", "covered", 2000 + n) for n in range(covered_ok)]
    rows += [row("covered", "unclear", 3000 + n) for n in range(covered_unclear)]
    return rows


def test_the_headline_is_one_quotable_sentence_with_the_bound_rounded_up_and_its_assumption():
    """17 Oct (review P0-8): the bound names its method and the independence it assumes, inside the sentence."""
    report = report_for(_set())

    assert report["headline"] == (
        "0 false passes in 76 gold-miss step ratings (95% upper bound 4.0% by the rule of three over those ratings, "
        "which assumes independent ratings); exact 95.9%; correct passes 40 of 45; asked again 4.1%. 121 answers in "
        "synthetic Gemini TTS voices (gemini-3.8-flash-tts), judged by Gemini (gemini-3.8-flash; judge B "
        "gemini-3.1-flash-lite)."
    )


def test_one_false_pass_is_singular_and_uses_the_wilson_bound():
    report = report_for(_set(false_passes=1))

    assert report["headline"].startswith(
        "1 false pass in 76 gold-miss step ratings (95% upper bound 7.1% by the Wilson score interval over those "
        "ratings, which assumes independent ratings); ")
    assert report["counts"]["falsePasses"] == report["metrics"]["unsafeErrors"] == 1


def test_every_bound_in_the_markdown_names_its_method_and_the_independence_it_assumes():
    rows = _set()
    report = report_for(rows)

    markdown = render_markdown(report, rows, meta())

    assert ("| unsafeUpperBound95 | 4.0% | 95% upper bound on false passes over the gold-miss ratings: rule of three "
            "(3/N) when no error is seen, Wilson 95% otherwise; assumes independent ratings; rounded up |") in markdown
    assert "| unsafeUpperBound95Items | 4.0% | the same bound over those items" in markdown
    assert "is rated covered); assumes independent items; rounded up |" in markdown
    subsets = markdown.split("## Held-out tasks, the model alone, and a keyword baseline")[1].split("\n## ")[0]
    assert "| 95% bound (steps) | 95% bound (items) |" in subsets and BOUND_NOTE in subsets
    assert ("the 95% upper bound is the rule of three, 3/N for N gold-miss ratings, and it assumes the N ratings are "
            "independent. At N = 76 that is 4.0%. Over the 76 items with a gold miss it is 4.0%, which assumes the "
            "items independent.") in markdown
    assert set(report["metrics"]) == set(METRIC_KEYS)  # the deck reads these keys; none is renamed


def test_an_incomplete_run_says_so_before_anything_else():
    report = report_for(_set(), complete=False)

    assert report["headline"].startswith("Incomplete run (121 of 46 items, not for quoting): ")


def test_the_report_carries_every_contract_metric_and_the_counts():
    report = report_for(_set())

    assert set(report["metrics"]) == set(METRIC_KEYS)
    assert report["counts"] == {"stepRatings": 121, "goldMiss": 76, "falsePasses": 0, "goldCovered": 45,
                                "correctPasses": 40, "askedAgain": 5}
    assert report["metrics"]["unsafeDenominator"] == report["counts"]["goldMiss"]


def test_the_markdown_states_synthetic_gemini_tts_voices_and_the_same_family_bias():
    rows = _set()
    report = report_for(rows)

    markdown = render_markdown(report, rows, meta())

    assert markdown.splitlines()[2] == f"> {report['headline']}"
    assert "**The answers are synthetic.**" in markdown
    assert "voiced by Gemini TTS (gemini-3.8-flash-tts)" in markdown
    assert "Known bias: the same model family speaks and judges." in markdown
    assert "At N = 76 that is 4.0%." in markdown
    assert "| unsafeUpperBound95 | 4.0% |" in markdown  # the table rounds the bound up, like the headline
    for key in METRIC_KEYS:
        assert f"| {key} |" in markdown


def test_an_incomplete_run_is_not_shown_as_a_plain_pass():
    rows = _set()
    report = report_for(rows, complete=False)

    markdown = render_markdown(report, rows, meta(complete=False))

    assert "**PASS (incomplete run, not for quoting)**" in markdown
    assert "**PASS**" not in markdown


def test_one_judge_pass_is_named_as_such():
    report = report_for(_set(), judge_b=None)

    assert report["headline"].endswith("judged by Gemini (gemini-3.8-flash, one judge pass).")


@pytest.mark.parametrize(("value", "shown"), [(3 / 76, "4.0%"), (3 / 40, "7.5%"), (0.1, "10.0%"), (None, "n/a")])
def test_bounds_round_up_to_a_tenth_of_a_percent(value, shown):
    assert _pct_up(value) == shown


def test_counts_match_the_rates():
    rows = _set(false_passes=2)

    c = counts(rows)

    assert c["askedAgain"] == sum(r.pred == "unclear" for r in rows)
    assert c["correctPasses"] + 5 == c["goldCovered"]


# v0.5 report fields, on a hand-made 4-item fixture --------------------------------------------------------------

def r4(item: str, step: str, gold: str, pred: str, *, held_out: bool = False, pattern: str = "complete",
       translation: str = "") -> Row:
    return Row(item_id=item, task_id="lifting-zone", worker_lang="ta", pattern=pattern, noise="clean", step_id=step,
               gold=gold, pred=pred, any_covered=pred == "covered", held_out=held_out, translation=translation)


FOUR = [
    r4("in-1", "s1", "covered", "covered", translation="I'll never go under the load."),
    r4("in-1", "s2", "missed", "missed", translation="I'll never go under the load."),
    r4("in-2", "s1", "unclear", "covered", pattern="silence"),  # an abstain item, falsely passed
    r4("held-1", "s1", "contradicted", "covered", held_out=True),  # a held-out false pass
    r4("held-2", "s1", "covered", "unclear", held_out=True),
]
FOUR_ITEMS = [{"id": i, "taskId": "lifting-zone", "workerLang": "ta", "pattern": p, "noise": "clean", "heldOut": h}
              for i, p, h in (("in-1", "complete", False), ("in-2", "silence", False),
                              ("held-1", "complete", True), ("held-2", "complete", True))]


def four_report(**kwargs) -> dict:
    return build_report(FOUR, FOUR_ITEMS, {**meta(), "testsetSha256": "ab" * 32}, **kwargs)


def test_v05_metrics_and_the_pass_bar_minimum_for_correct_passes():
    report = four_report()

    assert report["metrics"]["correctPassRate"] == pytest.approx(1 / 2)
    assert report["metrics"]["unsafeItemDenominator"] == 3
    assert report["passBar"]["correctPassMin"] == 0.75
    assert report["passBar"]["passed"] is False


def test_by_held_out_splits_held_out_from_in_set_items():
    held, in_set = four_report()["byHeldOut"]["heldOut"], four_report()["byHeldOut"]["inSet"]

    assert (held["nItems"], held["n"], held["unsafeErrors"], held["unsafeDenominator"]) == (2, 2, 1, 1)
    assert held["correctPassRate"] == 0.0
    assert (in_set["nItems"], in_set["n"], in_set["unsafeErrors"], in_set["unsafeDenominator"]) == (2, 3, 1, 2)
    assert set(held) == set(in_set) == {"n", "nItems", *METRIC_KEYS}


def test_model_only_leaves_out_the_abstain_patterns():
    model_only = four_report()["modelOnly"]

    assert model_only["excludedPatterns"] == ["silence", "wrong_language"]
    assert (model_only["nItems"], model_only["n"], model_only["unsafeErrors"]) == (3, 4, 1)


def test_testset_sha_and_per_item_held_out_and_translation_are_recorded():
    report = four_report()
    items = {item["id"]: item for item in report["items"]}

    assert report["testsetSha256"] == "ab" * 32
    assert items["held-1"]["heldOut"] is True and items["in-1"]["heldOut"] is False
    assert items["in-1"]["translation"] == "I'll never go under the load."


def test_the_baseline_is_scored_with_the_same_metrics_and_absent_unless_given():
    baseline = {"keyword": [r4("in-1", "s1", "covered", "covered")],
                "keywordNegation": [r4("in-1", "s1", "covered", "missed")]}

    report = four_report(baseline=baseline)

    assert "baseline" not in four_report()
    assert set(report["baseline"]) == {"keyword", "keywordNegation"}
    assert report["baseline"]["keyword"]["correctPassRate"] == 1.0
    assert report["baseline"]["keywordNegation"]["correctPassRate"] == 0.0


def test_by_source_splits_recorded_human_voices_from_synthetic_tts():
    rows = [r4("syn", "s1", "covered", "covered"),
            Row(item_id="syn.rec.V01", task_id="lifting-zone", worker_lang="ta", pattern="complete", noise="clean",
                step_id="s1", gold="missed", pred="covered", any_covered=True, source="recorded")]
    items = [{"id": "syn", "taskId": "lifting-zone", "workerLang": "ta", "pattern": "complete", "noise": "clean"},
             {"id": "syn.rec.V01", "taskId": "lifting-zone", "workerLang": "ta", "pattern": "complete",
              "noise": "clean", "source": "recorded"}]

    report = build_report(rows, items, meta())

    by_source = report["bySource"]
    assert set(by_source) == {"synthetic_tts", "recorded"}
    assert (by_source["synthetic_tts"]["nItems"], by_source["synthetic_tts"]["unsafeErrors"]) == (1, 0)
    assert (by_source["recorded"]["nItems"], by_source["recorded"]["unsafeErrors"]) == (1, 1)
    assert [entry["source"] for entry in report["items"]] == ["synthetic_tts", "recorded"]
    assert "| Recorded human voices | 1 | 1 |" in render_markdown(report, rows, meta())


def test_by_voice_splits_gemini_voices_from_another_vendor_and_from_people():
    """17 Oct: the judges are Gemini, so Gemini-voiced items share their model family; Sarvam-voiced ones do not."""
    def r(item_id: str, pred: str, source: str = "synthetic_tts") -> Row:
        return Row(item_id=item_id, task_id="lifting-zone", worker_lang="ta", pattern="complete", noise="clean",
                   step_id="s1", gold="missed", pred=pred, any_covered=pred == "covered", source=source)

    rows = [r("g1", "missed"), r("g2", "missed"), r("s1", "covered"), r("h1", "unclear", "recorded")]
    base = {"taskId": "lifting-zone", "workerLang": "ta", "pattern": "complete", "noise": "clean"}
    items = [{"id": "g1", **base, "voice": "Kore"}, {"id": "g2", **base},
             {"id": "s1", **base, "voice": "sarvam/bulbul:v4-flash/vijay_ta_narration"},
             {"id": "h1", **base, "source": "recorded", "voice": "sarvam/looks-like-a-vendor"}]

    report = build_report(rows, items, meta())

    voices = report["byVoice"]
    assert set(voices) == {"gemini", "otherVendor", "recorded"}
    assert [(voices[g]["nItems"], voices[g]["unsafeErrors"]) for g in ("gemini", "otherVendor", "recorded")] == [
        (2, 0), (1, 1), (1, 0)]
    md = render_markdown(report, rows, meta())
    assert "| Gemini TTS voices | 2 |" in md and "| Another vendor's TTS voices (Sarvam) | 1 |" in md
    assert md.index("Gemini TTS voices |") < md.index("Recorded human voices |")
    old = {k: v for k, v in report.items() if k != "byVoice"}  # a report written before 17 Oct
    assert "Gemini TTS voices |" not in render_markdown(old, rows, meta())


def test_each_item_carries_its_original_and_its_ratings_with_only_the_fields_they_have():
    long_reason = "x" * (REPORT_TEXT_MAX + 50)
    rows = [Row(item_id="a", task_id="lifting-zone", worker_lang="ta", pattern="complete", noise="clean",
                step_id="s1", gold="covered", pred="covered", any_covered=True, original="நான் சொன்னது",
                rating=RunRating("s1", "covered", quote="சொன்னது", quote_translation="said", reason="stated")),
            Row(item_id="a", task_id="lifting-zone", worker_lang="ta", pattern="complete", noise="clean",
                step_id="s2", gold="missed", pred="unclear", any_covered=False, original="நான் சொன்னது",
                rating=RunRating("s2", "unclear", reason=long_reason, flags=("quote_not_found",))),
            Row(item_id="a", task_id="lifting-zone", worker_lang="ta", pattern="complete", noise="clean",
                step_id="s3", gold="missed", pred="unclear", any_covered=False, flags=("not_rated",))]
    items = [{"id": "a", "taskId": "lifting-zone", "workerLang": "ta", "pattern": "complete", "noise": "clean"}]

    (entry,) = build_report(rows, items, meta())["items"]

    assert entry["original"] == "நான் சொன்னது"
    assert entry["ratings"][0] == {"stepId": "s1", "verdict": "covered", "quote": "சொன்னது", "quoteTranslation": "said",
                                   "reason": "stated"}
    assert entry["ratings"][1]["flags"] == ["quote_not_found"] and "quote" not in entry["ratings"][1]
    assert len(entry["ratings"][1]["reason"]) == REPORT_TEXT_MAX and entry["ratings"][1]["reason"].endswith("…")
    assert [r["stepId"] for r in entry["ratings"]] == ["s1", "s2"]  # s3 got no rating in the first run


def test_the_markdown_shows_the_v05_numbers():
    report = four_report(baseline={"keyword": FOUR, "keywordNegation": FOUR})

    markdown = render_markdown(report, FOUR, meta())

    assert "correct passes 50.0% (bar 75.0%)" in markdown
    assert "## Held-out tasks, the model alone, and a keyword baseline" in markdown
    for label in ("| In-set tasks |", "| Held-out tasks |", "| Model only (no silence or wrong_language) |",
                  "| Keyword baseline |", "| Keyword + negation baseline |"):
        assert label in markdown
    assert "items.json SHA-256 abababababab" in markdown
