# The paid eval run

This is the one paid job left in `eval/`. It renders the missing clips, spot-checks them and runs the eval, on Agent
Platform or a billed key. It produces the numbers on the results page and on deck slide 10. Plan of 15 Oct 2026, for
test set `2026-10-15` (58 items: 46 in-set and 12 on the two held-out tasks, v0.5).

**It spends money. Agree it with Sam first**, as for any billable step. Never use a free-tier AI Studio key: it
allows about 20 requests per model per day, and Google may use free-tier prompts.

## Quoting a bound (17 Oct, review P0-8)

No bound is quoted without its denominator and its assumption. With 0 false passes in n gold-miss ratings, the rule
of three gives 3/n as an approximate 95% upper bound on the false-pass rate **if the n ratings are independent**.
Here they are not: one answer's ratings share a clip, answers share tasks and voices, the team wrote the answers and
the gold, and Gemini voiced and judged them. Read it as a heuristic for this synthetic, team-labelled set, not as a
false-pass probability for real workers. Today's numbers (15 Oct run): 0 in 68 step ratings, 3/68 ≈ 4.5% (4.41%,
rounded up); 0 in 42 items with a gold miss, 3/42 ≈ 7.2%; held out, 0 in 13 ratings, 3/13 ≈ 23.1% (n = 13). Since
17 Oct the generated report says it too (`report.py`): the headline reads "95% upper bound X% by the rule of three over
those ratings, which assumes independent ratings" (the Wilson score interval once a false pass is seen), and the tables
and caveats name the same method and assumption. `reports/latest.*` (15 Oct) predate that and say only "95% upper
bound", so add the assumption when quoting them.

## Next paid run (16 Oct): the six demo follow-ups' back-translations, then the eval

Stored sample answers now answer every question of the two demos (`docs/API.md`, Deviations 2026-10-16), so six
`demo` items were added (`lifting-zone.q2.ta.demo.clean.r1`, `.q3.ta.demo.clean.r1`, `.q2.ta.demo.clean.r2`,
`.q3.ta.demo.clean.r2`, `scaffold-harness.q2.hi.demo.clean.r1`, `.q2.hi.demo.clean.r2`). Their text is the catalog's.

**Their clips are done (16 Oct, no Google account):** voiced by a second TTS vendor, Sarvam Bulbul
(`bulbul:v4-flash`; Tamil `vijay_ta_narration`, Hindi `rahul_hi_conversational`) through `vendor_tts.py`:
`SARVAM_API_KEY=... uv run python build_testset.py --vendor-only` (Gemini stays offline). 10 calls are in
`vendor_calls.log` (6 first takes, and the 4 Tamil clips voiced again after a check), about 670 characters, about
INR 1.4. Each clip was transcribed back with Sarvam's speech-to-text (`saaras:v4`): tolerant similarity 0.95 to 1.0.
The first Tamil voice (`gokul_ta_narration`) said டேக் லைன் (tag line) so that two STT models heard பேக் லைன், so
the Tamil four use Vijay. Only their back-translations wait for Gemini.

`build_testset.py --plan` now (17 Oct, after the breadth items and the four domain suites, all voiced by Sarvam):
translate 7 (the 30 pending question texts, one call per language), back-translate 2 (30 answers), TTS 0, Sarvam 0;
eval 99 items x 3 = 297 calls (about USD 0.56, an estimate): the 88 synthetic items and, since 17 Oct, Sam's 11 recorded Tamil answers (speaker V01). With the 159 logged lines and one retry each:
`SIB_EVAL_CALL_BUDGET=180` (plus the lines the demo stability run below added, if it ran first).
Steps, with the environment of step 0 below:

```bash
uv run python build_testset.py --plan        # expect: translate 7, back-translate 2 (30 answers), TTS 0
uv run python build_testset.py               # 10 text calls; no clip is rendered
uv run pytest -q -rs                         # every test passes, with no flag (CI dropped it on 16 Oct)
uv run python run_eval.py --dry-run          # expect: 99 items, 179 step ratings, 297 model calls, none not ready
uv run python run_eval.py                    # 297 calls; --resume after a stop
```

Then read the 30 back-translations against their gloss (set `"fidelity": "ok"` in `spec.json` only for a match,
then `uv run python build_testset.py --skip-audio --offline`), and the deck needs `EVAL_ITEMS = 99` and
`EVAL_GOLD_MISS = 92` in `deck/deck_content.py` before it shows the new report. Then redeploy as in "Afterwards".

## Demo stability (17 Oct, review P0-16): each lead stored answer, 10 runs, on the release build

On 15 Oct identical audio came back "Ask again" in one run and "Got it" in another. `demo_stability.py` runs the check
(`pipeline.run_check`, as `run_eval.py` calls it) 10 times on each stored answer of the lead demo, `sg-lead` (rounds 1
and 2, q1 to q3: 6 items, each on its own clip), round by round, and counts every step's labels into
`reports/stability/<date>.json` and `.md` (a second run that day writes `<date>-2`; nothing is overwritten).

**Stop rule.** A gold-miss step (gold missed, contradicted or unclear) rated covered ("Got it") in any run blocks the
release: exit code 1, verdict `blocked`, the step named in the report's first line. Do not release that build: find
the cause (the report's flags and distinct-transcript counts are the first clues), fix it, and run the whole check
again on the fixed build. Exit 2 is no verdict: the run was refused before any call (no report), or its counts are
short (verdict `incomplete`: a check failed twice, the budget ran out, or Ctrl-C); fix the cause and run it again.
`caffeinate` passes the exit code through. Only exit 0, with 10 runs of every item, clears the "Demo stability" line of
`SUBMISSION_CHECKLIST.md`. "Ask again" on a gold "Got it" step costs a re-ask, not safety: record it, don't block on it.

**Calls: 6 items x 10 runs x 3 model calls (transcriber, judge A, judge B) = 180**, about USD 0.36 at the measured
$0.006 a check (an upper estimate). Unlike `run_eval.py`, each check's three calls are written to `gemini_calls.log`
before it runs, one line per model call, under the build's cap `SIB_EVAL_CALL_BUDGET`, which must be set: the run
refuses to start without it, or when the log plus 180 would pass it. With the 159 lines logged today that is at least
339; 360 leaves room for 7 retried checks (a check that raises is tried once more, 3 more lines; at the cap the run
stops, incomplete). The backend's own retries of one call (`SIB_RETRY_ATTEMPTS`) stay inside its line. The lines count
against the build's cap too: a later build's budget ("Next paid run") rises by the report's `callsLogged`. Time: one
check at a time, about 15 to 40 minutes.

**The release build.** Run it from the tree that is deployed, with the service's model settings: the environment of
step 0 below, plus `SIB_MAX_OUTPUT_TOKENS=4096` (as `deploy/config.sh` sets it on the service; the backend default is
8192), and no `SIB_THINKING_*` unless the service sets one. The prompt version, models and judge passes that the dry
run prints must equal the deployed `/api/health`. The report records them, with the thinking levels, the output cap,
the backend, the `items.json` SHA-256, each clip's SHA-256, the item ids and N; there is no commit to name.

```bash
# the environment of step 0 below (Agent Platform), then:
export SIB_MAX_OUTPUT_TOKENS=4096                # as on the service (deploy/config.sh)
uv run python demo_stability.py --dry-run        # expect: 6 items x 10 runs = 60 checks x 3 model calls = 180; none made
curl -fsS "$SERVICE_URL/api/health"              # SERVICE_URL as in deploy/README.md (Verify); promptVersion,
                                                 # models.flash, models.judgeB and judgePasses as in the dry run
export SIB_EVAL_CALL_BUDGET=360                  # 159 logged + 180 + room for 7 retried checks
caffeinate -i uv run python demo_stability.py    # 180 calls -> reports/stability/<date>.json and .md
echo $?                                          # 0 pass; 1 BLOCKED: do not release; 2 no verdict: run it again
```

Then copy the verdict line and the per-step counts (printed at the end, and in the report's "Labels per step") into
`SUBMISSION_CHECKLIST.md` with the report's file name, and keep `reports/stability/` and `gemini_calls.log` with the
release. Other runs: `--repeat 20`; `--script chennai-second` (the second demo: 4 items, 120 calls at 10 runs);
`--items <id> ...`. A run with fewer than 10 runs says so in its first line and is not the release check.

## Real voices (after the 16 Oct recordings): the recordings and their site-noise copies

Once the volunteer's takes are saved (`record_clips.py`; eleven Tamil answers are planned for V01), the copies with
site noise are made locally with no call, and one paid run scores only the real voices. Protocol and meaning: README,
"Real voices at site noise". Steps, with the environment of step 0 below:

```bash
uv run pytest tests/test_items.py                        # the recordings pass the contract
uv run python augment_recorded.py --dry-run              # expect: 132 site-noise copies to write (132 new)
uv run python augment_recorded.py                        # no call; about a second per recording
uv run pytest -q                                         # every test passes, with no flag
uv run python run_eval.py --source recorded --dry-run    # expect: 143 items, 143 run_check calls = 429 model calls
uv run python run_eval.py --source recorded              # 429 calls into reports/recorded/; --resume after a stop
```

**Calls and cost, counted from the code.** Each item is one check: the blind transcriber, judge A and judge B, 3
calls. 11 recordings plus 11 x 4 profiles x 3 SNRs = 132 copies is 143 checks, so **429 calls, about $0.86** at the
measured $0.006 a check (an upper estimate, judge B being Flash-Lite). With `--repeat 3`: 1,287 calls, about $2.57.
These calls go through the backend, so `gemini_calls.log` and `SIB_EVAL_CALL_BUDGET` are not involved. For less,
make fewer copies before the run: `augment_recorded.py --snr snr0` gives 11 + 44 = 55 items (165 calls, about $0.33),
and `--profile site-hammer --snr snr5` gives 11 + 11 = 22 items (66 calls). Time: one check at a time, so about 2.5
times the 58-item run (allow up to about 95 minutes on the 15 Oct worst case). Keep the Mac awake with `caffeinate -i`.

Then check `reports/recorded/latest.json`:
- `selection` is `{"source": "recorded", "nItems": 143, "complete": true}`; the top-level `complete` stays false,
  because the synthetic items did not run, so the deck's slide 12 never takes this report;
- `recordedNoise.clean.nItems` is 11 and `recordedNoise.siteNoise.nItems` is 132;
- the headline starts "Recorded human voices only (143 of the ... items in the set)" and says "from consented human
  recordings (132 of them with synthetic site noise)".

The line to quote, next to the synthetic headline and never instead of it: "real voices: `bySource.recorded.nItems`
items, `unsafeErrors` false passes of `unsafeDenominator` (rule-of-three bound over items `unsafeUpperBound95Items`, if the items were independent: few speakers re-voice the same gold); at 0 dB
site noise: `recordedNoise.bySnr.snr0`, the same fields". Commit `testset/items.json`, `testset/audio/recorded/` and
`reports/recorded/latest.*`.

**The whole-set run includes them from now on.** A plain `run_eval.py` runs every item, recordings and copies too:
the synthetic items + 143 checks, 3 calls each. Its report is the only one that can be `complete: true`, so after it
the deck needs `EVAL_ITEMS` set to that report's `nItems`. If a withdrawal (`--forget`) removes a speaker after a run,
that run's reports still hold their results: rerun, or delete them, before anything is deployed.

## What happened (15 Oct 2026, Agent Platform)

The paid job is done. The plan below is kept as the record of what was planned, and as the procedure for a rerun.

- **Build calls: 133 logged**, against a plan of 62. `gemini_calls.log` went from 26 to 159 lines, within the
  raised cap of 160:
  - translate 6 and back-translate 1, as planned;
  - TTS 105: the 48 planned clips, 1 single re-voice, and 56 more, because every spoken clip was voiced again
    (below);
  - spot-check 21, against a plan of 7: two rounds, plus attempts on clips that a safety filter blocked.
- **The style prefix.** The build put a style line in front of each TTS text ("Say this in a calm natural
  conversational pace"). The spot-check showed that Agent Platform's TTS sometimes spoke it into the clip (in
  hot-work zh numbers and confined-space hi negation). `config.TTS_STYLE` is now empty, so the text goes alone,
  and all 56 spoken clips were voiced again with `--rerender`.
- **Safety blocks.** Agent Platform blocked some spot-check prompts with `SAFETY`, which cannot be turned off even
  with every adjustable safety setting OFF. The block is not deterministic. The build now names it
  (`ModelBlocked`), records the row as blocked and goes on.
  - `trench-entry.q1.or.complete.clean` was blocked in the first round and passed on a retry in the second
    (tolerant similarity 0.993).
  - `confined-space.q2.hi.negation.clean` was blocked on every try, so its spot-check row is `blocked`.
  - Neither clip was blocked in the eval: both runs finished with no error.
- **Spot-check.** 6 of 7 rows match, and the blocked row is the 7th. The raw score had flagged correct clips, so a
  match now uses the loanword- and numeral-tolerant score (step 5).
  - The raw scores were low because the transcriber writes loanwords in the worker's script (breaker as
    பிரேக்கர), and writes 30 for 三十.
  - The tolerant scores: lead r1 0.968, ta code-switch 0.981, bn 0.977, zh numbers 0.929, my 1.0, or 0.993.
- **Two eval runs**, both complete, 58 items and no error, at prompt `2026-10-15.10`, with judge B on
  `gemini-3.1-flash-lite`:
  - judges at thinking `medium` (`reports/2026-10-15-paid-judges-medium.*`): 0 false passes in 68 gold-miss
    ratings (rule-of-three bound 3/68 ≈ 4.5%, which assumes the 68 independent; see "Quoting a bound"), exact
    87.5%, correct passes 38 of 44;
  - judges at thinking `low` (`reports/2026-10-15-paid-judges-low.*`): the same 0 of 68 and 87.5%, correct
    passes 39 of 44, and about 35% faster.
- **Low was chosen.** It is as safe and as exact, passes one more correct step, and is faster. So the backend
  default is now judges `low`, and `reports/latest.*` is the low run.
  - It meets the pass bar.
  - The 12 held-out items: 0 false passes in 13 gold-miss ratings (rule-of-three bound 3/13 ≈ 23.1%, n = 13),
    exact 65.2%.
  - The keyword baselines on the same translations: 5 false passes, and 1 with the negation rule.
- **Not done:** no human voice is in the set yet (`record_clips.py` is ready), and the Odia, Burmese and
  `fidelity: review` items still need a native listen (`Google_BuilderCup/native-review/`).

## What it makes, counted from the code

`uv run python build_testset.py --plan` and `uv run python run_eval.py --dry-run` print these numbers, and neither
makes a call. Run them first: if a count differs from the table, something changed since 15 Oct, so stop and look.

| Step | Calls | What |
|---|---|---|
| Translate (Flash) | 6 | One batch per language with new rows: every language now has some. ta: the 2 lifting-zone hard cases, 2 held-out answers, `lifting-zone.q3` and the 3 `fragile-roof` questions. bn: 4 held-out answers, `lifting-zone.q3`, and the `confined-space` and `fragile-roof` questions. hi, or: 2 held-out answers each and the 2 `confined-space` questions. my: 2 held-out answers, `lifting-zone.q3` and the `fragile-roof` questions. zh: the reworded panel answer, `lifting-zone.q3` and the `fragile-roof` questions. 15 answers and 22 questions in all. |
| Back-translate (Flash) | 1 | 19 answers (one batch holds 20): lifting-zone demo r1 and r2, the 2 hard cases, panel-isolation demo r1 and r2 (their catalog lines changed), the reworded Chinese panel answer, and the 12 held-out answers. |
| TTS (one per clip) | 48 | 29 clips never rendered, the 4 items added on 14 Oct, the 12 held-out items, `panel-isolation.q1.ta.demo.clean.r1` (its clip still says the older line "நான் அதை ஆஃப் பண்ணிட்டு திறப்பேன்."), and the 2 panel answers reworded on 15 Oct (`panel-isolation.q1.ta.demo.clean.r2`, `panel-isolation.q1.zh.complete.clean`), whose clips still test before opening. The 10 current clips are not touched. |
| Spot-check (Flash) | 7 | 5 earlier ones, the lead demo's round 1 (`lifting-zone.q1.ta.demo.clean.r1`), and one held-out negation (`confined-space.q2.hi.negation.clean`). |
| **Build total** | **62** | Logged in `gemini_calls.log`. Each call may add one logged retry after a 429 or 503. |
| Smoke eval | 2 x 3 = 6 | 2 checks; each check is the transcriber plus judges A and B. |
| Eval | 58 x (1 + 2) = 174 | One check per item: the blind transcriber, then judge A on `gemini-3.8-flash` and judge B on `gemini-3.1-flash-lite` (`SIB_JUDGE_B_MODEL`). So the eval exercises two models. The backend makes these calls and the log doesn't count them. The backend's SDK may add one retry per call after a 429 or 5xx. The keyword baseline in the report makes no call. |

**The 70-call cap has to be raised.** The log holds 26 lines, and 26 + 62 = 88, which is over 70 before any retry.
In the worst case every call is retried once: 26 + 124 = 150. Set `SIB_EVAL_CALL_BUDGET=160` for this run. That
leaves room for one failed TTS probe and a few `--rerender` calls. The cap's default stays 70 in the code.

**Cost: about $0.45 for one full pass, and about $1.15 with `--repeat 3`.** The basis:
- **Eval: 58 checks x $0.006 = $0.35.** This is the measured cost of one one-question check on `gemini-3.8-flash`
  (findings.md, 14 Oct 16:35; tokens per call: transcriber 383 in / 77 out, judge A 1,091 / 154 + 328 thinking,
  judge B 806 / 148 + 439), at $0.75 / $3.75 per 1M tokens. Agent Platform's global endpoint charges the same.
  - Judge B now runs on Flash-Lite, which costs less, so $0.006 is an upper estimate per check.
  - Longer clips add about 32 audio tokens a second to two calls, which is under $0.001 for the longest (9 s).
  - With `--repeat 3`, the eval is about $1.04.
- **TTS: about $0.07.** The 11 rendered TTS clips average 5.8 s, so 48 clips come to about 280 s of audio. Audio
  output costs $9 per 1M tokens, which is $0.00225 per 10 s (findings.md price table).
- **The other Flash calls: about $0.04.** 14 calls (translate, back-translate, spot-check) of a few hundred
  tokens each. This is an estimate by analogy with the measured transcriber call, not a measurement.

**Time.** On the free key, the 13 Oct TTS calls took 5 to 60 s each, and checks took 14 to 183 s. The paid path
should be faster. Allow about 15 minutes for the build and up to 40 minutes for the eval, which runs one check at
a time. Keep the Mac awake with `caffeinate -i`.

## Commands, in order

Run these from `say-it-back/eval`. A fresh clone works too, and its plan is the same: the texts already made are in
`testset/items.json`, and what each clip says is in `testset/audio/clips.json`. `.cache/` only saves calls when a
stopped run is resumed on the same machine.

### 0. Environment (Agent Platform)

```bash
cd say-it-back/eval
uv sync
gcloud config list                      # the trial project, not some default
gcloud auth application-default login
export GOOGLE_GENAI_USE_ENTERPRISE=true
export GOOGLE_CLOUD_PROJECT=<project id>
export GOOGLE_CLOUD_LOCATION=global
export SIB_EVAL_CALL_BUDGET=160
unset GOOGLE_API_KEY                    # so that nothing goes to the Developer API by accident
```

Both the build and the eval read these variables through the backend's own switch (`sayitback.backends`), so
Flash, TTS and both judges follow them.

### 1. Plan (no call)

```bash
uv run python build_testset.py --plan   # expect: translate 6, back-translate 1 (19 answers), TTS 48, spot-check 7
uv run python run_eval.py --dry-run     # expect: 58 items, 112 step ratings, 174 model calls, held out 12 items,
                                        # 48 not ready
```

### 2. Texts, and one clip to probe TTS (8 calls)

```bash
uv run python build_testset.py --only lifting-zone.q1.ta.demo.clean.r1
afplay testset/audio/lifting-zone.q1.ta.demo.clean.r1.wav
```

The text stages always run first: 6 translate calls and 1 back-translate call. Then this one clip is voiced.
Nobody has yet checked whether `gemini-3.8-flash-tts` is served on Agent Platform. If this step stops with a
model-not-found or permission error, send the voice calls alone to the Developer API, with a billed key:

```bash
export SIB_TTS_BACKEND=developer-api
export GOOGLE_API_KEY=<billed key>      # never a free-tier key
uv run python build_testset.py --only lifting-zone.q1.ta.demo.clean.r1   # texts are cached now: 1 TTS call
```

Flash stays on Agent Platform. `testset/audio/clips.json` records which backend voiced each clip.

### 3. Render the rest (47 calls)

```bash
uv run python build_testset.py
```

It should end with `pending answer 0, backTranslation 0, audio 0; questions pending 0`. If it stops (two 429s in
a row, or a 180 s timeout), run the same command again. The clips already rendered and the cached texts are kept.
The log keeps the failed lines, and they count against the cap.

### 4. Tests, then read what is new

```bash
uv run pytest -q                        # every test passes now, with no flag
```

Then read what is new against its gloss, in `testset/items.json`:
- the 15 new texts: the two Tamil hard cases (`lifting-zone.q1.ta.negation.clean` and
  `lifting-zone.q1.ta.fluent_wrong.snr10`), the reworded `panel-isolation.q1.zh.complete.clean`, and the 12
  held-out answers (`"heldOut": true`);
- the 19 new back-translations (those 15, the lifting-zone demo r1 and r2, and the panel demo r1 and r2);
- the 22 new question texts (`questions`: `lifting-zone.q3`, and every `confined-space` and `fragile-roof` question).

Check above all that each negation survived ("won't go under", "never go under", "won't go down after them",
"won't put a foot on the roof"), and that the two reworded panel answers test for power after opening, not
before. The gold labels depend on it.
- If a text and its back-translation match the gloss, set `"fidelity": "ok"` for that item in `testset/spec.json`.
- If they don't, keep `"review"` and tell the team. A lost negation means the gold is wrong for that clip.
- Then rebuild without a call: `uv run python build_testset.py --skip-audio --offline`.
- A native Tamil speaker's check is still wanted; see README "Native review needed".

### 5. Spot-check (7 calls)

```bash
uv run python build_testset.py --spot-check
```

It writes `testset/spotcheck.json`, and every row should say `"match": true`. Since v0.5.1, a match means
`tolerantSimilarity` is at least 0.90 and `gap` is at most 15.
- `tolerantSimilarity` excuses the spans where a Latin loanword of the answer ("breaker", "load") was heard in the
  worker's script, and in Chinese it reads digits as numerals, so 30 must equal 三十.
- `tolerated` lists every excused span. Read them: each should be the loanword, said in another script.
- `gap` is the longest run of unexplained extra or missing speech, so a spoken style prefix or a dropped phrase still
  fails.
- `similarity` is the raw score, kept beside it. Code-switched clips score low there even when they are right.

If a row doesn't match, listen to that clip. If the clip says the wrong thing, voice it again (1 call) and repeat
the spot-check (1 call: the others are cached):

```bash
uv run python build_testset.py --rerender <item id>
uv run python build_testset.py --spot-check
```

To score the stored transcripts again after a change to the comparison, with no call:
`uv run python build_testset.py --rescore-spot-check`. A row blocked by a safety filter (`"blocked"`) stays as it is.

### 6. Smoke eval (6 calls)

```bash
uv run python run_eval.py --limit 2 --out reports/smoke
```

It runs the lead demo's two rounds, including the hard case. In `reports/smoke/latest.json`:
- check that `models` names `flash` and `judgeB` (`gemini-3.1-flash-lite`). That proves both models answer on
  Agent Platform before the 174 calls start;
- round 1 should not be `covered` on s1.

Delete `reports/smoke/` afterwards. The deploy ships only `reports/latest.json`.

### 7. The eval (174 calls)

```bash
uv run python run_eval.py               # writes reports/latest.json and reports/latest.md, prints the headline
```

Each finished item goes to `reports/progress.jsonl` at once (v0.5.1). If the run stops, or ends with
`ERRORS: N of 58 items errored twice` (exit code 1, `"complete": false`), run
`uv run python run_eval.py --resume`: it reuses what is done under the same settings and runs only the rest, so no
check is paid for twice. Keep the same environment (models, `SIB_THINKING_*`) for a resume; a different one is
refused.

Optionally, if time allows: `uv run python run_eval.py --repeat 3` (522 calls, about $1.04). It adds a repeat
stability line, and an item counts as unsafe if any of its three runs covers a gold miss.

Then check:
- `reports/latest.json` has `"complete": true` and `"nItems": 58`, and its `testset.ttsModels` is right;
- `testsetSha256` equals `shasum -a 256 testset/items.json`, `byHeldOut.heldOut.nItems` is 12, and `baseline` has
  `keyword` and `keywordNegation`;
- `passBar.passed` now also needs `correctPassRate` at least 0.75 (`passBar.correctPassMin`);
- `reports/latest.md` starts with the headline. That is the sentence to quote. Since 17 Oct it names the bound's
  method and assumption itself ("95% upper bound X% by the rule of three over those ratings, which assumes
  independent ratings"); add that in this synthetic, team-labelled set they are not, for example "0 false passes in N
  gold-miss step ratings (rule-of-three bound 3/N ≈ X%, if the ratings were independent, which in this synthetic,
  team-labelled set they are not); exact Y%; correct passes A of B; asked again Z%. 58 answers in synthetic Gemini
  TTS voices (...), judged by Gemini (...)". Quote the held-out row with its own n and bound (today 0 in 13, 3/13 ≈ 23.1%) and the keyword
  baseline rows of its subsets table next to it, never instead of it;
- every unsafe error is listed with the judge's evidence;
- the report says the voices are synthetic and that the same model family speaks and judges.

## Afterwards, in this order

1. **Copy the report.**
   - Keep this run as evidence, in case `latest.*` is overwritten later:
     `cp reports/latest.json reports/2026-10-<day>-paid.json` and `cp reports/latest.md reports/2026-10-<day>-paid.md`.
   - Paste the headline wherever the numbers are quoted (the README, the video script).
2. **Rebuild the deck.** `deck/build_deck.py` reads `eval/reports/latest.json`, but it shows results only when
   `nItems` equals `deck_content.EVAL_ITEMS`, which is **46**. The set now has **58** items, so first:
   - set `EVAL_ITEMS = 58` in `deck/deck_content.py`, or better, check the report's `complete`;
   - check the item count on slide 10 (`deck/slides_proof.py`);
   - update the set description in `deck_content.py`: 112 gold step ratings (covered 44, missed 36, contradicted
     26, unclear 6, so 68 gold misses; rule-of-three bound 3/68 = 4.5% rounded up, if independent), languages ta 15, hi 11, bn 11, zh 7, or 8 (6
     genuine), my 6, noise 38 clean / 12 at 10 dB / 8 at 5 dB, 6 demo answers, and 12 held-out items on 2 tasks.

   Then run `cd deck && python3 build_deck.py && python3 export_pdf.py`, and look at every page. Its warning that
   the sg-lead round-1 line differs from `deck_content.ANSWER_TA` must be gone.
3. **Redeploy the backend**, with Sam's go-ahead: `PROJECT_ID=<id> bash deploy/02_deploy_backend.sh`.
   - It copies `eval/testset` (with `audio/clips.json`) and `eval/reports/latest.json` into the image.
   - Then do the Verify steps in `deploy/README.md`.
   - Check that `/api/eval/latest` shows `"complete": true` and that `/api/demo-answers` lists all twelve demo answers
     (since 16 Oct: lifting-zone q1-q3 and scaffold-harness q1-q2 in rounds 1 and 2, panel-isolation q1 in both).
4. **Commit** these files, and not `.cache/`:
   - `testset/items.json`, `testset/spec.json`;
   - `testset/audio/*.wav`, `testset/audio/clips.json`, `testset/spotcheck.json`;
   - `reports/latest.json`, `reports/latest.md` and the dated copies;
   - `gemini_calls.log`.

   Then log the numbers, and the calls actually used (the last `#` in `gemini_calls.log`), in `tasks.md` and
   `findings.md`.
