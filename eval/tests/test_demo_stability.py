"""demo_stability.py with a fake check: no backend, no model, no network, and the call log is a temp file.

The fake knows each item by its stand-in clip (one small unique WAV per item, as in test_run_eval.py) and scripts each
step's verdict per run, so the counts, the exit code on a false pass, the dry run and the budget refusals are exact.
"""

import hashlib
import io
import json
import wave
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from sayitback.errors import UpstreamError

import demo_stability
import gemini_client
import items_io
from catalog_io import load_catalog
from items_io import audio_path, file_sha256, load_items

LEAD_R1 = "lifting-zone.q1.ta.demo.clean.r1"  # the lead hard case: gold s1 contradicted, s2 missed
Q2_R1, Q3_R1 = "lifting-zone.q2.ta.demo.clean.r1", "lifting-zone.q3.ta.demo.clean.r1"
SG_LEAD = [f"lifting-zone.{q}.ta.demo.clean.r{r}" for r in (1, 2) for q in ("q1", "q2", "q3")]
DAY = date(2026, 10, 17)
FLASH, LITE = "gemini-3.8-flash", "gemini-3.1-flash-lite"
PRIOR_LINES = 5  # lines already in the (temp) call log
DEFAULT_CALLS = 6 * 10 * 3  # sg-lead's 6 stored answers x 10 runs x (transcriber + judge A + judge B)

Verdict = Callable[[str, str, int], str]


@pytest.fixture(autouse=True)
def call_log(tmp_path, monkeypatch) -> Path:
    """No test can reach a model: the real check is replaced by a failure and the key is removed. The call log and the
    default report folder are temp paths, the retry wait is 0, and the settings behind the call count are pinned."""

    def real_check() -> None:
        raise AssertionError("a test must never build the real check")

    monkeypatch.setattr(demo_stability, "backend_run_check", real_check)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("SIB_EVAL_CALL_BUDGET", raising=False)
    for name, value in (("SIB_JUDGE_PASSES", "2"), ("SIB_FLASH_MODEL", FLASH), ("SIB_JUDGE_B_MODEL", LITE)):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(demo_stability, "RETRY_WAIT_S", 0.0)
    monkeypatch.setattr(demo_stability, "STABILITY_DIR", tmp_path / "default-reports")
    log = tmp_path / "calls.log"
    log.write_text("".join(f"earlier call {n}\n" for n in range(1, PRIOR_LINES + 1)), encoding="utf-8")
    monkeypatch.setattr(gemini_client, "CALL_LOG_PATH", log)
    return log


def budget(monkeypatch, cap: int) -> None:
    """SIB_EVAL_CALL_BUDGET as a paid run sets it: in the environment, and so in the build's cap."""
    monkeypatch.setenv("SIB_EVAL_CALL_BUDGET", str(cap))
    monkeypatch.setattr(gemini_client, "GEMINI_CALL_BUDGET", cap)


def _wav(n: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(n.to_bytes(2, "little", signed=True) * 160)
    return buffer.getvalue()


@pytest.fixture
def stand_in(tmp_path, monkeypatch) -> dict:
    """Every item gets a unique stand-in clip and a manifest entry that makes it current."""
    doc = load_items()
    clips = {}
    for n, item in enumerate(doc["items"], start=1):
        path = tmp_path / item["audio"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_wav(n))
        clips[item["id"]] = {"text": item["answer"], "voice": item["voice"], "model": "stand-in",
                             "sha256": file_sha256(path)}
    monkeypatch.setattr(items_io, "TESTSET_DIR", tmp_path)
    monkeypatch.setattr(demo_stability, "load_items", lambda: doc)
    monkeypatch.setattr(demo_stability, "load_clip_manifest", lambda: clips)
    return doc


class Judge:
    """A fake check. It rates each payload step verdict(item id, step id, n), n counting that item's calls from 1 (a
    retry is a call; a None verdict leaves the step unrated), or raises what fail(item id, n) returns."""

    def __init__(self, doc: dict, verdict: Verdict, fail: Callable[[str, int], BaseException | None] | None = None):
        self.by_clip = {audio_path(item).read_bytes(): item["id"] for item in doc["items"]}
        self.verdict, self.fail, self.calls = verdict, fail, Counter()

    def __call__(self, *, steps: list[dict], questions: list[dict], clips: dict[str, bytes], worker_lang: str,
                 supervisor_lang: str) -> dict:
        (clip,) = clips.values()
        item_id = self.by_clip[clip]
        self.calls[item_id] += 1
        n = self.calls[item_id]
        problem = self.fail(item_id, n) if self.fail else None
        if problem is not None:
            raise problem
        ratings = []
        for step in steps:
            verdict = self.verdict(item_id, step["id"], n)
            if verdict is not None:
                ratings.append({"stepId": step["id"], "verdict": verdict, "quote": "q", "reason": "r",
                                "flags": ["passes_disagreed"] if verdict == "unclear" else []})
        return {"ratings": ratings, "passB": True, "modelIds": {"transcribe": FLASH, "judge_a": FLASH, "judge_b": LITE},
                "transcripts": [{"questionId": questions[0]["id"], "original": f"heard {n % 2}", "translation": "t"}]}


def as_gold(doc: dict) -> Verdict:
    gold = {item["id"]: item["gold"] for item in doc["items"]}
    return lambda item_id, step_id, n: gold[item_id][step_id]


def read(out: Path, stem: str = "2026-10-17") -> tuple[dict, str]:
    return (json.loads((out / f"{stem}.json").read_text(encoding="utf-8")),
            (out / f"{stem}.md").read_text(encoding="utf-8"))


def by_step(report: dict) -> dict[tuple[str, str], dict]:
    return {(entry["id"], step["stepId"]): step for entry in report["items"] for step in entry["steps"]}


def test_the_default_run_checks_each_sg_lead_answer_ten_times_and_counts_every_label(stand_in, tmp_path, monkeypatch):
    gold = as_gold(stand_in)

    def verdict(item_id: str, step_id: str, n: int) -> str:
        if (item_id, step_id) == (LEAD_R1, "s2"):  # gold missed: Ask again on runs 3, 6 and 9, else Missed
            return "unclear" if n % 3 == 0 else "missed"
        if (item_id, step_id) == (Q2_R1, "s3"):  # gold covered: Ask again on runs 4 and 8 (a cost, not a false pass)
            return "unclear" if n in (4, 8) else "covered"
        if (item_id, step_id, n) == (Q3_R1, "s4", 5):  # no rating at all: Ask again, never Got it
            return None
        return gold(item_id, step_id, n)

    judge, out = Judge(stand_in, verdict), tmp_path / "r"
    budget(monkeypatch, PRIOR_LINES + DEFAULT_CALLS)

    code = demo_stability.main([], run_check=judge, out_dir=out, today=DAY)

    report, md = read(out)
    steps = by_step(report)
    assert code == 0 and report["verdict"] == "pass" and report["complete"] is True and report["falsePasses"] == 0
    assert report["itemIds"] == SG_LEAD and dict(judge.calls) == dict.fromkeys(SG_LEAD, 10)
    assert (report["repeat"], report["checksRun"], report["goldMissSteps"]) == (10, 60, 3)
    assert (report["callsLogged"], report["logLines"]) == (DEFAULT_CALLS, PRIOR_LINES + DEFAULT_CALLS)
    s2 = steps[(LEAD_R1, "s2")]
    assert s2["counts"] == {"covered": 0, "missed": 7, "contradicted": 0, "unclear": 3}
    assert s2["sequence"] == ["missed", "missed", "unclear"] * 3 + ["missed"]
    assert s2["flags"] == {"passes_disagreed": 3} and not s2["stable"] and not s2["falsePass"]
    assert steps[(LEAD_R1, "s1")]["counts"] == {"covered": 0, "missed": 0, "contradicted": 10, "unclear": 0}
    assert steps[(LEAD_R1, "s1")]["stable"] and steps[(LEAD_R1, "s1")]["flags"] == {}
    assert steps[(Q2_R1, "s3")]["counts"] == {"covered": 8, "missed": 0, "contradicted": 0, "unclear": 2}
    assert not steps[(Q2_R1, "s3")]["falsePass"]
    assert steps[(Q3_R1, "s4")]["counts"] == {"covered": 0, "missed": 0, "contradicted": 9, "unclear": 1}
    assert steps[(Q3_R1, "s4")]["sequence"][4] == "unclear" and steps[(Q3_R1, "s4")]["flags"] == {"not_rated": 1}
    lead = next(entry for entry in report["items"] if entry["id"] == LEAD_R1)
    assert lead["clipSha256"] == file_sha256(audio_path(next(i for i in stand_in["items"] if i["id"] == LEAD_R1)))
    assert (lead["runs"], lead["distinctTranscripts"], lead["demo"]) == (10, 2, {"script": "sg-lead", "round": 0})
    assert report["settings"]["thinking"].keys() == {"blind_transcriber", "judge_a", "judge_b"}
    assert report["models"] == {"flash": FLASH, "judgeB": LITE} and report["promptVersion"]
    assert md.splitlines()[2] == "> PASS: no gold-miss step was rated Got it in 60 checks (6 items x 10 runs)."
    assert "| Item | Step | Gold | Got it | Missed | Wrong | Ask again | Result |" in md
    assert f"| {LEAD_R1} | s2 | missed | 0 | 7 | 0 | 3 | varies |" in md
    assert f"| {LEAD_R1} | s1 | contradicted | 0 | 0 | 10 | 0 | same every run |" in md
    assert f"| {Q2_R1} | s3 | covered | 8 | 0 | 0 | 2 | varies |" in md
    assert f"- {Q3_R1} s4: not_rated 1" in md


def test_one_got_it_on_a_gold_miss_in_ten_runs_blocks_the_release(stand_in, tmp_path, monkeypatch):
    gold = as_gold(stand_in)
    verdict: Verdict = lambda i, s, n: "covered" if (i, s, n) == (LEAD_R1, "s1", 4) else gold(i, s, n)  # noqa: E731
    out = tmp_path / "r"
    budget(monkeypatch, PRIOR_LINES + DEFAULT_CALLS)

    code = demo_stability.main([], run_check=Judge(stand_in, verdict), out_dir=out, today=DAY)

    report, md = read(out)
    s1 = by_step(report)[(LEAD_R1, "s1")]
    assert code == demo_stability.EXIT_FALSE_PASS == 1
    assert report["verdict"] == "blocked" and report["complete"] is True and report["falsePasses"] == 1
    assert s1["falsePass"] and s1["counts"] == {"covered": 1, "missed": 0, "contradicted": 9, "unclear": 0}
    assert sum(step["falsePass"] for step in by_step(report).values()) == 1
    assert md.splitlines()[2] == (f"> BLOCKED: 1 false pass, a gold-miss step rated Got it: {LEAD_R1} s1 (gold "
                                  "contradicted) in 1 of 10 runs. Do not release.")
    assert f"| {LEAD_R1} | s1 | contradicted | 1 | 0 | 9 | 0 | FALSE PASS |" in md


def test_dry_run_prints_the_plan_and_makes_no_call_even_without_the_budget(stand_in, tmp_path, call_log, capsys):
    judge, before = Judge(stand_in, as_gold(stand_in)), call_log.read_bytes()

    code = demo_stability.main(["--dry-run"], run_check=judge, out_dir=tmp_path / "r", today=DAY)

    printed = capsys.readouterr().out
    assert code == 0 and not judge.calls and call_log.read_bytes() == before and not (tmp_path / "r").exists()
    assert ("dry run: 6 items x 10 runs = 60 checks x 3 model calls (blind_transcriber + judge_a + judge_b) = "
            f"{DEFAULT_CALLS} model calls; none made") in printed
    assert all(item_id in printed for item_id in SG_LEAD)
    assert f"gemini_calls.log: {PRIOR_LINES} lines now, {PRIOR_LINES + DEFAULT_CALLS} after this run" in printed
    assert "SIB_EVAL_CALL_BUDGET is not set: a real run refuses to start" in printed


def test_a_real_run_refuses_to_start_without_the_budget_set(stand_in, tmp_path, call_log, monkeypatch, capsys):
    monkeypatch.setattr(gemini_client, "GEMINI_CALL_BUDGET", 10_000)  # a default cap that fits: only the unset variable
    judge, before = Judge(stand_in, as_gold(stand_in)), call_log.read_bytes()

    code = demo_stability.main([], run_check=judge, out_dir=tmp_path / "r", today=DAY)

    err = capsys.readouterr().err
    assert code == demo_stability.EXIT_NO_VERDICT == 2
    assert not judge.calls and call_log.read_bytes() == before and not (tmp_path / "r").exists()
    assert "SIB_EVAL_CALL_BUDGET is not set" in err and f"at least {PRIOR_LINES + DEFAULT_CALLS}" in err
    assert "Nothing was called." in err


def test_a_budget_one_line_short_of_the_plan_is_refused_and_an_exact_one_runs(stand_in, tmp_path, call_log,
                                                                              monkeypatch, capsys):
    judge, before = Judge(stand_in, as_gold(stand_in)), call_log.read_bytes()
    budget(monkeypatch, PRIOR_LINES + DEFAULT_CALLS - 1)

    refused = demo_stability.main([], run_check=judge, out_dir=tmp_path / "r", today=DAY)

    assert refused == 2 and not judge.calls and call_log.read_bytes() == before
    assert "too low" in capsys.readouterr().err
    budget(monkeypatch, PRIOR_LINES + DEFAULT_CALLS)
    assert demo_stability.main([], run_check=judge, out_dir=tmp_path / "r", today=DAY) == 0
    assert len(call_log.read_text(encoding="utf-8").splitlines()) == PRIOR_LINES + DEFAULT_CALLS


def test_each_check_is_logged_before_it_runs_one_line_per_model_call(stand_in, tmp_path, call_log, monkeypatch):
    gold, seen = as_gold(stand_in), []

    def verdict(item_id: str, step_id: str, n: int) -> str:  # runs inside the check: its lines must be in the log
        seen.append(gemini_client.logged_call_count())
        return gold(item_id, step_id, n)

    budget(monkeypatch, 1000)

    code = demo_stability.main(["--items", LEAD_R1, "--repeat", "2"], run_check=Judge(stand_in, verdict),
                               out_dir=tmp_path / "r", today=DAY)

    fields = [line.split("\t") for line in call_log.read_text(encoding="utf-8").splitlines()[PRIOR_LINES:]]
    clip = audio_path(next(item for item in stand_in["items"] if item["id"] == LEAD_R1)).read_bytes()
    assert code == 0 and seen == [PRIOR_LINES + 3] * 2 + [PRIOR_LINES + 6] * 2  # two steps per check
    assert [f[1:4] for f in fields] == [[f"#{PRIOR_LINES + k}", "attempt=1", model]
                                        for k, model in enumerate([FLASH, FLASH, LITE] * 2, start=1)]
    assert {f[4] for f in fields} == {hashlib.sha256(clip).hexdigest()[:12]}
    assert [f[5] for f in fields] == [f"stability {LEAD_R1} run {n}/2 {agent}"
                                      for n in (1, 2) for agent in ("blind_transcriber", "judge_a", "judge_b")]


def test_a_retried_check_is_logged_again_and_a_check_that_would_pass_the_cap_never_starts(stand_in, tmp_path, call_log,
                                                                                          monkeypatch):
    flaky = Judge(stand_in, as_gold(stand_in),
                  fail=lambda item_id, n: UpstreamError("499 CANCELLED") if (item_id, n) == (LEAD_R1, 1) else None)
    budget(monkeypatch, PRIOR_LINES + DEFAULT_CALLS + 1)  # room for 60 checks and one line; the retry takes a check

    code = demo_stability.main([], run_check=flaky, out_dir=tmp_path / "r", today=DAY)

    report, md = read(tmp_path / "r")
    lines = call_log.read_text(encoding="utf-8").splitlines()
    assert code == 2 and report["verdict"] == "incomplete" and report["stopped"] == "budget"
    assert report["checksRun"] == 59 and report["callsLogged"] == DEFAULT_CALLS
    assert len(lines) == PRIOR_LINES + DEFAULT_CALLS  # whole checks only: the last needed 3 lines and 1 was left
    assert [line.split("\t")[2] for line in lines[PRIOR_LINES:PRIOR_LINES + 6]] == ["attempt=1"] * 3 + ["attempt=2"] * 3
    assert md.splitlines()[2].startswith("> NO VERDICT: 59 of 60 checks ran (the call budget ran out)")


def test_a_check_that_fails_twice_is_an_error_and_leaves_no_verdict(stand_in, tmp_path, monkeypatch):
    failing = Judge(stand_in, as_gold(stand_in),  # Q3_R1's run 3 is its calls 3 and 4 (the retry)
                    fail=lambda item_id, n: UpstreamError("boom") if item_id == Q3_R1 and n in (3, 4) else None)
    budget(monkeypatch, 1000)

    code = demo_stability.main([], run_check=failing, out_dir=tmp_path / "r", today=DAY)

    report, md = read(tmp_path / "r")
    runs = {entry["id"]: entry["runs"] for entry in report["items"]}
    assert code == 2 and report["verdict"] == "incomplete" and report["complete"] is False
    assert report["errors"] == [{"id": Q3_R1, "run": 3, "class": "UpstreamError", "message": "boom"}]
    assert runs == {**dict.fromkeys(SG_LEAD, 10), Q3_R1: 9} and failing.calls[Q3_R1] == 11
    assert "## Errors" in md and f"| {Q3_R1} | 3 | UpstreamError | boom |" in md


def test_ctrl_c_writes_the_finished_runs_and_a_false_pass_before_it_still_blocks(stand_in, tmp_path, monkeypatch):
    gold = as_gold(stand_in)
    stopped = Judge(stand_in, lambda i, s, n: "covered" if (i, s) == (LEAD_R1, "s2") else gold(i, s, n),
                    fail=lambda item_id, n: KeyboardInterrupt() if (item_id, n) == (Q2_R1, 2) else None)
    budget(monkeypatch, 1000)

    try:
        code = demo_stability.main([], run_check=stopped, out_dir=tmp_path / "r", today=DAY)
    except KeyboardInterrupt:
        pytest.fail("Ctrl-C escaped the run: the paid checks before it were not written")

    report, _ = read(tmp_path / "r")
    assert code == 1 and report["verdict"] == "blocked" and report["stopped"] == "interrupted"
    assert report["checksRun"] == 7 and report["falsePasses"] == 2  # round 1, then LEAD_R1's run 2
    assert by_step(report)[(LEAD_R1, "s2")]["counts"]["covered"] == 2


def test_script_and_items_choose_the_answers_and_unknown_names_stop_the_run(stand_in, tmp_path):
    catalog, judge = load_catalog(), Judge(stand_in, as_gold(stand_in))
    ids = lambda chosen: [item["id"] for item in chosen]  # noqa: E731

    assert ids(demo_stability.select_items(stand_in, catalog, None, None)) == SG_LEAD
    assert ids(demo_stability.select_items(stand_in, catalog, None, ["chennai-second"])) == [
        f"scaffold-harness.{q}.hi.demo.clean.r{r}" for r in (1, 2) for q in ("q1", "q2")]
    assert ids(demo_stability.select_items(stand_in, catalog, [Q3_R1, LEAD_R1, Q3_R1], None)) == [Q3_R1, LEAD_R1]
    with pytest.raises(demo_stability.Refused, match="unknown item ids: nope"):
        demo_stability.select_items(stand_in, catalog, ["nope"], None)
    with pytest.raises(SystemExit):
        demo_stability.parse_args(["--items", LEAD_R1, "--script", "sg-lead"])
    assert demo_stability.main(["--script", "sg-nope"], run_check=judge, out_dir=tmp_path / "r") == 2
    assert not judge.calls and not (tmp_path / "r").exists()


def test_a_stale_clip_stops_the_run_before_any_call(stand_in, tmp_path, monkeypatch, capsys):
    stale = {**demo_stability.load_clip_manifest()}
    stale[LEAD_R1] = {**stale[LEAD_R1], "text": "an older line"}
    monkeypatch.setattr(demo_stability, "load_clip_manifest", lambda: stale)
    judge = Judge(stand_in, as_gold(stand_in))
    budget(monkeypatch, 1000)

    code = demo_stability.main([], run_check=judge, out_dir=tmp_path / "r", today=DAY)

    assert code == 2 and not judge.calls and LEAD_R1 in capsys.readouterr().err


def test_a_second_run_the_same_day_never_overwrites_the_first(stand_in, tmp_path, monkeypatch):
    judge, out = Judge(stand_in, as_gold(stand_in)), tmp_path / "r"
    budget(monkeypatch, 1000)

    codes = [demo_stability.main(["--items", LEAD_R1, "--repeat", "1"], run_check=judge, out_dir=out, today=DAY)
             for _ in range(2)]

    first, md = read(out)
    assert codes == [0, 0] and judge.calls[LEAD_R1] == 2
    assert sorted(path.name for path in out.iterdir()) == ["2026-10-17-2.json", "2026-10-17-2.md",
                                                           "2026-10-17.json", "2026-10-17.md"]
    assert first["selection"] == {"items": [LEAD_R1]} and read(out, "2026-10-17-2")[0]["checksRun"] == 1
    assert "Fewer than the review's 10 runs per answer: not the release check." in md
