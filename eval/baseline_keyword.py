"""A keyword baseline for the eval report (plan v0.5, Task 6): what a check with no judge model would score.

It reads the same input the judges get as text, the blind transcriber's English translation of the answer (stored per
item in the report), and each step's catalog `essential` phrases. No model and no network.

- rate(step, translation): covered when every content word of every essential phrase appears in the translation,
  missed when none does, unclear otherwise.
- rate(step, translation, negation=True), the "+negation" variant: the same, except contradicted when an essential
  phrase and the translation's clause that best matches it disagree on negation (one says "never" or "won't" and the
  other does not).

Content words are lowercased whole words with the stopwords below (function words, a few light verbs and every
negation) removed; a possessive "'s" and a final plural "s" are dropped on both sides. There is no other stemming or
synonym list: that is what makes it a keyword check.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace

from catalog_io import task_map
from metrics import Row

NEGATIONS = frozenset({
    "no", "not", "never", "nobody", "nothing", "none", "nowhere", "neither", "nor", "without", "cannot",
})
STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "because", "as", "than", "that", "this", "these",
    "those", "there", "here", "it", "its", "i", "me", "my", "mine", "we", "us", "our", "you", "your", "he", "him",
    "his", "she", "her", "they", "them", "their", "what", "which", "who", "whom", "when", "where", "why", "how",
    "at", "by", "for", "from", "in", "into", "of", "off", "on", "onto", "out", "over", "to", "up", "down", "with",
    "under", "above", "below", "before", "after", "until", "till", "while", "during", "about", "through", "again",
    "all", "any", "both", "each", "every", "some", "such", "only", "own", "same", "too", "very", "just", "also",
    "be", "is", "am", "are", "was", "were", "been", "being", "have", "has", "had", "do", "does", "did", "done",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must", "go", "goes", "going", "went",
    "gone", "get", "gets", "got", "make", "makes", "let", "yes", "ok", "okay", "first", "one",
})
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
_CLAUSE = re.compile(r"[.,;:!?]+|\b(?:and|but|then|so|because|while)\b")


def rate(step: dict, transcript_translation: str, negation: bool = False) -> str:
    """The baseline's verdict for one step (its `essential` phrases) on the English translation of the answer."""
    have = content_words(transcript_translation)
    phrases = [wanted for wanted in (content_words(text) for text in step["essential"]) if wanted]
    if not phrases:
        return "unclear"
    if negation and any(_polarity_differs(text, transcript_translation) for text in step["essential"]):
        return "contradicted"
    hits = [wanted & have for wanted in phrases]
    if all(hit == wanted for hit, wanted in zip(hits, phrases)):
        return "covered"
    return "missed" if not any(hits) else "unclear"


def content_words(text: str) -> set[str]:
    return {_stem(word) for word in _plain(_words(text)) if word not in STOPWORDS}


def is_negated(text: str) -> bool:
    return any(word in NEGATIONS or word.endswith("n't") for word in _words(text))


def _polarity_differs(essential: str, translation: str) -> bool:
    """The clause of the translation that best matches the essential phrase (most shared content words, then most
    shared words; the first wins a tie) says the opposite: one is negated and the other is not. No clause sharing a
    content word, no verdict."""
    wanted = content_words(essential)
    words = set(_words(essential))
    best, best_score = None, (0, 0)
    for clause in _CLAUSE.split(translation):
        score = (len(wanted & content_words(clause)), len(words & set(_words(clause))))
        if score[0] and score > best_score:
            best, best_score = clause, score
    return best is not None and is_negated(best) != is_negated(essential)


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("’", "'"))


def _plain(words: list[str]) -> list[str]:
    """Drop negations and contractions ("i'll", "won't"); a possessive "'s" is cut ("signalman's" -> "signalman")."""
    out = []
    for word in words:
        if word in NEGATIONS or word.endswith("n't"):
            continue
        word = word[:-2] if word.endswith("'s") else word
        if "'" not in word:
            out.append(word)
    return out


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def baseline_rows(rows: Sequence[Row], catalog: dict, negation: bool = False) -> list[Row]:
    """The model's rows with each prediction replaced by the baseline's, read from the row's stored translation."""
    steps = {(task_id, step["id"]): step for task_id, task in task_map(catalog).items()
             for step in task["referenceSteps"]}
    out = []
    for row in rows:
        pred = rate(steps[(row.task_id, row.step_id)], row.translation, negation=negation)
        out.append(replace(row, pred=pred, any_covered=pred == "covered", flags=(), evidence=""))
    return out


def all_baselines(rows: Sequence[Row], catalog: dict) -> dict[str, list[Row]]:
    """The report's `baseline` inputs: keyword, and keyword + negation."""
    return {"keyword": baseline_rows(rows, catalog), "keywordNegation": baseline_rows(rows, catalog, negation=True)}
