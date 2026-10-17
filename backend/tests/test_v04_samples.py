"""API v0.4, endpoint 24 (stored sample answers), `meta.sampleAnswers` on the check (13), and the
reference text in the eval items (17). Since 2026-10-16 a demo round stores an answer per question
(its own answer and its catalog `followUps`), listed with `questionId` and `stepIds`."""

from __future__ import annotations

import json

import pytest

from sayitback.evalset import demo_round
from tests.fakes import tone_wav
from tests.flow_support import round_1_scenario
from tests.helpers import api_client, drive_to_round, error_of, make_app, post_check

CLIPS = {
    "r1": tone_wav(1.0), "r2": tone_wav(1.5), "panel": tone_wav(1.2),
    "lz.q2.r1": tone_wav(1.1), "lz.q3.r1": tone_wav(1.3), "lz.q2.r2": tone_wav(1.6),
    "sh.q2.r1": tone_wav(1.4),
}  # fmt: skip
FILES = {  # audio file stem -> clip
    "lifting-zone.r1": "r1", "lifting-zone.r2": "r2", "panel-isolation.r1": "panel",
    "scaffold-harness.r2": "panel",  # stale: pending
    "lifting-zone.q2.r1": "lz.q2.r1", "lifting-zone.q3.r1": "lz.q3.r1", "lifting-zone.q9.r1": "r2",
    "lifting-zone.q2.r2": "lz.q2.r2", "lifting-zone.q3.r2": "r2",  # q3.r2: pending below
    "scaffold-harness.q2.r1": "sh.q2.r1", "panel-isolation.q2.r1": "r2",
}  # fmt: skip


def demo_item(task, lang, n, audio=True, qid="q1", pending=()):
    stem = f"{task}.r{n}" if qid == "q1" else f"{task}.{qid}.r{n}"
    item = {
        "id": f"{task}.{qid}.{lang}.demo.clean.r{n}", "taskId": task, "questionId": qid,
        "workerLang": lang, "pattern": "demo", "noise": "clean", "source": "synthetic_tts",
        "answer": "…", "answerGloss": f"{task} {qid} round {n} gloss", "gold": {"s1": "covered"},
        "audio": f"audio/{stem}.wav" if audio else "audio/missing.wav",
        "pending": list(pending),
    }  # fmt: skip
    item["demo"] = {"script": "x", "round": n - 1}
    return item


def write_testset(settings) -> None:
    testset = settings.eval_dir / "testset"
    (testset / "audio").mkdir(parents=True)
    for stem, clip in FILES.items():
        (testset / "audio" / f"{stem}.wav").write_bytes(CLIPS[clip])
    items = [
        demo_item("lifting-zone", "ta", 1, qid="q2"),  # a follow-up before its round's own answer
        demo_item("lifting-zone", "ta", 1),
        demo_item("lifting-zone", "ta", 1, qid="q3"),
        demo_item("lifting-zone", "ta", 1, qid="q9"),  # the catalog scripts no answer to q9
        demo_item("lifting-zone", "ta", 2),
        demo_item("lifting-zone", "ta", 2, qid="q3", pending=["backTranslation", "audio"]),
        demo_item("lifting-zone", "ta", 2, qid="q2"),
        demo_item("panel-isolation", "ta", 1),
        demo_item("panel-isolation", "ta", 1, qid="q2"),  # sg-panel has no follow-ups
        demo_item("panel-isolation", "ta", 2, audio=False),  # no clip: not offered
        demo_item("scaffold-harness", "hi", 1, audio=False),
        demo_item("scaffold-harness", "hi", 1, qid="q2"),  # its round's own answer has no clip
        demo_item("scaffold-harness", "hi", 2, pending=["backTranslation", "audio"]),
        demo_item("lifting-zone", "my", 1),  # no catalog demo script for Burmese
        {"id": "lifting-zone.q1.ta.complete.clean", "taskId": "lifting-zone", "questionId": "q1",
         "workerLang": "ta", "pattern": "complete", "noise": "clean", "source": "synthetic_tts",
         "answerGloss": "g", "gold": {"s1": "covered", "s2": "missed"}, "audio": "audio/lifting-zone.r1.wav"},
        {"id": "lifting-zone.q3.ta.complete.clean", "taskId": "lifting-zone", "questionId": "q3",
         "workerLang": "ta", "pattern": "complete", "noise": "clean", "source": "synthetic_tts",
         "answerGloss": "g", "gold": {"s4": "covered"}, "audio": "audio/nothing.wav"},
    ]  # fmt: skip
    doc = {"version": "v", "questions": {}, "items": items}
    (testset / "items.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def env(settings):
    write_testset(settings)
    app, _rt, llm, _store = make_app(settings, round_1_scenario())
    return api_client(app), llm, app


def listed(task, lang, n, qid, step_ids):
    return {
        "taskId": task, "workerLang": lang, "round": n, "questionId": qid, "stepIds": step_ids,
        "gloss": f"{task} {qid} round {n} gloss",
    }  # fmt: skip


class TestTheList:
    def test_it_lists_every_question_s_catalog_demo_answer_that_has_a_clip(self, env):
        """Catalog order, a round's answers in reference question order (q2 before q3 even though
        q2's item comes first in items.json), with the reference question's steps. Not listed: a
        pending or missing clip, an answer the catalog does not script (lifting-zone q9, sg-panel
        q2), a language with no demo script."""
        client, llm, _ = env
        items = client.get("/api/demo-answers").json()["items"]
        assert items == [
            listed("lifting-zone", "ta", 1, "q1", ["s1", "s2"]),
            listed("lifting-zone", "ta", 1, "q2", ["s3"]),
            listed("lifting-zone", "ta", 1, "q3", ["s4"]),
            listed("lifting-zone", "ta", 2, "q1", ["s1", "s2"]),
            listed("lifting-zone", "ta", 2, "q2", ["s3"]),
            listed("panel-isolation", "ta", 1, "q1", ["s1", "s2", "s3"]),
            listed("scaffold-harness", "hi", 1, "q2", ["s3"]),
        ]
        assert llm.seen == []  # no Gemini call

    def test_the_v04_fields_are_kept_and_two_are_added(self, env):
        client, *_ = env
        for item in client.get("/api/demo-answers").json()["items"]:
            assert set(item) == {"taskId", "workerLang", "round", "gloss", "questionId", "stepIds"}

    def test_the_real_catalog_scripts_every_question_of_both_demo_rounds(self):
        """sg-lead answers q1-q3 in both rounds, chennai-second q1-q2; sg-panel still q1 only."""
        from sayitback import catalog

        asked = {
            s["id"]: [[a["questionId"] for a in catalog.round_answers(s["taskId"], r)] for r in s["rounds"]]
            for s in catalog.load_catalog()["demoScripts"]
        }  # fmt: skip
        assert asked == {
            "sg-lead": [["q1", "q2", "q3"], ["q1", "q2", "q3"]],
            "sg-panel": [["q1"], ["q1"]],
            "chennai-second": [["q1", "q2"], ["q1", "q2"]],
            "sg-hot-work": [["q1", "q2"], ["q1", "q2"]],  # breadth, 16 Oct (build-notes/34-breadth.md)
            "chennai-trench": [["q1", "q2"], ["q1", "q2"]],
            # demo suites, 17 Oct (build-notes/37-domain-suites.md)
            "sg-hydrojet": [["q1", "q2"], ["q1", "q2"]],
            "sg-steam-line": [["q1", "q2"], ["q1", "q2"]],
            "chennai-press": [["q1", "q2"], ["q1", "q2"]],
            "chennai-tower": [["q1", "q2"], ["q1", "q2"]],
        }

    def test_no_test_set_is_an_empty_list(self, settings):
        app, *_ = make_app(settings)
        assert api_client(app).get("/api/demo-answers").json() == {"items": []}

    def test_it_needs_a_device_key_like_every_route(self, env):
        _, _, app = env
        assert api_client(app, device=None).get("/api/demo-answers").status_code == 401

    def test_an_items_round_is_its_0_based_demo_round_plus_one_and_the_id_is_never_parsed(self):
        assert demo_round({"demo": {"script": "sg-lead", "round": 0}}) == 1
        assert demo_round({"demo": {"script": "sg-lead", "round": 1}}) == 2
        assert demo_round({"id": "a.q1.ta.demo.clean.r1", "variant": "r1", "demo": None}) is None
        assert (
            demo_round({"demo": {"round": -1}}) is None
            and demo_round({"demo": {"round": True}}) is None
        )


class TestTheAudio:
    def url(self, task="lifting-zone", lang="ta", n=1):
        return f"/api/demo-answers/{task}/{lang}/{n}/audio"

    def qurl(self, qid, task="lifting-zone", lang="ta", n=1):
        return f"/api/demo-answers/{task}/{lang}/{n}/{qid}/audio"

    def test_round_1_and_round_2(self, env):
        """The route without a question id is the round's own first answer, as before, though a
        follow-up's item comes first in items.json."""
        client, llm, _ = env
        one = client.get(self.url(n=1))
        assert one.status_code == 200 and one.content == CLIPS["r1"]
        assert one.headers["content-type"] == "audio/wav"
        assert client.get(self.url(n=2)).content == CLIPS["r2"]
        assert llm.seen == []

    def test_every_later_round_gets_round_2s_answer(self, env):
        client, *_ = env
        assert client.get(self.url(n=3)).content == CLIPS["r2"]
        assert client.get(self.qurl("q2", n=3)).content == CLIPS["lz.q2.r2"]

    def test_each_question_has_its_own_route(self, env):
        client, llm, _ = env
        served = {
            (qid, n): client.get(self.qurl(qid, n=n))
            for qid, n in (("q1", 1), ("q2", 1), ("q3", 1), ("q1", 2), ("q2", 2))
        }
        assert {key: r.status_code for key, r in served.items()} == dict.fromkeys(served, 200)
        assert [served[k].content for k in served] == [
            CLIPS[c] for c in ("r1", "lz.q2.r1", "lz.q3.r1", "r2", "lz.q2.r2")
        ]
        assert served[("q2", 1)].headers["content-type"] == "audio/wav"
        hindi = client.get(self.qurl("q2", task="scaffold-harness", lang="hi"))
        assert hindi.content == CLIPS["sh.q2.r1"]
        assert llm.seen == []

    def test_the_old_route_never_serves_a_follow_up_in_place_of_the_rounds_own_answer(self, env):
        client, *_ = env
        # scaffold-harness round 1: q2's follow-up has a clip, the round's own answer has none
        assert error_of(client.get(self.url(task="scaffold-harness", lang="hi"))) == (
            404,
            "no_demo_answer",
        )

    def test_no_such_question_answer_is_404_no_demo_answer(self, env):
        client, *_ = env
        for url in (
            self.qurl("q9"),  # a clip, but no catalog answer to q9
            self.qurl("q3", n=2),  # pending
            self.qurl("q2", task="panel-isolation"),  # sg-panel scripts q1 only
            self.qurl("q1", task="scaffold-harness", lang="hi"),  # no clip
            self.qurl("q1", n=0),
            self.qurl("q1", lang="my"),
            self.qurl("Q1"),
            self.qurl("q1", task="hot-work"),
        ):
            assert error_of(client.get(url)) == (404, "no_demo_answer"), url
        assert client.get(self.qurl("..")).status_code == 404  # never a path
        assert client.get(self.qurl("q1", n="x")).status_code == 422

    def test_no_such_answer_is_404_no_demo_answer(self, env):
        client, *_ = env
        for url in (
            self.url(n=0),
            self.url(task="panel-isolation", n=2),  # its clip is missing
            self.url(lang="my"),  # no demo script
            self.url(task="lifting-zone.."),
            self.url(task="hot-work"),
        ):
            assert error_of(client.get(url)) == (404, "no_demo_answer"), url
        assert client.get(self.url(task="../../etc")).status_code == 404  # never a path
        assert (
            error_of(client.get(self.url(task="scaffold-harness", lang="hi", n=2)))[1]
            == "no_demo_answer"
        )

    def test_a_pending_clip_is_not_served_by_the_eval_routes_either(self, env):
        client, *_ = env
        stale = "scaffold-harness.q1.hi.demo.clean.r2"
        assert error_of(client.get(f"/api/eval/items/{stale}/audio")) == (404, "no_audio")
        items = {i["id"]: i for i in client.get("/api/eval/items").json()["items"]}
        assert items[stale]["hasAudio"] is False
        assert client.get(self.url(n="x")).status_code == 422


class TestSampleAnswersOnTheCheck:
    def post(self, client, bid, samples, **clips):
        files = [
            (q, (f"{q}.wav", d, "audio/wav")) for q, d in (clips or {"q1": tone_wav()}).items()
        ]
        meta = json.dumps({"mode": "turn", "sampleAnswers": samples})
        return client.post(f"/api/briefings/{bid}/rounds/1/check", files=files, data={"meta": meta})

    def test_they_are_stored_on_the_round_and_in_its_event(self, env):
        client, *_ = env
        bid, _ = drive_to_round(client)
        rnd = self.post(client, bid, ["q1"]).json()
        assert rnd["sampleAnswers"] == ["q1"]
        events = client.get(f"/api/briefings/{bid}").json()["events"]
        assert next(e for e in events if e["type"] == "round_judged")["data"]["sampleAnswers"] == [
            "q1"
        ]

    def test_they_are_kept_in_question_order_once_each(self, env):
        client, *_ = env
        bid, _ = drive_to_round(client)
        rnd = self.post(client, bid, ["q2", "q1", "q2"], q1=tone_wav(), q2=tone_wav()).json()
        assert rnd["sampleAnswers"] == ["q1", "q2"]

    def test_none_or_an_empty_list_leaves_the_field_out(self, env):
        client, *_ = env
        bid, _ = drive_to_round(client)
        assert "sampleAnswers" not in self.post(client, bid, []).json()
        bid, _ = drive_to_round(client)
        assert "sampleAnswers" not in post_check(client, bid, 1).json()

    def test_an_id_that_is_not_a_question_of_the_round_or_has_no_clip_is_422(self, env):
        client, llm, _ = env
        bid, _ = drive_to_round(client)
        seen = len(llm.seen)
        assert error_of(self.post(client, bid, ["q9"])) == (422, "validation_error")
        assert error_of(self.post(client, bid, ["q2"])) == (422, "validation_error")  # no q2 clip
        assert error_of(self.post(client, bid, "q1")) == (422, "validation_error")
        assert len(llm.seen) == seen  # refused before any model call


class TestTheEvalItems:
    def test_each_item_has_its_reference_text_and_whether_its_clip_is_here(self, env):
        client, *_ = env
        items = {i["id"]: i for i in client.get("/api/eval/items").json()["items"]}
        complete = items["lifting-zone.q1.ta.complete.clean"]
        assert complete["steps"] == {
            "s1": "Never stand or walk under the load",
            "s2": "Stay outside the barrier until the load is landed",
        }
        assert complete["questionText"] == "Where will you be while the load is moving?"
        assert complete["hasAudio"] is True
        sop_only = items["lifting-zone.q3.ta.complete.clean"]
        assert sop_only["steps"] == {
            "s4": "Control the load with tag lines; never steady it by hand"
        }
        assert sop_only["hasAudio"] is False
        assert "answer" not in complete and "audio" not in complete  # still not public
