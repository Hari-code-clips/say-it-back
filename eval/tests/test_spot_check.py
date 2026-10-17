"""The spot-check's tolerant comparison (v0.5.1): a correct code-switched clip is not flagged, and a wrong one still is.
The strings are the real 15 Oct spot-check rows (answer and Flash transcript), copied here as fixtures."""

import json

import pytest

import build_testset as bt

TA_ANSWER = ("முதல்ல breaker-ஐ ஆஃப் பண்ணிட்டு, என் lock மற்றும் tag போடுவேன், அப்புறம் current இல்லைன்னு tester "
             "வச்சு செக் பண்ணிட்டு panel-ஐ திறப்பேன்.")
TA_HEARD = ("முதல்ல பிரேக்கர ஆப் பண்ணிட்டு என் லாக் மற்றும் டேக் போடுவேன் அப்புறம் கரண்ட் இல்லன்னு டெஸ்ட்டர வெச்சு "
            "செக் பண்ணிட்டு பேனல்ல திறப்பேன்.")
ZH_ANSWER, ZH_HEARD = "干完之后我会继续盯着三十分钟。", "干完之后，我会继续盯者30分钟。"
MY_ANSWER, MY_HEARD = "ကျွန်တော် load အောက် မဝင်ဘူး။", "ကျွန်တော် လုပ်အောက် မဝင်ဘူး"
HI_ANSWER = ("अगर मेरे साथी ने जवाब देना बंद कर दिया, तो मैं उसके पीछे नीचे नहीं जाऊँगा। मैं मदद के लिए चिल्लाऊँगा और "
             "ऊपर से ही winch चलाकर उसे ऊपर खींच लूँगा।")
PREFIX = "Say this in a calm, natural, conversational pace. "


@pytest.mark.parametrize(("answer", "heard", "lang"), [(TA_ANSWER, TA_HEARD, "ta"), (ZH_ANSWER, ZH_HEARD, "zh"),
                                                        (MY_ANSWER, MY_HEARD, "my")])
def test_a_correct_clip_with_loanwords_or_numerals_in_another_script_matches(answer, heard, lang):
    tolerant = bt.tolerant_similarity(answer, heard, lang)

    assert bt.similarity(answer, heard) < bt.SPOT_SIMILARITY_MATCH  # the raw score flagged these correct clips
    assert tolerant.score >= bt.SPOT_SIMILARITY_MATCH and bt.spot_match(tolerant)


def test_every_excused_span_is_listed_with_the_loanwords_it_stands_for():
    tolerated = bt.tolerant_similarity(TA_ANSWER, TA_HEARD, "ta").tolerated

    assert [span["loanwords"] for span in tolerated] == [["breaker"], ["lock"], ["tag"], ["current"], ["tester"],
                                                         ["panel"]]
    assert tolerated[0]["heard"] == "பிரேக்கர" and tolerated[-1]["heard"] == "பேனல்ல"


def test_a_wrong_number_is_still_a_mismatch():
    tolerant = bt.tolerant_similarity(ZH_ANSWER, ZH_HEARD.replace("30", "50"), "zh")

    assert not bt.spot_match(tolerant)


def test_a_spoken_style_prefix_fails_even_when_the_answer_is_long_enough_to_keep_the_ratio_high():
    long_answer = HI_ANSWER + " " + HI_ANSWER  # the prefix alone would not pull the ratio under 0.90

    tolerant = bt.tolerant_similarity(long_answer, PREFIX + long_answer, "hi")

    assert tolerant.score >= bt.SPOT_SIMILARITY_MATCH
    assert tolerant.gap > bt.SPOT_GAP_MAX and not bt.spot_match(tolerant)
    assert not bt.spot_match(bt.tolerant_similarity(HI_ANSWER, PREFIX + HI_ANSWER, "hi"))


def test_a_dropped_phrase_or_a_dropped_loanword_is_not_excused():
    dropped_phrase = HI_ANSWER.replace("मैं मदद के लिए चिल्लाऊँगा और ", "")
    dropped_loanword = MY_ANSWER.replace("load ", "")

    assert not bt.spot_match(bt.tolerant_similarity(HI_ANSWER, dropped_phrase, "hi"))
    assert bt.tolerant_similarity(MY_ANSWER, dropped_loanword.replace("load", ""), "my").tolerated == []
    assert bt.tolerant_similarity(MY_ANSWER, "ကျွန်တော် အောက် မဝင်ဘူး", "my").tolerated == []


def test_a_loanword_heard_far_too_long_is_not_excused():
    heard = MY_HEARD.replace("လုပ်", "လုပ်ငန်းခွင်တစ်ခုလုံးကိုစစ်ဆေးပြီး")  # 30-odd characters where one word was

    assert bt.tolerant_similarity(MY_ANSWER, heard, "my").tolerated == []


def test_a_word_for_word_transcript_scores_one_on_both_comparisons():
    assert bt.similarity(TA_ANSWER, TA_ANSWER) == 1.0
    assert bt.tolerant_similarity(TA_ANSWER, TA_ANSWER, "ta").score == 1.0


@pytest.mark.parametrize(("n", "said"), [(3, "三"), (10, "十"), (15, "十五"), (30, "三十"), (35, "三十五"),
                                         (100, "一百"), (105, "一百零五"), (110, "一百一十"), (230, "二百三十"),
                                         (1005, "一千零五")])
def test_chinese_numerals_are_written_as_they_are_said(n, said):
    assert bt.zh_numeral(n) == said


def test_a_row_keeps_the_raw_score_beside_the_tolerant_one():
    item = {"id": "x", "answer": TA_ANSWER, "workerLang": "ta"}

    row = bt.spot_row(item, TA_HEARD, "Tamil")

    assert set(row) == {"id", "answer", "transcript", "language", "similarity", "tolerantSimilarity", "tolerated",
                        "gap", "match"}
    assert row["similarity"] == 0.684 and row["tolerantSimilarity"] >= 0.9 and row["match"] is True


def test_rescoring_rewrites_only_spotcheck_json_from_its_own_transcripts(tmp_path, monkeypatch):
    def no_calls(*args, **kwargs):
        raise AssertionError("rescoring must not make a model call")

    monkeypatch.setattr(bt, "GeminiCalls", no_calls)
    path = tmp_path / "spotcheck.json"
    blocked = {"id": "b", "answer": HI_ANSWER, "transcript": "", "language": "none", "similarity": 0.0,
               "match": False, "blocked": "the model returned no text: SAFETY"}
    path.write_text(json.dumps({"model": "m", "items": [
        {"id": "a", "answer": TA_ANSWER, "transcript": TA_HEARD, "language": "Tamil", "similarity": 0.684,
         "match": False}, blocked]}, ensure_ascii=False), encoding="utf-8")
    doc = {"items": [{"id": "a", "answer": TA_ANSWER, "workerLang": "ta"}, {"id": "b", "answer": HI_ANSWER,
                                                                            "workerLang": "hi"}]}

    rows = bt.rescore_spot_check(doc, path)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["model"] == "m" and stored["items"] == rows
    assert rows[0]["match"] is True and rows[0]["similarity"] == 0.684
    assert rows[1] == blocked
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spotcheck.json"]
