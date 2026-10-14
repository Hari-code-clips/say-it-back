"""A reply cut off by the output ceiling (finish reason MAX_TOKENS: half-written JSON, only thinking,
or nothing at all) is 502 `upstream_error`: never a partial result, and no model content in the logs
or the error body. The ceiling itself: test_output_ceiling.py."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest
from google.genai import types

from sayitback import phases
from sayitback.adk_run import CUT_OFF_MESSAGE
from sayitback.errors import UpstreamError
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
from tests.cap_support import make_capped, new_briefing
from tests.check_support import check
from tests.check_support import scenario as judged_scenario
from tests.fakes import Reply, Scenario, fake_runtime, tone_wav, usage
from tests.flow_support import round_1_scenario
from tests.helpers import drive_to_round, error_of, post_check
from tests.test_phases import SOP, STEPS, script_for
from tests.wire_support import runtime_returning, wire_reply

MARKER = "WORDSTHEMODELWROTE"
AT_THE_CEILING = types.FinishReason.MAX_TOKENS


def half_written(ok: Any) -> Reply:
    return Reply(
        f'{{"text": "{MARKER} and then it was cut o', AT_THE_CEILING, usage(900, 7000, 292)
    )


def only_thinking(ok: Any) -> Reply:
    return Reply(f"{MARKER} thinking", AT_THE_CEILING, usage(900, 0, 8192), thought=True)


def nothing_at_all(ok: Any) -> Reply:
    return Reply(None, AT_THE_CEILING, usage(900, 0, 8192))


def complete_at_the_ceiling(ok: Any) -> Reply:
    """Valid JSON that happens to end exactly at the ceiling: the finish reason is all we have."""
    return Reply(ok, AT_THE_CEILING, usage(900, 200, 7092))


SHAPES = {
    "half-written JSON": half_written,
    "only thinking": only_thinking,
    "nothing at all": nothing_at_all,
    "complete JSON ending at the ceiling": complete_at_the_ceiling,
}


@dataclass(frozen=True)
class Phase:
    """One Flash call to cut off: how to run it, and which request is the one to cut."""

    run: Callable[[Runtime], Awaitable[object]]
    schema: type
    audio: bool | None = None  # the judges: A hears the clips, B does not
    in_check: bool = False

    def hit(self, seen: Any) -> bool:
        return seen.schema is self.schema and self.audio in (None, seen.has_audio)


async def extract(rt: Runtime) -> object:
    return await phases.extract_steps(rt, instruction="Isolate it.", supervisor_lang="en", sop=SOP)


async def explain(rt: Runtime) -> object:
    return await phases.explain(
        rt, steps=STEPS[1:], ratings={}, supervisor_lang="en", sop_title="Panel"
    )


async def transcribe(rt: Runtime) -> object:
    return await phases.transcribe_instruction(rt, tone_wav(), "en")


# In the check, ADK's Workflow carries on past a node that wrote nothing, and the guard then rates
# every step `unclear`: only the finish reason tells that apart from a real answer.
PHASES = {
    "extract": Phase(extract, ExtractOut),
    "script": Phase(script_for, ScriptOut),
    "back-translation": Phase(script_for, BackOut),
    "re-explain": Phase(explain, ReExplainOut),
    "transcribe the instruction": Phase(transcribe, SpokenText),
    "blind transcriber": Phase(check, TranscribeOut, in_check=True),
    "judge A": Phase(check, JudgeOut, audio=True, in_check=True),
    "judge B": Phase(check, JudgeOut, audio=False, in_check=True),
}


class TestACutOffReply:
    @pytest.mark.parametrize("shape", SHAPES.values(), ids=SHAPES)
    @pytest.mark.parametrize("phase", PHASES.values(), ids=PHASES)
    async def test_is_a_502_with_no_model_content_in_the_error_or_the_logs(
        self, settings, caplog, phase, shape
    ):
        base = judged_scenario() if phase.in_check else Scenario()
        rt, llm = fake_runtime(base, settings)

        def handler(seen):
            ok = base.handler(seen)
            return shape(ok) if phase.hit(seen) else ok

        llm.handler = handler

        with caplog.at_level(logging.DEBUG), pytest.raises(UpstreamError) as err:
            await phase.run(rt)

        assert (err.value.status, err.value.code) == (502, "upstream_error")
        assert err.value.body() == {"error": {"code": "upstream_error", "message": CUT_OFF_MESSAGE}}
        assert caplog.records  # the failure was logged ...
        assert MARKER not in caplog.text  # ... without a word the model wrote

    async def test_a_cut_off_script_is_not_retried(self, settings):
        """The retry is for a script that breaks a check; a reply that stopped mid-answer would
        likely stop again, and would cost the same again."""
        rt, llm = fake_runtime(Scenario(), settings)
        llm.handler = lambda seen: half_written(None)

        with pytest.raises(UpstreamError):
            await script_for(rt)

        assert [s.schema for s in llm.seen] == [ScriptOut]

    async def test_a_reply_that_stopped_normally_is_not_mistaken_for_one(self, settings, caplog):
        body = wire_reply([{"text": '{"explanation": "Do it safely."}'}], finish="STOP")
        rt = runtime_returning(settings, body)
        with caplog.at_level(logging.INFO):
            text, _ = await explain(rt)
        assert text == "Do it safely."


class TestACutOffReplyThroughTheApi:
    def test_a_cut_off_extract_is_a_502_and_the_briefing_stays_a_draft(self, settings, caplog):
        env = make_capped(settings)
        env.llm.handler = lambda seen: half_written(None)
        bid = new_briefing(env)

        with caplog.at_level(logging.DEBUG):
            response = env.client.post(f"/api/briefings/{bid}/steps/extract")

        assert error_of(response) == (502, "upstream_error")
        assert response.json()["error"]["message"] == CUT_OFF_MESSAGE
        assert MARKER not in response.text and MARKER not in caplog.text
        assert env.client.get(f"/api/briefings/{bid}").json()["status"] == "draft"
        assert env.ledger.spent == 1  # the call was made and billed: nothing is refunded

    def test_a_cut_off_judge_is_a_502_not_ratings_and_the_round_stays_unjudged(self, settings):
        scenario = round_1_scenario()
        env = make_capped(settings, scenario)
        bid = drive_to_round(env.client)[0]
        spent = env.ledger.spent

        def handler(seen):
            if seen.schema is JudgeOut and seen.has_audio:
                return nothing_at_all(None)
            return scenario.handler(seen)

        env.llm.handler = handler
        response = post_check(env.client, bid, 1)

        assert error_of(response) == (502, "upstream_error")
        body = env.client.get(f"/api/briefings/{bid}").json()
        assert body["status"] == "briefing" and body["rounds"][0]["ratings"] == []
        assert env.ledger.spent == spent + 3  # the whole check was reserved, and stays spent


class TestOnTheWireWithTheRealClient:
    """What Gemini sends when the ceiling is reached: the finish reason MAX_TOKENS, with half a JSON
    reply, with only thinking, or with no content at all. ADK turns the last into an error response;
    the first two it passes on as replies."""

    @pytest.mark.parametrize(
        "parts",
        [
            [{"text": f'{{"explanation": "{MARKER} and then it was cut o'}],
            [{"text": f"{MARKER} thinking", "thought": True}],
            None,
        ],
        ids=["half-written JSON", "only thinking", "nothing at all"],
    )
    async def test_is_a_502_and_the_call_is_still_logged_with_its_billed_thinking(
        self, settings, caplog, parts
    ):
        rt = runtime_returning(settings, wire_reply(parts, finish="MAX_TOKENS"))

        with caplog.at_level(logging.INFO), pytest.raises(UpstreamError) as err:
            await explain(rt)

        assert err.value.body()["error"] == {"code": "upstream_error", "message": CUT_OFF_MESSAGE}
        assert MARKER not in caplog.text
        usage_line = next(r.getMessage() for r in caplog.records if r.getMessage()[:6] == "usage ")
        assert (
            '"thinking_tokens": 8192' in usage_line
            and '"finish_reason": "MAX_TOKENS"' in usage_line
        )
