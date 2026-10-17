"""2026-10-17, the in-person check (API.md Deviations; build-notes/38-in-person-check.md): a worker
who says "Not now" to the recording must never hold their own permit. While the latest round's
recorded consent is a decline, a Go is also allowed in `briefing`: the reason is always required,
every step of that round's scope is open, hazards still block it, and the decision carries
`inPerson: true`. No model call is made, the decline gates stay, and the chain binds the flag."""

from __future__ import annotations

import json

import pytest

from sayitback import chain
from sayitback import state_machine as sm
from sayitback.errors import InvalidState, Unprocessable
from sayitback.models import (
    Briefing,
    DecisionBody,
    Hazard,
    Question,
    Round,
    RoundConsent,
    Script,
    Sop,
    Step,
)
from sayitback.settings import Settings
from tests.fakes import FakeTtsClient, tone_wav
from tests.helpers import api_client, drive_to_round, error_of, make_app, post_check

S = Settings()
REASON = "Went through every step face to face; he showed me each one."
STEPS = ("s1", "s2", "s3")


def make_round(n: int, scope: list[str], *, given: bool | None, judged: bool = False) -> Round:
    script = Script(
        instruction="a", questions=[Question(id=f"q{n}", text="t", step_ids=scope)], closing="c"
    )
    return Round(
        n=n,
        kind="initial" if n == 1 else "reexplain",
        step_ids=scope,
        script=script,
        created_at="2026-10-17T00:00:00Z",
        approved_at="2026-10-17T00:00:30Z",
        judged_at="2026-10-17T00:01:00Z" if judged else None,
        consent=None if given is None else RoundConsent(given=given, at="2026-10-17T00:00:40Z"),
    )


def make_briefing(rounds: list[Round], verdicts: dict | None = None, status="briefing") -> Briefing:
    return Briefing(
        id="b_abcdefghijkl", site_id="sg", task_id="panel-isolation", supervisor_lang="en",
        worker_lang="ta", sop=Sop(id="SOP", version="v1", title="t", text="x"),
        instruction="do it", status=status, steps=[Step(id=s, text=s) for s in STEPS],
        rounds=rounds, latest_verdicts=verdicts or {}, prompt_version="p", created_at="x",
        updated_at="x",
    )  # fmt: skip


def declined(**kw) -> Briefing:
    return make_briefing([make_round(1, list(STEPS), given=False)], **kw)


def go(reason: str | None = REASON) -> DecisionBody:
    return DecisionBody(value="go", reason=reason, by="Sam")


class TestTheRule:
    def test_a_go_after_a_decline_is_recorded_as_an_in_person_check(self):
        d = sm.decide(declined(), go(), S)
        assert (d.value, d.in_person, d.reason) == ("go", True, REASON)
        assert d.open_step_ids == list(STEPS)  # nothing of the round was checked by a model
        assert d.wire()["inPerson"] is True

    @pytest.mark.parametrize("reason", [None, "", "   ", "four"])
    def test_it_always_needs_the_reason(self, reason):
        with pytest.raises(Unprocessable) as refused:
            sm.decide(declined(), go(reason), S)
        assert (refused.value.status, refused.value.code) == (422, "reason_required")

    def test_a_reported_hazard_still_blocks_it_and_is_checked_before_the_reason(self):
        b = declined()
        b.hazards = [Hazard(id="h1", kind="tap", raised_at="2026-10-17T00:00:50Z")]
        for reason in (None, REASON):
            with pytest.raises(InvalidState) as refused:
                sm.decide(b, go(reason), S)
            assert refused.value.code == "hazard_open"

    @pytest.mark.parametrize("given", [None, True])
    def test_without_a_decline_a_go_in_briefing_is_still_409(self, given):
        b = make_briefing([make_round(1, list(STEPS), given=given)])
        with pytest.raises(InvalidState) as refused:
            sm.decide(b, go(), S)
        assert refused.value.code == "invalid_state"

    def test_a_no_go_after_a_decline_is_the_early_no_go_as_before(self):
        d = sm.decide(declined(), DecisionBody(value="no_go"), S)
        assert (d.value, d.in_person, d.open_step_ids) == ("no_go", None, list(STEPS))
        assert "inPerson" not in d.wire()

    def test_a_declined_re_explain_round_opens_its_scope_beside_the_steps_already_open(self):
        first = make_round(1, list(STEPS), given=True, judged=True)
        verdicts = {"s1": "covered", "s2": "missed", "s3": "unclear"}
        b = make_briefing([first, make_round(2, ["s2"], given=False)], verdicts)
        d = sm.decide(b, go(), S)
        assert (d.in_person, d.open_step_ids) == (True, ["s2", "s3"])  # s1 stays covered

    def test_the_rule_as_written_holds_where_no_api_round_can_reach(self):
        # "Every step in scope counts as open" and "the reason is always required": a covered step
        # in the declined round's scope is open, and with nothing open at all a reason is needed.
        first = make_round(1, list(STEPS), given=True, judged=True)
        covered = {s: "covered" for s in STEPS}
        b = make_briefing([first, make_round(2, ["s1"], given=False)], covered)
        assert sm.decide(b, go(), S).open_step_ids == ["s1"]
        empty = make_briefing([first, make_round(2, [], given=False)], covered)
        with pytest.raises(Unprocessable):
            sm.decide(empty, go(None), S)
        assert sm.decide(empty, go(), S).open_step_ids == []

    def test_a_judged_go_carries_no_in_person(self):
        b = make_briefing([make_round(1, list(STEPS), given=True, judged=True)], status="judged")
        b.latest_verdicts = {s: "covered" for s in STEPS}
        d = sm.decide(b, go(None), S)
        assert d.in_person is None and "inPerson" not in d.wire()
        assert "inPerson" not in chain.decided(d)


# Over HTTP, with the service's consent gate on --------------------------------------------------


@pytest.fixture
def world(settings):
    app, _runtime, llm, _store = make_app(
        settings.with_overrides(require_consent=True), tts_client=FakeTtsClient()
    )
    client = api_client(app)
    bid, rnd = drive_to_round(client)
    return client, llm, bid, rnd


def decline(client, bid: str, n: int = 1):
    return client.post(f"/api/briefings/{bid}/rounds/{n}/consent", json={"given": False})


def decide(client, bid: str, **body):
    return client.post(f"/api/briefings/{bid}/decision", json=body)


def raw_of(settings: Settings, bid: str) -> tuple[dict, object]:
    path = settings.data_dir / "briefings" / f"{bid}.json"
    return json.loads(path.read_text("utf-8")), path


class TestOverHttp:
    def test_decline_then_an_in_person_go_with_no_model_call_and_no_audio(self, world):
        client, llm, bid, rnd = world
        calls = len(llm.seen)
        assert decline(client, bid).status_code == 200
        assert error_of(decide(client, bid, value="go")) == (422, "reason_required")
        decided = decide(client, bid, value="go", reason=REASON, by="Sam")
        assert decided.status_code == 200, decided.text
        b = decided.json()
        assert (b["status"], b["decision"]["inPerson"], b["decision"]["reason"]) == (
            "decided", True, REASON,
        )  # fmt: skip
        assert b["decision"]["openStepIds"] == rnd["stepIds"] == [s["id"] for s in b["steps"]]
        assert b["latestVerdicts"] == {} and b["rounds"][0]["ratings"] == []
        assert len(llm.seen) == calls  # no model call anywhere on this path
        # The decline gates stay, and nothing is writable after the decision.
        assert error_of(post_check(client, bid, 1, q1=tone_wav()))[0] == 409
        assert error_of(client.post(f"/api/briefings/{bid}/rounds/1/live-session"))[0] == 409
        assert error_of(decide(client, bid, value="no_go")) == (409, "invalid_state")
        assert error_of(decide(client, bid, value="go", reason=REASON)) == (409, "invalid_state")
        assert len(llm.seen) == calls

    def test_the_chain_records_it_and_the_record_verifies(self, world):
        client, _, bid, _ = world
        decline(client, bid)
        decide(client, bid, value="go", reason=REASON)
        b = client.get(f"/api/briefings/{bid}").json()
        last = b["events"][-1]
        assert (last["type"], last["data"]["inPerson"], last["data"]["value"]) == (
            "decided", True, "go",
        )  # fmt: skip
        assert [e["data"]["given"] for e in b["events"] if e["type"] == "consent"] == [False]
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True

    def test_without_a_decline_a_go_before_the_check_is_still_409(self, world):
        client, _, bid, _ = world
        assert error_of(decide(client, bid, value="go", reason=REASON)) == (409, "invalid_state")
        client.post(f"/api/briefings/{bid}/rounds/1/consent", json={"given": True})
        assert error_of(decide(client, bid, value="go", reason=REASON)) == (409, "invalid_state")

    def test_a_worker_who_agrees_after_all_goes_back_to_the_ai_check(self, world):
        client, _, bid, _ = world
        decline(client, bid)
        client.post(f"/api/briefings/{bid}/rounds/1/consent", json={"given": True})
        assert error_of(decide(client, bid, value="go", reason=REASON)) == (409, "invalid_state")
        assert post_check(client, bid, 1, q1=tone_wav()).status_code == 200

    def test_a_hazard_blocks_the_in_person_go_until_it_is_acknowledged(self, world):
        client, _, bid, _ = world
        decline(client, bid)
        client.post(f"/api/briefings/{bid}/hazards")  # a tap, never consent-gated
        assert error_of(decide(client, bid, value="go", reason=REASON)) == (409, "hazard_open")
        ack = client.post(f"/api/briefings/{bid}/hazards/h1/ack", json={"note": "Moved the cones."})
        assert ack.status_code == 200
        assert decide(client, bid, value="go", reason=REASON).json()["decision"]["inPerson"]

    def test_a_no_go_after_the_decline_is_recorded_as_before(self, world):
        client, _, bid, _ = world
        decline(client, bid)
        b = decide(client, bid, value="no_go").json()
        assert b["decision"]["value"] == "no_go" and "inPerson" not in b["decision"]
        assert "inPerson" not in b["events"][-1]["data"]


class TestTamper:
    @pytest.mark.parametrize("edit", ["flip", "drop"])
    def test_an_edited_in_person_flag_is_found_at_the_decided_event(self, world, settings, edit):
        client, _, bid, _ = world
        decline(client, bid)
        decide(client, bid, value="go", reason=REASON)
        raw, path = raw_of(settings, bid)
        if edit == "flip":
            raw["decision"]["inPerson"] = False
        else:
            del raw["decision"]["inPerson"]
        path.write_text(json.dumps(raw, ensure_ascii=False), "utf-8")
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["ok"], result["reason"], result["brokenAt"]) == (
            False, "decision_mismatch", raw["events"][-1]["seq"],
        )  # fmt: skip

    def test_a_flag_added_to_an_ai_checked_decision_is_found_too(self, world, settings):
        client, _, bid, _ = world
        client.post(f"/api/briefings/{bid}/rounds/1/consent", json={"given": True})
        post_check(client, bid, 1, q1=tone_wav())
        decide(client, bid, value="no_go")
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True
        raw, path = raw_of(settings, bid)
        raw["decision"]["inPerson"] = True
        path.write_text(json.dumps(raw, ensure_ascii=False), "utf-8")
        assert client.get(f"/api/briefings/{bid}/verify").json()["reason"] == "decision_mismatch"
