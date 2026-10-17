"""checkpoint.py: the run's progress file, on temp files."""

import json

import pytest

import checkpoint

SETTINGS = {"promptVersion": "p", "models": {"flash": "f", "judgeB": "b"}, "judgePasses": 2,
            "thinking": {"blind_transcriber": "low", "judge_a": "medium", "judge_b": "medium"},
            "testsetSha256": "ab", "repeat": 1}
RUN = {"ratings": {"s1": {"verdict": "covered"}}, "passB": True, "modelIds": {}, "transcripts": {}, "originals": {}}


def test_each_finished_item_is_one_line_and_errors_are_not_reused(tmp_path):
    path = tmp_path / "progress.jsonl"
    checkpoint.append(path, "a", SETTINGS, runs=[RUN])
    checkpoint.append(path, "b", SETTINGS, error={"class": "UpstreamError", "message": "499"})

    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert checkpoint.load(path, SETTINGS) == {"a": [RUN]}


def test_a_line_cut_off_by_a_crash_is_skipped_but_a_broken_middle_line_stops_the_resume(tmp_path):
    path = tmp_path / "progress.jsonl"
    checkpoint.append(path, "a", SETTINGS, runs=[RUN])
    with path.open("a", encoding="utf-8") as out:
        out.write('{"itemId": "b", "settin')

    assert checkpoint.load(path, SETTINGS) == {"a": [RUN]}
    path.write_text('{"broken\n' + json.dumps({"itemId": "a", "settings": SETTINGS, "runs": [RUN]}) + "\n",
                    encoding="utf-8")
    with pytest.raises(checkpoint.ResumeRefused, match="line 1 is not JSON"):
        checkpoint.load(path, SETTINGS)


def test_other_settings_are_refused_and_named(tmp_path):
    path = tmp_path / "progress.jsonl"
    checkpoint.append(path, "a", SETTINGS, runs=[RUN])
    other = {**SETTINGS, "thinking": {**SETTINGS["thinking"], "judge_b": "low"}, "testsetSha256": "cd"}

    with pytest.raises(checkpoint.ResumeRefused) as refused:
        checkpoint.load(path, other)

    assert "thinking.judge_b" in str(refused.value) and "testsetSha256" in str(refused.value)
    assert "promptVersion" not in str(refused.value)


def test_no_progress_file_means_nothing_done(tmp_path):
    assert checkpoint.load(tmp_path / "progress.jsonl", SETTINGS) == {}
