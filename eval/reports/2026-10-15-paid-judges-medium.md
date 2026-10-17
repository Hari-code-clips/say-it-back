# Say It Back eval report

> 0 false passes in 68 gold-miss step ratings (95% upper bound 4.5%); exact 87.5%; correct passes 38 of 44; asked again 14.3%. 58 answers in synthetic Gemini TTS voices (gemini-3.8-flash-tts), judged by Gemini (gemini-3.8-flash; judge B gemini-3.1-flash-lite).

**PASS**: exact accuracy 87.5% (bar 80.0%); unsafe errors 0 of 68 gold-miss ratings (bar 0); correct passes 86.4% (bar 75.0%).

Generated 2026-10-15T14:41:24Z | prompt 2026-10-15.10 | models flash=gemini-3.8-flash, judgeB=gemini-3.1-flash-lite | judge passes 2 | repeats 1 | items 58 of 58 (test set 2026-10-15, items.json SHA-256 14db18afaaff) | step ratings 112 | thinking blind_transcriber low, judge_a medium, judge_b medium

## What these numbers are

- **The answers are synthetic.** They were written by the team as English glosses, translated by Gemini, and voiced by Gemini TTS (gemini-3.8-flash-tts), about a third with synthetic site noise. No real worker was recorded.
- **Known bias: the same model family speaks and judges.** Gemini models (gemini-3.8-flash; judge B gemini-3.1-flash-lite) grade speech that a Gemini model produced: clean, fluent and without accent. That is probably easier than a real worker on a phone at a site, so treat these numbers as a check of the logic, not a measure of real-world accuracy.
- **Gold labels are the authors' judgement**, from the rubric in docs/API.md; items marked `fidelity: review` still need a native speaker's check.

## Overall

| Metric | Value | Meaning |
|---|---|---|
| exactAccuracy | 87.5% | predicted label equals gold; unclear counts only against unclear gold |
| unsafeErrors | 0 | false passes: gold missed, contradicted or unclear, rated covered |
| unsafeDenominator | 68 | gold-miss ratings (gold missed, contradicted or unclear) |
| unsafeUpperBound95 | 4.5% | rule of three (3/N) when no error is seen; Wilson 95% otherwise; rounded up |
| catchRate | 100.0% | gold missed, contradicted or unclear, not rated covered |
| overFlagRate | 13.6% | gold covered, not rated covered |
| unclearRate | 14.3% | predictions that are unclear (asked again: 16 of 112) |
| correct passes | 38 of 44 | gold covered, rated covered |
| correctPassRate | 86.4% | gold covered, rated covered, as a share |
| unsafeItemDenominator | 42 | items with at least one gold-miss step |
| unsafeUpperBound95Items | 7.2% | the same bound over those items (an item is an error if any of its gold-miss steps is rated covered); rounded up |

## Held-out tasks, the model alone, and a keyword baseline

- **Held-out tasks** (confined-space entry, fragile roofs) have no demo script, and no prompt example uses their words, so these items test judgement, not recall. They are few: read their bound, not their rate.
- **Model only** leaves out the silence and wrong_language items, which the code guards (no speech, wrong language) catch before any judgement matters.
- **Recorded human voices** are consented volunteers (speaker codes, no names) re-voicing synthetic items with the same gold (eval/record_clips.py); the gap to the synthetic row is the first sign of real speech.
- **Keyword baselines** rate each step from the same English translation of the answer that the judges read: covered when every content word of every essential phrase appears, missed when none does, unclear otherwise; the negation variant also says contradicted when the matching clause and the essential phrase disagree on negation (eval/baseline_keyword.py).

| Subset | items | step ratings | exact | false passes | 95% bound (steps) | 95% bound (items) | correct passes | asked again |
|---|---|---|---|---|---|---|---|---|
| All items | 58 | 112 | 87.5% | 0 of 68 | 4.5% | 7.2% | 86.4% | 14.3% |
| In-set tasks | 46 | 89 | 93.3% | 0 of 55 | 5.5% | 8.9% | 94.1% | 9.0% |
| Held-out tasks | 12 | 23 | 65.2% | 0 of 13 | 23.1% | 37.5% | 60.0% | 34.8% |
| Model only (no silence or wrong_language) | 54 | 106 | 86.8% | 0 of 62 | 4.9% | 7.9% | 86.4% | 9.4% |
| Synthetic TTS voices | 58 | 112 | 87.5% | 0 of 68 | 4.5% | 7.2% | 86.4% | 14.3% |
| Recorded human voices | 0 | 0 | n/a | 0 of 0 | n/a | n/a | n/a | n/a |
| Keyword baseline | 58 | 112 | 33.0% | 5 of 68 | 16.1% | 25.1% | 22.7% | 50.0% |
| Keyword + negation baseline | 58 | 112 | 38.4% | 1 of 68 | 7.9% | 12.4% | 22.7% | 42.0% |

## By language

| Language | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| bn | 22 | 81.8% | 0 |
| hi | 19 | 73.7% | 0 |
| my | 9 | 66.7% | 0 |
| or | 14 | 100.0% | 0 |
| ta | 33 | 93.9% | 0 |
| zh | 15 | 100.0% | 0 |

## By pattern

| Pattern | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| code_switch | 6 | 83.3% | 0 |
| complete | 13 | 76.9% | 0 |
| contradicted | 18 | 77.8% | 0 |
| demo | 14 | 85.7% | 0 |
| echo | 3 | 100.0% | 0 |
| fluent_wrong | 11 | 90.9% | 0 |
| negation | 10 | 80.0% | 0 |
| numbers | 4 | 100.0% | 0 |
| one_missing | 12 | 100.0% | 0 |
| silence | 3 | 100.0% | 0 |
| two_missing | 7 | 85.7% | 0 |
| vague | 8 | 100.0% | 0 |
| wrong_language | 3 | 100.0% | 0 |

## By task

| Task | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| confined-space | 14 | 57.1% | 0 |
| fragile-roof | 9 | 77.8% | 0 |
| hot-work | 8 | 100.0% | 0 |
| lifting-zone | 22 | 81.8% | 0 |
| panel-isolation | 28 | 100.0% | 0 |
| scaffold-harness | 15 | 86.7% | 0 |
| trench-entry | 16 | 100.0% | 0 |

## By noise

| Noise | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| clean | 75 | 86.7% | 0 |
| snr10 | 23 | 100.0% | 0 |
| snr5 | 14 | 71.4% | 0 |

## Unsafe errors

None. No gold-miss step was rated covered.

## Caveats

- This is not the real-recording spike: synthetic speech flatters the judges (see above).
- wrong_language and silence items are gold `unclear` on every step, because the right response is to abstain. An `unclear` rating is exact there, and a `covered` rating is an unsafe error.
- `n` in the group tables counts step ratings. A ratio with no denominator shows as n/a.
- With no unsafe error, the 95% bound is 3/N for N gold-miss ratings. At N = 68 that is 4.5%. Over the 42 items with a gold miss it is 7.2%.
- Step ratings of one answer are not independent, so the bound over items is the more cautious number.

