"""Security fixes B, M3 and M4 (build-notes/36-security-fixes-b.md): consent makes the record
consistent.

With SIB_REQUIRE_CONSENT a round with no recorded choice is checked only as all stored samples
(every question of the round listed in `meta.sampleAnswers`), whatever clips are sent, in either
mode, and gets a Live ticket only when the request declares `{"samplesOnly": true}`. The server
cannot tell a sample from a voice on the wire, so this keeps the record honest for an honest
client: a round with no recorded choice can only be judged as all samples. The judges' path, a
sample-only round in Turn mode and in Live mode, still runs end to end.
"""

from __future__ import annotations

import json

import pytest

from sayitback import consent
from sayitback.daily_cap import LIVE_TICKET_CALLS
from sayitback.errors import InvalidState
from sayitback.models import Question, Round, Script
from tests.fake_live import fake_opener
from tests.fakes import FakeTtsClient, tone_wav
from tests.helpers import api_client, check_files, drive_to_round, error_of, make_app, seed_round
from tests.relay_support import Wire

ORIGIN = "http://localhost:5173"


def client_for(settings, *, required: bool = True, **changes):
    s = settings.with_overrides(require_consent=required, **changes)
    handles: list = []
    app, _rt, llm, store = make_app(s, tts_client=FakeTtsClient(), live_opener=fake_opener(handles))
    client = api_client(app)
    client.llm, client.store = llm, store
    return client


def qids_of(rnd: dict) -> list[str]:
    return [q["id"] for q in rnd["script"]["questions"]]


def check(client, bid: str, clips: list[str], samples: list[str] | None, mode: str = "turn"):
    meta = {"mode": mode, **({"sampleAnswers": samples} if samples is not None else {})}
    files = check_files(**{q: tone_wav() for q in clips})
    return client.post(
        f"/api/briefings/{bid}/rounds/1/check", files=files, data={"meta": json.dumps(meta)}
    )


def ticket(client, bid: str, body: object = None, n: int = 1):
    args = {} if body is None else {"json": body}
    return client.post(f"/api/briefings/{bid}/rounds/{n}/live-session", **args)


def choose(client, bid: str, given: bool):
    reply = client.post(f"/api/briefings/{bid}/rounds/1/consent", json={"given": given})
    assert reply.status_code == 200, reply.text


def round_with(*qids: str) -> Round:
    questions = [Question(id=q, text="?", step_ids=["s1"]) for q in qids]
    script = Script(instruction="x", questions=questions, step_map={}, closing="")
    return Round(n=1, kind="initial", step_ids=["s1"], script=script, created_at="2026-10-16")


class TestSamplesOnly:
    def test_it_is_every_question_of_the_round_listed(self):
        assert consent.samples_only(round_with("q1", "q2"), ["q2", "q1"]) is True
        assert consent.samples_only(round_with("q1", "q2"), ["q1"]) is False
        assert consent.samples_only(round_with("q1"), None) is False

    def test_a_round_with_no_questions_is_never_all_samples(self):
        """A script's question count is a soft check, so an empty list can happen: it must not
        open the gate by an empty `all()`."""
        assert consent.samples_only(round_with(), []) is False
        with pytest.raises(InvalidState):
            consent.require_for_check(round_with(), None, True)


class TestTheCheck:
    def test_every_question_a_sample_needs_no_consent(self, settings):
        client = client_for(settings)
        bid, rnd = drive_to_round(client)
        judged = check(client, bid, qids_of(rnd), qids_of(rnd))
        assert judged.status_code == 200, judged.text
        assert judged.json()["sampleAnswers"] == qids_of(rnd) and "consent" not in judged.json()

    def test_samples_for_only_some_questions_need_consent_whatever_clips_are_sent(self, settings):
        """The gap: clips for q1 only, labelled a sample, used to pass; q2 had no clip at all."""
        client = client_for(settings)
        bid, rnd = drive_to_round(client)
        assert len(qids_of(rnd)) == 2
        seen = len(client.llm.seen)

        assert error_of(check(client, bid, ["q1"], ["q1"])) == (409, "consent_required")
        assert error_of(check(client, bid, ["q1", "q2"], ["q1"])) == (409, "consent_required")
        assert error_of(check(client, bid, ["q1"], None)) == (409, "consent_required")
        assert len(client.llm.seen) == seen  # refused before any model call
        assert client.get(f"/api/briefings/{bid}").json()["status"] == "briefing"

    def test_in_live_mode_too_before_any_wait_for_the_relay(self, settings):
        client = client_for(settings, live_record_wait_s=30.0)
        bid, _ = drive_to_round(client)
        assert error_of(check(client, bid, ["q1"], ["q1"], mode="live")) == (
            409,
            "consent_required",
        )

    def test_after_the_worker_agrees_any_mix_is_checked(self, settings):
        client = client_for(settings)
        bid, _ = drive_to_round(client)
        choose(client, bid, True)
        judged = check(client, bid, ["q1"], ["q1"])
        assert judged.status_code == 200, judged.text
        assert judged.json()["sampleAnswers"] == ["q1"]

    def test_with_the_gate_off_a_partial_sample_check_runs_as_before(self, settings):
        client = client_for(settings, required=False)
        bid, _ = drive_to_round(client)
        assert check(client, bid, ["q1"], ["q1"]).status_code == 200

    def test_a_declined_round_stays_declined_even_as_all_samples(self, settings):
        client = client_for(settings)
        bid, rnd = drive_to_round(client)
        choose(client, bid, False)
        assert error_of(check(client, bid, qids_of(rnd), qids_of(rnd))) == (
            409,
            "consent_declined",
        )


class TestTheLiveTicket:
    def test_no_choice_and_no_declaration_is_409_consent_required(self, settings):
        client = client_for(settings)
        bid, _ = drive_to_round(client)
        for body in (None, {}, {"samplesOnly": False}):
            assert error_of(ticket(client, bid, body)) == (409, "consent_required"), body

    def test_a_samples_only_session_gets_its_ticket(self, settings):
        client = client_for(settings)
        bid, _ = drive_to_round(client)
        issued = ticket(client, bid, {"samplesOnly": True})
        assert issued.status_code == 200, issued.text
        assert set(issued.json()) == {"wsUrl", "ticket", "model", "expiresAt"}

    def test_after_the_worker_agrees_no_declaration_is_needed(self, settings):
        client = client_for(settings)
        bid, _ = drive_to_round(client)
        choose(client, bid, True)
        assert ticket(client, bid).status_code == 200

    def test_a_declined_round_gets_none_even_samples_only(self, settings):
        client = client_for(settings)
        bid, _ = drive_to_round(client)
        choose(client, bid, False)
        assert error_of(ticket(client, bid, {"samplesOnly": True})) == (409, "consent_declined")

    def test_with_the_gate_off_the_ticket_is_issued_as_before(self, settings):
        client = client_for(settings, required=False)
        bid, _ = drive_to_round(client)
        assert ticket(client, bid).status_code == 200

    @pytest.mark.parametrize(
        "body", [{"samplesOnly": "true"}, {"samplesOnly": 1}, {"samplesOnly": True, "x": 1}, []]
    )
    def test_only_a_json_boolean_declares_it(self, settings, body):
        client = client_for(settings)
        bid, _ = drive_to_round(client)
        assert error_of(ticket(client, bid, body)) == (422, "validation_error")

    def test_the_rounds_own_state_is_answered_first(self, settings):
        client = client_for(settings)
        bid, _ = drive_to_round(client, approve=False)
        assert error_of(ticket(client, bid)) == (409, "script_not_approved")
        assert error_of(ticket(client, bid, n=2))[0] == 404

    def test_a_refusal_costs_no_ticket_slot_and_no_daily_call(self, settings):
        """After the round's checks, before the allowance (2 a round) and the cap (one ticket)."""
        client = client_for(settings, daily_gemini_calls=LIVE_TICKET_CALLS)
        bid = seed_round(client.store)  # no model call: the day's cap holds exactly one ticket
        for _ in range(3):
            assert error_of(ticket(client, bid)) == (409, "consent_required")

        assert ticket(client, bid, {"samplesOnly": True}).status_code == 200
        assert error_of(ticket(client, bid, {"samplesOnly": True})) == (429, "daily_limit")


class TestTheJudgesPathWithConsentOn:
    """The evaluator plays the stored sample answers: no consent screen, no consent needed."""

    def test_turn_mode_from_round_to_go(self, settings):
        client = client_for(settings)
        bid, rnd = drive_to_round(client)

        judged = check(client, bid, qids_of(rnd), qids_of(rnd))
        decided = client.post(
            f"/api/briefings/{bid}/decision", json={"value": "go", "reason": "Samples, a demo."}
        )

        assert judged.status_code == 200, judged.text
        assert decided.status_code == 200, decided.text
        assert decided.json()["status"] == "decided"
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True

    def test_live_mode_from_ticket_to_go(self, settings):
        client = client_for(settings)
        bid, rnd = drive_to_round(client)
        issued = ticket(client, bid, {"samplesOnly": True})
        assert issued.status_code == 200, issued.text

        with client.websocket_connect(f"/api/live/{bid}/1", headers={"origin": ORIGIN}) as ws:
            wire = Wire(ws)
            assert wire.start(issued.json()["ticket"])[1]["type"] == "ready"
            wire.send(type="cue", cue="READ_INSTRUCTION")
            wire.until("turn_complete")
            for qid in qids_of(rnd):  # the stored sample is streamed into each answer window
                wire.send(type="cue", cue="ASK", qid=qid)
                wire.until("turn_complete")
                wire.send(type="answer_start", qid=qid)
                wire.audio(3)
                wire.send(type="answer_end", qid=qid)
                wire.until("turn_complete")
            wire.send(type="cue", cue="CLOSE")
            wire.until("turn_complete")
            wire.send(type="stop")
            assert wire.next() == ("close", 1000)

        judged = check(client, bid, qids_of(rnd), qids_of(rnd), mode="live")
        decided = client.post(
            f"/api/briefings/{bid}/decision", json={"value": "go", "reason": "Samples, a demo."}
        )

        assert judged.status_code == 200, judged.text
        assert (judged.json()["mode"], judged.json()["sampleAnswers"]) == ("live", qids_of(rnd))
        assert decided.status_code == 200, decided.text
