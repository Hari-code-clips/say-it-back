# Say It Back eval

A labelled test set of spoken worker answers, plus a runner that measures the check workflow
(`sayitback.pipeline.run_check`) against it. It stands in for the real-recording spike until that runs.

**State at the end of 15 Oct 2026 (v0.5.1):** 58 items (46 in-set, 12 held out), 112 gold step ratings, every item
ready: nothing pending, every clip current, and every question translated. The paid render and two paid eval runs
are done ([`RUN_PAID.md`](RUN_PAID.md), "What happened"); `reports/latest.*` is the judges-low run.

**16 Oct: six demo follow-ups, voiced by a second vendor.** So that stored sample answers answer every question of the
two demos (`docs/API.md`, Deviations 2026-10-16), each demo round now scripts an answer to its task's other questions
too (`catalog.json` `followUps`): `lifting-zone` q2 and q3 in rounds 1 and 2, `scaffold-harness` q2 in rounds 1 and 2.
They are six new `demo` items; with the eight added the same night for hot work (Bengali) and trench entry (Odia), the set is 72 items (60 in-set, 12 held out) and 130 gold step ratings. Their text
comes from the catalog. Their clips were voiced by Sarvam Bulbul (`vendor_tts.py`; `spec.json` names the voice;
`build_testset.py --vendor-only`), with no Google account, and each was transcribed back by Sarvam's STT for a check;
only their back-translations wait for Gemini (RUN_PAID.md, "Next paid run"). Every test passes with no flag.
`reports/latest.*` still covers the 58 items of 15 Oct.

| Run (15 Oct, prompt 2026-10-15.10) | False passes | Exact | Correct passes | Asked again |
|---|---|---|---|---|
| Judges at thinking `low` (`reports/latest.*`, the backend default now) | 0 of 68 gold-miss step ratings (rule-of-three bound 3/68 ≈ 4.5%, if independent) | 87.5% | 39 of 44 | 14.3% |
| Judges at thinking `medium` (`reports/2026-10-15-paid-judges-medium.*`) | 0 of 68 gold-miss step ratings (rule-of-three bound 3/68 ≈ 4.5%, if independent) | 87.5% | 38 of 44 | 14.3% |

In the low run:
- the pass bar is met;
- over the 42 items with a gold miss, the rule-of-three bound is 3/42 ≈ 7.2% (rounded up; it assumes only that the items are independent, not each item's steps);
- the 12 held-out items: 0 false passes in 13 gold-miss ratings, so a rule-of-three bound of 3/13 ≈ 23.1% (n = 13), exact 65.2%, correct passes 60%;
- the model alone, without the silence and wrong_language items: 0 false passes, exact 86.8%;
- the keyword baselines on the same translations: 5 false passes (keyword) and 1 (keyword + negation), at about 34%
  and 39% exact.

Every clip is still synthetic Gemini TTS: no human voice yet (`record_clips.py` is ready for that).

**How to read the bound (17 Oct, review P0-8).** With 0 false passes seen in n trials, the rule of three puts an approximate 95% upper
bound of 3/n on the false-pass rate, but only if the n trials are independent. These are not: the ratings of one answer share
its clip, answers share tasks and voices, the team wrote the answers and the gold labels, and Gemini both voiced and judged
them. So the bound is a heuristic for this constructed, synthetic, team-labelled set, never a false-pass probability for real
workers, and it is always quoted with its denominator: 3/68 ≈ 4.5% over step ratings (4.41%, rounded up), 3/42 ≈ 7.2% over
items, 3/13 ≈ 23.1% over the held-out ratings (n = 13: too few to say much). Since 17 Oct the report says it too
(`report.py`): its headline reads "95% upper bound X% by the rule of three over those ratings, which assumes independent
ratings", and its tables and caveats name the same method and assumption. `reports/latest.*` (15 Oct) predate that and
say only "95% upper bound"; quote them with these words added.

## What the set is

`testset/items.json` holds 88 items in 7 worker languages, every clip rendered (the 30 demo items of 16 and 17 Oct by Sarvam, their back-translations pending; four of them are the 17 Oct domain suites in Telugu, `build-notes/37-domain-suites.md`). Each item is one

The report splits the voices three ways (`byVoice`, 17 Oct): **Gemini TTS voices** (the 58 of 15 Oct), which share the judges' model family; **another vendor's TTS voices** (the 30 Sarvam clips), which do not but are still synthetic; and **recorded human voices**. Quote the three rows separately, never pooled.
catalog question, one worker language, one spoken answer, and gold labels (`covered | missed | contradicted`) for
exactly the steps that question maps to. Gold step ratings: covered 48, missed 36, contradicted 28, unclear 6, so
70 are gold misses, spread over 44 items (until 16 Oct: covered 44, contradicted 26, 68 gold misses over 42 items).

- **Source: synthetic TTS.** Answers are voiced by `gemini-3.8-flash-tts` (six prebuilt voices). They are
  written as English glosses in `testset/spec.json`, translated per language by `gemini-3.8-flash`, and
  back-translated in a separate call. Items with `fidelity: "review"` need a check against their gloss
  (see below). All 56 spoken clips were voiced on 15 Oct through `generate_content` on Agent Platform, with
  the answer text alone (`config.TTS_STYLE` is empty). The first paid render had put a style line ("Say this
  in a calm natural conversational pace") in front of the text, and the TTS sometimes read it aloud into the
  clip, so every clip was voiced again without it. `testset/audio/clips.json` records each clip's render path
  and backend. The 2 silence clips are made locally.
- **Noise.** 44 items are clean (38 rendered, and the 6 follow-ups). 20 are mixed with synthetic site noise at
  10 dB (12) or 5 dB (8) SNR. The noise is brown and pink noise, 50/100/150 Hz hum and sparse decaying clicks, all
  from fixed ffmpeg seeds. SNR is measured over the whole clip.
- **Languages** (genuine answers, workerLang): ta 19, bn 11, hi 13, or 6, my 6, zh 7 (ta 15 and hi 11 before the
  follow-ups). Two more Odia-expected items are Hindi answers (wrong language).
- **Patterns:** complete, one_missing, two_missing, contradicted, vague, echo, fluent_wrong, negation,
  numbers, code_switch, wrong_language, silence, and demo. Demo items are the twelve catalog demo answers
  (`demoScripts`: each round's own answer and, since 16 Oct, its `followUps`), with their expected labels as gold.
  A demo item is keyed by `(taskId, workerLang, demo.round, questionId)`:
  - `sg-lead`: lifting-zone, ta, rounds 1 and 2, questions q1 to q3. This is the lead demo, and round 1's q1 is
    its hard case: "I'll stand under the load and hold it straight with my hand" is gold s1 `contradicted`, s2
    `missed`. Round 1's q2 covers s3 (the signalman) and q3 contradicts s4 (grabs the load by hand); round 2's q2
    and q3 cover s3 and s4.
  - `sg-panel`: panel-isolation, ta, rounds 1 and 2, q1 only.
  - `chennai-second`: scaffold-harness, hi, rounds 1 and 2, q1 and q2 (round 1's q2 unclips once up, s3
    `contradicted`; round 2's stays clipped, s3 `covered`).
- **Lifting-zone hard cases (new, Tamil q1):**
  - `negation.clean`: "I won't go under the load. But while it's coming down, I'll go inside the barrier
    and guide it with my hand." Gold s1 `covered` (the rubric's own negation example), s2 `contradicted`.
  - `fluent_wrong.snr10`: the right words ("outside the barrier") for the wrong action, going under the
    load before it lands. Gold s1 and s2 `contradicted`.

  Both are generated like every other item, from an English gloss through Flash, so their Tamil text is
  pending until the paid run. Nobody wrote it by hand.
- **Held-out tasks (v0.5).** 12 items (`"heldOut": true`) are on two catalog tasks that no demo script and no
  prompt example touches: `confined-space` (sewer manhole entry; hi, or and bn) and `fragile-roof` (ta, bn
  and my). Each task has one item of each pattern complete, one_missing, contradicted, negation,
  fluent_wrong and vague; 23 step ratings, 13 of them gold misses over 8 items. The glosses were written fresh,
  with no phrasing from the prompts (backend `tests/test_prompt_leak.py` checks every gloss against the prompt
  text), and the prompt examples use forklift traffic and chemical decanting, which no task here uses. Every
  other item is `"heldOut": false`. `config.HELD_OUT_TASKS` names the two tasks, and the contract checks that
  `heldOut` is true exactly for their items and that neither task has a demo script. The report scores them
  apart (`byHeldOut`). They are few, so read their bound, not their rate.
- **Panel gold fix (v0.5).** Four panel-isolation answers tested for power before opening the panel, while
  the SOP proves it dead after opening and before touching. Catalog step s3 now says "After opening, ...".
  - Reworded to the SOP order, gold unchanged, so their answer (or back-translation) and clip are pending:
    `panel-isolation.q1.zh.complete.clean`, and the `sg-panel` round-2 line in `catalog.json`
    (`panel-isolation.q1.ta.demo.clean.r2`).
  - Kept in the wrong order, with s3 now gold `contradicted` (was `covered`); answer and clip unchanged:
    `panel-isolation.q1.ta.code_switch.clean` and `panel-isolation.q1.zh.one_missing.clean`.
- **Policy.** `wrong_language` and `silence` items are gold `unclear` on every step, because the right
  response is to abstain.
  - An `unclear` rating is exact there. A `covered` rating is an unsafe error, and `missed` or
    `contradicted` is caught but not exact.
  - Gold `unclear` is a gold miss for `unsafeErrors`, `unsafeDenominator` and `catchRate`, and it is exact
    only when the prediction is `unclear`.
  - Gold `unclear` appears on no other pattern.

## What is pending, and how the set knows

Each item lists in `pending` what is not final: `answer` (its translation has not been made), `backTranslation`,
or `audio` (no clip, or a clip that says other words than `answer`). `[]` means the item is ready.

- `testset/audio/clips.json` records what each clip says: text, voice, model, render path, TTS cache key and the
  file's SHA-256. A clip is current only when all of those match the item.
- Since the 15 Oct render nothing is pending: the earlier clips (the 13 Oct ones, the panel round-1 clip that said
  the older "switch it off" line, and the two panel answers that tested before opening) were all voiced again.
- `pendingQuestions` lists catalog questions not yet translated (empty now). The contract allows an item whose
  question is pending only while its clip is pending too, so a question a catalog change adds can never be
  judged untranslated.
- `run_eval.py` runs an item only when its clip is current and its question has a text. `tests/test_items.py`
  checks that the `pending` marks match the files on disk.

## The ledger: only what changed goes to Gemini

`build_testset.py` treats the previous `items.json` as the record of model outputs:
- an item keeps its worker-language text while its English gloss (`answerGloss`) is unchanged;
- it keeps its back-translation while its text is unchanged;
- a question keeps its worker-language text while the catalog's English is unchanged (`questionSources`);
- a clip is rendered only when it is missing or says something else.

So reordering the catalog, adding a question or adding an item translates and voices only the new rows. This matters
because the old build cached whole batches: the 14 Oct catalog change (lifting-zone moved first, `q3` added) changed
every Singapore-language batch, and a paid build would have re-translated about 30 existing answers and re-voiced
their clips. To redo one item on purpose, change its gloss. To voice one clip again, use `--rerender ITEM_ID`.

## This is not the real-recording spike

The clips are clean, fluent TTS, voiced and judged by models of the same family, which likely flatters the
judges. Real workers have accents, hesitations, code-switching at the site, and noisy recordings made on the
phone. A pass here does not show the judge works on real speech. The gold labels are the authors' judgement and
have not been checked by a native speaker, except as noted below. The report says this in its own words.

**Native review needed:**
- items whose `fidelity` is `review`:
  - the back-translation drifted from the gloss;
  - or the item is new or changed on 14 or 15 Oct and its back-translation has not been read yet (the
    lifting-zone demo and hard-case items, the panel rounds 1 and 2, the reworded Chinese panel answer, and the 12
    held-out items);
- the Odia and Burmese clips;
- the hand-corrected Burmese question (`questionFixes` in `spec.json`);
- the catalog's machine-drafted Tamil: the reworded `sg-panel` round-2 line and the two held-out tasks' titles and
  sample instructions.

## Add consented real recordings (v0.5.1)

`record_clips.py` records a volunteer re-voicing existing items on the Mac microphone, so the set gains real human
voices without new gold labels to write.

```
uv run python record_clips.py --list-devices                    # the Mac's audio inputs (":0" is usually the built-in mic)
uv run python record_clips.py --speaker V01 --lang ta --dry-run # what would be recorded; no mic, nothing written
uv run python record_clips.py --speaker V01 --lang ta --limit 5 # the session
uv run python record_clips.py --forget V01                      # delete V01's clips and items (a deletion request)
uv run pytest tests/test_items.py                               # afterwards
```

- **Consent first.** The tool shows the consent text and records nothing until the volunteer types `yes`. The text
  says the recording is used only to test Say It Back, that it is kept in the public repository and can be played
  on the public evaluation page, that no name is stored, and that it is deleted on request.
- **No names.** The speaker is a code from V01 to V99; keep the list of who is who outside the repo.
- **One take per item.** For each item it shows the question, the English gloss and the worker-language text. The
  volunteer says it in their own words with the same meaning (no step added or left out, every "not" kept), then
  plays it back, redoes it, keeps it or skips. A take is refused if it is shorter than 0.5 s or quieter than
  -45 dBFS. Enter stops a recording; 30 s is the limit.
- **What is saved.** A new item `<item id>.rec.<speaker>` with the source item's task, question, language, pattern,
  gloss and gold, and `source: "recorded"`, `voice: "<speaker>"`, `consent: true`, `recordedFrom`,
  `fidelity: "review"` and `noise: "clean"` (no synthetic noise mixed in; the room's own noise is in the clip). The
  clip is `testset/audio/recorded/<id>.wav`, 16 kHz mono 16-bit. If the volunteer read the text word for word, the
  item keeps the source's text and back-translation; otherwise the transcript can be typed in, or it stays pending.
  A recorded item can run while its transcript is pending, because the judges hear the clip.
- **Not offered:** demo items (endpoint 24 keys on them), silence and wrong_language items, and items whose text or
  question is still pending translation.
- `items_io.problems` checks every recorded item: consent, the speaker code, its clip path and id, and that it
  matches its `recordedFrom` item. `build_testset.py` keeps recorded items across rebuilds. The report scores them
  apart (`bySource`).
- Never run it while `build_testset.py` runs: both write `testset/items.json`.

## Real voices at site noise (16 Oct): the protocol

The set's real-voice numbers come from consented volunteers re-voicing existing items (`record_clips.py`, above), and
from copies of those recordings with synthetic site noise mixed in (`augment_recorded.py`). Real voices, synthetic
noise: this is not a field trial.

1. **Consent.** The volunteer reads the consent text and types `yes`; nothing is recorded before that. Every saved
   item, and every noisy copy of it, says `consent: true`. To withdraw, `record_clips.py --forget V01` deletes the
   recordings, their copies and every clip of that speaker under `audio/recorded/`. Copies already committed or
   deployed must be removed there too.
2. **Speaker codes, never names.** V01 to V99. Keep the list of who is who outside the repo.
3. **Where to record.** A quiet room (fan and TV off, door shut). Hold the microphone about 30 cm from the mouth, as
   a worker holds a phone at chest height, and speak at a normal voice and pace. `--list-devices` shows the Mac's
   inputs: use the phone's microphone if it is listed there, else the built-in one at the same distance.
4. **Say it, don't read it.** In your own words with the same meaning: no step added or left out, and every "not"
   and "never" kept, because the gold labels depend on it.
5. **Add site noise.** Run `uv run python augment_recorded.py --dry-run`, then the same command without `--dry-run`.
   It makes no model call. For every recording it writes 12 copies, `<recording id>.<profile>.<snr>`:
   - `site-drone`: steady machinery hum and generator drone (an engine's low harmonics over rumble);
   - `site-hammer`: hammering and riveting (short decaying knocks with a metal ring, at random intervals);
   - `site-beeper`: a reversing beeper (near 1 kHz, about half a second on and half off);
   - `site-babble`: distant crowd or radio babble (speech-band noise that rises and falls like syllables and
     phrases).

   Each profile is mixed at 10, 5 and 0 dB SNR. The SNR is measured over the speech frames (those within 30 dB of
   the loud frames), not over room tone and pauses, so 0 dB means the noise is as loud as the voice while the person
   speaks. The noise is made in code (`site_noise.py`: no download, licence-clean) and seeded by the recording and the
   profile, so a rerun writes the same bytes and a profile's three SNRs differ only in level. A copy keeps the
   recording's gold, texts, speaker code and consent. It points back with `augmentedFrom` (the recording) and
   `recordedFrom` (the synthetic item both re-voice). A rerun adds what is missing, and brings the copies back in line
   once a transcript is typed in (until then `tests/test_items.py` flags them).
6. **Score them.** `uv run python run_eval.py --source recorded` (paid: RUN_PAID.md, "Real voices") runs only the
   recordings and their copies, into `reports/recorded/`. The report's `bySource.recorded` is the real-voice row, and
   `recordedNoise` splits it: `clean` (as recorded), `siteNoise` (every copy), `bySnr` and `byNoise` (each profile at
   each SNR). The headline names the subset: "Recorded human voices only (N of the M items in the set): ...".

**What the numbers mean.** Real human voices, a real microphone and a real room, judged by the same check as the
synthetic set. The site noise is synthetic and mixed in afterwards, so it lacks the site's own distance, wind and
echo. It also misses the way people raise their voice in noise (the Lombard effect), which makes it a little
harsher than a real site in that one respect. The speakers are few, and each item re-voices a synthetic one with
the same gold, so read the bound over items, not the rate. Quote it as "real voices: N items, F false passes; with
site noise down to 0 dB: ..." next to the synthetic run, and never as a field trial.

## Native review sheets (v0.5.1)

`uv run python export_native_review.py` writes one Markdown sheet per worker language to
`Google_BuilderCup/native-review/<lang>.md`, outside the repo. Each lists every string in that language, grouped by
file, with the English beside it and empty "OK?" and "Fix" columns: the web UI tables (Tamil and Chinese only), the
worker-screen words, the catalog's language name, negation markers, number words, thanks words, task titles, sample
instructions and demo answers, fixed backend strings, and the eval questions and answers (with gloss and
back-translation). It only reads; run it again after any change.

## Run

```
cd say-it-back/eval
uv sync                                    # Python 3.13, google-genai 2.30; the backend is an editable path dependency
uv run pytest -q                           # no network; fails only the every-clip-rendered check until the paid render
uv run pytest -q --allow-missing-audio     # the same, with that one check skipped (its reason lists the pending clips)
uv run python build_testset.py --plan      # count the calls a full build and the eval would make; no call
uv run python build_testset.py --skip-audio --offline  # regenerate items.json with no call; misses stay pending
uv run python build_testset.py             # paid: translate, back-translate and voice what is pending
uv run python build_testset.py --spot-check            # paid: transcribe the 7 spot-check clips back with Flash
uv run python build_testset.py --rescore-spot-check    # score spotcheck.json again (raw and loanword-tolerant); no call
uv run python build_testset.py --rerender ITEM_ID      # paid: voice one clip again, bypassing the cache
uv run python run_eval.py --dry-run        # validate and print the plan; no calls
uv run python run_eval.py                  # paid: the real check (stops if a clip is not current)
uv run python run_eval.py --limit 2 --out reports/smoke   # paid smoke run that leaves reports/latest.* alone
uv run python run_eval.py --lang ta --limit 5 --repeat 3
uv run python run_eval.py --resume         # after a crash, a stop or errored items: runs only what progress.jsonl lacks
uv run python run_eval.py --restart        # discard <out>/progress.jsonl and run everything again
uv run python augment_recorded.py --dry-run   # site-noise copies of the recordings it would write; no call
uv run python run_eval.py --source recorded   # paid: only the real voices and their copies, into reports/recorded/
uv run python demo_stability.py --dry-run     # the lead demo answers' stability plan (6 x 10 runs, 180 calls); no call
```

**A run that survives failures (v0.5.1).** Each finished item is appended at once to `<out>/progress.jsonl`, with
the run's settings: prompt version, models, judge passes, the thinking levels of the transcriber and both judges
(`SIB_THINKING_BLIND_TRANSCRIBER`, `SIB_THINKING_JUDGE_A`, `SIB_THINKING_JUDGE_B`), the `items.json` SHA-256 and the
repeats. A crash or Ctrl-C keeps everything finished; `--resume` reuses those lines and runs the rest, and refuses a
file written under other settings, so two configurations never mix in one report. A run never silently overwrites an
earlier progress file: it stops and asks for `--resume` or `--restart`. A check that raises is tried once more after
20 s. If it fails again, the item is an error: the run goes on, the report lists it under `errors` (class and
message), is `"complete": false` and cannot be quoted, the exit code is 1, and `progress.jsonl` stays so `--resume`
retries only those items. After a run with no error, `progress.jsonl` is removed: the report holds it all. The
report records the settings under `settings`, and its Markdown names the thinking levels.

```
```

`run_eval.py` writes `reports/latest.json` (schema in `docs/API.md`, "Eval report" and Deviations) and
`reports/latest.md`. The Markdown report has these sections:
- a quotable headline: false passes with their rule-of-three bound (3/n; since 17 Oct "95% upper bound X% by the
  rule of three over those ratings, which assumes independent ratings", or the Wilson score interval once a false
  pass is seen; quote it with its n, see "How to read the bound"), exact accuracy, correct passes and asked again;
- a plain statement that the voices are synthetic Gemini TTS, judged by Gemini;
- every contract metric, including (v0.5) `correctPassRate` and the 95% bound over items
  (`unsafeUpperBound95Items`);
- (v0.5) one table of subsets: all items, in-set tasks, held-out tasks, the model alone (no silence or
  wrong_language items, which the code guards catch), and the two keyword baselines;
- tables by language, pattern, task and noise;
- every unsafe error, with the judge's evidence.

v0.5 report fields, all additive: `metrics.correctPassRate`, `metrics.unsafeUpperBound95Items`,
`metrics.unsafeItemDenominator`, `passBar.correctPassMin`, `byHeldOut`, `modelOnly`, `testsetSha256` (the SHA-256 of
the `items.json` bytes the run read), `baseline`, and per item `heldOut` and `translation`. v0.5.1 adds `bySource`
(`synthetic_tts`, `recorded`), and per item `source`, `original` (the blind transcriber's text in the worker's
language) and `ratings` (each gold step's final, guarded rating: `stepId`, `verdict`, and `quote`,
`quoteTranslation`, `reason` and `flags` when present). With `--repeat`, `translation`, `original` and `ratings` come
from the first run. Free text there is cut at 600 characters.

**The keyword baseline** (`baseline_keyword.py`) shows what a check with no judge model would score. It reads the
blind transcriber's English translation of each answer (kept per item as `translation`) and the step's catalog
`essential` phrases: `covered` when every content word of every phrase appears, `missed` when none does, `unclear`
otherwise. The `keywordNegation` variant also says `contradicted` when the clause that best matches a phrase
disagrees with it on negation. The lead hard case, "I'll stand under the load", is `covered` by the first and
`contradicted` by the second.

How to read the numbers:
- `--repeat K` runs each item K times. An item is unsafe if any run rates a gold miss as covered. Exact
  accuracy uses the unanimous verdict, or `unclear` when runs disagree. A correct pass (`correctPassRate`,
  `counts.correctPasses`) needs every run to rate the step covered; a step covered in only some runs is not one.
  Both rules lean the same way: disagreement can only add false passes and remove correct passes.
- `--ready-only` runs only items whose clip is current. The report is then `"complete": false`, and its headline
  says not to quote it.
- Ratios with no denominator show as n/a. In the group tables, `n` counts step ratings.

## Gemini call budget

- **Logging.** Every real build call is appended to `gemini_calls.log` before it is made, and cache hits are not
  logged. Each line is one logical call: `generate_content` runs with a single HTTP attempt, so a line is one
  request.
- **Cap.** The whole project is capped at 70 logged calls (26 used), and the build refuses to call past it.
  `SIB_EVAL_CALL_BUDGET` raises the cap for a paid run; the plan needs 62 calls, so it must be raised (to 160,
  RUN_PAID.md).
- **Retries.** A 429 or 503 waits 30 s and retries once. A second failure, or any timeout (180 s), stops the build.
  A re-run resumes from the cache and the manifest.
- **Failed calls.** Lines for calls that failed or were aborted stay in the log, so the count includes them.
- **The eval is not counted.** `run_eval.py`'s check calls go through the backend and are not logged here.
- **The demo stability run is counted (17 Oct).** `demo_stability.py` writes one line per model call of each check (3 a
  check) before running it, under the same cap, and refuses to start unless `SIB_EVAL_CALL_BUDGET` is set and covers
  its plan (RUN_PAID.md, "Demo stability").

## Pass bar

- `exactAccuracy` at least 0.80 over step ratings.
- `unsafeErrors` equal to 0.
- (v0.5) `correctPassRate` at least 0.75 (`PASS_CORRECT_MIN`), so a checker that asks again on everything it could
  pass cannot meet the bar on exactness alone. A rate that cannot be measured does not meet it.
- With no unsafe error among N gold-miss ratings, the report's 95% bound is 3/N (the rule of three), shown rounded up.
  The rule assumes N independent trials. Steps of one answer are not independent, so the report also gives the bound
  over the N items with a gold miss (`unsafeUpperBound95Items`: 3/42 = 7.2% for the full set), which still assumes
  the items independent (they share tasks, voices and labellers). Quote either with its N and that assumption.

## Backend link

`pyproject.toml` declares the backend as an editable path dependency (`../backend`, package `sayitback`).
`uv sync` installs it with its ADK 2.11 dependencies.
- `run_eval.py` imports `sayitback.pipeline.run_check` lazily, so `--dry-run` and the tests do not need the
  backend's models at run time.
- The adapter in `check_adapter.py` passes camelCase dicts, and the backend's Pydantic `Step` and `Question` models
  accept them. If the backend renames anything, change only `check_adapter.py`.
- Each item's payload is exactly its question's `stepIds`, plus that one question. A step a task gains, such as
  lifting-zone `s4` (asked only by `q3`), cannot reach another item or become `not_asked` noise; the tests prove it.

## Environment

- **Gemini backend.** The build picks its Flash and TTS clients with the backend's own switch (`sayitback.backends`).
  - Agent Platform: `GOOGLE_GENAI_USE_ENTERPRISE=true`, `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION=global`,
    with application-default credentials.
  - `SIB_TTS_BACKEND=developer-api` sends only the voice calls to the Developer API (`GOOGLE_API_KEY`, a billed
    key).
  - The eval's check calls use the backend runtime, with the same variables.
- **Keys.** `GOOGLE_API_KEY` is read from the environment by the SDK. It is never printed or written to a file.
- **Model ids.** `SIB_FLASH_MODEL`, `SIB_TTS_MODEL` and `SIB_JUDGE_B_MODEL` override the defaults
  (`gemini-3.8-flash`, `gemini-3.8-flash-tts`, `gemini-3.1-flash-lite`).

## Files

- `spec.json`: the authored glosses, gold labels, notes and hand fixes. Edit this, then rebuild.
- `items.json`: the generated set. `audio/`: its WAV clips, and `audio/clips.json`, what each one says.
- `spotcheck.json`: the spot-check transcripts.
- The build: `build_testset.py`, `testset_text.py`, `audio_tools.py`, `gemini_client.py`.
- The runner: `run_eval.py`, `check_adapter.py`, `metrics.py`, `report.py`, and `baseline_keyword.py` (v0.5).
- `demo_stability.py` (17 Oct, review P0-16): each lead demo answer checked 10 times on its clip, the labels counted
  into `reports/stability/<date>.*`; exit 1 on a false pass (RUN_PAID.md, "Demo stability").
- `record_clips.py` (v0.5.1): consented human recordings; `audio/recorded/` holds their clips.
- `augment_recorded.py` and `site_noise.py` (16 Oct): site-noise copies of the recordings, and the four noise
  profiles they use.
- `export_native_review.py` (v0.5.1): the native-review sheets.
- `RUN_PAID.md`: the paid run, step by step.
- `tests/`: pytest. `conftest.py` defines `--allow-missing-audio`.
