"""The HTTP API with the model layer replaced by fakes: the whole briefing, endpoint by endpoint."""

from __future__ import annotations

import re

import pytest

from tests.fakes import tone_wav, transcript
from tests.flow_support import (
    ANSWER_1,
    CAMEL,
    all_keys,
    make_env,
    round_1_scenario,
    round_2_answers,
)
from tests.helpers import PANEL, api_client, make_app, post_check


@pytest.fixture
def scenario():
    return round_1_scenario()


@pytest.fixture
def env(settings, scenario):
    return make_env(settings, scenario)


class TestWireShapes:
    def test_the_briefing_is_camel_case_with_the_documented_fields(self, settings):
        app, *_ = make_app(settings)
        body = api_client(app).post("/api/briefings", json=PANEL).json()
        assert re.fullmatch(r"b_[a-z2-7]{12}", body["id"])
        assert body["status"] == "draft" and body["stepsVersion"] == 0
        assert (
            body["steps"] == []
            and body["conflicts"] == []
            and body["rounds"] == []
            and body["latestVerdicts"] == {}
        )
        assert {"id", "siteId", "taskId", "sop", "supervisorLang", "workerLang", "instruction", "status", "steps", "stepsVersion",
                "conflicts", "rounds", "latestVerdicts", "promptVersion", "createdAt", "updatedAt"} <= set(body)  # fmt: skip
        assert (
            set(body["sop"]) == {"id", "version", "title", "text"}
            and body["sop"]["id"] == "SOP-EL-04"
        )
        assert body["createdAt"].endswith("Z") and "decision" not in body
        assert bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", body["createdAt"]))

    def test_every_key_on_the_wire_is_camel_case(self, env):
        env.client.post(f"/api/briefings/{env.bid}/rounds/1/live-session")
        post_check(env.client, env.bid, 1)
        briefing = env.client.get(f"/api/briefings/{env.bid}").json()
        keys = all_keys(briefing)
        assert keys and all(CAMEL.match(k) for k in keys), sorted(
            k for k in keys if not CAMEL.match(k)
        )
        assert {"stepIds", "backTranslation", "instructionBackTranslation", "stepMap", "passA", "passB", "nextAction",
                "modelIds", "timingsMs", "questionId", "detectedLang", "judgedAt", "createdAt"} <= keys  # fmt: skip

    def test_step_and_round_fields(self, env):
        steps = env.client.get(f"/api/briefings/{env.bid}").json()["steps"]
        assert [s["id"] for s in steps] == ["s1", "s2", "s3"]
        assert {"id", "text", "hazard", "essential", "source", "speakable"} <= set(steps[0])
        assert steps[2]["source"] == "sop" and steps[2]["sopQuote"].startswith(
            "Test the panel dead"
        )
        rnd = env.rnd
        assert (rnd["n"], rnd["kind"], rnd["stepIds"]) == (1, "initial", ["s1", "s2", "s3"])
        assert (
            rnd["transcripts"] == []
            and rnd["passA"] == []
            and rnd["ratings"] == []
            and rnd["delivery"] == []
        )
        assert (
            rnd["nextAction"] == "reexplain"
            and "judgedAt" not in rnd
            and "live" not in rnd
            and "mode" not in rnd
        )
        script = rnd["script"]
        assert script["instruction"].count("\n") == 2 and set(script["stepMap"]) == {
            "s1",
            "s2",
            "s3",
        }
        assert [q["id"] for q in script["questions"]] == ["q1", "q2"]
        assert script["questions"][0]["backTranslation"] and script["instructionBackTranslation"]
        assert set(rnd["modelIds"]) == {"script", "back_translate"}


class TestWorkflow:
    def test_extract_flags_the_sop_only_step_and_lists_conflicts(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        body = client.post(f"/api/briefings/{bid}/steps/extract").json()
        assert body["status"] == "steps_proposed" and body["stepsVersion"] == 0
        assert [s["source"] for s in body["steps"]] == ["instruction", "both", "sop"]
        assert body["conflicts"] == [
            {"stepId": "s3", "message": "The SOP also asks to prove the tester."}
        ]

    def test_confirming_bumps_the_steps_version_and_can_be_repeated_before_round_1(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        steps = client.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
        first = client.put(f"/api/briefings/{bid}/steps", json={"steps": steps}).json()
        steps[0]["text"] = "Isolate the supply and say so"
        second = client.put(f"/api/briefings/{bid}/steps", json={"steps": steps}).json()
        assert (first["status"], first["stepsVersion"], second["stepsVersion"]) == (
            "steps_confirmed",
            1,
            2,
        )
        assert second["steps"][0]["text"] == "Isolate the supply and say so"

    def test_re_extract_is_allowed_after_editing_the_instruction(self, settings):
        app, *_ = make_app(settings)
        client = api_client(app)
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        client.post(f"/api/briefings/{bid}/steps/extract")
        patched = client.patch(f"/api/briefings/{bid}", json={"instruction": "Do it differently."})
        assert (
            patched.json()["instruction"] == "Do it differently."
            and patched.json()["status"] == "steps_proposed"
        )
        assert client.post(f"/api/briefings/{bid}/steps/extract").status_code == 200

    def test_the_check_judges_a_round_and_updates_the_briefing(self, env):
        response = post_check(env.client, env.bid, 1)
        assert response.status_code == 200, response.text
        rnd = response.json()
        assert {r["stepId"]: r["verdict"] for r in rnd["ratings"]} == {
            "s1": "covered",
            "s2": "missed",
            "s3": "missed",
        }
        assert rnd["nextAction"] == "reexplain" and rnd["judgedAt"]
        assert rnd["mode"] == "turn" and rnd["delivery"] == []
        assert {t["questionId"] for t in rnd["transcripts"]} == {"q1", "q2"}
        assert len(rnd["passA"]) == len(rnd["passB"]) == 3
        assert {"script", "back_translate", "transcribe", "judge_a", "judge_b"} <= set(
            rnd["modelIds"]
        )
        assert {"transcribe", "judge_a", "judge_b", "check_total"} <= set(rnd["timingsMs"])
        briefing = env.client.get(f"/api/briefings/{env.bid}").json()
        assert briefing["status"] == "judged"
        assert briefing["latestVerdicts"] == {"s1": "covered", "s2": "missed", "s3": "missed"}

    def test_a_reexplain_round_covers_only_open_steps_and_continues_numbering(self, env):
        post_check(env.client, env.bid, 1)
        env.scenario.script = {**env.scenario.script, "step_map": [m for m in env.scenario.script["step_map"] if m["step_id"] != "s1"],
                               "questions": [{"text": "புதிய கேள்வி?", "step_ids": ["s2", "s3"]}]}  # fmt: skip
        rnd2 = env.client.post(
            f"/api/briefings/{env.bid}/rounds", json={"supervisorNote": "Lock it and test it."}
        ).json()
        assert (rnd2["n"], rnd2["kind"], rnd2["stepIds"], rnd2["supervisorNote"]) == (
            2,
            "reexplain",
            ["s2", "s3"],
            "Lock it and test it.",
        )
        assert [q["id"] for q in rnd2["script"]["questions"]] == ["q3"]
        assert set(rnd2["script"]["stepMap"]) == {"s2", "s3"}
        script_calls = [s for s in env.llm.seen if s.schema.__name__ == "ScriptOut"]
        assert (
            "Lock it and test it." in script_calls[-1].system
        )  # the supervisor's own words are the basis
        assert not any(s.schema.__name__ == "ReExplainOut" for s in env.llm.seen)

    def test_without_a_note_the_re_explain_agent_writes_the_basis(self, env):
        post_check(env.client, env.bid, 1)
        env.scenario.script = {**env.scenario.script, "step_map": [m for m in env.scenario.script["step_map"] if m["step_id"] != "s1"],
                               "questions": [{"text": "புதிய கேள்வி?", "step_ids": ["s2", "s3"]}]}  # fmt: skip
        rnd2 = env.client.post(f"/api/briefings/{env.bid}/rounds").json()
        assert "supervisorNote" not in rnd2
        assert any(s.schema.__name__ == "ReExplainOut" for s in env.llm.seen)
        assert (
            "Switch it off, lock it, and test it dead."
            in [s for s in env.llm.seen if s.schema.__name__ == "ScriptOut"][-1].system
        )
        assert "re_explain" in rnd2["modelIds"]

    def test_a_full_loop_ends_in_go_when_everything_is_covered(self, env):
        post_check(env.client, env.bid, 1)
        env.scenario.script = {**env.scenario.script, "step_map": [m for m in env.scenario.script["step_map"] if m["step_id"] != "s1"],
                               "questions": [{"text": "புதிய கேள்வி?", "step_ids": ["s2", "s3"]}]}  # fmt: skip
        env.client.post(f"/api/briefings/{env.bid}/rounds", json={"supervisorNote": "again"})
        round_2_answers(env.scenario)
        result = post_check(env.client, env.bid, 2, q3=tone_wav()).json()
        assert result["nextAction"] == "decide"
        briefing = env.client.get(f"/api/briefings/{env.bid}").json()
        assert briefing["latestVerdicts"] == {"s1": "covered", "s2": "covered", "s3": "covered"}
        decided = env.client.post(f"/api/briefings/{env.bid}/decision", json={"value": "go"})
        assert decided.status_code == 200 and decided.json()["decision"]["openStepIds"] == []


class TestRoundCap:
    def test_a_fourth_round_is_409_so_the_supervisor_verifies_by_demonstration(self, env):
        post_check(env.client, env.bid, 1)
        sc = env.scenario
        sc.script = {**sc.script, "step_map": [m for m in sc.script["step_map"] if m["step_id"] != "s1"],
                     "questions": [{"text": "புதிய கேள்வி?", "step_ids": ["s2", "s3"]}]}  # fmt: skip
        for n in (2, 3):
            assert (
                env.client.post(
                    f"/api/briefings/{env.bid}/rounds", json={"supervisorNote": "again"}
                ).status_code
                == 200
            )
            sc.transcripts = [transcript(f"q{n + 1}", ANSWER_1)]
            assert (
                post_check(env.client, env.bid, n, **{f"q{n + 1}": tone_wav()}).status_code == 200
            )
        fourth = env.client.post(f"/api/briefings/{env.bid}/rounds")
        assert fourth.status_code == 409 and "demonstration" in fourth.json()["error"]["message"]
        assert (
            env.client.post(
                f"/api/briefings/{env.bid}/decision", json={"value": "go", "reason": "demonstrated"}
            ).status_code
            == 200
        )
