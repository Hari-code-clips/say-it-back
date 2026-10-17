"""The check as an ADK `Workflow` graph (API.md, "Check workflow"): its nodes and edges, what each
model call is sent, the one-judge path and the guard node. What the move off the deprecated
SequentialAgent and ParallelAgent must not change is in test_check_workflow_guarantees.py.
"""

from __future__ import annotations

import pytest
from google.adk.agents import LlmAgent
from google.adk.workflow import START, FunctionNode, JoinNode, Workflow
from google.genai import types

from sayitback import adk_run, demo
from sayitback.agents.check_answer.agent import NAME, build_agent
from sayitback.check_state import FINAL_KEY
from sayitback.guard_node import guard_event
from sayitback.guards import GuardConfig
from sayitback.llm_schemas import TranscribeOut
from sayitback.pipeline import CHECK_META_KEYS
from tests.check_support import (
    ANSWER,
    LEAD_ANSWER,
    PANEL,
    audio_parts,
    check,
    lead_scenario,
    requests_by_node,
    scenario,
)
from tests.fakes import Scenario, fake_runtime, rating, tone_wav, transcript
from tests.helpers import graph_edges, graph_nodes

START_NAME = START.name
TWO_JUDGE_EDGES = {
    (START_NAME, "blind_transcriber"),
    ("blind_transcriber", "judge_a"),
    ("blind_transcriber", "judge_b"),
    ("judge_a", "join_judges"),
    ("judge_b", "join_judges"),
    ("join_judges", "guard"),
}
ONE_JUDGE_EDGES = {
    (START_NAME, "blind_transcriber"),
    ("blind_transcriber", "judge_a"),
    ("judge_a", "guard"),
}


class TestGraph:
    def test_start_transcriber_fan_out_to_two_judges_join_then_the_guard(self, fake_rt):
        rt, _ = fake_rt
        root = build_agent(rt)
        assert isinstance(root, Workflow) and root.name == NAME == "check_answer"
        assert graph_edges(root) == TWO_JUDGE_EDGES
        nodes = graph_nodes(root)
        assert set(nodes) == {n for edge in TWO_JUDGE_EDGES for n in edge}
        assert [type(nodes[n]) for n in ("blind_transcriber", "judge_a", "judge_b")] == [
            LlmAgent
        ] * 3
        assert isinstance(nodes["join_judges"], JoinNode)
        assert isinstance(nodes["guard"], FunctionNode)

    def test_the_guard_is_the_only_end_of_the_graph(self, fake_rt):
        rt, _ = fake_rt
        root = build_agent(rt)
        sources = {a for a, _ in graph_edges(root)}
        assert set(graph_nodes(root)) - sources == {"guard"}

    def test_one_judge_pass_is_a_chain_without_judge_b_or_the_join(self, fake_rt):
        rt, _ = fake_rt
        root = build_agent(rt, passes=1)
        assert graph_edges(root) == ONE_JUDGE_EDGES
        assert set(graph_nodes(root)) == {START_NAME, "blind_transcriber", "judge_a", "guard"}

    def test_the_judge_passes_setting_picks_the_graph(self, settings):
        one, _ = fake_runtime(Scenario(), settings.with_overrides(judge_passes=1))
        two, _ = fake_runtime(Scenario(), settings)
        assert graph_edges(build_agent(one)) == ONE_JUDGE_EDGES
        assert graph_edges(build_agent(two)) == TWO_JUDGE_EDGES

    def test_every_model_node_is_named_in_the_pipelines_audit_keys(self, fake_rt):
        rt, _ = fake_rt
        models = {
            n for n, node in graph_nodes(build_agent(rt)).items() if isinstance(node, LlmAgent)
        }
        assert models == set(CHECK_META_KEYS) == {"blind_transcriber", "judge_a", "judge_b"}

    def test_the_module_level_root_agent_is_the_workflow_adk_web_loads(self):
        from sayitback.agents.check_answer.agent import root_agent

        assert isinstance(root_agent, Workflow) and root_agent.name == NAME
        assert graph_edges(root_agent) == TWO_JUDGE_EDGES

    @pytest.mark.filterwarnings("ignore:Accessing the 'model_fields' attribute:DeprecationWarning")
    def test_the_dev_ui_can_serialise_and_draw_the_graph(self, fake_rt):
        """What `adk web` serves at /dev/apps/check_answer/build_graph and build_graph_image.
        (ADK's own serializer reads `model_fields` off instances, a Pydantic 2.11 deprecation.)"""
        from google.adk.apps import App
        from google.adk.cli.utils.graph_serialization import serialize_app_info
        from google.adk.cli.utils.graph_visualization import plot_workflow_graph

        rt, _ = fake_rt
        info = serialize_app_info(App(name=NAME, root_agent=build_agent(rt)))
        dot = plot_workflow_graph({"root_agent": info["root_agent"]}, format="dot")
        assert {n["name"]: n["type"] for n in info["root_agent"]["graph"]["nodes"]} == {
            START_NAME: "start",
            "blind_transcriber": "agent",
            "judge_a": "agent",
            "judge_b": "agent",
            "join_judges": "join",
            "guard": "function",
        }
        assert all(f"{a} -> {b}" in dot for a, b in TWO_JUDGE_EDGES)


class TestWhatEachNodeIsSent:
    async def test_judge_a_gets_the_clip_once_and_judge_b_gets_no_audio_at_all(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        wav = tone_wav()
        await check(rt, wav)
        sent = requests_by_node(llm)
        assert set(sent) == {"blind_transcriber", "judge_a", "judge_b"}
        for node in ("blind_transcriber", "judge_a"):
            (clip,) = audio_parts(sent[node])  # exactly one copy, not the clip twice
            assert clip.inline_data.mime_type == "audio/wav" and clip.inline_data.data == wav
        assert audio_parts(sent["judge_b"]) == []
        assert ANSWER in sent["judge_b"].system  # B judges the blind transcript, in its instruction

    async def test_the_transcriber_request_has_no_step_text_question_or_essential(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        await check(rt)
        sent = requests_by_node(llm)["blind_transcriber"]
        everything = sent.system + "\n" + sent.text
        secrets = [
            *(s["text"] for s in demo.steps(PANEL)),
            *(s["hazard"] for s in demo.steps(PANEL)),
            *(e for s in demo.steps(PANEL) for e in s["essential"]),
            *(q["text"] for q in demo.questions(PANEL)),
        ]
        assert len(secrets) > 6
        assert [s for s in secrets if s in everything] == []

    async def test_judge_b_still_gets_no_audio_when_the_transcriber_returns_nothing(self, settings):
        """With no transcript to anchor on, ADK hands judge B the user's own message: the clips.
        The media strip is what keeps them out of its request."""
        rt, llm = fake_runtime(scenario(), settings)
        handler = llm.handler
        llm.handler = lambda seen: "" if seen.schema is TranscribeOut else handler(seen)
        result = await check(rt)
        sent = requests_by_node(llm)
        assert audio_parts(sent["judge_a"]) and audio_parts(sent["judge_b"]) == []
        assert {r.verdict for r in result.ratings} == {"unclear"}
        assert all("no_speech" in r.flags for r in result.ratings)

    async def test_the_judges_instructions_carry_the_steps_and_the_blind_transcript(self, settings):
        rt, llm = fake_runtime(scenario(), settings)
        await check(rt)
        for node in ("judge_a", "judge_b"):
            system = requests_by_node(llm)[node].system
            assert ANSWER in system and demo.steps(PANEL)[0]["text"] in system


class TestOneJudgePass:
    async def test_only_judge_a_runs(self, settings):
        rt, llm = fake_runtime(scenario(), settings.with_overrides(judge_passes=1))
        result = await check(rt)
        sent = requests_by_node(llm)
        assert set(sent) == {"blind_transcriber", "judge_a"} and len(llm.seen) == 2
        assert audio_parts(sent["judge_a"])
        assert result.pass_b == [] and len(result.pass_a) == 3
        assert set(result.model_ids) == {"transcribe", "judge_a"}
        assert set(result.timings_ms) == {"transcribe", "judge_a", "check_total"}
        assert [r.verdict for r in result.ratings] == ["covered", "missed", "missed"]

    async def test_a_judge_a_covered_is_still_guarded_by_its_quote(self, settings):
        sc = scenario()
        sc.judge_a[0] = rating("s1", "covered", "இது சொல்லவே இல்லை")
        rt, _ = fake_runtime(sc, settings.with_overrides(judge_passes=1))
        result = await check(rt)
        assert (
            result.ratings[0].verdict == "unclear" and "quote_not_found" in result.ratings[0].flags
        )


class TestTheGuardNode:
    def test_it_writes_the_final_ratings_and_a_summary_without_the_transcript(self):
        state = {
            "input": demo.check_input(PANEL),
            "transcribe_out": {"transcripts": [transcript("q1", ANSWER)]},
            "judge_a_out": {"ratings": scenario().judge_a},
            "judge_b_out": {"ratings": scenario().judge_a},
        }
        event = guard_event(state, GuardConfig(passes=2))
        final = event.actions.state_delta[FINAL_KEY]
        assert [r["verdict"] for r in final["ratings"]] == ["covered", "missed", "missed"]
        text = event.content.parts[0].text
        assert text.startswith("Guard rules applied. s1: covered;") and text.endswith("reexplain.")
        assert ANSWER not in text and event.content.role == "model"

    async def test_an_empty_session_runs_on_the_demo_task_as_it_does_in_adk_web(self, settings):
        """With no state, the workflow runs the lead demo (sg-lead): round 1's answer stands
        under the load and steadies it by hand."""
        rt, llm = fake_runtime(lead_scenario(), settings)
        run = await adk_run.run_phase(
            rt,
            build_agent(rt),
            app_name=NAME,
            phase_input={},
            parts=[types.Part.from_bytes(data=tone_wav(), mime_type="audio/wav")],
        )
        verdicts = {r["step_id"]: r["verdict"] for r in run.state[FINAL_KEY]["ratings"]}
        # Only q1 has a clip. s3 is asked by q2 alone, which was never answered: unclear, not
        # missed. s4's contradiction is quoted from q1, which was speech, so it stands (rule 5).
        assert verdicts == {
            "s1": "contradicted",
            "s2": "missed",
            "s3": "unclear",
            "s4": "contradicted",
        }
        assert len(llm.seen) == 3 and "q1" in requests_by_node(llm)["blind_transcriber"].system
        judge = requests_by_node(llm)["judge_a"].system
        assert LEAD_ANSWER in judge and "Never stand or walk under the load" in judge

    async def test_the_workflow_leaves_the_result_in_state_for_run_check(self, settings):
        rt, _ = fake_runtime(scenario(), settings)
        run = await adk_run.run_phase(
            rt,
            build_agent(rt),
            app_name=NAME,
            phase_input=demo.check_input(PANEL),
            parts=[types.Part.from_bytes(data=tone_wav(), mime_type="audio/wav")],
        )
        assert [r["verdict"] for r in run.state[FINAL_KEY]["ratings"]] == [
            "covered",
            "missed",
            "missed",
        ]
        assert set(run.audit.calls) == {"blind_transcriber", "judge_a", "judge_b"}
