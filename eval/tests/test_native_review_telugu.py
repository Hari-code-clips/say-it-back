"""17 Oct (build-notes/37-telugu-consent.md): the native-review export writes a Telugu sheet. Read-only on the real tree,
except one sheet written to a temp folder."""

import json

import export_native_review as ex

CATALOG = json.loads((ex.REPO / "backend" / "sayitback" / "data" / "catalog.json").read_text(encoding="utf-8"))


def test_telugu_is_exported_as_a_worker_language():
    assert "te" in ex.LANGS
    assert "te" not in ex.UI_LANGS  # the supervisor UI has no Telugu


def test_the_telugu_sheet_lists_every_worker_word_with_its_english():
    words = {e.key: e for e in ex.build_sheet(ex.REPO, "te").groups["web/src/i18n/worker.ts"]}
    english = ex.const_object((ex.REPO / "web" / "src" / "i18n" / "worker.ts").read_text(encoding="utf-8"), "WORKER_WORDS")["en"]

    assert set(words) == set(english)
    assert words["consentUse"].text.startswith("మీ గొంతు")
    assert words["consentUse"].english.startswith("Your voice goes to Google's computers outside this country")


def test_the_telugu_sheet_lists_the_markers_the_delivery_check_counts():
    sheet = ex.build_sheet(ex.REPO, "te")
    entries = {e.key: e.text for e in sheet.groups["backend/sayitback/data/catalog.json"]}
    spec = CATALOG["languages"]["te"]

    assert entries["languages.te.native"] == "తెలుగు"
    for field in ("negationMarkers", "numberWords", "thanksWords"):
        assert [entries[f"languages.te.{field}[{n}]"] for n in range(len(spec[field]))] == spec[field], field
    assert not [name for name in sheet.groups if "/i18n/" in name and not name.endswith("worker.ts")]


def test_telugu_text_goes_to_the_telugu_sheet_and_kannada_to_none():
    assert ex.script_of("మీ గొంతు దేశం బయట", CATALOG) == "te"
    assert ex.script_of("ನಾನು ಏಣಿಯಿಂದ ಹೋಗುತ್ತೇನೆ", CATALOG) is None  # Kannada is no catalog language


def test_a_telugu_sheet_is_written_to_the_out_folder(tmp_path):
    paths = ex.write_sheets(ex.REPO, tmp_path, ("te",))

    assert [p.name for p in paths] == ["te.md"]
    assert paths[0].read_text(encoding="utf-8").startswith("# Native review: Telugu (te)")
