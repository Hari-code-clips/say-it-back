"""Test helpers: build an app with fakes, drive a briefing through the API, multipart uploads."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient

from sayitback import catalog
from sayitback.caller import Caller, owner_hash
from sayitback.main import create_app
from sayitback.models import Briefing, Question, Round, Script, Sop, Step, new_briefing_id, now_iso
from sayitback.prompts import PROMPT_VERSION
from sayitback.settings import Settings
from sayitback.store import LocalStore, Store
from tests.fakes import PANEL_SCRIPT, Scenario, fake_runtime, tone_wav

ORIGIN = "http://localhost:5173"
DEVICE = "test-device-key-aaaaaaaaaaaa"  # a browser's key: 22 to 64 of A-Z a-z 0-9 _ -
OTHER_DEVICE = "other-device-key-bbbbbbbbbb"
CALLER = Caller(owner_hash(DEVICE), "203.0.113.7")  # for tests that call a service directly
SPOKEN = " ".join("\n".join(PANEL_SCRIPT["sentences"]).split())  # round 1's instruction, as spoken
PANEL = {
    "siteId": "sg",
    "taskId": "panel-isolation",
    "supervisorLang": "en",
    "workerLang": "ta",
    "instruction": "Isolate the breaker, lock it, and test it dead before you open the panel.",
}


def make_app(settings: Settings, scenario: Scenario | None = None, **kwargs: Any):
    runtime, llm = fake_runtime(
        scenario or Scenario(),
        settings,
        tts_client=kwargs.pop("tts_client", None),
        live=kwargs.pop("live", None),
    )
    store = kwargs.pop("store", None) or LocalStore(settings.data_dir)
    app = create_app(settings, runtime=runtime, store=store, **kwargs)
    return app, runtime, llm, store


def api_client(app: Any, device: str | None = DEVICE, **kwargs: Any) -> TestClient:
    """A TestClient that is one browser: it sends its device key on every request (API.md v0.3).
    `device=None` is a client with no key. `client=(host, port)` sets the socket peer."""
    headers = dict(kwargs.pop("headers", None) or {})
    if device is not None:
        headers.setdefault("X-SIB-Device", device)
    return TestClient(app, headers=headers, **kwargs)


def run_sync(coro: Any) -> Any:
    """Run a coroutine from sync test code, even inside a running event loop (in a thread)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def seed_round(
    store: Store, device: str = DEVICE, instruction: str | None = None, approved: bool = True
) -> str:
    """A briefing owned by `device`, at round 1 with the scenario's script (or with `instruction`
    as its spoken instruction), written straight into the store: no model call and no reservation,
    so a test of what a call costs spends nothing on its setup. The script is approved (API v0.4)
    unless `approved=False`. It has no record chain. Returns the briefing id."""
    now = now_iso()
    questions = [
        Question(id=f"q{i}", text=q["text"], step_ids=q["step_ids"])
        for i, q in enumerate(PANEL_SCRIPT["questions"], 1)
    ]
    script = Script(
        instruction=instruction or "\n".join(PANEL_SCRIPT["sentences"]),
        questions=questions,
        step_map={m["step_id"]: m["sentence_indices"] for m in PANEL_SCRIPT["step_map"]},
        closing=PANEL_SCRIPT["closing"],
    )
    steps = [Step.model_validate(s) for s in catalog.reference_steps("panel-isolation")]
    round_1 = Round(
        n=1,
        kind="initial",
        step_ids=[s.id for s in steps],
        script=script,
        created_at=now,
        approved_at=now if approved else None,
    )
    briefing = Briefing(
        id=new_briefing_id(),
        site_id=PANEL["siteId"],
        task_id=PANEL["taskId"],
        sop=Sop.model_validate(catalog.task(PANEL["taskId"])["sop"]),
        supervisor_lang=PANEL["supervisorLang"],
        worker_lang=PANEL["workerLang"],
        instruction=PANEL["instruction"],
        status="briefing",
        steps=steps,
        steps_version=1,
        rounds=[round_1],
        prompt_version=PROMPT_VERSION,
        created_at=now,
        updated_at=now,
    )
    run_sync(store.create({**briefing.wire(), "owner": owner_hash(device)}))
    return briefing.id


def drive_to_round(
    client: TestClient, body: dict[str, Any] | None = None, approve: bool = True
) -> tuple[str, dict[str, Any]]:
    """Create, extract, confirm and open round 1, and approve its script (API v0.4) unless
    `approve=False`. Returns (briefing id, round)."""
    created = client.post("/api/briefings", json=body or PANEL)
    assert created.status_code == 200, created.text
    bid = created.json()["id"]
    extracted = client.post(f"/api/briefings/{bid}/steps/extract")
    assert extracted.status_code == 200, extracted.text
    confirmed = client.put(f"/api/briefings/{bid}/steps", json={"steps": extracted.json()["steps"]})
    assert confirmed.status_code == 200, confirmed.text
    rnd = client.post(f"/api/briefings/{bid}/rounds", json={})
    assert rnd.status_code == 200, rnd.text
    if not approve:
        return bid, rnd.json()
    return bid, approve_round(client, bid, rnd.json()["n"])


def approve_round(client: TestClient, bid: str, n: int, by: str | None = None) -> dict[str, Any]:
    """The supervisor approves round `n`'s script (endpoint 23). Returns the round."""
    approved = client.post(f"/api/briefings/{bid}/rounds/{n}/approve", json={"by": by})
    assert approved.status_code == 200, approved.text
    return approved.json()


def check_files(**clips: bytes) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [(qid, (f"{qid}.wav", data, "audio/wav")) for qid, data in clips.items()]


def post_check(client: TestClient, bid: str, n: int, mode: str | None = None, **clips: bytes):
    files = check_files(**(clips or {"q1": tone_wav()}))
    data = {"meta": json.dumps({"mode": mode})} if mode else None
    return client.post(f"/api/briefings/{bid}/rounds/{n}/check", files=files, data=data)


def graph_nodes(workflow: Any) -> dict[str, Any]:
    """The nodes of an ADK Workflow by name (the START sentinel included)."""
    return {node.name: node for node in workflow.graph.nodes}


def graph_edges(workflow: Any) -> set[tuple[str, str]]:
    """The edges of an ADK Workflow as (from, to) node names."""
    return {(edge.from_node.name, edge.to_node.name) for edge in workflow.graph.edges}


def error_of(response) -> tuple[int, str]:
    """(status, code) of an error response, asserting the {"error": {"code", "message"}} shape."""
    body = response.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}
    return response.status_code, body["error"]["code"]
