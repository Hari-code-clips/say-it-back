"""The state machine: every 409 path, and decision validation (API.md, "State machine")."""

from __future__ import annotations

import pytest

from sayitback import state_machine as sm
from sayitback.errors import InvalidState, NotFound, Unprocessable
from sayitback.models import Briefing, DecisionBody, Question, Round, Script, Sop, Step
from sayitback.settings import Settings

S = Settings()
STATUSES = ["draft", "steps_proposed", "steps_confirmed", "briefing", "judged", "decided"]


def make_round(n=1, judged=False) -> Round:
    script = Script(
        instruction="a", questions=[Question(id="q1", text="t", step_ids=["s1"])], closing="c"
    )
    return Round(n=n, kind="initial" if n == 1 else "reexplain", step_ids=["s1", "s2"], script=script,
                 created_at="2026-10-14T00:00:00Z", judged_at="2026-10-14T00:01:00Z" if judged else None)  # fmt: skip


def make_briefing(status="draft", rounds=0, verdicts=None, judged_rounds=None) -> Briefing:
    n_rounds = [
        make_round(i + 1, judged=(judged_rounds is None or i < judged_rounds))
        for i in range(rounds)
    ]
    return Briefing(
        id="b_abcdefghijkl", site_id="sg", task_id="panel-isolation", supervisor_lang="en", worker_lang="ta",
        sop=Sop(id="SOP", version="v1", title="t", text="x"), instruction="do it", status=status,
        steps=[Step(id="s1", text="one"), Step(id="s2", text="two")], rounds=n_rounds,
        latest_verdicts=verdicts or {}, prompt_version="p", created_at="x", updated_at="x",
    )  # fmt: skip


class TestExtractAndEdit:
    @pytest.mark.parametrize("status", ["draft", "steps_proposed"])
    def test_allowed_before_confirmation(self, status):
        sm.require_editable(make_briefing(status), "Extracting steps")

    @pytest.mark.parametrize("status", ["steps_confirmed", "briefing", "judged", "decided"])
    def test_409_after_confirmation(self, status):
        with pytest.raises(InvalidState) as err:
            sm.require_editable(make_briefing(status), "Extracting steps")
        assert err.value.status == 409
        assert err.value.code == "invalid_state"


class TestConfirm:
    @pytest.mark.parametrize("status", ["steps_proposed", "steps_confirmed"])
    def test_allowed_before_round_1(self, status):
        sm.require_confirmable(make_briefing(status))

    @pytest.mark.parametrize("status", ["draft", "briefing", "judged", "decided"])
    def test_409_in_other_states(self, status):
        with pytest.raises(InvalidState):
            sm.require_confirmable(make_briefing(status))

    def test_409_once_a_round_exists_even_if_the_status_looks_confirmed(self):
        with pytest.raises(InvalidState):
            sm.require_confirmable(make_briefing("steps_confirmed", rounds=1))


class TestCreateRound:
    def test_round_1_needs_steps_confirmed(self):
        assert sm.next_round(make_briefing("steps_confirmed"), 3) == ("initial", 1)

    @pytest.mark.parametrize("status", ["draft", "steps_proposed", "briefing", "decided"])
    def test_409_when_not_confirmed_or_judged(self, status):
        with pytest.raises(InvalidState):
            sm.next_round(make_briefing(status), 3)

    def test_reexplain_needs_judged_and_an_open_step(self):
        b = make_briefing("judged", rounds=1, verdicts={"s1": "covered", "s2": "missed"})
        assert sm.next_round(b, 3) == ("reexplain", 2)

    def test_409_when_every_step_is_covered(self):
        b = make_briefing("judged", rounds=1, verdicts={"s1": "covered", "s2": "covered"})
        with pytest.raises(InvalidState, match="nothing to re-explain"):
            sm.next_round(b, 3)

    def test_409_after_three_rounds(self):
        b = make_briefing("judged", rounds=3, verdicts={"s1": "missed"})
        with pytest.raises(InvalidState, match="At most 3 rounds"):
            sm.next_round(b, 3)

    def test_the_third_round_is_allowed(self):
        b = make_briefing("judged", rounds=2, verdicts={"s1": "missed"})
        assert sm.next_round(b, 3) == ("reexplain", 3)


class TestLiveSessionAndCheck:
    def test_an_unjudged_round_in_briefing_is_usable(self):
        b = make_briefing("briefing", rounds=1, judged_rounds=0)
        assert sm.require_unjudged_round(b, 1).n == 1

    def test_404_for_a_missing_round(self):
        b = make_briefing("briefing", rounds=1, judged_rounds=0)
        with pytest.raises(NotFound) as err:
            sm.require_unjudged_round(b, 2)
        assert err.value.status == 404

    def test_409_for_an_already_judged_round(self):
        b = make_briefing("judged", rounds=1)
        with pytest.raises(InvalidState):
            sm.require_unjudged_round(b, 1)

    def test_409_when_an_earlier_round_is_asked_while_a_later_one_is_open(self):
        b = make_briefing("briefing", rounds=2, judged_rounds=1)
        with pytest.raises(InvalidState):
            sm.require_unjudged_round(b, 1)
        assert sm.require_unjudged_round(b, 2).n == 2

    @pytest.mark.parametrize("status", ["draft", "steps_confirmed", "decided"])
    def test_409_when_the_briefing_is_not_in_briefing(self, status):
        b = make_briefing(status, rounds=1, judged_rounds=0)
        with pytest.raises(InvalidState):
            sm.require_unjudged_round(b, 1)


class TestDecision:
    def go(self, reason=None):
        return DecisionBody(value="go", reason=reason)

    def no_go(self, reason=None):
        return DecisionBody(value="no_go", reason=reason)

    def test_go_with_every_step_covered_needs_no_reason(self):
        b = make_briefing("judged", rounds=1, verdicts={"s1": "covered", "s2": "covered"})
        d = sm.decide(b, self.go(), S)
        assert d.value == "go"
        assert d.open_step_ids == []

    def test_go_with_open_steps_needs_a_reason_of_five_characters(self):
        b = make_briefing("judged", rounds=1, verdicts={"s1": "covered", "s2": "missed"})
        for reason in (None, "", "   ", "four"):
            with pytest.raises(Unprocessable) as err:
                sm.decide(b, self.go(reason), S)
            assert err.value.status == 422
            assert err.value.code == "reason_required"
        d = sm.decide(b, self.go("  seen it  "), S)
        assert (d.reason, d.open_step_ids) == ("seen it", ["s2"])

    def test_a_step_with_no_verdict_counts_as_open(self):
        b = make_briefing("judged", rounds=1, verdicts={"s1": "covered"})
        with pytest.raises(Unprocessable):
            sm.decide(b, self.go(), S)

    def test_no_go_never_needs_a_reason(self):
        b = make_briefing("judged", rounds=1, verdicts={"s1": "missed"})
        assert sm.decide(b, self.no_go(), S).value == "no_go"

    @pytest.mark.parametrize("status", ["steps_confirmed", "briefing"])
    def test_an_explicit_no_go_is_allowed_early(self, status):
        assert sm.decide(make_briefing(status), self.no_go(), S).value == "no_go"

    @pytest.mark.parametrize("status", ["steps_confirmed", "briefing"])
    def test_go_is_409_before_judging(self, status):
        with pytest.raises(InvalidState):
            sm.decide(make_briefing(status), self.go("some reason"), S)

    @pytest.mark.parametrize("status", ["draft", "steps_proposed", "decided"])
    def test_409_for_any_decision_in_other_states(self, status):
        for body in (self.go("some reason"), self.no_go()):
            with pytest.raises(InvalidState):
                sm.decide(make_briefing(status), body, S)

    def test_nothing_is_writable_after_decided(self):
        b = make_briefing("decided")
        with pytest.raises(InvalidState):
            sm.require_editable(b, "Editing")
        with pytest.raises(InvalidState):
            sm.require_confirmable(b)
        with pytest.raises(InvalidState):
            sm.next_round(b, 3)

    def test_overlong_reason_and_name_are_422(self):
        b = make_briefing("judged", rounds=1, verdicts={"s1": "covered", "s2": "covered"})
        with pytest.raises(Unprocessable):
            sm.decide(b, DecisionBody(value="go", reason="x" * 501), S)
        with pytest.raises(Unprocessable):
            sm.decide(b, DecisionBody(value="go", by="x" * 81), S)
