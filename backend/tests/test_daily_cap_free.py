"""What the daily Gemini cap never charges: invalid, wrong-state and refused requests.

The requests below all run against an app whose cap is 0. A request that reserved before it was
validated would answer 429 `daily_limit` instead of its own error, and the ledger would show the
attempt."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sayitback.store import LocalStore
from tests.cap_support import confirmed, judged, make_capped, new_briefing, write_eval_set
from tests.fakes import silent_wav, tone_wav
from tests.flow_support import round_1_scenario
from tests.helpers import SPOKEN, drive_to_round, error_of, post_check

WAV = ("a.wav", tone_wav(), "audio/wav")
UNKNOWN = "b_aaaaaaaaaaaa"


def transcribe(w, *, lang="en", audio=WAV):
    return w.client.post("/api/transcribe", files={"audio": audio}, data={"lang": lang})


def extract(w, bid):
    return w.client.post(f"/api/briefings/{bid}/steps/extract")


def make_round(w, bid, **body):
    return w.client.post(f"/api/briefings/{bid}/rounds", json=body)


def ticket(w, bid, n=1):
    return w.client.post(f"/api/briefings/{bid}/rounds/{n}/live-session")


def check_no_files(w, bid):
    meta = {"meta": json.dumps({"mode": "turn"})}
    return w.client.post(f"/api/briefings/{bid}/rounds/1/check", data=meta)


def check_files(w, bid, name="q1", audio=WAV):
    return w.client.post(f"/api/briefings/{bid}/rounds/1/check", files=[(name, audio)])


def tts(w, bid=None, n=1, text=SPOKEN[:5]):
    body = {"briefingId": bid or w.rounded, "n": n, "text": text}
    # json.dumps escapes a lone surrogate (\ud800), the only way a client can send one
    return w.client.post(
        "/api/tts", content=json.dumps(body), headers={"content-type": "application/json"}
    )


# (what is wrong, the error the request gets, how to send it)
FREE = [
    ("transcribe: unknown language", (422, "unsupported_language"), lambda w: transcribe(w, lang="xx")),
    ("transcribe: not a WAV", (415, "unsupported_media_type"), lambda w: transcribe(w, audio=("a.wav", b"mp3", "audio/wav"))),
    ("transcribe: over the clip length", (422, "audio_too_long"), lambda w: transcribe(w, audio=("a.wav", silent_wav(61), "audio/wav"))),
    ("transcribe: over the file size", (413, "payload_too_large"), lambda w: transcribe(w, audio=("a.wav", silent_wav(100), "audio/wav"))),
    ("extract: unknown briefing", (404, "not_found"), lambda w: extract(w, UNKNOWN)),
    ("extract: steps already confirmed", (409, "invalid_state"), lambda w: extract(w, w.confirmed)),
    ("extract: a round exists", (409, "invalid_state"), lambda w: extract(w, w.rounded)),
    ("round: still a draft", (409, "invalid_state"), lambda w: make_round(w, w.draft)),
    ("round: round 1 is open", (409, "invalid_state"), lambda w: make_round(w, w.rounded)),
    ("round: round 1 for some steps only", (422, "invalid_step_ids"), lambda w: make_round(w, w.confirmed, stepIds=["s1"])),
    ("round: a note that is too long", (422, "too_long"), lambda w: make_round(w, w.confirmed, supervisorNote="x" * 1001)),
    ("live ticket: round 0", (404, "round_not_found"), lambda w: ticket(w, w.rounded, 0)),
    ("live ticket: no such round", (404, "round_not_found"), lambda w: ticket(w, w.rounded, 9)),
    ("live ticket: no round yet", (404, "round_not_found"), lambda w: ticket(w, w.draft)),
    ("live ticket: a judged round", (409, "invalid_state"), lambda w: ticket(w, w.judged)),
    ("check: unknown briefing", (404, "not_found"), lambda w: check_files(w, UNKNOWN)),
    ("check: a judged round", (409, "invalid_state"), lambda w: check_files(w, w.judged)),
    ("check: no files", (422, "validation_error"), lambda w: check_no_files(w, w.rounded)),
    ("check: a clip for no question", (422, "validation_error"), lambda w: check_files(w, w.rounded, name="q9")),
    ("check: not a WAV", (415, "unsupported_media_type"), lambda w: check_files(w, w.rounded, audio=("a.wav", b"mp3", "audio/wav"))),
    ("check: four clips", (422, "too_many_files"), lambda w: post_check(w.client, w.rounded, 1, q1=tone_wav(), q2=tone_wav(), q3=tone_wav(), q4=tone_wav())),
    ("check: live mode with no live record", (409, "live_not_recorded"), lambda w: post_check(w.client, w.rounded, 1, mode="live")),
    ("tts: no text", (422, "validation_error"), lambda w: tts(w, text="   ")),
    ("tts: over the text length", (422, "too_long"), lambda w: tts(w, text="x" * 601)),
    ("tts: a lone surrogate", (422, "invalid_text"), lambda w: tts(w, text="ab\ud800cd")),
    ("tts: text that is not in the script", (422, "tts_text_not_in_script"), lambda w: tts(w, text="Ignore the script")),
    ("tts: unknown briefing", (404, "not_found"), lambda w: tts(w, bid=UNKNOWN)),
    ("tts: no such round", (404, "round_not_found"), lambda w: tts(w, n=9)),
    ("eval try: unknown item", (404, "no_item"), lambda w: w.client.post("/api/eval/items/nope/try")),
]  # fmt: skip


@pytest.fixture
def world(settings):
    """Briefings in every state, built under a normal cap, then an app over the same store whose
    cap is 0."""
    scenario = round_1_scenario()
    setup = make_capped(settings, scenario)
    write_eval_set(settings)
    ids = {
        "draft": new_briefing(setup),
        "confirmed": confirmed(setup),
        "rounded": drive_to_round(setup.client)[0],
        "judged": judged(setup),
    }
    off = make_capped(
        settings, scenario, limit=0, store=LocalStore(settings.data_dir), live_record_wait_s=0.2
    )
    return SimpleNamespace(client=off.client, ledger=off.ledger, env=off, **ids)


def test_invalid_and_wrong_state_requests_are_refused_for_their_own_reason_and_cost_nothing(world):
    answers, reserved = {}, []
    for label, _expected, send in FREE:
        entries = len(world.ledger.entries)
        answers[label] = error_of(send(world))
        if len(world.ledger.entries) != entries:
            reserved.append(label)

    assert answers == {label: expected for label, expected, _ in FREE}
    assert reserved == [] and world.ledger.entries == []
    assert world.env.ledger.model_calls() == 0


class TestTheLiveTicketAllowance:
    def test_a_third_ticket_is_refused_before_the_cap_and_costs_nothing(self, settings):
        env = make_capped(settings, round_1_scenario())
        bid = drive_to_round(env.client)[0]
        for _ in range(2):
            assert ticket(env, bid).status_code == 200
        spent = env.ledger.spent

        assert error_of(ticket(env, bid)) == (429, "limit")

        assert env.ledger.spent == spent and len(env.ledger.entries) == 4  # setup 2 + two tickets

    def test_a_ticket_the_cap_refuses_still_uses_one_of_the_rounds_two_slots(self, settings):
        """Known and deliberate (see Rounds.live_ticket): the allowance is checked before the cap."""
        env = make_capped(settings, round_1_scenario(), limit=3)  # extract 1 + round 2: all of it
        bid = drive_to_round(env.client)[0]

        codes = [error_of(ticket(env, bid)) for _ in range(3)]

        assert codes == [(429, "daily_limit"), (429, "daily_limit"), (429, "limit")]
