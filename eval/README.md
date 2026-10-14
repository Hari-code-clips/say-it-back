# Say It Back eval

A labelled test set of spoken worker answers, plus a runner that measures the check workflow
(`sayitback.pipeline.run_check`) against it. It stands in for the real-recording spike until that runs.

## What the set is

`testset/items.json` holds 42 items. Each item is one catalog question, one worker language, one spoken
answer, and gold labels (`covered | missed | contradicted`) for exactly the steps that question maps to.

- **Source: synthetic TTS.** Answers are voiced by `gemini-3.8-flash-tts` (six prebuilt voices). They are
  written as English glosses in `testset/spec.json`, translated per language by `gemini-3.8-flash`, and
  back-translated in a separate call. Items with `fidelity: "review"` need a native check (see below).
  Ten clips were rendered through the Interactions API, with a style annotation. That path then stalled
  for minutes, so the rest use `generate_content` with the style as a text prefix. Both use the same model
  and voice families; the ten clips keep their cache entries.
- **Noise.** 28 clips are clean. 14 are mixed with synthetic site noise at 10 dB (8) or 5 dB (6) SNR. The
  noise is brown and pink noise, 50/100/150 Hz hum and sparse decaying clicks, all from fixed ffmpeg seeds.
  SNR is measured over the whole clip.
- **Languages** (genuine answers, workerLang): ta 9, bn 7, hi 9, or 4, my 4, zh 7. Two more Odia-expected
  items are Hindi answers (wrong language).
- **Patterns:** complete, one_missing, two_missing, contradicted, vague, echo, fluent_wrong, negation,
  numbers, code_switch, wrong_language, silence, and demo (the four catalog demo answers, with their
  expected labels as gold).
- **Policy.** `wrong_language` and `silence` items are gold `unclear` on every step, because the right response
  is to abstain. An `unclear` rating is exact there. A `covered` rating is an unsafe error, and `missed` or
  `contradicted` is caught but not exact. Gold `unclear` is a gold miss for `unsafeErrors`,
  `unsafeDenominator` and `catchRate`, and it is exact only when the prediction is `unclear`.
  Gold `unclear` appears on no other pattern.

## This is not the real-recording spike

The clips are clean, fluent TTS. Real workers have accents, hesitations, code-switching at the site, and
noisy recordings made on the phone. A pass here does not show the judge works on real speech. The gold
labels are the authors' judgement and have not been checked by a native speaker, except as noted below.

**Native review needed:** items whose `fidelity` is `review` (the back-translation drifted from the gloss),
the Odia and Burmese clips, and the hand-corrected Burmese question (`questionFixes` in `spec.json`).

## Add a consented real recording

1. Get written consent from the speaker for use in this eval, and agree how long the clip is kept.
2. Save the clip as 16 kHz mono 16-bit WAV at `testset/recordings/<item-id>.wav`.
3. Add an item to `testset/items.json` with `"source": "recorded"`, `"audio": "recordings/<item-id>.wav"`,
   `"voice": null`, the transcript as `answer`, the English gloss as `answerGloss`, the back-translation,
   `gold` for the question's stepIds, and `fidelity`. `build_testset.py` keeps recorded items across rebuilds.
4. Run `uv run pytest tests/test_items.py`.

## Run

```
cd say-it-back/eval
uv sync                                    # Python 3.13, google-genai 2.30
uv run pytest                              # metric maths, set contract, runner wiring; no network
uv run python build_testset.py             # needs GOOGLE_API_KEY; cached results make no calls
uv run python build_testset.py --only lifting-zone   # re-render clips whose id contains the text
uv run python build_testset.py --skip-audio --offline  # regenerate items.json from the cache; makes no calls
uv run python build_testset.py --spot-check          # transcribe 5 clips back with Flash (5 calls)
uv run python run_eval.py --dry-run        # validate and print the plan; no calls
uv run python run_eval.py                  # the real check (needs the backend, see below)
uv run python run_eval.py --lang ta --limit 5 --repeat 3
```

`run_eval.py` writes `reports/latest.json` (schema in `docs/API.md`) and `reports/latest.md`. The Markdown
report has overall metrics, tables by language, pattern, task and noise, and every unsafe error with the
judge's evidence.

- `--repeat K` runs each item K times. An item is unsafe if any run rates a gold miss as covered. Exact
  accuracy uses the unanimous verdict, or `unclear` when runs disagree.
- Ratios with no denominator show as n/a. In the group tables, `n` counts step ratings.

## Gemini call budget

Every real call is appended to `gemini_calls.log` before it is made. Cache hits are not logged. Each line is
one logical call: `generate_content` runs with a single HTTP attempt, so a line is one request. The whole
project is capped at 70 logged calls, and the build refuses to call past the cap. A 429 or 503 waits 30 s
and retries once; a second failure, or any timeout (180 s), stops the build. A re-run resumes from the cache.
Lines for calls that failed or were aborted stay in the log, so the count includes them.

## Pass bar

- `exactAccuracy` at least 0.80 over step ratings.
- `unsafeErrors` equal to 0.
- With no unsafe error among N gold-miss ratings, the 95% bound is 3/N (the rule of three).

## Backend link

`pyproject.toml` declares the backend as an editable path dependency (`../backend`, package `sayitback`).
`uv sync` installs it with its ADK 2.11 dependencies. `run_eval.py` imports `sayitback.pipeline.run_check`
lazily, so `--dry-run` and the tests do not need the backend's models at run time. The adapter in
`check_adapter.py` passes camelCase dicts, and the backend's Pydantic `Step` and `Question` models accept them.
If the backend renames anything, change only `check_adapter.py`.

## Environment

- `GOOGLE_API_KEY` is read from the environment by the SDK. It is never printed or written to a file.
- `SIB_FLASH_MODEL` and `SIB_TTS_MODEL` override the default model ids (`gemini-3.8-flash`,
  `gemini-3.8-flash-tts`).

## Files

- `spec.json`: the authored glosses, gold labels, notes and hand fixes. Edit this, then rebuild.
- `items.json`: the generated set. `audio/`: its WAV clips. `spotcheck.json`: the spot-check transcripts.
- `build_testset.py`, `testset_text.py`, `audio_tools.py`, `gemini_client.py`: the build.
- `run_eval.py`, `check_adapter.py`, `metrics.py`, `report.py`: the runner.
- `tests/`: pytest.
