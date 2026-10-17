"""17 Oct (build-notes/37-telugu-consent.md): Telugu is a Chennai worker language. A site language the eval set has no item
in must add no question translation to the paid plan until it joins config.WORKER_LANGS. Telugu joined it the same night
with the telecom-tower demo suite's items (build-notes/37-domain-suites.md), so the rule is checked with Telugu taken out."""

import catalog_io
import config
from catalog_io import load_catalog, site_worker_langs
from testset_text import questions_by_language


def chennai_task(catalog: dict) -> dict:
    return next(t for t in catalog["tasks"] if t["demoSite"] == "chennai")


def test_a_site_language_with_no_eval_item_is_left_out_of_the_question_set(monkeypatch):
    catalog = load_catalog()
    chennai = next(s for s in catalog["sites"] if s["id"] == "chennai")
    monkeypatch.setattr(catalog_io, "WORKER_LANGS", tuple(lang for lang in config.WORKER_LANGS if lang != "te"))

    assert "te" in chennai["workerLanguages"]
    assert site_worker_langs(catalog, chennai_task(catalog)) == [lang for lang in chennai["workerLanguages"] if lang != "te"]
    assert "te" not in questions_by_language(catalog)


def test_it_joins_the_question_set_with_the_eval_languages():
    catalog = load_catalog()

    assert "te" in config.WORKER_LANGS  # the telecom-tower demo items are Telugu
    assert "te" in site_worker_langs(catalog, chennai_task(catalog))
    assert "te" in questions_by_language(catalog)
