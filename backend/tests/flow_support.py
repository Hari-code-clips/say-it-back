"""Shared pieces of the API flow tests: Tamil answers, scenarios and the app under test."""

from __future__ import annotations

import json
import re

import httpx

from tests.fakes import Scenario, rating, transcript
from tests.helpers import api_client, drive_to_round, make_app

ANSWER_1 = "நான் அதை ஆஃப் பண்ணிட்டு திறப்பேன்."
ANSWER_2 = "முதல்ல பிரேக்கரை ஆஃப் பண்ணுவேன், லாக் போட்டு டேக் மாட்டுவேன், டெஸ்டர் வச்சு செக் பண்ணுவேன்"
CAMEL = re.compile(r"^[a-z][A-Za-z0-9]*$")


def round_1_scenario() -> Scenario:
    return Scenario(
        transcripts=[transcript("q1", ANSWER_1)],
        judge_a=[
            rating("s1", "covered", "ஆஃப் பண்ணிட்டு"),
            rating("s2", "missed"),
            rating("s3", "missed"),
        ],
    )


def round_2_answers(scenario: Scenario) -> None:
    scenario.transcripts = [transcript("q3", ANSWER_2)]
    scenario.judge_a = [
        rating("s2", "covered", "லாக் போட்டு"),
        rating("s3", "covered", "டெஸ்டர் வச்சு செக் பண்ணுவேன்"),
    ]


def make_env(settings, scenario):
    """The app with a recording Chat webhook, driven to round 1; `env` in the test modules."""
    hooks = []
    transport = httpx.MockTransport(
        lambda r: (hooks.append(json.loads(r.content)), httpx.Response(200))[1]
    )
    s = settings.with_overrides(
        webhook_url="https://chat.googleapis.com/v1/spaces/X/messages?key=k&token=t",
        live_record_wait_s=0.3,
    )
    app, rt, llm, store = make_app(s, scenario, webhook_transport=transport)
    client = api_client(app)
    bid, rnd = drive_to_round(client)
    return type(
        "Env",
        (),
        {
            "client": client,
            "bid": bid,
            "rnd": rnd,
            "llm": llm,
            "hooks": hooks,
            "scenario": scenario,
            "store": store,
            "settings": s,
        },
    )


def all_keys(value, found=None):
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            if k not in (
                "stepMap",
                "latestVerdicts",
                "delivered",
                "heard",
                "modelIds",
                "timingsMs",
                "gold",
            ):
                all_keys(v, found)
    elif isinstance(value, list):
        for v in value:
            all_keys(v, found)
    return found
