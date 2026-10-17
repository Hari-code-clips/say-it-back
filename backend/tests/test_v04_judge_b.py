"""API v0.4, "Judge B on a second model": SIB_JUDGE_B_MODEL runs judge B, the round records the id
the API returned, and health names it."""

from __future__ import annotations

from google.adk.models import Gemini

from sayitback.agents.check_answer.agent import build_agent
from sayitback.llm_schemas import JudgeOut
from sayitback.main import create_app
from sayitback.runtime import Runtime
from sayitback.settings import Settings
from sayitback.store import LocalStore
from tests.check_support import check, scenario
from tests.fakes import FakeLlm, fake_runtime
from tests.helpers import api_client, drive_to_round, graph_nodes, make_app, post_check


def second_model(sc) -> FakeLlm:
    return FakeLlm(model="fake-lite", handler=sc.handler, version="fake-lite-002")


class TestTheSecondModel:
    async def test_judge_b_runs_on_its_own_model_and_judge_a_on_flash(self, settings):
        sc = scenario()
        lite = second_model(sc)
        rt, flash = fake_runtime(sc, settings, judge_b=lite)
        result = await check(rt)
        assert [s.schema for s in lite.seen] == [JudgeOut] and not lite.seen[0].has_audio
        assert sorted(s.schema.__name__ for s in flash.seen) == ["JudgeOut", "TranscribeOut"]
        assert result.model_ids["judge_b"] == "fake-lite-002"
        assert result.model_ids["judge_a"] == "fake-flash-001"

    def test_the_graph_node_holds_the_second_model_and_keeps_its_thinking_level(self, settings):
        sc = scenario()
        rt, flash = fake_runtime(sc, settings, judge_b=second_model(sc))
        nodes = graph_nodes(build_agent(rt))
        assert nodes["judge_b"].model is rt.judge_b and nodes["judge_a"].model is flash
        config = nodes["judge_b"].generate_content_config
        assert (
            config.thinking_config.thinking_level.value == rt.settings.thinking["judge_b"].upper()
        )

    def test_round_model_ids_name_the_returned_id(self, settings):
        sc = scenario()
        lite = second_model(sc)
        runtime, _ = fake_runtime(sc, settings, judge_b=lite)
        app = create_app(settings, runtime=runtime, store=LocalStore(settings.data_dir))
        client = api_client(app)
        bid, _ = drive_to_round(client)
        rnd = post_check(client, bid, 1).json()
        assert rnd["modelIds"]["judge_b"] == "fake-lite-002"
        assert rnd["modelIds"]["judge_a"] == "fake-flash-001"


class TestTheSetting:
    def test_the_default_is_flash_lite(self):
        s = Settings.from_env({})
        assert s.judge_b_model == "gemini-3.1-flash-lite" == s.judge_b_model_id

    def test_empty_means_the_flash_model(self):
        s = Settings.from_env({"SIB_JUDGE_B_MODEL": "", "SIB_FLASH_MODEL": "gemini-3.8-flash-001"})
        assert s.judge_b_model_id == "gemini-3.8-flash-001"

    def test_it_is_read_from_the_environment(self):
        assert (
            Settings.from_env({"SIB_JUDGE_B_MODEL": " other-model "}).judge_b_model_id
            == "other-model"
        )

    def test_the_production_runtime_builds_a_second_gemini_only_when_it_differs(self):
        rt = Runtime.from_settings(Settings())
        assert isinstance(rt.judge_b, Gemini) and rt.judge_b is not rt.flash
        assert (rt.flash.model, rt.judge_b.model) == ("gemini-3.8-flash", "gemini-3.1-flash-lite")
        same = Runtime.from_settings(Settings(judge_b_model=""))
        assert same.judge_b is same.flash

    def test_health_names_it(self, settings):
        app, *_ = make_app(settings.with_overrides(judge_b_model="gemini-x-lite"))
        assert api_client(app).get("/api/health").json()["models"]["judgeB"] == "gemini-x-lite"
        app, *_ = make_app(settings.with_overrides(judge_b_model=""))
        assert api_client(app).get("/api/health").json()["models"]["judgeB"] == "gemini-3.8-flash"
