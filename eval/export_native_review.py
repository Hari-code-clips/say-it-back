"""Write the native-review sheets (v0.5.1): one Markdown file per worker language listing every string in that
language that a native speaker must check, with the English beside it and empty "OK?" and "Fix" columns.

Each sheet is grouped by the file the strings come from:
- web/src/i18n/<lang>/*.ts, catalogText.ts and langNames.ts: the supervisor UI (Tamil and Chinese only; the UI has
  no other language);
- web/src/i18n/worker.ts: the words on the worker's screen (every worker language);
- backend/sayitback/data/catalog.json: the language's own name, the negationMarkers, numberWords and thanksWords that
  the delivery check counts, task titles and sample instructions, and the scripted demo answers;
- backend/sayitback/*.py: fixed strings in the language's script (module constants, such as demo.py's);
- eval/testset/items.json: the eval questions, and the answers spoken in the language, each with its English gloss
  and its independent back-translation. Texts still pending translation are counted, not listed.

It only reads. The sheets go outside the repo, to Google_BuilderCup/native-review/ by default, because a review
copy is working material, not code.

Usage, from say-it-back/eval:
  uv run python export_native_review.py                    # all seven languages
  uv run python export_native_review.py --lang ta --out /tmp/review
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

LANGS = ("ta", "zh", "hi", "bn", "or", "my", "te")
UI_LANGS = ("ta", "zh")
UI_PARTS = ("core", "flow", "pages")
REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO.parent / "native-review"
MARKER_LISTS = (
    ("negationMarkers", "negation marker: its count in a delivered line must match the approved script"),
    ("numberWords", "number word: its count in a delivered line must match the approved script"),
    ("thanksWords", "a word a neutral thank-you may contain"),
)


@dataclass(frozen=True)
class Entry:
    key: str
    english: str
    text: str


@dataclass(frozen=True)
class Sheet:
    lang: str
    groups: dict[str, list[Entry]]
    pending: int  # eval answers and questions in the language still waiting for translation


# A minimal reader for the TypeScript object literals of the i18n files ------------------------------------------

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}


def _skip(text: str, i: int) -> int:
    """Past whitespace and comments."""
    while i < len(text):
        if text[i].isspace():
            i += 1
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = len(text) if i < 0 else i
        elif text.startswith("/*", i):
            i = text.find("*/", i)
            i = len(text) if i < 0 else i + 2
        else:
            return i
    return i


def _string(text: str, i: int) -> tuple[str | None, int]:
    """A '...', "..." or `...` literal at i (None for a template with ${}), and the index after it; 'a' + 'b' joins."""
    parts, dynamic = [], False
    while True:
        quote, i, buf = text[i], i + 1, []
        while i < len(text) and text[i] != quote:
            if text[i] == "\\":
                buf.append(_ESCAPES.get(text[i + 1], text[i + 1]))
                i += 2
                continue
            if quote == "`" and text.startswith("${", i):
                dynamic, depth, i = True, 1, i + 2
                while i < len(text) and depth:
                    depth += {"{": 1, "}": -1}.get(text[i], 0)
                    i += 1
                continue
            buf.append(text[i])
            i += 1
        parts.append("".join(buf))
        i = _skip(text, i + 1)
        if i < len(text) and text[i] == "+":
            j = _skip(text, i + 1)
            if j < len(text) and text[j] in "'\"`":
                i = j
                continue
        return (None if dynamic else "".join(parts)), i


def _skip_value(text: str, i: int) -> int:
    """Past an expression this reader does not keep, to the ',' or '}' that ends it."""
    depth = 0
    while i < len(text):
        ch = text[i]
        if ch in "'\"`":
            _, i = _string(text, i)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif ch == "," and depth == 0:
            return i
        i += 1
    return i


def parse_object(text: str, i: int) -> tuple[dict, int]:
    """The object literal starting at text[i] == '{': string values and nested objects; anything else is skipped."""
    out: dict = {}
    i = _skip(text, i + 1)
    while i < len(text) and text[i] != "}":
        if text.startswith("...", i):
            i = _skip_value(text, i)
        else:
            if text[i] in "'\"":
                key, i = _string(text, i)
            else:
                m = re.compile(r"[\w$]+").match(text, i)
                key, i = (m.group(0), _skip(text, m.end())) if m else (None, _skip_value(text, i))
            if key is not None and i < len(text) and text[i] == ":":
                i = _skip(text, i + 1)
                if text[i] == "{":
                    out[key], i = parse_object(text, i)
                    i = _skip(text, i + 1)
                elif text[i] in "'\"`":
                    value, i = _string(text, i)
                    if value is not None:
                        out[key] = value
                    i = _skip_value(text, i)
                else:
                    i = _skip_value(text, i)
        i = _skip(text, i)
        if i < len(text) and text[i] == ",":
            i = _skip(text, i + 1)
    return out, i


def const_object(text: str, name: str) -> dict:
    """The object literal assigned to `const <name>` (or `export const <name>`); {} when there is none."""
    m = re.search(rf"\bconst\s+{re.escape(name)}\b[^=]*=\s*\{{", text)
    return parse_object(text, m.end() - 1)[0] if m else {}


# The sources ---------------------------------------------------------------------------------------------------

def ui_groups(repo: Path, lang: str) -> dict[str, list[Entry]]:
    if lang not in UI_LANGS:
        return {}
    i18n = repo / "web" / "src" / "i18n"
    english: dict[str, str] = {}
    for part in UI_PARTS:  # a key may sit in another part file in English
        english.update(const_object((i18n / "en" / f"{part}.ts").read_text(encoding="utf-8"), part))
    groups = {}
    for part in UI_PARTS:
        table = const_object((i18n / lang / f"{part}.ts").read_text(encoding="utf-8"), part)
        groups[f"web/src/i18n/{lang}/{part}.ts"] = [Entry(k, english.get(k, ""), v) for k, v in table.items()]
    return groups


def worker_groups(repo: Path, lang: str, catalog: dict) -> dict[str, list[Entry]]:
    i18n = repo / "web" / "src" / "i18n"
    words = const_object((i18n / "worker.ts").read_text(encoding="utf-8"), "WORKER_WORDS")
    groups = {"web/src/i18n/worker.ts": [Entry(k, words.get("en", {}).get(k, ""), v)
                                         for k, v in words.get(lang, {}).items()]}
    if lang in UI_LANGS:
        text = (i18n / "catalogText.ts").read_text(encoding="utf-8")
        titles = {t["id"]: t["title"]["en"] for t in catalog["tasks"]}
        sites = {s["id"]: s for s in catalog["sites"]}
        entries = [Entry(f"TASK_TITLES.{lang}.{k}", titles.get(k, ""), v)
                   for k, v in const_object(text, "TASK_TITLES").get(lang, {}).items()]
        for table, field in (("SITE_NAMES", "name"), ("SITE_CONTEXT", "context")):
            entries += [Entry(f"{table}.{site}.{lang}", sites.get(site, {}).get(field, ""), by_lang[lang])
                        for site, by_lang in const_object(text, table).items() if lang in by_lang]
        groups["web/src/i18n/catalogText.ts"] = entries
        names = const_object((i18n / "langNames.ts").read_text(encoding="utf-8"), "LANG_NAMES")
        groups["web/src/i18n/langNames.ts"] = [Entry(f"LANG_NAMES.{lang}.{k}", names.get("en", {}).get(k, ""), v)
                                               for k, v in names.get(lang, {}).items()]
    return groups


def catalog_entries(catalog: dict, lang: str) -> list[Entry]:
    spec = catalog["languages"][lang]
    out = [Entry(f"languages.{lang}.native", f"the name of the language ({spec['name']})", spec["native"])]
    for field, meaning in MARKER_LISTS:
        out += [Entry(f"languages.{lang}.{field}[{n}]", meaning, word) for n, word in enumerate(spec.get(field, []))]
    for task in catalog["tasks"]:
        for field in ("title", "sampleInstruction"):
            if task[field].get(lang):
                out.append(Entry(f"tasks.{task['id']}.{field}", task[field]["en"], task[field][lang]))
    for script in catalog["demoScripts"]:
        for n, turn in enumerate(script["rounds"], start=1):
            for answer in (turn, *turn.get("followUps", [])):  # the round's own answer, then its followUps (16 Oct)
                if answer["answer"].get(lang):
                    out.append(Entry(f"demoScripts.{script['id']} round {n} ({answer['questionId']})",
                                     answer["answer"].get("en", ""), answer["answer"][lang]))
    return out


def backend_entries(repo: Path, catalog: dict, lang: str) -> dict[str, list[Entry]]:
    """Module-level string constants written in the language's script."""
    package = repo / "backend" / "sayitback"
    groups: dict[str, list[Entry]] = {}
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str) and script_of(node.value.value, catalog) == lang):
                name = ", ".join(t.id for t in node.targets if isinstance(t, ast.Name))
                groups.setdefault(f"backend/{path.relative_to(repo / 'backend')}", []).append(
                    Entry(name, "(no English beside it in the code)", node.value.value))
    return groups


def eval_groups(repo: Path, catalog: dict, lang: str) -> tuple[dict[str, list[Entry]], int]:
    path = repo / "eval" / "testset" / "items.json"
    if not path.exists():
        return {}, 0
    doc = json.loads(path.read_text(encoding="utf-8"))
    english = {(t["id"], q["id"]): q["text"] for t in catalog["tasks"] for q in t["referenceQuestions"]}
    entries = []
    for task_id, questions in doc["questions"].items():
        for qid, texts in questions.items():
            if lang in texts:
                source = doc.get("questionSources", {}).get(task_id, {}).get(qid, {}).get(lang)
                entries.append(Entry(f"questions.{task_id}.{qid}", source or english.get((task_id, qid), ""),
                                     texts[lang]))
    pending = sum(key.endswith(f".{lang}") for key in doc.get("pendingQuestions", []))
    for item in doc["items"]:
        if item.get("augmentedFrom"):
            continue  # a site-noise copy (augment_recorded.py) repeats its recording's words: review those once
        if not item["answer"]:
            pending += "answer" in item["pending"] and item["workerLang"] == lang
            continue
        if script_of(item["answer"], catalog) != lang:
            continue
        english_cell = f"Gloss: {item['answerGloss']}"
        if item["backTranslation"]:
            english_cell += f"\nBack-translation: {item['backTranslation']}"
        flag = f" (fidelity {item['fidelity']})" if item["fidelity"] != "ok" else ""
        entries.append(Entry(f"{item['id']}{flag}", english_cell, item["answer"]))
    return ({"eval/testset/items.json": entries} if entries else {}), pending


def script_of(text: str, catalog: dict) -> str | None:
    """The worker language whose script most of the text's letters are in (None for none: Latin, digits)."""
    counts: dict[str, int] = {}
    for code in LANGS:
        ranges = [(int(lo, 16), int(hi, 16)) for lo, hi in catalog["languages"][code]["unicodeRanges"]]
        counts[code] = sum(any(lo <= ord(ch) <= hi for lo, hi in ranges) for ch in text)
    best = max(counts, key=lambda code: counts[code])
    return best if counts[best] else None


def build_sheet(repo: Path, lang: str) -> Sheet:
    catalog = json.loads((repo / "backend" / "sayitback" / "data" / "catalog.json").read_text(encoding="utf-8"))
    groups = {**ui_groups(repo, lang), **worker_groups(repo, lang, catalog),
              "backend/sayitback/data/catalog.json": catalog_entries(catalog, lang),
              **backend_entries(repo, catalog, lang)}
    evals, pending = eval_groups(repo, catalog, lang)
    groups.update(evals)
    return Sheet(lang, {name: entries for name, entries in groups.items() if entries}, pending)


# The Markdown --------------------------------------------------------------------------------------------------

def render(sheet: Sheet, catalog: dict) -> str:
    spec = catalog["languages"][sheet.lang]
    total = sum(len(entries) for entries in sheet.groups.values())
    lines = [
        f"# Native review: {spec['name']} ({sheet.lang})",
        "",
        f"Every {spec['name']} string Say It Back shows, speaks or checks: {total} strings in {len(sheet.groups)} "
        "files. All of them are machine drafts. Written by `say-it-back/eval/export_native_review.py` from the "
        "working tree; run it again after any change, and copy your answers over by Key.",
        "",
        f"How to review: in **OK?** write `y` if the {spec['name']} is right and natural for a worker or a "
        "supervisor on a construction site, or `n` and the corrected text in **Fix**. Check above all that every "
        "negation (not, never, don't) and every number survived. Leave the English as it is.",
        "",
    ]
    if sheet.pending:
        lines += [f"{sheet.pending} eval texts in {spec['name']} are still waiting for translation and are not "
                  "listed; run this again after the paid render.", ""]
    lines += [f"- [{name}](#{_anchor(name)}) ({len(entries)})" for name, entries in sheet.groups.items()] + [""]
    for name, entries in sheet.groups.items():
        lines += [f"## {name}", "", f"| # | Key | English | {spec['native']} ({sheet.lang}) | OK? | Fix |",
                  "|---|---|---|---|---|---|"]
        lines += [f"| {n} | `{_cell(e.key)}` | {_cell(e.english)} | {_cell(e.text)} |  |  |"
                  for n, e in enumerate(entries, start=1)]
        lines.append("")
    return "\n".join(lines)


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _anchor(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def write_sheets(repo: Path, out: Path, langs: tuple[str, ...] = LANGS) -> list[Path]:
    catalog = json.loads((repo / "backend" / "sayitback" / "data" / "catalog.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for lang in langs:
        path = out / f"{lang}.md"
        path.write_text(render(build_sheet(repo, lang), catalog), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None, repo: Path = REPO) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", action="append", choices=LANGS, help="one language (repeatable); default all seven")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output folder (default {DEFAULT_OUT})")
    args = parser.parse_args(argv)
    for path in write_sheets(repo, args.out, tuple(args.lang or LANGS)):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
