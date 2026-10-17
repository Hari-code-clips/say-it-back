"""The worker's everyday word, 2026-10-16.12 (build-notes/27). Found on a real run: the Tamil script
spelled an English technical term letter for letter in Tamil script, which a worker does not say,
because the script prompt told the writer to "keep the English site words workers use ... written
in the worker's own script". The prompt now asks for the word a worker on site actually says: a
native everyday word when one is in use, a borrowed word only when that is itself the everyday
spoken word, never a letter-for-letter spelling of an English technical term, and a few extra words
when the everyday word could also name a weaker or different thing. These tests pin the wording in
both places worker-facing words are chosen. The leak rules its examples must obey are in
test_prompt_leak.py, which now reads these two prompts as well."""

from __future__ import annotations

from pathlib import Path

import pytest

from sayitback import prompts

SCRIPT = {
    "worker_lang_name": "Tamil",
    "supervisor_lang_name": "English",
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
RE_EXPLAIN = {"supervisor_lang_name": "Hindi", "steps": [], "sop_title": "X"}


def flat(text: str) -> str:
    return " ".join(text.split())


def script_text(round_kind: str = "initial") -> str:
    return flat(prompts.script_instruction({**SCRIPT, "round_kind": round_kind}))


def re_explain_text() -> str:
    return flat(prompts.re_explain_instruction(RE_EXPLAIN))


# (id, builder, the language the words are chosen in)
WHERE = {
    "script_initial": (lambda: script_text("initial"), "Tamil"),
    "script_reexplain": (lambda: script_text("reexplain"), "Tamil"),
    "re_explain": (re_explain_text, "Hindi"),
}


@pytest.fixture(params=list(WHERE), ids=list(WHERE))
def where(request):
    build, lang = WHERE[request.param]
    return build(), lang


class TestTheRuleIsStated:
    def test_the_word_a_worker_on_site_actually_says(self, where):
        text, lang = where
        assert f"the word a worker on site actually says in {lang}" in text

    def test_a_native_everyday_word_when_one_is_in_use(self, where):
        text, _ = where
        assert "Use a native everyday word when one is in everyday use." in text

    def test_a_borrowed_word_only_when_it_is_the_everyday_word(self, where):
        text, _ = where
        assert (
            "Use a borrowed word (English or any other) only when that borrowed word is itself "
            "the everyday spoken word." in text
        )

    def test_never_a_letter_for_letter_spelling_of_a_term_workers_do_not_say(self, where):
        text, lang = where
        assert (
            "Never spell an English technical term out letter for letter in the "
            f"{lang} writing system when workers do not say it that way" in text
        )

    def test_even_when_the_words_given_use_that_term(self, where):
        text, _ = where
        assert "even if the words you were given use that term" in text

    def test_a_few_words_pin_down_an_ambiguous_word(self, where):
        text, _ = where
        assert "ambiguous in a way that matters for safety" in text
        assert "add a few words so that it can only mean the step's own object" in text

    def test_plain_spoken_register_not_a_formal_or_coined_term(self, where):
        text, _ = where
        assert "in the plain spoken register" in text
        assert "never a formal, literary or newly coined term" in text

    def test_the_ambiguity_example_is_a_neutral_one(self, where):
        text, _ = where
        assert "a chemical-resistant glove and an ordinary glove" in text


class TestTheOldLoanwordRuleIsGone:
    @pytest.mark.parametrize(
        "builder", [script_text, re_explain_text], ids=["script", "re_explain"]
    )
    def test_no_keep_the_english_site_words(self, builder):
        text = builder()
        for old in (
            "keep the English site words",
            "such as breaker, lock",
            "harness, tester",
            "written in Tamil's own script",
        ):
            assert old not in text

    def test_the_script_no_longer_keeps_a_loanword_list(self):
        text = script_text().lower()
        assert "site words" not in text
        assert "breaker" not in text and "harness" not in text and "tester" not in text


class TestTheScriptRuleReachesEveryWorkerFacingPart:
    def test_it_covers_the_sentences_the_questions_and_the_closing(self):
        text = script_text()
        assert "WORDS (for the sentences, the questions and the closing):" in text

    def test_it_comes_after_the_four_outputs_it_governs(self):
        text = script_text()
        assert text.index("4. closing:") < text.index("WORDS (for the sentences")

    def test_it_still_holds_within_the_length_limits(self):
        assert "Keep to the length limits above." in script_text()

    def test_the_supervisors_wording_does_not_override_it(self):
        assert "(the WORDS rule below still applies)" in script_text()

    def test_it_is_in_the_worker_language_not_the_supervisors(self):
        text = script_text()
        assert "the word a worker on site actually says in Tamil" in text
        assert "actually says in English" not in text

    def test_the_other_script_rules_are_still_there(self):
        text = script_text()
        for kept in (
            'State prohibitions explicitly ("Do not ...", "Never ...")',
            "Deliver every step.",
            "Add nothing that is not in the steps",
            "Never yes/no.",
            "A question must NOT contain the key words of its answer",
        ):
            assert kept in text


class TestTheReExplanationRule:
    def test_it_is_a_rule_line_in_the_supervisors_language(self):
        text = re_explain_text()
        assert "- Words: For each object and action, write the word a worker on site" in text
        assert "actually says in Hindi" in text

    def test_an_english_re_explanation_has_every_part_but_the_spelling_sentence(self):
        """An English term cannot be spelled letter for letter in English, so that sentence (and
        only it) is left out when the supervisor speaks English."""
        text = flat(
            prompts.re_explain_instruction({**RE_EXPLAIN, "supervisor_lang_name": "English"})
        )
        assert "the word a worker on site actually says in English" in text
        assert "Use a native everyday word when one is in everyday use." in text
        assert "itself the everyday spoken word. If the everyday word is ambiguous" in text
        assert "letter for letter" not in text

    def test_the_other_re_explain_rules_are_still_there(self):
        text = re_explain_text()
        for kept in (
            "Cover only these steps, in plain words, 2 to 5 short sentences.",
            "Never mention the worker's earlier answer, mistakes or failure.",
            "Add no new steps and no advice outside the steps.",
        ):
            assert kept in text


class TestTheLiveBrieferIsUntouched:
    """The briefer reads the approved script as written. The words are chosen before approval."""

    INP = {"lang_name": "Tamil", "instruction": "X", "questions": [], "closing": "X"}

    def test_it_still_says_it_exactly_as_written(self):
        text = flat(prompts.briefer_instruction(self.INP))
        assert "THE SCRIPT (say it exactly as written, add nothing)" in text
        assert "READ_INSTRUCTION: read INSTRUCTION exactly, then stop." in text

    def test_it_is_given_no_word_choice_rule(self):
        text = flat(prompts.briefer_instruction(self.INP)).lower()
        assert "everyday" not in text and "letter for letter" not in text


class TestVersion:
    def test_the_prompt_version_is_bumped_with_a_reason_line(self):
        assert prompts.PROMPT_VERSION == "2026-10-16.12"
        source = Path(prompts.__file__).read_text(encoding="utf-8")
        reason = next(ln for ln in source.splitlines() if ln.startswith("# .12:"))
        assert "everyday" in reason and "letter" in reason and "script" in reason
