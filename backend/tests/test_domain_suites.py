"""17 Oct demo suites (build-notes/37-domain-suites.md): four tasks from other work domains, each with a
demo script that answers every question in both rounds, and a `domain` on every catalog task.

marine (hydro-jetting, en->bn), process plant (steam-line-break, en->ta), manufacturing (press-lockout,
ta->hi) and telecom (telecom-tower, ta->te). Each task has exactly one SOP-only step, the one its sample
instruction leaves out; round 1 gets exactly one step wrong; round 2 covers every step and says each
negation. The backend needed no code but the public field; these tests pin the data and that a real
server lists the suites' stored answers once their clips are rendered."""

from __future__ import annotations

import json

import pytest

from sayitback import catalog, validators
from sayitback.delivery import negations
from sayitback.guards import GuardConfig, is_language_mismatch, script_shares
from sayitback.models import CreateBriefing
from tests.fakes import tone_wav
from tests.helpers import api_client, make_app

DOMAINS = ("construction", "utilities", "marine", "process", "manufacturing", "telecom")
EARLIER = {
    "lifting-zone": "construction", "panel-isolation": "construction", "scaffold-harness": "construction",
    "hot-work": "construction", "trench-entry": "construction", "confined-space": "utilities",
    "fragile-roof": "construction",
}  # fmt: skip
# script -> (task, domain, site, supervisor, worker, the SOP-only step, round 1's wrong step and verdict,
# a word of the SOP-only step that the English sample instruction never says)
SUITES = {
    "sg-hydrojet": ("hydro-jetting", "marine", "sg", "en", "bn", "s3", ("s2", "contradicted"), "pressure"),
    "sg-steam-line": ("steam-line-break", "process", "sg", "en", "ta", "s1", ("s1", "contradicted"), "lock"),
    "chennai-press": ("press-lockout", "manufacturing", "chennai", "ta", "hi", "s3", ("s4", "contradicted"), "block"),
    "chennai-tower": ("telecom-tower", "telecom", "chennai", "ta", "te", "s2", ("s2", "missed"), "antenna"),
}  # fmt: skip


def answers(script_id: str, index: int) -> list[dict]:
    script = catalog.demo_script(script_id)
    return catalog.round_answers(script["taskId"], script["rounds"][index])


# Domains --------------------------------------------------------------------------------------------


def test_every_task_names_one_known_domain_and_the_earlier_seven_keep_theirs():
    tasks = {t["id"]: t for t in catalog.load_catalog()["tasks"]}
    assert all(t.get("domain") in DOMAINS for t in tasks.values()), {k: t.get("domain") for k, t in tasks.items()}
    assert {k: tasks[k]["domain"] for k in EARLIER} == EARLIER
    assert {suite[0]: suite[1] for suite in SUITES.values()} == {
        k: t["domain"] for k, t in tasks.items() if k not in EARLIER
    }


def test_the_public_catalog_carries_each_tasks_domain_for_the_start_screen():
    public = {t["id"]: t["domain"] for t in catalog.public_view()["tasks"]}
    assert public == {t["id"]: t["domain"] for t in catalog.load_catalog()["tasks"]}
    assert set(public.values()) == set(DOMAINS)


# The four tasks -------------------------------------------------------------------------------------


@pytest.mark.parametrize("script_id", sorted(SUITES))
def test_each_task_is_on_its_demo_pair_with_one_sop_only_step_the_instruction_leaves_out(script_id):
    task_id, _domain, site, supervisor, worker, sop_step, _wrong, unsaid = SUITES[script_id]
    task = catalog.task(task_id)
    assert (task["demoSite"], task["demoPair"]) == (site, {"supervisorLang": supervisor, "workerLang": worker})
    assert [s["id"] for s in task["referenceSteps"] if s["source"] == "sop"] == [sop_step]
    assert unsaid not in task["sampleInstruction"]["en"].lower()
    step = next(s for s in task["referenceSteps"] if s["id"] == sop_step)
    assert unsaid in step["text"].lower()  # the word names the SOP-only step's own thing
    assert task["sop"]["version"] == "v1" and task["sop"]["id"].startswith("SOP-")
    assert len(task["referenceQuestions"]) == 2
    assert {s for q in task["referenceQuestions"] for s in q["stepIds"]} == {s["id"] for s in task["referenceSteps"]}
    assert set(task["sampleInstruction"]) == {"en", "ta"} and set(task["title"]) == {"en", "ta"}
    assert "DRAFT" in task["designNote"] and "native review" in task["designNote"]


@pytest.mark.parametrize("script_id", sorted(SUITES))
def test_a_briefing_on_each_demo_pair_is_valid(settings, script_id):
    task_id, _domain, site, supervisor, worker, *_ = SUITES[script_id]
    body = CreateBriefing.model_validate(
        {"siteId": site, "taskId": task_id, "supervisorLang": supervisor, "workerLang": worker,
         "instruction": catalog.task(task_id)["sampleInstruction"][supervisor]}
    )  # fmt: skip
    assert validators.briefing_request(body, settings).id == catalog.task(task_id)["sop"]["id"]
    assert worker in catalog.site(site)["workerLanguages"]


# The four scripts -----------------------------------------------------------------------------------


@pytest.mark.parametrize("script_id", sorted(SUITES))
def test_round_1_gets_exactly_one_step_wrong_and_round_2_covers_every_step(script_id):
    task_id, *_rest, (wrong, verdict), _unsaid = SUITES[script_id]
    steps = [s["id"] for s in catalog.reference_steps(task_id)]
    one = {sid: v for a in answers(script_id, 0) for sid, v in a["expected"].items()}
    two = {sid: v for a in answers(script_id, 1) for sid, v in a["expected"].items()}
    assert one == {**dict.fromkeys(steps, "covered"), wrong: verdict}
    assert two == dict.fromkeys(steps, "covered")
    assert len(catalog.demo_script(script_id)["rounds"]) == 2


@pytest.mark.parametrize("script_id", sorted(SUITES))
def test_every_round_answers_each_question_in_order_and_is_marked_draft(script_id):
    script = catalog.demo_script(script_id)
    assert (script["taskId"], script["siteId"], script["supervisorLang"], script["workerLang"]) == (
        SUITES[script_id][0], *SUITES[script_id][2:5])
    assert "DRAFT" in script["note"] and "native review" in script["note"]
    for index in (0, 1):
        assert [a["questionId"] for a in answers(script_id, index)] == ["q1", "q2"]
        for follow_up in script["rounds"][index]["followUps"]:
            assert "DRAFT" in follow_up["note"] and "native review" in follow_up["note"]


@pytest.mark.parametrize("script_id", sorted(SUITES))
def test_every_answer_is_in_the_workers_script_so_guard_rule_4_never_flags_it(script_id):
    worker = SUITES[script_id][4]
    ranges = catalog.unicode_ranges(worker)
    for index in (0, 1):
        for a in answers(script_id, index):
            text = a["answer"][worker]
            share, latin, _other = script_shares(text, ranges)
            assert share >= 0.9 and latin == 0.0, (script_id, index, a["questionId"], share)
            assert not is_language_mismatch(text, ranges, GuardConfig())
            assert a["answer"]["en"] and set(a["answer"]) == {worker, "en"}


@pytest.mark.parametrize("script_id", sorted(SUITES))
def test_every_round_2_answer_says_a_negation_the_delivery_check_counts(script_id):
    worker = SUITES[script_id][4]
    for a in answers(script_id, 1):
        assert negations(a["answer"][worker], catalog.markers(worker)) >= 1, (script_id, a["questionId"])


def test_no_suite_is_on_a_held_out_task():
    scripted = {s["taskId"] for s in catalog.load_catalog()["demoScripts"]}
    assert not scripted & {"confined-space", "fragile-roof"}
    assert {suite[0] for suite in SUITES.values()} <= scripted


# Endpoint 24 lists the suites' answers once their clips are rendered ---------------------------------


def _item(task_id: str, lang: str, n: int, qid: str, pending: list[str]) -> dict:
    return {
        "id": f"{task_id}.{qid}.{lang}.demo.clean.r{n}", "taskId": task_id, "questionId": qid,
        "workerLang": lang, "pattern": "demo", "noise": "clean", "source": "synthetic_tts", "answer": "…",
        "answerGloss": f"{task_id} {qid} r{n}", "gold": {}, "audio": f"audio/{task_id}.{qid}.r{n}.wav",
        "pending": pending, "demo": {"script": "x", "round": n - 1},
    }  # fmt: skip


def _write_testset(settings, pending: list[str]) -> None:
    testset = settings.eval_dir / "testset"
    (testset / "audio").mkdir(parents=True)
    items = []
    for task_id, _domain, _site, _sup, lang, *_ in SUITES.values():
        for n in (1, 2):
            for qid in ("q1", "q2"):
                (testset / "audio" / f"{task_id}.{qid}.r{n}.wav").write_bytes(tone_wav(1.0))
                items.append(_item(task_id, lang, n, qid, pending))
    doc = {"version": "v", "questions": {}, "items": items}
    (testset / "items.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def test_endpoint_24_lists_all_sixteen_answers_with_their_steps_once_rendered(settings):
    _write_testset(settings, pending=["backTranslation"])
    app, *_ = make_app(settings)
    rows = api_client(app).get("/api/demo-answers").json()["items"]
    got = [(r["taskId"], r["workerLang"], r["round"], r["questionId"], r["stepIds"]) for r in rows]
    want = []
    for task_id, _domain, _site, _sup, lang, *_ in SUITES.values():
        steps = {q["id"]: q["stepIds"] for q in catalog.reference_questions(task_id)}
        want += [(task_id, lang, n, qid, steps[qid]) for n in (1, 2) for qid in ("q1", "q2")]
    assert got == want
    assert ("press-lockout", "hi", 1, "q1", ["s1", "s2", "s3"]) in got


def test_endpoint_24_lists_none_of_them_while_their_clips_are_pending(settings):
    _write_testset(settings, pending=["backTranslation", "audio"])
    app, *_ = make_app(settings)
    assert api_client(app).get("/api/demo-answers").json() == {"items": []}
