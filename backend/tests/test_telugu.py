"""17 Oct: Telugu (`te`) as a worker language of the Chennai site (build-notes/37-telugu-consent.md).

The catalog entry and every Telugu string here are machine drafts pending native review. These tests pin what the
backend does with the entry: Telugu is offered on Chennai only; guard rule 4 tells a Telugu answer from its neighbours'
scripts (Kannada, Tamil, Devanagari); the delivery check counts negations fused into the Telugu verb (substring match),
including the negative imperative of a verb whose stem ends in క (తాకకండి "don't touch" against తాకండి "touch"), and
Telugu numbers in words and in Telugu digits; the Live briefer is told to speak only Telugu; and a worker's "Not now"
makes no model call at all."""

from __future__ import annotations

import pytest

from sayitback import catalog, validators
from sayitback.delivery import negation_changed, numbers, reply_not_neutral
from sayitback.guards import GuardConfig, is_language_mismatch
from sayitback.live_runner import briefer_state
from sayitback.models import CreateBriefing, Question, Script
from sayitback.prompts import briefer_instruction
from tests.fakes import FakeTtsClient, tone_wav
from tests.helpers import PANEL, api_client, drive_to_round, error_of, make_app, post_check

TE = catalog.unicode_ranges("te")
SPEC = catalog.markers("te")
CFG = GuardConfig()
TE_BRIEFING = {**PANEL, "siteId": "chennai", "supervisorLang": "ta", "workerLang": "te"}
ZWNJ = "‌"  # written inside borrowed words (సూపర్‌వైజర్); normalise drops it

TE_ANSWER = "నేను ముందుగా బ్రేకర్ ఆఫ్ చేసి, దానికి తాళం వేస్తాను."  # I'll switch the breaker off first and lock it
KN_ANSWER = "ನಾನು ಮೊದಲು ಬ್ರೇಕರ್ ಆಫ್ ಮಾಡಿ ಬೀಗ ಹಾಕುತ್ತೇನೆ."  # the same in Kannada, the script nearest to Telugu
TA_ANSWER = "நான் பிரேக்கரை ஆஃப் பண்ணுவேன்"
HI_ANSWER = "मैं पहले ब्रेकर बंद करूँगा और ताला लगाऊँगा।"


# The catalog and validation ------------------------------------------------------------------


def test_telugu_is_a_catalog_language_in_its_own_unicode_block():
    spec = catalog.load_catalog()["languages"]["te"]
    assert (spec["name"], spec["native"], spec["bcp47"], spec["script"]) == ("Telugu", "తెలుగు", "te-IN", "Telu")
    assert TE == ((0x0C00, 0x0C7F),)
    assert SPEC.match == "substring" and SPEC.spaced  # suffixes fuse into the word; words are spaced
    assert catalog.lang_name("te") == "Telugu"
    assert catalog.public_view()["languages"]["te"]["native"] == "తెలుగు"


def test_every_telugu_marker_is_written_in_telugu_letters_only():
    lists = (SPEC.negation_markers, SPEC.number_words, SPEC.thanks_words)
    assert all(lists)
    for word in (w for words in lists for w in words):
        letters = word.replace(ZWNJ, "")
        assert letters and all(0x0C00 <= ord(ch) <= 0x0C7F for ch in letters), word


def test_the_negation_markers_name_the_four_everyday_negatives():
    assert {"లేదు", "కాదు", "వద్దు", "కూడదు"} <= set(SPEC.negation_markers)


def test_chennai_offers_telugu_to_workers_and_singapore_does_not():
    chennai, sg = catalog.site("chennai"), catalog.site("sg")
    assert "te" in chennai["workerLanguages"] and "te" not in chennai["supervisorLanguages"]
    assert chennai["defaultWorkerLanguage"] == "hi"  # the lead Chennai demo stays Tamil -> Hindi
    assert "te" not in sg["workerLanguages"]
    assert "te" not in chennai.get("bcp47Overrides", {})  # te-IN as the catalog says


def test_a_telugu_worker_briefing_is_valid_with_each_chennai_supervisor_language(settings):
    for supervisor in catalog.site("chennai")["supervisorLanguages"]:
        body = CreateBriefing.model_validate({**TE_BRIEFING, "supervisorLang": supervisor})
        assert validators.briefing_request(body, settings).id == "SOP-EL-04"


# Guard rule 4 ------------------------------------------------------------------------------------


def test_rule_4_takes_a_telugu_answer_as_right_for_a_telugu_worker():
    assert not is_language_mismatch(TE_ANSWER, TE, CFG)


@pytest.mark.parametrize("answer", [KN_ANSWER, TA_ANSWER, HI_ANSWER], ids=["kannada", "tamil", "hindi"])
def test_rule_4_flags_a_neighbouring_script_for_a_telugu_worker(answer):
    assert is_language_mismatch(answer, TE, CFG)


def test_rule_4_flags_a_telugu_answer_for_a_tamil_worker():
    assert is_language_mismatch(TE_ANSWER, catalog.unicode_ranges("ta"), CFG)


# The delivery check (guard rule 8) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("approved", "said"),
    [
        ("లోడ్ కింద నిలబడకండి.", "లోడ్ కింద నిలబడండి."),  # don't stand under the load -> stand
        ("కరెంటు తీగను తాకకండి.", "కరెంటు తీగను తాకండి."),  # don't touch the wire -> touch (stem ends in క)
        # ఎక్కండి ("climb") itself holds the letters కండి, so a క-stem's other negatives carry one marker more:
        ("బెల్టు లేకుండా పైకి ఎక్కవద్దు.", "బెల్టు లేకుండా పైకి ఎక్కండి."),  # don't climb -> climb
        ("తడి నిచ్చెన ఎక్కకూడదు.", "తడి నిచ్చెన ఎక్కండి."),  # must not climb -> climb
        ("తడి నిచ్చెన ఎక్కరాదు.", "తడి నిచ్చెన ఎక్కండి."),  # must not climb (formal, as on a sign) -> climb
        ("గుంట లోపలికి ఒంటరిగా వెళ్లకూడదు.", "గుంట లోపలికి ఒంటరిగా వెళ్లాలి."),  # must not go -> must go
        ("బెల్టు లేకుండా పైకి వెళ్లకండి.", "బెల్టు పెట్టుకుని పైకి వెళ్లకండి."),  # "without" turned to "wearing"
        # "if you have not checked the gas, don't go down" -> "if you check the gas, don't go down": the condition flipped
        ("గ్యాస్ చెక్ చేయకపోతే లోపలికి దిగకండి.", "గ్యాస్ చెక్ చేస్తే లోపలికి దిగకండి."),
    ],
    ids=["kandi", "ka-stem", "vaddu", "ka-stem-kudadu", "ka-stem-radu", "kudadu", "kunda", "kapote"],
)
def test_the_delivery_check_catches_a_telugu_negation_dropped_from_the_verb(approved, said):
    assert negation_changed(said, approved, SPEC)
    assert not negation_changed(approved, approved, SPEC)


@pytest.mark.parametrize(
    ("approved", "said"),
    [
        ("లోడ్ కింద నిలబడకండి.", "లోడ్ కింద నిలబడవద్దు."),  # the polite -కండి and వద్దు both say "don't"
        ("కరెంటు తీగను తాకవద్దు.", "కరెంటు తీగను తాకకండి."),  # the same for a క-stem: two markers each
        ("నిచ్చెన ఎక్కకూడదు.", "నిచ్చెన ఎక్కవద్దు."),
    ],
)
def test_a_telugu_negative_said_another_way_is_not_a_change(approved, said):
    assert not negation_changed(said, approved, SPEC)


def test_the_delivery_check_reads_telugu_numbers_in_words_and_in_telugu_digits():
    def said(text: str) -> list[str]:
        return numbers(text, SPEC.number_words, SPEC.match)

    assert said("పది మీటర్ల దూరంలో ఉండండి.") != said("పదిహేను మీటర్ల దూరంలో ఉండండి.")  # 10 against 15
    assert said("ముప్పై నిమిషాలు చూడండి.") != said("మూడు నిమిషాలు చూడండి.")  # 30 against 3
    assert said("రెండున్నర మీటర్లు") == ["రెండు", "న్నర"]  # two and a half
    assert said("౧౦ మీటర్లు") == said("10 మీటర్లు") == ["#10"]  # Telugu digits are digits


def test_a_short_telugu_thanks_is_neutral_and_a_repeated_step_is_not():
    # The script says "stay outside the barricade; don't come in until your supervisor says": the thanks may repeat its
    # "stay" (ఉండండి) and "supervisor" (సూపర్‌వైజర్), which are thanks words, but not a word of the step.
    script = f"బారికేడ్ బయటే ఉండండి. మీ సూపర్{ZWNJ}వైజర్ చెప్పే వరకు లోపలికి రాకండి. మీరు ఎక్కడ ఉంటారు?"
    thanks = f"ధన్యవాదాలు. దయచేసి మీ సూపర్{ZWNJ}వైజర్ కోసం వేచి ఉండండి."
    assert not reply_not_neutral(thanks, script, SPEC)
    assert reply_not_neutral("ధన్యవాదాలు. బారికేడ్ బయటే ఉండండి.", script, SPEC)


def test_the_live_briefer_is_told_to_speak_only_telugu():
    script = Script(
        instruction="లోడ్ కింద నిలబడకండి.",
        questions=[Question(id="q1", text="లోడ్ కింద మీరు ఏం చేయరు?")],
        closing="ధన్యవాదాలు.",
    )
    text = briefer_instruction(briefer_state(script, "te"))
    assert "Speak only Telugu. RESPOND IN TELUGU." in text
    assert "a short neutral thanks in Telugu" in text


# "Not now" (outside review P0-14) ------------------------------------------------------------------


def test_not_now_from_a_telugu_worker_makes_no_model_call(settings):
    """After the worker's "Not now" nothing hears the worker: the check and the Live ticket are refused, and the fake
    model sees no call at all after the decline (the transcriber and both judges would each be one)."""
    tts = FakeTtsClient()
    app, _, llm, _ = make_app(settings.with_overrides(require_consent=True), tts_client=tts)
    client = api_client(app)
    bid, _ = drive_to_round(client, TE_BRIEFING)
    calls_before = len(llm.seen)

    declined = client.post(f"/api/briefings/{bid}/rounds/1/consent", json={"given": False})
    check = post_check(client, bid, 1, q1=tone_wav())
    ticket = client.post(f"/api/briefings/{bid}/rounds/1/live-session")

    assert declined.status_code == 200 and declined.json()["consent"]["given"] is False
    assert error_of(check) == (409, "consent_declined")
    assert error_of(ticket) == (409, "consent_declined")
    assert len(llm.seen) == calls_before
    assert tts.calls == []
    assert client.get(f"/api/briefings/{bid}").json()["workerLang"] == "te"
