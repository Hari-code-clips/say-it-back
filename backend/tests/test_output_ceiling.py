"""Every Flash call and every TTS call has an output ceiling (API.md, "Daily cap"):
`SIB_MAX_OUTPUT_TOKENS`, thinking tokens included. What happens to a reply that hits it:
test_cut_off_replies.py (Flash) and test_tts_binding.py (TTS)."""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent
from google.genai import types

from sayitback.agents.back_translate import agent as back_translate
from sayitback.agents.briefer_live import agent as briefer_live
from sayitback.agents.check_answer import agent as check_answer
from sayitback.agents.extract_steps import agent as extract_steps
from sayitback.agents.hazard_report import agent as hazard_report
from sayitback.agents.re_explain import agent as re_explain
from sayitback.agents.transcribe_instruction import agent as transcribe_instruction
from sayitback.agents.write_script import agent as write_script
from sayitback.llm_schemas import (
    BackOut,
    ExtractOut,
    JudgeOut,
    ReExplainOut,
    ScriptOut,
    SpokenText,
    TranscribeOut,
)
from sayitback.runtime import Runtime
from sayitback.settings import DEFAULT_THINKING
from sayitback.tts import Tts
from tests.cap_support import script_for_open_steps
from tests.check_support import check
from tests.fakes import FakeTtsClient, fake_runtime, tone_wav
from tests.flow_support import round_1_scenario
from tests.helpers import api_client, drive_to_round, graph_nodes, make_app, post_check
from tests.test_check_workflow_guarantees import wire_runtime

CEILING = 3000  # not the default, so a hard-coded 8192 would show


def flash_agents(rt: Runtime) -> dict[str, LlmAgent]:
    """The nine Flash agents the service runs, by name: six phases and the check's three nodes."""
    phase_modules = (
        extract_steps,
        write_script,
        back_translate,
        re_explain,
        transcribe_instruction,
        hazard_report,
    )
    agents = {m.NAME: m.build_agent(rt) for m in phase_modules}
    nodes = graph_nodes(check_answer.build_agent(rt))
    return agents | {n: nodes[n] for n in ("blind_transcriber", "judge_a", "judge_b")}


class TestEveryFlashCallHasTheCeiling:
    def test_each_flash_agent_is_built_with_the_ceiling_and_keeps_its_thinking_level(
        self, settings
    ):
        rt, _ = fake_runtime(settings=settings.with_overrides(max_output_tokens=CEILING))
        agents = flash_agents(rt)

        assert set(agents) == set(DEFAULT_THINKING)  # all nine, and no agent left out
        for name, agent in agents.items():
            config = agent.generate_content_config
            assert config.max_output_tokens == CEILING, name
            level = types.ThinkingLevel(DEFAULT_THINKING[name].upper())
            assert config.thinking_config.thinking_level == level, name

    def test_the_default_ceiling_is_8192(self, settings):
        rt, _ = fake_runtime(settings=settings)
        assert {a.generate_content_config.max_output_tokens for a in flash_agents(rt).values()} == {
            8192
        }

    def test_every_request_of_a_whole_briefing_carries_it(self, settings):
        """transcribe, extract, round 1, a check and a re-explain round with no note: ten Flash
        requests, one for each kind of output schema."""
        scenario = round_1_scenario()
        app, _rt, llm, _store = make_app(
            settings.with_overrides(max_output_tokens=CEILING), scenario
        )
        client = api_client(app)
        clip = {"audio": ("a.wav", tone_wav(), "audio/wav")}
        assert client.post("/api/transcribe", files=clip, data={"lang": "en"}).status_code == 200
        bid = drive_to_round(client)[0]
        assert post_check(client, bid, 1).status_code == 200
        script_for_open_steps(scenario)
        assert client.post(f"/api/briefings/{bid}/rounds", json={}).status_code == 200

        assert len(llm.seen) == 10
        assert {s.max_output_tokens for s in llm.seen} == {CEILING}
        assert {s.schema for s in llm.seen} == {
            ExtractOut,
            ScriptOut,
            BackOut,
            ReExplainOut,
            SpokenText,
            TranscribeOut,
            JudgeOut,
        }

    async def test_neither_the_tts_call_nor_the_live_briefer_sends_it(self, settings):
        """Agent Platform's TTS answers 400 INVALID_ARGUMENT to any request with max_output_tokens
        (probed 15 Oct 2026), so the TTS config never carries it; the script's line limits bound it."""
        rt, _ = fake_runtime(settings=settings.with_overrides(max_output_tokens=CEILING))
        assert briefer_live.build_agent(rt).generate_content_config is None
        tts_client = FakeTtsClient()
        rt, _ = fake_runtime(
            settings=settings.with_overrides(max_output_tokens=CEILING), tts_client=tts_client
        )
        await Tts(rt).speak("hello")
        assert tts_client.calls[0]["config"].max_output_tokens is None

    async def test_the_real_client_puts_it_on_the_wire_for_every_check_request(self, settings):
        bodies: list[dict[str, Any]] = []
        rt = wire_runtime(settings.with_overrides(max_output_tokens=CEILING), bodies)

        await check(rt)

        assert len(bodies) == 3  # the transcriber and both judges
        for body in bodies:
            assert body["generationConfig"]["maxOutputTokens"] == CEILING
            levels = set(body["generationConfig"]["thinkingConfig"].values())
            assert levels <= {"LOW", "MEDIUM"}  # the thinking level is still sent, next to it
