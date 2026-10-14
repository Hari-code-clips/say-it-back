"""SIB_WEBHOOK_URL: a Google Chat message for chat.googleapis.com, the JSON record for any other."""

from __future__ import annotations

import json

import httpx

from sayitback.models import Briefing, Decision, Round, Script, Sop, Step
from sayitback.webhook import WebhookSender, chat_payload, is_chat_url, json_record, payload_for

CHAT = "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=KEY123&token=TOK456"
OTHER = "https://hooks.example.com/sib?sig=abc"


def decided(
    value="go", open_ids=("s3",), reason="Verified by demonstration.", by="Supervisor A"
) -> Briefing:
    script = Script(instruction="a", questions=[], closing="c")
    return Briefing(
        id="b_abcdefghijkl", site_id="sg", task_id="panel-isolation", supervisor_lang="en", worker_lang="ta",
        sop=Sop(id="SOP-EL-04", version="v3", title="Isolation", text="x"), instruction="secret instruction text",
        status="decided", steps=[Step(id=f"s{i}", text=f"Step {i}", source="instruction") for i in (1, 2, 3)],
        rounds=[Round(n=1, kind="initial", step_ids=["s1"], script=script, created_at="x"),
                Round(n=2, kind="reexplain", step_ids=["s3"], script=script, created_at="x")],
        latest_verdicts={"s1": "covered", "s2": "covered", "s3": "missed"},
        decision=Decision(value=value, reason=reason, by=by, open_step_ids=list(open_ids), at="2026-10-14T10:00:00Z"),
        prompt_version="p", created_at="2026-10-14T09:00:00Z", updated_at="x",
    )  # fmt: skip


class TestChatMessage:
    def test_the_payload_is_exactly_a_text_field(self):
        payload = chat_payload(decided())
        assert set(payload) == {"text"} and isinstance(payload["text"], str)

    def test_the_summary_says_what_was_decided_and_what_is_open(self):
        text = chat_payload(decided())["text"]
        assert "*Say It Back: GO* at Singapore" in text
        assert "Open a distribution panel (English to Tamil), 2 round(s)" in text
        assert "Covered 2 of 3 steps." in text
        assert "Open: Step 3" in text
        assert "Reason: Verified by demonstration." in text
        assert "By: Supervisor A" in text

    def test_no_go_and_an_all_covered_briefing(self):
        text = chat_payload(decided("no_go", open_ids=(), reason=None, by=None))["text"]
        assert "NO-GO" in text and "Covered 3 of 3 steps." in text
        assert "Open:" not in text and "Reason:" not in text and "By:" not in text

    def test_it_carries_no_instruction_transcript_or_audio(self):
        text = chat_payload(decided())["text"]
        assert "secret instruction text" not in text

    def test_it_stays_within_the_chat_size_limit(self):
        assert len(chat_payload(decided(reason="x" * 450))["text"].encode()) < 4096


class TestJsonRecord:
    def test_the_record_has_ids_verdicts_and_the_decision(self):
        record = json_record(decided())
        assert record["event"] == "briefing_decided" and record["briefingId"] == "b_abcdefghijkl"
        assert record["sop"] == {"id": "SOP-EL-04", "version": "v3"}
        assert record["decision"]["value"] == "go" and record["decision"]["openStepIds"] == ["s3"]
        assert [s["finalVerdict"] for s in record["steps"]] == ["covered", "covered", "missed"]
        assert record["rounds"] == 2

    def test_the_record_carries_no_content(self):
        blob = json.dumps(json_record(decided()))
        for banned in ("transcript", "audio", "secret instruction text", "original"):
            assert banned not in blob


class TestRouting:
    def test_only_the_exact_chat_host_gets_a_chat_message(self):
        assert is_chat_url(CHAT)
        for url in (
            OTHER,
            "https://chat.googleapis.com.evil.example/x",
            "https://evil.example/chat.googleapis.com",
            "https://notchat.googleapis.com/x",
        ):
            assert not is_chat_url(url)

    def test_payload_for_picks_the_shape(self):
        assert set(payload_for(CHAT, decided())) == {"text"}
        assert "briefingId" in payload_for(OTHER, decided())


class TestSender:
    async def send(self, url, handler):
        sender = WebhookSender(url, 1.0, httpx.MockTransport(handler))
        return await sender.send(decided()), sender

    async def test_a_chat_url_receives_a_text_post(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((str(request.url), json.loads(request.content)))
            return httpx.Response(200, json={})

        ok, _ = await self.send(CHAT, handler)
        assert ok
        assert seen[0][0] == CHAT
        assert set(seen[0][1]) == {"text"}

    async def test_another_url_receives_the_json_record(self):
        seen = []
        ok, _ = await self.send(
            OTHER, lambda r: (seen.append(json.loads(r.content)), httpx.Response(204))[1]
        )
        assert ok and seen[0]["event"] == "briefing_decided"

    async def test_a_failing_webhook_never_raises(self):
        ok, _ = await self.send(CHAT, lambda r: httpx.Response(500))
        assert ok is False

        def boom(request):
            raise httpx.ConnectError("no route")

        ok, _ = await self.send(CHAT, boom)
        assert ok is False

    async def test_the_url_with_its_key_and_secret_is_never_logged(self, caplog):
        with caplog.at_level("DEBUG"):
            await self.send(CHAT, lambda r: httpx.Response(500))
            await self.send(CHAT, lambda r: httpx.Response(200, json={}))
        assert "KEY123" not in caplog.text and "TOK456" not in caplog.text
        assert "chat.googleapis.com" in caplog.text

    async def test_disabled_without_a_url_or_a_decision(self):
        assert WebhookSender("", 1.0).enabled is False
        assert await WebhookSender("", 1.0).send(decided()) is False
        undecided = decided().model_copy(update={"decision": None})
        assert (
            await WebhookSender(
                OTHER, 1.0, httpx.MockTransport(lambda r: httpx.Response(200))
            ).send(undecided)
            is False
        )
