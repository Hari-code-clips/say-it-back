"""export_native_review.py on a fixture tree in a temp folder (plus one read-only check of the real i18n tables)."""

import json
import re
import shutil
from pathlib import Path

import pytest

import export_native_review as ex

CATALOG = ex.REPO / "backend" / "sayitback" / "data" / "catalog.json"

EN_CORE = """export const core = {
  // a comment, ignored
  'app.home': 'Say It Back home',
  'error.daily': "Today's limit is reached.",
  'long.value':
    'A value on the next line',
  'joined': 'one ' + 'two',
  'escaped': 'it\\'s here',
  'dynamic': `count ${n} left`,
}
"""
TA_CORE = """export const core = {
  'app.home': 'Say It Back முகப்பு',
  'error.daily': "இன்றைய வரம்பு | எட்டப்பட்டது.",
  'long.value':
    'அடுத்த வரியில்',
  'joined': 'ஒன்று ' + 'இரண்டு',
  'escaped': 'இங்கே \\'உள்ளது\\'',
  'dynamic': `${n} மீதம்`,
}
"""
WORKER = """export interface WorkerWords { start: string }
export const WORKER_WORDS: Record<Lang, WorkerWords> = {
  en: { start: 'Start', done: 'Done' },
  ta: { start: 'தொடங்கு', done: 'முடிந்தது' },
  zh: { start: '开始', done: '完成' },
  hi: { start: 'शुरू करें', done: 'हो गया' },
  bn: { start: 'শুরু', done: 'শেষ' },
  or: { start: 'ଆରମ୍ଭ', done: 'ହୋଇଗଲା' },
  my: { start: 'စတင်ပါ', done: 'ပြီးပြီ' },
}
"""
CATALOG_TEXT = """const TASK_TITLES: Partial<Record<Lang, Record<string, string>>> = {
  zh: {
    'panel-isolation': '打开配电箱',
  },
}
const SITE_NAMES: Record<string, Partial<Record<string, string>>> = {
  sg: { ta: 'சிங்கப்பூர்', zh: '新加坡' },
}
const SITE_CONTEXT: Record<string, Partial<Record<string, string>>> = {
  chennai: {
    ta: 'தளத்தின் மொழி தமிழ்.',
  },
}
"""
LANG_NAMES = """export const LANG_NAMES: Record<'en' | 'ta' | 'zh', Record<Lang, string>> = {
  en: { en: 'English', ta: 'Tamil' },
  ta: { en: 'ஆங்கிலம்', ta: 'தமிழ்' },
  zh: { en: '英语', ta: '泰米尔语' },
}
"""
DEMO_PY = '''"""Fixture module."""
TAMIL_QUESTION = "பேனலைத் திறப்பதற்கு முன் என்ன செய்வீர்கள்?"
ENGLISH_ONLY = "What will you do?"


def f():
    LOCAL = "உள்ளே"  # not a module constant
    return LOCAL
'''


def item(item_id: str, lang: str, answer: str, **extra) -> dict:
    return {"id": item_id, "workerLang": lang, "answer": answer, "answerGloss": f"gloss of {item_id}",
            "backTranslation": f"back of {item_id}", "fidelity": "ok", "pending": [], **extra}


ITEMS = {
    "questions": {"trench-entry": {"q1": {"hi": "ट्रेंच में जाने से पहले?", "or": "ଟ୍ରେଞ୍ଚ ପୂର୍ବରୁ?"}}},
    "questionSources": {"trench-entry": {"q1": {"hi": "What will you check and do before you go into the trench?"}}},
    "pendingQuestions": ["confined-space.q1.hi", "fragile-roof.q1.ta"],
    "items": [
        item("a.ta", "ta", "முதல்ல breaker-ஐ ஆஃப் பண்ணுவேன் | சரி", fidelity="review"),
        item("b.or.wrong_language", "or", "मैं सीढ़ी से जाऊँगा।"),  # Hindi spoken where Odia is expected
        item("c.hi.pending", "hi", "", backTranslation="", pending=["answer", "backTranslation", "audio"]),
        item("d.zh", "zh", "先关掉breaker。", backTranslation=""),
        item("e.silence", "zh", "", backTranslation=""),
    ],
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "say-it-back"
    i18n = root / "web" / "src" / "i18n"
    for lang, core in (("en", EN_CORE), ("ta", TA_CORE), ("zh", TA_CORE.replace("முகப்பு", "首页"))):
        for part in ex.UI_PARTS:
            text = core if part == "core" else f"export const {part} = {{\n  '{part}.only': '{lang} {part}',\n}}\n"
            if part == "flow" and lang == "en":  # an English key that the Tamil table keeps in another file
                text = text.replace("}\n", "  'moved.key': 'Moved',\n}\n")
            if part == "pages" and lang == "ta":
                text = text.replace("}\n", "  'moved.key': 'நகர்ந்தது',\n}\n")
            (i18n / lang).mkdir(parents=True, exist_ok=True)
            (i18n / lang / f"{part}.ts").write_text(text, encoding="utf-8")
    (i18n / "worker.ts").write_text(WORKER, encoding="utf-8")
    (i18n / "catalogText.ts").write_text(CATALOG_TEXT, encoding="utf-8")
    (i18n / "langNames.ts").write_text(LANG_NAMES, encoding="utf-8")
    package = root / "backend" / "sayitback"
    (package / "data").mkdir(parents=True)
    shutil.copy(CATALOG, package / "data" / "catalog.json")
    (package / "demo.py").write_text(DEMO_PY, encoding="utf-8")
    (root / "eval" / "testset").mkdir(parents=True)
    (root / "eval" / "testset" / "items.json").write_text(json.dumps(ITEMS, ensure_ascii=False), encoding="utf-8")
    return root


def sheet(repo: Path, lang: str) -> ex.Sheet:
    return ex.build_sheet(repo, lang)


def test_one_sheet_per_language_goes_to_the_out_folder_and_nothing_into_the_tree(repo, tmp_path):
    before = sorted(p for p in repo.rglob("*"))
    out = tmp_path / "native-review"

    assert ex.main(["--out", str(out)], repo=repo) == 0

    assert sorted(p.name for p in out.iterdir()) == sorted(f"{lang}.md" for lang in ex.LANGS)
    assert sorted(p for p in repo.rglob("*")) == before


def test_the_default_folder_is_outside_the_repo():
    assert ex.DEFAULT_OUT == ex.REPO.parent / "native-review"
    assert ex.REPO not in ex.DEFAULT_OUT.parents


def test_the_tamil_sheet_is_grouped_by_source_file_with_english_beside_each_string(repo):
    groups = sheet(repo, "ta").groups

    assert list(groups) == [
        "web/src/i18n/ta/core.ts", "web/src/i18n/ta/flow.ts", "web/src/i18n/ta/pages.ts", "web/src/i18n/worker.ts",
        "web/src/i18n/catalogText.ts", "web/src/i18n/langNames.ts", "backend/sayitback/data/catalog.json",
        "backend/sayitback/demo.py", "eval/testset/items.json"]
    core = {e.key: (e.english, e.text) for e in groups["web/src/i18n/ta/core.ts"]}
    assert core == {
        "app.home": ("Say It Back home", "Say It Back முகப்பு"),
        "error.daily": ("Today's limit is reached.", "இன்றைய வரம்பு | எட்டப்பட்டது."),
        "long.value": ("A value on the next line", "அடுத்த வரியில்"),
        "joined": ("one two", "ஒன்று இரண்டு"),
        "escaped": ("it's here", "இங்கே 'உள்ளது'"),
    }  # the template with ${} is left out: it is not a fixed string
    assert [(e.key, e.english) for e in groups["web/src/i18n/ta/pages.ts"]] == [
        ("pages.only", "en pages"), ("moved.key", "Moved")]
    assert [(e.key, e.english) for e in groups["web/src/i18n/worker.ts"]] == [("start", "Start"), ("done", "Done")]
    assert [(e.key, e.english) for e in groups["web/src/i18n/catalogText.ts"]] == [
        ("SITE_NAMES.sg.ta", "Singapore"), ("SITE_CONTEXT.chennai.ta", next(
            s["context"] for s in json.loads(CATALOG.read_text(encoding="utf-8"))["sites"] if s["id"] == "chennai"))]
    assert [e.key for e in groups["backend/sayitback/demo.py"]] == ["TAMIL_QUESTION"]


def test_the_catalog_group_lists_the_language_name_markers_titles_instructions_and_demo_answers(repo):
    entries = {e.key: e for e in sheet(repo, "ta").groups["backend/sayitback/data/catalog.json"]}
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    markers = catalog["languages"]["ta"]["negationMarkers"]

    assert entries["languages.ta.native"].text == "தமிழ்"
    assert [entries[f"languages.ta.negationMarkers[{n}]"].text for n in range(len(markers))] == markers
    assert entries["tasks.fragile-roof.title"].english == "Work on a fragile roof"
    assert entries["tasks.lifting-zone.sampleInstruction"].text.startswith("லோடுக்கு")
    lead = entries["demoScripts.sg-lead round 1 (q1)"]
    assert lead.english.startswith("I'll stand under the load") and lead.text.startswith("லோடுக்கு")
    follow_up = entries["demoScripts.sg-lead round 2 (q3)"]  # a round's followUps are listed too (16 Oct)
    assert follow_up.english.startswith("If the load swings, I'll steady it") and "டேக் லைன்" in follow_up.text
    assert sum(key.startswith("demoScripts.sg-lead ") for key in entries) == 6
    assert any(key.startswith("languages.ta.numberWords[") for key in entries)
    assert any(key.startswith("languages.ta.thanksWords[") for key in entries)


def test_a_worker_only_language_gets_no_ui_tables(repo):
    for lang in ("hi", "bn", "or", "my"):
        groups = sheet(repo, lang).groups
        assert not [name for name in groups if "/i18n/" in name and not name.endswith("worker.ts")], lang
        assert groups["web/src/i18n/worker.ts"], lang


def test_eval_answers_go_to_the_sheet_of_the_language_they_are_spoken_in(repo):
    hi, odia, ta, zh = (sheet(repo, lang) for lang in ("hi", "or", "ta", "zh"))

    hi_eval = {e.key: e for e in hi.groups["eval/testset/items.json"]}
    assert "b.or.wrong_language" in hi_eval  # Devanagari text, though the item expects Odia
    assert hi_eval["questions.trench-entry.q1"].english == "What will you check and do before you go into the trench?"
    assert [e.key for e in odia.groups["eval/testset/items.json"]] == ["questions.trench-entry.q1"]
    assert [e.key for e in ta.groups["eval/testset/items.json"]] == ["a.ta (fidelity review)"]
    assert [e.key for e in zh.groups["eval/testset/items.json"]] == ["d.zh"]
    assert (hi.pending, ta.pending, zh.pending) == (2, 1, 0)  # pending answers and questions are counted


def test_the_markdown_has_empty_ok_and_fix_columns_and_escapes_cells(repo):
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    text = ex.render(sheet(repo, "ta"), catalog)

    assert text.startswith("# Native review: Tamil (ta)")
    assert "| # | Key | English | தமிழ் (ta) | OK? | Fix |" in text
    assert "| 2 | `error.daily` | Today's limit is reached. | இன்றைய வரம்பு \\| எட்டப்பட்டது. |  |  |" in text
    assert "Gloss: gloss of a.ta<br>Back-translation: back of a.ta" in text
    assert "1 eval texts in Tamil are still waiting" in text
    assert "- [web/src/i18n/ta/core.ts](#websrci18ntacorets) (5)" in text
    rows = [line for line in text.splitlines() if re.match(r"^\| \d+ \|", line)]
    assert rows and all(line.endswith("|  |  |") for line in rows)


def test_the_reader_finds_every_key_of_the_real_ui_tables():
    """Read-only, on the real web/src/i18n: no entry may be lost to a formatting the reader does not know."""
    i18n = ex.REPO / "web" / "src" / "i18n"
    for lang in ("en", *ex.UI_LANGS):
        for part in ex.UI_PARTS:
            text = (i18n / lang / f"{part}.ts").read_text(encoding="utf-8")
            keys = re.findall(r"(?m)^\s*'([^']+)'\s*:", text)
            parsed = ex.const_object(text, part)
            assert keys and [k for k in keys if k not in parsed] == [], (lang, part)
    words = ex.const_object((i18n / "worker.ts").read_text(encoding="utf-8"), "WORKER_WORDS")
    assert set(ex.LANGS) <= set(words) and all(set(words[lang]) == set(words["en"]) for lang in ex.LANGS)


def test_a_site_noise_copy_of_a_recording_is_not_listed_again(tmp_path):
    """augment_recorded.py (16 Oct) writes noisy copies with the recording's own words: the sheet lists them once."""
    base = {"id": "x.rec.V01", "workerLang": "ta", "answer": "நான் போக மாட்டேன்.", "answerGloss": "I won't go.",
            "backTranslation": "", "fidelity": "review", "pending": []}
    copy = {**base, "id": "x.rec.V01.site-hammer.snr5", "augmentedFrom": "x.rec.V01"}
    testset = tmp_path / "eval" / "testset"
    testset.mkdir(parents=True)
    doc = {"questions": {}, "questionSources": {}, "pendingQuestions": [], "items": [base, copy]}
    (testset / "items.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    groups, _ = ex.eval_groups(tmp_path, json.loads(CATALOG.read_text(encoding="utf-8")), "ta")

    assert [entry.key for entry in groups["eval/testset/items.json"]] == ["x.rec.V01 (fidelity review)"]
