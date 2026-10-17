# Say It Back eval report

> 0 false passes in 92 gold-miss step ratings (95% upper bound 3.3% by the rule of three over those ratings, which assumes independent ratings); exact 86.6%; correct passes 82 of 87; asked again 14.0%. 99 answers in synthetic Gemini TTS voices (bulbul:v3, bulbul:v4-flash, gemini-3.8-flash-tts) and 11 consented recordings, judged by Gemini (gemini-3.8-flash; judge B gemini-3.1-flash-lite).

**PASS**: exact accuracy 86.6% (bar 80.0%); unsafe errors 0 of 92 gold-miss ratings (bar 0); correct passes 94.3% (bar 75.0%).

Generated 2026-10-17T07:21:40Z | prompt 2026-10-16.12 | models flash=gemini-3.8-flash, judgeB=gemini-3.1-flash-lite | judge passes 2 | repeats 1 | items 99 of 99 (test set 2026-10-15, items.json SHA-256 4018e55c0b14) | step ratings 179 | thinking blind_transcriber low, judge_a low, judge_b low

## What these numbers are

- **The answers are synthetic.** They were written by the team as English glosses, translated by Gemini, and voiced by Gemini TTS (bulbul:v3, bulbul:v4-flash, gemini-3.8-flash-tts), about a third with synthetic site noise. 11 answers are consented recordings.
- **Known bias: the same model family speaks and judges.** Gemini models (gemini-3.8-flash; judge B gemini-3.1-flash-lite) grade speech that a Gemini model produced: clean, fluent and without accent. That is probably easier than a real worker on a phone at a site, so treat these numbers as a check of the logic, not a measure of real-world accuracy.
- **Real voices, synthetic site noise: not a field trial.** 11 answers are consented recordings (speaker codes, never names) re-voicing synthetic items with the same gold, made in a quiet room; 0 are copies of them with procedural site noise (machinery drone, hammering, a reversing beeper, distant babble) mixed in at 10, 5 and 0 dB SNR over the speech (eval/site_noise.py). A site adds distance, wind, echo and accents this does not, and the speakers are few: read the bound, not the rate.
- **Gold labels are the authors' judgement**, from the rubric in docs/API.md; items marked `fidelity: review` still need a native speaker's check.

## Overall

| Metric | Value | Meaning |
|---|---|---|
| exactAccuracy | 86.6% | predicted label equals gold; unclear counts only against unclear gold |
| unsafeErrors | 0 | false passes: gold missed, contradicted or unclear, rated covered |
| unsafeDenominator | 92 | gold-miss ratings (gold missed, contradicted or unclear) |
| unsafeUpperBound95 | 3.3% | 95% upper bound on false passes over the gold-miss ratings: rule of three (3/N) when no error is seen, Wilson 95% otherwise; assumes independent ratings; rounded up |
| catchRate | 100.0% | gold missed, contradicted or unclear, not rated covered |
| overFlagRate | 5.7% | gold covered, not rated covered |
| unclearRate | 14.0% | predictions that are unclear (asked again: 25 of 179) |
| correct passes | 82 of 87 | gold covered, rated covered |
| correctPassRate | 94.3% | gold covered, rated covered, as a share |
| unsafeItemDenominator | 59 | items with at least one gold-miss step |
| unsafeUpperBound95Items | 5.1% | the same bound over those items (an item is an error if any of its gold-miss steps is rated covered); assumes independent items; rounded up |

## Held-out tasks, the model alone, and a keyword baseline

- **Held-out tasks** (confined-space entry, fragile roofs) have no demo script, and no prompt example uses their words, so these items test judgement, not recall. They are few: read their bound, not their rate.
- **Model only** leaves out the silence and wrong_language items, which the code guards (no speech, wrong language) catch before any judgement matters.
- **Gemini TTS voices** share the judges' model family; **another vendor's TTS voices** (Sarvam Bulbul) do not, so the gap between the two rows is a first look at that bias, although both are synthetic: clean, fluent and without a site accent.
- **Recorded human voices** are consented volunteers (speaker codes, no names) re-voicing synthetic items with the same gold (eval/record_clips.py); the gap to the synthetic row is the first sign of real speech.
- **Keyword baselines** rate each step from the same English translation of the answer that the judges read: covered when every content word of every essential phrase appears, missed when none does, unclear otherwise; the negation variant also says contradicted when the matching clause and the essential phrase disagree on negation (eval/baseline_keyword.py).

| Subset | items | step ratings | exact | false passes | 95% bound (steps) | 95% bound (items) | correct passes | asked again |
|---|---|---|---|---|---|---|---|---|
| All items | 99 | 179 | 86.6% | 0 of 92 | 3.3% | 5.1% | 94.3% | 14.0% |
| In-set tasks | 85 | 152 | 85.5% | 0 of 77 | 3.9% | 6.0% | 94.7% | 15.1% |
| Held-out tasks | 14 | 27 | 92.6% | 0 of 15 | 20.0% | 33.4% | 91.7% | 7.4% |
| Model only (no silence or wrong_language) | 95 | 173 | 86.1% | 0 of 86 | 3.5% | 5.5% | 94.3% | 11.0% |
| Synthetic TTS voices | 88 | 156 | 85.9% | 0 of 76 | 4.0% | 6.0% | 93.8% | 15.4% |
| Gemini TTS voices | 58 | 112 | 83.0% | 0 of 68 | 4.5% | 7.2% | 93.2% | 18.8% |
| Another vendor's TTS voices (Sarvam) | 30 | 44 | 93.2% | 0 of 8 | 37.5% | 37.5% | 94.4% | 6.8% |
| Recorded human voices | 11 | 23 | 91.3% | 0 of 16 | 18.8% | 33.4% | 100.0% | 4.3% |
| Keyword baseline | 99 | 179 | 26.8% | 6 of 92 | 13.6% | 20.5% | 19.5% | 58.7% |
| Keyword + negation baseline | 99 | 179 | 33.0% | 1 of 92 | 6.0% | 9.0% | 19.5% | 46.9% |

95% bound: the rule of three (3/N) over the row's gold-miss ratings (steps) or over its items with a gold miss (items) when the row has no false pass, else the Wilson score interval; it assumes those ratings (or items) are independent, and is rounded up.

## Real voices by noise

- Consented recordings (eval/record_clips.py), and copies of them with procedural site noise mixed in (eval/augment_recorded.py): machinery drone, hammering, a reversing beeper and distant babble, at an SNR measured over the speech. Real voices with synthetic noise: not a field trial.

| Subset | items | step ratings | exact | false passes | 95% bound (steps) | 95% bound (items) | correct passes | asked again |
|---|---|---|---|---|---|---|---|---|
| As recorded (quiet room) | 11 | 23 | 91.3% | 0 of 16 | 18.8% | 33.4% | 100.0% | 4.3% |
| All site noise | 0 | 0 | n/a | 0 of 0 | n/a | n/a | n/a | n/a |

95% bound: the rule of three (3/N) over the row's gold-miss ratings (steps) or over its items with a gold miss (items) when the row has no false pass, else the Wilson score interval; it assumes those ratings (or items) are independent, and is rounded up.

## By language

| Language | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| bn | 34 | 88.2% | 0 |
| hi | 29 | 89.7% | 0 |
| my | 9 | 55.6% | 0 |
| or | 20 | 95.0% | 0 |
| ta | 66 | 89.4% | 0 |
| te | 6 | 100.0% | 0 |
| zh | 15 | 66.7% | 0 |

## By pattern

| Pattern | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| code_switch | 9 | 77.8% | 0 |
| complete | 15 | 100.0% | 0 |
| contradicted | 25 | 92.0% | 0 |
| demo | 58 | 93.1% | 0 |
| echo | 3 | 66.7% | 0 |
| fluent_wrong | 14 | 57.1% | 0 |
| negation | 13 | 76.9% | 0 |
| numbers | 6 | 83.3% | 0 |
| one_missing | 12 | 91.7% | 0 |
| silence | 3 | 100.0% | 0 |
| two_missing | 7 | 42.9% | 0 |
| vague | 11 | 100.0% | 0 |
| wrong_language | 3 | 100.0% | 0 |

## By task

| Task | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| confined-space | 14 | 100.0% | 0 |
| fragile-roof | 13 | 84.6% | 0 |
| hot-work | 16 | 81.2% | 0 |
| hydro-jetting | 6 | 66.7% | 0 |
| lifting-zone | 33 | 69.7% | 0 |
| panel-isolation | 38 | 92.1% | 0 |
| press-lockout | 8 | 87.5% | 0 |
| scaffold-harness | 17 | 88.2% | 0 |
| steam-line-break | 6 | 100.0% | 0 |
| telecom-tower | 6 | 100.0% | 0 |
| trench-entry | 22 | 95.5% | 0 |

## By noise

| Noise | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| clean | 142 | 87.3% | 0 |
| snr10 | 23 | 78.3% | 0 |
| snr5 | 14 | 92.9% | 0 |

## Unsafe errors

None. No gold-miss step was rated covered.

## Caveats

- This is not the real-recording spike: synthetic speech flatters the judges (see above).
- wrong_language and silence items are gold `unclear` on every step, because the right response is to abstain. An `unclear` rating is exact there, and a `covered` rating is an unsafe error.
- `n` in the group tables counts step ratings. A ratio with no denominator shows as n/a.
- With no unsafe error, the 95% upper bound is the rule of three, 3/N for N gold-miss ratings, and it assumes the N ratings are independent. At N = 92 that is 3.3%. Over the 59 items with a gold miss it is 5.1%, which assumes the items independent.
- They are not: the ratings of one answer share its clip, and answers share tasks, voices and labellers. So the bound over items is the more cautious number, and neither is a false-pass probability for real workers.

