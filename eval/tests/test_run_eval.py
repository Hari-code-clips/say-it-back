"""Runner wiring with an injected fake run_check. No backend and no Gemini calls are made."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

import run_eval
from config import AUDIO_DIR
from items_io import audio_path, load_items
from metrics import GOLD_MISS

Verdict = Callable[[bytes, str], str]


def _built() -> bool:
    return all(audio_path(item).exists() for item in load_items()["items"])


pytestmark = pytest.mark.skipif(not _built(), reason="testset audio incomplete; finish build_testset.py first")


def _fake(verdict: Verdict) -> Callable[..., dict]:
    def fake(*, steps: list[dict], questions: list[dict], clips: dict[str, bytes],
             worker_lang: str, supervisor_lang: str) -> dict:
        (clip,) = clips.values()
        ratings = [{"stepId": step["id"], "verdict": verdict(clip, step["id"]), "flags": [],
                    "quote": "quote", "reason": "reason"} for step in steps]
        return {"ratings": ratings, "passB": [], "modelIds": {"transcribe": "gemini-3.8-flash"}}

    return fake


def _gold_by_clip() -> dict[bytes, dict]:
    return {audio_path(item).read_bytes(): item["gold"] for item in load_items()["items"]}


def _read(out: Path, name: str) -> str:
    return (out / name).read_text(encoding="utf-8")


def test_a_perfect_judge_passes_and_writes_the_schema_keys(tmp_path):
    gold = _gold_by_clip()

    code = run_eval.main(["--lang", "ta"], run_check=_fake(lambda clip, sid: gold[clip][sid]), out_dir=tmp_path)

    report = json.loads(_read(tmp_path, "latest.json"))
    assert code == 0
    assert report["passBar"]["passed"] is True
    assert report["metrics"]["exactAccuracy"] == 1.0
    assert report["metrics"]["unsafeErrors"] == 0
    assert set(report["byLanguage"]) == {"ta"}
    assert {"generatedAt", "promptVersion", "models", "judgePasses", "nItems", "nStepRatings", "metrics",
            "passBar", "byLanguage", "byPattern", "items"} <= set(report)
    assert _read(tmp_path, "latest.md").startswith("# Say It Back eval report")


def test_a_judge_that_covers_everything_fails_and_lists_each_unsafe_item(tmp_path):
    code = run_eval.main(["--lang", "bn"], run_check=_fake(lambda clip, sid: "covered"), out_dir=tmp_path)

    report = json.loads(_read(tmp_path, "latest.json"))
    markdown = _read(tmp_path, "latest.md")
    unsafe_ids = [item["id"] for item in report["items"] if item["unsafe"]]
    assert code == 0
    assert report["passBar"]["passed"] is False
    assert report["metrics"]["unsafeErrors"] == report["metrics"]["unsafeDenominator"] > 0
    assert unsafe_ids and all(item_id in markdown for item_id in unsafe_ids)
    assert "None." not in markdown.split("## Unsafe errors")[1].split("## ")[0]


def test_dry_run_plans_the_run_without_calling_the_check(tmp_path, capsys):
    def never_called(**kwargs: object) -> dict:
        raise AssertionError("dry run must not call the check")

    code = run_eval.main(["--dry-run", "--limit", "3"], run_check=never_called, out_dir=tmp_path)

    assert code == 0
    assert "none made" in capsys.readouterr().out
    assert not (tmp_path / "latest.json").exists()


def test_repeats_mark_an_item_unsafe_when_any_run_covers_a_gold_miss(tmp_path):
    doc = load_items()
    seen: dict[tuple[bytes, str], int] = {}

    def first_misses_then_covers(clip: bytes, step_id: str) -> str:
        seen[(clip, step_id)] = seen.get((clip, step_id), 0) + 1
        return "missed" if seen[(clip, step_id)] == 1 else "covered"

    code = run_eval.main(["--lang", "my", "--repeat", "2"], run_check=_fake(first_misses_then_covers),
                         out_dir=tmp_path)

    report = json.loads(_read(tmp_path, "latest.json"))
    my_items = [item for item in doc["items"] if item["workerLang"] == "my"]
    gold_misses = sum(label in GOLD_MISS for item in my_items for label in item["gold"].values())
    assert code == 0
    assert report["judgePasses"] == 1
    assert report["nStepRatings"] == sum(len(item["gold"]) for item in my_items)
    assert report["metrics"]["unsafeErrors"] == gold_misses
    assert report["passBar"]["passed"] is False
