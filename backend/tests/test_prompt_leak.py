"""The prompts' worked examples must not leak the answers the eval and the demo use (plan v0.5,
Task 1). An example sentence the judge has seen word for word ("I won't go under the load") would
make an eval item on that sentence a test of recall, not of judgement. So the static prompt text
shares no 4-word run with any English gloss of the test set or any scripted demo answer, and names
none of the catalog's or the held-out set's hazards. Contractions are expanded first, so "I'll be
careful" is the prompt's "I will be careful". No gloss is, or holds, one of the prompt's quoted
examples; a held-out gloss holds none of them, even a one-word one ("yes"). And the examples
themselves share no 3-word phrase with any answer, unless all three words are stopwords ("it is the"):
"walk behind the forklift to guide it" was "I'll go under it to guide it" with the nouns swapped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sayitback import catalog, prompts

SPEC = Path(__file__).resolve().parents[2] / "eval" / "testset" / "spec.json"
N = 4
# Function words: a 3-word phrase made only of these ("i will not", "it is the") is not a copy
_STOPWORDS = """a an the and or but if then so to of in on at by for with from up down out off into
onto i me my we us our you your it its he him his she her they them their this that these those
there here is are was were be been being am will would shall should can could do does did have has
had not no what when while as all any just only also too very than"""
STOPWORDS = frozenset(_STOPWORDS.split())
# The 5 catalog tasks (lifting, panel, scaffold, hot work, trench) and the 2 held-out eval tasks
# (confined-space entry, fragile roofs). The examples use forklift traffic and chemical decanting.
# The 4 demo suites of 2026-10-17 (hydro-jetting, steam line, power press, telecom tower) are the
# last words of the list.
BANNED_WORDS = (
    "load",
    "barrier",
    "harness",
    "scaffold",
    "breaker",
    "panel",
    "trench",
    "crack",
    "fire watch",
    "grind",
    "manhole",
    "confined",
    "roof",
    "guide",  # the lead demo's hard case is "go under it to guide it"
    "jet",
    "nozzle",
    "hull",
    "steam",
    "valve",
    "tongs",
    "antenna",
    "tower",
)
NEUTRAL_EXTRACT = {
    "sop": {"id": "X", "version": "X", "title": "X", "text": "X"},
    "supervisor_lang_name": "X",
    "instruction": "X",
    "max_steps": 6,
}
NEUTRAL_JUDGE = {
    "supervisor_lang_name": "X",
    "worker_lang_name": "X",
    "steps": [],
    "questions": [],
    "transcripts": [],
    "with_audio": True,
}
NEUTRAL_SCRIPT = {
    "worker_lang_name": "X",
    "supervisor_lang_name": "X",
    "round_kind": "initial",
    "site_context": "X",
    "steps": [],
    "basis": "X",
    "max_sentences_per_step": 2,
    "max_line_chars": 90,
    "questions_min": 2,
    "questions_max": 3,
    "previous_questions": [],
}
NEUTRAL_RE_EXPLAIN = {"supervisor_lang_name": "X", "steps": [], "sop_title": "X"}


def static_prompt_text() -> str:
    """Every fixed line the extractor, the script writer, the re-explainer and the judges read, with
    "X" for whatever is per request. The script and re-explain prompts were left out until
    2026-10-16.12, so their word-list example ("breaker, lock, harness, tester") was never checked."""
    return "\n".join(
        (
            prompts.JUDGE_VERDICTS,
            prompts.JUDGE_WITH_AUDIO,
            prompts.JUDGE_NO_AUDIO,
            prompts.extract_instruction(NEUTRAL_EXTRACT),
            prompts.script_instruction(NEUTRAL_SCRIPT),
            prompts.script_instruction({**NEUTRAL_SCRIPT, "round_kind": "reexplain"}),
            prompts.re_explain_instruction(NEUTRAL_RE_EXPLAIN),
            prompts.judge_instruction(NEUTRAL_JUDGE),
            prompts.judge_instruction({**NEUTRAL_JUDGE, "with_audio": False}),
        )
    )


CONTRACTIONS = (
    (r"\bwon't\b", "will not"),
    (r"\bcan't\b", "can not"),
    (r"\bshan't\b", "shall not"),
    (r"n't\b", " not"),
    (r"\bi'm\b", "i am"),
    (r"\bit's\b", "it is"),
    (r"'ll\b", " will"),
    (r"'re\b", " are"),
    (r"'ve\b", " have"),
)


def words(text: str) -> list[str]:
    """Lowercased, contractions expanded ("I'll" is "i will", "won't" is "will not"), punctuation
    stripped."""
    text = text.lower().replace("’", "'")
    for pattern, full in CONTRACTIONS:
        text = re.sub(pattern, full, text)
    return re.sub(r"[^\w\s]", "", text).split()


def ngrams(text: str, n: int = N) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i : i + n]) for i in range(len(w) - n + 1)}


def demo_answers() -> dict[str, str]:
    """Every scripted demo answer, each round's follow-ups included (2026-10-16)."""
    return {
        f"{script['id']} round {i + 1} {a['questionId']}": a["answer"]["en"]
        for script in catalog.load_catalog()["demoScripts"]
        for i, rnd in enumerate(script["rounds"])
        for a in catalog.round_answers(script["taskId"], rnd)
        if (a.get("answer") or {}).get("en")
    }


def eval_glosses(held_out_only: bool = False) -> dict[str, str]:
    if not SPEC.exists():
        return {}
    items = json.loads(SPEC.read_text(encoding="utf-8"))["items"]
    return {
        f"spec item {i} ({it.get('taskId')} {it.get('pattern')})": it["gloss"]
        for i, it in enumerate(items)
        if it.get("gloss") and (it.get("heldOut") or not held_out_only)
    }


def example_phrases() -> list[str]:
    """The prompts' worked examples: every quoted phrase of the judge's verdict rules, and the
    extractor's reactive example."""
    quoted = re.findall(r'"([^"\n]{1,80})"', prompts.JUDGE_VERDICTS)
    reactive = re.findall(r"warning sign \(([^)]+)\)", prompts.extract_instruction(NEUTRAL_EXTRACT))
    return quoted + reactive


def holds(text: str, phrase: str) -> bool:
    """`phrase` is a run of whole words of `text` (both normalised by `words`)."""
    return f" {' '.join(words(phrase))} " in f" {' '.join(words(text))} "


def copied_examples(answers: dict[str, str], *, single_words: bool) -> dict[str, list[str]]:
    """Answers that equal an example phrase, or hold one of 2 words or more (or of any length with
    `single_words`)."""
    found = {}
    for where, answer in answers.items():
        hits = [
            p
            for p in example_phrases()
            if words(answer) == words(p)
            or (holds(answer, p) and (single_words or len(words(p)) > 1))
        ]
        if hits:
            found[where] = hits
    return found


def content_trigrams(text: str) -> set[tuple[str, ...]]:
    return {g for g in ngrams(text, 3) if not all(w in STOPWORDS for w in g)}


def example_trigrams_in(answers: dict[str, str]) -> dict[str, list[str]]:
    """For each (example, answer) pair, the 3-word phrases they share that are not all stopwords."""
    found = {}
    for phrase in example_phrases():
        for where, answer in answers.items():
            common = content_trigrams(phrase) & content_trigrams(answer)
            if common:
                found[f"{phrase!r} / {where}"] = sorted(" ".join(g) for g in common)
    return found


def shared_runs(prompt: str, answers: dict[str, str]) -> dict[str, list[str]]:
    grams = ngrams(prompt)
    found = {}
    for where, answer in answers.items():
        common = sorted(" ".join(g) for g in ngrams(answer) & grams)
        if common:
            found[where] = common
    return found


def test_the_prompt_shares_no_4_word_run_with_a_scripted_demo_answer():
    answers = demo_answers()
    assert answers, "the catalog has scripted demo answers to compare against"
    assert shared_runs(static_prompt_text(), answers) == {}


def test_the_checked_demo_answers_include_every_round_s_follow_ups():
    answers = demo_answers()
    # 6 rounds' own answers and their 6 follow-ups (2026-10-16), + 8 breadth answers, + 16 answers of
    # the four demo suites (2026-10-17)
    assert len(answers) == 36
    assert answers["sg-lead round 1 q3"].startswith("If the load swings, I'll grab it")
    assert answers["chennai-second round 2 q2"].startswith("Only once I'm back on the ground")
    assert answers["chennai-press round 1 q2"].startswith("I'll quickly pull the stuck piece out")


def test_the_prompt_shares_no_4_word_run_with_an_eval_gloss():
    glosses = eval_glosses()
    if not glosses:
        pytest.skip("eval/testset/spec.json is not in this checkout")
    assert shared_runs(static_prompt_text(), glosses) == {}


@pytest.mark.parametrize("word", BANNED_WORDS)
def test_the_prompt_names_no_catalog_or_held_out_hazard(word):
    # a word start, so "cracks" and "loads" are caught but "proof" is not "roof"
    assert re.findall(rf"\b{re.escape(word)}\w*", static_prompt_text().lower()) == []


def test_no_answer_is_or_holds_a_quoted_example():
    """ "OK, understood." (two in-set vague items) holds the one-word examples "OK" and
    "understood": the rule the prompt states, so in-set answers are held to multi-word examples."""
    answers = {**demo_answers(), **eval_glosses()}
    assert copied_examples(answers, single_words=False) == {}


def test_no_held_out_answer_holds_any_quoted_example():
    glosses = eval_glosses(held_out_only=True)
    if not glosses:
        pytest.skip("no held-out items in eval/testset/spec.json")
    assert copied_examples(glosses, single_words=True) == {}


def test_no_example_shares_a_3_word_phrase_with_an_answer():
    assert example_trigrams_in({**demo_answers(), **eval_glosses()}) == {}


def test_the_checked_text_includes_the_script_and_re_explain_prompts():
    """The word-list example in the script prompt ("breaker, lock, harness, tester") named two
    catalog hazards and passed only because this text did not include that prompt."""
    text = static_prompt_text()
    assert "You write the spoken script for a safety briefing" in text
    assert "RE-EXPLANATION" in text  # the script prompt's second round kind
    assert "You help a supervisor" in text


def test_the_old_script_word_list_would_have_been_caught():
    old = "keep the English site words workers use (such as breaker, lock, harness, tester)"
    for word in ("harness", "breaker"):
        assert re.findall(rf"\b{re.escape(word)}\w*", old.lower()), word
        assert word in BANNED_WORDS


def test_the_examples_are_read_from_the_prompt():
    phrases = example_phrases()
    assert "I will be careful" in phrases and "OK" in phrases
    assert any("reversing alarm" in p for p in phrases)


def test_the_check_is_live():
    """The comparison itself works: the old judge example is caught by both checks, a contraction
    does not hide a copy, and a copied example is found."""
    old = 'Negation matters: "I won\'t go under the load" covers it.'
    assert shared_runs(old, {"demo": "I won't go under the load at all."}) != {}
    assert re.search(r"\bload", old.lower())
    assert shared_runs("I will not walk behind it", {"gloss": "I won't walk behind it."}) != {}
    assert " ".join(words("I'll, it's, I'm, can't, isn't")) == "i will it is i am can not is not"
    careful = {"gloss": "Yes, I'll be careful up there."}
    assert copied_examples(careful, single_words=False) == {"gloss": ["I will be careful"]}
    assert copied_examples({"gloss": "Yes, yes."}, single_words=True) == {"gloss": ["yes"]}
    assert copied_examples({"gloss": "Yes, yes."}, single_words=False) == {}
    assert copied_examples({"gloss": "OK."}, single_words=False) == {"gloss": ["OK"]}
    swapped = {"gloss": "I'll go under it to guide it."}
    assert content_trigrams("walk behind the forklift to guide it") & content_trigrams(
        swapped["gloss"]
    ) == {("to", "guide", "it")}
    assert content_trigrams("it is the one") == {("is", "the", "one")}  # "it is the" is ignored


def test_the_de_leak_has_its_reason_line():
    source = Path(prompts.__file__).read_text(encoding="utf-8")
    reason = next(ln for ln in source.splitlines() if ln.startswith("# .8:"))
    assert "leak" in reason
