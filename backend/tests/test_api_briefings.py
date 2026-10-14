"""Briefing endpoints at the boundary: create, steps, rounds, list and export."""

from __future__ import annotations

import pytest

from tests.helpers import (
    PANEL,
    error_of,
    post_check,
)


class TestCreateBriefing:
    @pytest.mark.parametrize(
        ("patch", "code"),
        [
            ({"siteId": "mars"}, "unknown_site"),
            ({"taskId": "no-such-task"}, "unknown_task"),
            ({"workerLang": "xx"}, "unsupported_language"),
            ({"supervisorLang": "klingon"}, "unsupported_language"),
            ({"instruction": ""}, "validation_error"),
            ({"instruction": "   "}, "validation_error"),
            ({"instruction": "x" * 1001}, "too_long"),
            ({"taskId": "custom"}, "sop_required"),
        ],
    )
    def test_invalid_input_is_422(self, client, patch, code):
        assert error_of(client.post("/api/briefings", json={**PANEL, **patch})) == (422, code)

    def test_the_instruction_limit_is_1000_characters(self, client):
        assert (
            client.post("/api/briefings", json={**PANEL, "instruction": "x" * 1000}).status_code
            == 200
        )

    def test_a_custom_task_brings_its_own_sop(self, client):
        sop = {"title": "My SOP", "text": "1. Do the thing safely."}
        body = client.post("/api/briefings", json={**PANEL, "taskId": "custom", "sop": sop}).json()
        assert body["sop"] == {"id": "custom", "version": "v1", **sop}

    def test_the_custom_sop_limits(self, client):
        too_long = {"title": "t", "text": "x" * 8001}
        assert (
            error_of(
                client.post("/api/briefings", json={**PANEL, "taskId": "custom", "sop": too_long})
            )[0]
            == 422
        )
        empty = {"title": "t", "text": ""}
        assert (
            error_of(
                client.post("/api/briefings", json={**PANEL, "taskId": "custom", "sop": empty})
            )[0]
            == 422
        )

    def test_a_missing_field_names_the_field_and_never_echoes_input(self, client):
        response = client.post(
            "/api/briefings", json={"siteId": "sg", "instruction": "PRIVATE-TEXT"}
        )
        status, code = error_of(response)
        assert (status, code) == (422, "validation_error")
        assert (
            "taskId" in response.json()["error"]["message"] and "PRIVATE-TEXT" not in response.text
        )

    def test_control_characters_are_stripped(self, client):
        body = client.post(
            "/api/briefings", json={**PANEL, "instruction": "Isolate\x00 it\x07."}
        ).json()
        assert body["instruction"] == "Isolate it."


class TestSteps:
    def put(self, client, bid, steps):
        return client.put(f"/api/briefings/{bid}/steps", json={"steps": steps})

    @pytest.fixture
    def fresh(self, client):
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        client.post(f"/api/briefings/{bid}/steps/extract")
        return bid

    def step(self, i=1, **kw):
        return {
            "id": f"s{i}",
            "text": f"Step {i}",
            "hazard": "h",
            "essential": ["e"],
            "source": "instruction",
            "speakable": True,
            **kw,
        }

    @pytest.mark.parametrize(
        "steps",
        [
            [],
            [{"id": f"s{i}", "text": "x"} for i in range(1, 8)],
            [{"id": "s1", "text": "a"}, {"id": "s1", "text": "b"}],
            [{"id": "s1", "text": ""}],
            [{"id": "s1", "text": "   "}],
            [{"id": "", "text": "a"}],
            [{"id": "bad id!", "text": "a"}],
            [{"id": "s1", "text": "x" * 301}],
            [{"id": "s1", "text": "a", "source": "invented"}],
        ],
    )
    def test_invalid_step_lists_are_422(self, client, fresh, steps):
        assert self.put(client, fresh, steps).status_code == 422

    def test_one_to_six_steps_are_accepted(self, client, fresh):
        assert self.put(client, fresh, [self.step(1)]).status_code == 200
        assert self.put(client, fresh, [self.step(i) for i in range(1, 7)]).status_code == 200

    def test_strings_are_trimmed_and_essentials_capped(self, client, fresh):
        step = self.step(1, text="  trimmed  ", essential=[f"e{i}" for i in range(9)])
        stored = self.put(client, fresh, [step]).json()["steps"][0]
        assert stored["text"] == "trimmed" and len(stored["essential"]) == 6

    def test_409_before_extract_and_after_round_1_exists(self, client, briefing):
        draft = client.post("/api/briefings", json=PANEL).json()["id"]
        assert error_of(self.put(client, draft, [self.step()])) == (409, "invalid_state")
        assert error_of(self.put(client, briefing, [self.step()])) == (409, "invalid_state")


class TestRounds:
    def test_round_1_covers_all_steps_so_other_step_ids_are_422(self, client):
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        steps = client.post(f"/api/briefings/{bid}/steps/extract").json()["steps"]
        client.put(f"/api/briefings/{bid}/steps", json={"steps": steps})
        assert error_of(client.post(f"/api/briefings/{bid}/rounds", json={"stepIds": ["s1"]})) == (
            422,
            "invalid_step_ids",
        )
        assert (
            client.post(
                f"/api/briefings/{bid}/rounds", json={"stepIds": ["s1", "s2", "s3"]}
            ).status_code
            == 200
        )

    def test_round_creation_409s_in_the_wrong_state(self, client):
        bid = client.post("/api/briefings", json=PANEL).json()["id"]
        assert error_of(client.post(f"/api/briefings/{bid}/rounds"))[0] == 409  # draft
        client.post(f"/api/briefings/{bid}/steps/extract")
        assert error_of(client.post(f"/api/briefings/{bid}/rounds"))[0] == 409  # steps_proposed

    def test_a_second_round_1_is_409(self, client, briefing):
        assert error_of(client.post(f"/api/briefings/{briefing}/rounds")) == (409, "invalid_state")

    def test_the_supervisor_note_is_length_limited(self, client, briefing):
        post_check(client, briefing, 1)
        response = client.post(
            f"/api/briefings/{briefing}/rounds", json={"supervisorNote": "x" * 1001}
        )
        assert error_of(response)[0] == 422


class TestListAndExport:
    def test_the_list_is_newest_first_with_summaries(self, client):
        ids = [client.post("/api/briefings", json=PANEL).json()["id"] for _ in range(3)]
        items = client.get("/api/briefings?limit=2").json()["items"]
        assert [i["id"] for i in items] == [ids[2], ids[1]]
        assert set(items[0]) == {
            "id",
            "siteId",
            "taskId",
            "taskTitle",
            "supervisorLang",
            "workerLang",
            "status",
            "rounds",
            "createdAt",
        }
        assert items[0]["taskTitle"] == "Open a distribution panel" and items[0]["rounds"] == 0

    @pytest.mark.parametrize("limit", ["0", "101", "abc"])
    def test_the_limit_is_validated(self, client, limit):
        assert client.get(f"/api/briefings?limit={limit}").status_code == 422

    def test_a_decided_summary_carries_the_decision(self, client, briefing):
        client.post(f"/api/briefings/{briefing}/decision", json={"value": "no_go"})
        item = client.get("/api/briefings").json()["items"][0]
        assert (
            item["status"] == "decided"
            and item["decision"]["value"] == "no_go"
            and item["rounds"] == 1
        )

    def test_the_csv_has_one_row_per_briefing_and_step(self, client, briefing):
        post_check(client, briefing, 1)
        client.post(
            f"/api/briefings/{briefing}/decision",
            json={"value": "go", "reason": "demonstrated it", "by": "=cmd|' /C calc'!A0"},
        )
        response = client.get("/api/export/briefings.csv")
        assert response.headers["content-type"].startswith("text/csv")
        lines = response.text.strip().split("\n")
        assert lines[0] == ("briefingId,createdAt,siteId,taskId,sopId,sopVersion,supervisorLang,workerLang,stepId,stepText,source,"
                            "finalVerdict,rounds,decision,decisionReason,decidedBy,decidedAt")  # fmt: skip
        assert len(lines) == 4 and lines[1].split(",")[0] == briefing
        assert (
            "'=cmd" in response.text and ",=cmd" not in response.text
        )  # spreadsheet formula guard
        assert "go,demonstrated it" in lines[1]
