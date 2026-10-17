"""Privacy, 16 Oct: the worker's consent before any answer is recorded (consent.py, API.md
Deviations). The choice is on the round and in the record chain; a declined round takes no audio;
with SIB_REQUIRE_CONSENT a person's voice needs consent first, and stored sample answers need none.
"""

from __future__ import annotations

import json

import pytest

from sayitback import chain
from sayitback.errors import InvalidState
from sayitback.models import Briefing, CheckResult
from sayitback.rounds import record_check
from sayitback.settings import ConfigError, Settings
from tests.fakes import FakeTtsClient, tone_wav
from tests.helpers import (
    OTHER_DEVICE,
    api_client,
    check_files,
    drive_to_round,
    error_of,
    make_app,
    post_check,
)


def client_for(settings: Settings, *, required: bool):
    app, *_ = make_app(
        settings.with_overrides(require_consent=required), tts_client=FakeTtsClient()
    )
    return api_client(app)


def consent(client, bid: str, given: object, n: int = 1):
    return client.post(f"/api/briefings/{bid}/rounds/{n}/consent", json={"given": given})


def sample_check(client, bid: str, clips: dict[str, bytes], samples: list[str]):
    meta = json.dumps({"mode": "turn", "sampleAnswers": samples})
    return client.post(
        f"/api/briefings/{bid}/rounds/1/check", files=check_files(**clips), data={"meta": meta}
    )


def stored(settings: Settings, bid: str) -> dict:
    return json.loads((settings.data_dir / "briefings" / f"{bid}.json").read_text("utf-8"))


def rewrite(settings: Settings, bid: str, raw: dict) -> None:
    path = settings.data_dir / "briefings" / f"{bid}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), "utf-8")


class TestSettings:
    def test_the_service_requires_consent_and_keeps_records_90_days_by_default(self):
        s = Settings.from_env({})
        assert (s.require_consent, s.retention_days) == (True, 90)

    def test_both_are_read_from_the_environment(self):
        s = Settings.from_env({"SIB_REQUIRE_CONSENT": "false", "SIB_RETENTION_DAYS": "0"})
        assert (s.require_consent, s.retention_days) == (False, 0)
        assert Settings.from_env({"SIB_RETENTION_DAYS": "30"}).retention_days == 30

    @pytest.mark.parametrize("raw", ["-1", "3651", "ninety"])
    def test_a_bad_retention_stops_start_up(self, raw):
        with pytest.raises(ConfigError):
            Settings.from_env({"SIB_RETENTION_DAYS": raw})

    def test_a_bad_consent_flag_stops_start_up(self):
        with pytest.raises(ConfigError):
            Settings.from_env({"SIB_REQUIRE_CONSENT": "maybe"})

    def test_settings_built_by_hand_leave_the_consent_gate_off(self):
        assert Settings().require_consent is False


class TestRequired:
    """SIB_REQUIRE_CONSENT=true, the service's default."""

    def test_a_voice_without_consent_is_refused_before_any_model_call(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        assert error_of(post_check(client, bid, 1, q1=tone_wav())) == (409, "consent_required")
        assert client.get(f"/api/briefings/{bid}").json()["status"] == "briefing"

    def test_after_the_worker_agrees_the_check_runs(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        assert consent(client, bid, True).status_code == 200
        judged = post_check(client, bid, 1, q1=tone_wav())
        assert judged.status_code == 200, judged.text
        assert judged.json()["judgedAt"]

    def test_stored_sample_answers_record_no_human_voice_so_they_need_no_consent(self, settings):
        # The evaluator's path: every clip is a stored synthetic sample, and the web never shows the
        # consent step for it.
        client = client_for(settings, required=True)
        bid, rnd = drive_to_round(client)
        qids = [q["id"] for q in rnd["script"]["questions"]]
        judged = sample_check(client, bid, {q: tone_wav() for q in qids}, qids)
        assert judged.status_code == 200, judged.text
        assert judged.json()["sampleAnswers"] == qids
        assert "consent" not in judged.json()

    def test_one_clip_of_a_person_among_samples_still_needs_consent(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        mixed = sample_check(client, bid, {"q1": tone_wav(), "q2": tone_wav()}, ["q1"])
        assert error_of(mixed) == (409, "consent_required")


class TestNotRequired:
    def test_with_the_gate_off_a_check_runs_as_before(self, settings):
        client = client_for(settings, required=False)
        bid, _ = drive_to_round(client)
        assert post_check(client, bid, 1, q1=tone_wav()).status_code == 200


@pytest.mark.parametrize("required", [True, False])
class TestDeclined:
    """A decline is the worker's choice: in both modes nothing of the round is heard or checked."""

    def test_the_check_is_refused(self, settings, required):
        client = client_for(settings, required=required)
        bid, _ = drive_to_round(client)
        assert consent(client, bid, False).json()["consent"]["given"] is False
        assert error_of(post_check(client, bid, 1, q1=tone_wav())) == (409, "consent_declined")

    def test_even_a_sample_only_check_and_a_live_ticket_are_refused(self, settings, required):
        client = client_for(settings, required=required)
        bid, _ = drive_to_round(client)
        consent(client, bid, False)
        assert error_of(sample_check(client, bid, {"q1": tone_wav()}, ["q1"]))[1] == (
            "consent_declined"
        )
        ticket = client.post(f"/api/briefings/{bid}/rounds/1/live-session")
        assert error_of(ticket) == (409, "consent_declined")

    def test_the_upload_is_never_read(self, settings, required):
        client = client_for(settings, required=required)
        bid, _ = drive_to_round(client)
        consent(client, bid, False)
        bad = client.post(f"/api/briefings/{bid}/rounds/1/check", files=check_files(q1=b"x"))
        assert error_of(bad) == (409, "consent_declined")  # not 415: refused before parsing

    def test_a_decline_is_no_verdict_and_the_worker_may_agree_later(self, settings, required):
        client = client_for(settings, required=required)
        bid, _ = drive_to_round(client)
        consent(client, bid, False)
        b = client.get(f"/api/briefings/{bid}").json()
        assert (b["status"], b["latestVerdicts"], b.get("decision")) == ("briefing", {}, None)
        assert consent(client, bid, True).json()["consent"]["given"] is True
        assert post_check(client, bid, 1, q1=tone_wav()).status_code == 200


class TestEndpoint:
    def test_it_needs_the_approved_script(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client, approve=False)
        assert error_of(consent(client, bid, True)) == (409, "script_not_approved")

    def test_a_judged_round_takes_no_new_choice(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        consent(client, bid, True)
        post_check(client, bid, 1, q1=tone_wav())
        assert error_of(consent(client, bid, False)) == (409, "invalid_state")

    def test_unknown_rounds_and_other_callers_get_404(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        assert error_of(consent(client, bid, True, n=4)) == (404, "round_not_found")
        assert error_of(consent(client, bid, True, n=0)) == (404, "round_not_found")
        app = client.app
        stranger = api_client(app, OTHER_DEVICE)
        assert error_of(consent(stranger, bid, True)) == (404, "not_found")
        assert "consent" not in client.get(f"/api/briefings/{bid}").json()["rounds"][0]

    @pytest.mark.parametrize("body", [{"given": "true"}, {"given": 1}, {}, {"given": True, "x": 1}])
    def test_only_a_json_boolean_is_a_choice(self, settings, body):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        refused = client.post(f"/api/briefings/{bid}/rounds/1/consent", json=body)
        assert error_of(refused) == (422, "validation_error")
        assert error_of(post_check(client, bid, 1, q1=tone_wav())) == (409, "consent_required")


class TestChain:
    def test_the_choice_is_a_consent_event_with_ids_only_and_the_record_verifies(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        consent(client, bid, True)
        b = client.get(f"/api/briefings/{bid}").json()
        last = b["events"][-1]
        assert (last["type"], last["data"]) == ("consent", {"n": 1, "given": True})
        assert b["recordHash"] == last["hash"]
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True

    def test_the_same_choice_twice_adds_nothing_and_a_change_of_mind_adds_an_event(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        consent(client, bid, False)
        count = len(client.get(f"/api/briefings/{bid}").json()["events"])
        consent(client, bid, False)
        assert len(client.get(f"/api/briefings/{bid}").json()["events"]) == count
        consent(client, bid, True)
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        assert [e["data"]["given"] for e in events if e["type"] == "consent"] == [False, True]
        assert post_check(client, bid, 1, q1=tone_wav()).status_code == 200
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True

    def test_an_edited_choice_is_detected_at_its_event(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        consent(client, bid, False)
        raw = stored(settings, bid)
        seq = raw["events"][-1]["seq"]
        raw["rounds"][0]["consent"]["given"] = True
        rewrite(settings, bid, raw)
        result = client.get(f"/api/briefings/{bid}/verify").json()
        assert (result["ok"], result["brokenAt"], result["reason"]) == (
            False,
            seq,
            "consent_mismatch",
        )

    def test_a_removed_choice_and_an_unrecorded_one_are_detected(self, settings):
        client = client_for(settings, required=True)
        bid, _ = drive_to_round(client)
        consent(client, bid, True)
        raw = stored(settings, bid)
        del raw["rounds"][0]["consent"]
        rewrite(settings, bid, raw)
        assert client.get(f"/api/briefings/{bid}/verify").json()["reason"] == "consent_mismatch"
        other, _ = drive_to_round(client)
        raw = stored(settings, other)
        raw["rounds"][0]["consent"] = {"given": True, "at": raw["createdAt"]}
        rewrite(settings, other, raw)
        assert client.get(f"/api/briefings/{other}/verify").json()["reason"] == "unrecorded_change"

    def test_a_record_with_no_consent_verifies_as_before(self, settings):
        client = client_for(settings, required=False)
        bid, _ = drive_to_round(client)
        post_check(client, bid, 1, q1=tone_wav())
        b = client.get(f"/api/briefings/{bid}").json()
        assert all(e["type"] != "consent" for e in b["events"])
        assert client.get(f"/api/briefings/{bid}/verify").json()["ok"] is True


def test_a_decline_recorded_while_the_check_ran_stops_its_result_being_written(settings):
    client = client_for(settings, required=True)
    bid, _ = drive_to_round(client)
    consent(client, bid, False)
    briefing = Briefing.model_validate(client.get(f"/api/briefings/{bid}").json())
    result = CheckResult(transcripts=[], pass_a=[], pass_b=[], ratings=[], next_action="reexplain")
    with pytest.raises(InvalidState) as refused:
        record_check(briefing, 1, "turn", result, [])
    assert refused.value.code == "consent_declined"
    assert briefing.rounds[0].judged_at is None
    assert chain.verify(briefing)["ok"] is True
