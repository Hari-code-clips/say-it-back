# Say It Back eval report

> Recorded human voices only (46 of the 134 items in the set): 1 false pass in 60 gold-miss step ratings (95% upper bound 8.9% by the Wilson score interval over those ratings, which assumes independent ratings); exact 85.7%; correct passes 29 of 31; asked again 8.8%. 46 answers from consented human recordings, judged by Gemini (gemini-3.8-flash; judge B gemini-3.1-flash-lite).

**FAIL (recorded human voices only, not the whole set)**: exact accuracy 85.7% (bar 80.0%); unsafe errors 1 of 60 gold-miss ratings (bar 0); correct passes 93.5% (bar 75.0%).

Generated 2026-10-18T03:12:21Z | prompt 2026-10-16.12 | models flash=gemini-3.8-flash, judgeB=gemini-3.1-flash-lite | judge passes 2 | repeats 1 | items 46 of 134 (test set 2026-10-15, items.json SHA-256 8e23296e3591) | step ratings 91 | thinking blind_transcriber low, judge_a low, judge_b low

## What these numbers are

- **Recorded human voices only:** 46 of the 134 items in the set (`run_eval.py --source recorded`). Quote them as that subset, beside the whole set's run (reports/latest.md), never as the whole set.
- **Real voices, synthetic site noise: not a field trial.** 46 answers are consented recordings (speaker codes, never names) re-voicing synthetic items with the same gold, made in a quiet room; 0 are copies of them with procedural site noise (machinery drone, hammering, a reversing beeper, distant babble) mixed in at 10, 5 and 0 dB SNR over the speech (eval/site_noise.py). A site adds distance, wind, echo and accents this does not, and the speakers are few: read the bound, not the rate.
- **Gold labels are the authors' judgement**, from the rubric in docs/API.md; items marked `fidelity: review` still need a native speaker's check.

## Overall

| Metric | Value | Meaning |
|---|---|---|
| exactAccuracy | 85.7% | predicted label equals gold; unclear counts only against unclear gold |
| unsafeErrors | 1 | false passes: gold missed, contradicted or unclear, rated covered |
| unsafeDenominator | 60 | gold-miss ratings (gold missed, contradicted or unclear) |
| unsafeUpperBound95 | 8.9% | 95% upper bound on false passes over the gold-miss ratings: rule of three (3/N) when no error is seen, Wilson 95% otherwise; assumes independent ratings; rounded up |
| catchRate | 98.3% | gold missed, contradicted or unclear, not rated covered |
| overFlagRate | 6.5% | gold covered, not rated covered |
| unclearRate | 8.8% | predictions that are unclear (asked again: 8 of 91) |
| correct passes | 29 of 31 | gold covered, rated covered |
| correctPassRate | 93.5% | gold covered, rated covered, as a share |
| unsafeItemDenominator | 36 | items with at least one gold-miss step |
| unsafeUpperBound95Items | 14.2% | the same bound over those items (an item is an error if any of its gold-miss steps is rated covered); assumes independent items; rounded up |

## Held-out tasks, the model alone, and a keyword baseline

- **Held-out tasks** (confined-space entry, fragile roofs) have no demo script, and no prompt example uses their words, so these items test judgement, not recall. They are few: read their bound, not their rate.
- **Model only** leaves out the silence and wrong_language items, which the code guards (no speech, wrong language) catch before any judgement matters.
- **Gemini TTS voices** share the judges' model family; **another vendor's TTS voices** (Sarvam Bulbul) do not, so the gap between the two rows is a first look at that bias, although both are synthetic: clean, fluent and without a site accent.
- **Recorded human voices** are consented volunteers (speaker codes, no names) re-voicing synthetic items with the same gold (eval/record_clips.py); the gap to the synthetic row is the first sign of real speech.
- **Keyword baselines** rate each step from the same English translation of the answer that the judges read: covered when every content word of every essential phrase appears, missed when none does, unclear otherwise; the negation variant also says contradicted when the matching clause and the essential phrase disagree on negation (eval/baseline_keyword.py).

| Subset | items | step ratings | exact | false passes | 95% bound (steps) | 95% bound (items) | correct passes | asked again |
|---|---|---|---|---|---|---|---|---|
| All items | 46 | 91 | 85.7% | 1 of 60 | 8.9% | 14.2% | 93.5% | 8.8% |
| In-set tasks | 34 | 66 | 86.4% | 1 of 46 | 11.4% | 17.8% | 95.0% | 6.1% |
| Held-out tasks | 12 | 25 | 84.0% | 0 of 14 | 21.5% | 37.5% | 90.9% | 16.0% |
| Model only (no silence or wrong_language) | 46 | 91 | 85.7% | 1 of 60 | 8.9% | 14.2% | 93.5% | 8.8% |
| Synthetic TTS voices | 0 | 0 | n/a | 0 of 0 | n/a | n/a | n/a | n/a |
| Gemini TTS voices | 0 | 0 | n/a | 0 of 0 | n/a | n/a | n/a | n/a |
| Another vendor's TTS voices (Sarvam) | 0 | 0 | n/a | 0 of 0 | n/a | n/a | n/a | n/a |
| Recorded human voices | 46 | 91 | 85.7% | 1 of 60 | 8.9% | 14.2% | 93.5% | 8.8% |
| Keyword baseline | 46 | 91 | 30.8% | 4 of 60 | 16.0% | 25.4% | 22.6% | 54.9% |
| Keyword + negation baseline | 46 | 91 | 40.7% | 0 of 60 | 5.0% | 8.4% | 22.6% | 44.0% |

95% bound: the rule of three (3/N) over the row's gold-miss ratings (steps) or over its items with a gold miss (items) when the row has no false pass, else the Wilson score interval; it assumes those ratings (or items) are independent, and is rounded up.

## Real voices by noise

- Consented recordings (eval/record_clips.py), and copies of them with procedural site noise mixed in (eval/augment_recorded.py): machinery drone, hammering, a reversing beeper and distant babble, at an SNR measured over the speech. Real voices with synthetic noise: not a field trial. Recordings made in real noise (the item's ambient note) get no synthetic noise.

| Subset | items | step ratings | exact | false passes | 95% bound (steps) | 95% bound (items) | correct passes | asked again |
|---|---|---|---|---|---|---|---|---|
| As recorded (quiet room) | 36 | 70 | 84.3% | 1 of 45 | 11.6% | 17.8% | 92.0% | 10.0% |
| As recorded in real background noise | 10 | 21 | 90.5% | 0 of 15 | 20.0% | 37.5% | 100.0% | 4.8% |
| All site noise | 0 | 0 | n/a | 0 of 0 | n/a | n/a | n/a | n/a |

95% bound: the rule of three (3/N) over the row's gold-miss ratings (steps) or over its items with a gold miss (items) when the row has no false pass, else the Wilson score interval; it assumes those ratings (or items) are independent, and is rounded up.

## By language

| Language | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| bn | 21 | 85.7% | 0 |
| hi | 15 | 93.3% | 0 |
| or | 11 | 54.5% | 0 |
| ta | 44 | 90.9% | 1 |

## By pattern

| Pattern | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| code_switch | 8 | 75.0% | 1 |
| complete | 10 | 100.0% | 0 |
| contradicted | 25 | 80.0% | 0 |
| echo | 1 | 0.0% | 0 |
| fluent_wrong | 12 | 83.3% | 0 |
| negation | 8 | 100.0% | 0 |
| numbers | 3 | 100.0% | 0 |
| one_missing | 9 | 77.8% | 0 |
| two_missing | 5 | 80.0% | 0 |
| vague | 10 | 100.0% | 0 |

## By task

| Task | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| confined-space | 14 | 71.4% | 0 |
| fragile-roof | 11 | 100.0% | 0 |
| hot-work | 3 | 100.0% | 0 |
| lifting-zone | 14 | 85.7% | 0 |
| panel-isolation | 26 | 92.3% | 1 |
| scaffold-harness | 11 | 90.9% | 0 |
| trench-entry | 12 | 66.7% | 0 |

## By noise

| Noise | step ratings (n) | exact | unsafe errors |
|---|---|---|---|
| clean | 91 | 85.7% | 1 |

## Unsafe errors

| Item | Step | Gold | Pred | Judge evidence |
|---|---|---|---|---|
| panel-isolation.q1.ta.code_switch.clean.rec.V01 | s3 | contradicted | covered | கரண்ட் இல்லைன்னு டெஸ்டர் வச்சு செக் பண்ணிட்டு பேனலை திறப்பேன் |

## Caveats

- This is not the real-recording spike: synthetic speech flatters the judges (see above).
- wrong_language and silence items are gold `unclear` on every step, because the right response is to abstain. An `unclear` rating is exact there, and a `covered` rating is an unsafe error.
- `n` in the group tables counts step ratings. A ratio with no denominator shows as n/a.
- With no unsafe error, the 95% upper bound is the rule of three, 3/N for N gold-miss ratings, and it assumes the N ratings are independent. At N = 60 that is 5.0%. Over the 36 items with a gold miss it is 8.4%, which assumes the items independent.
- They are not: the ratings of one answer share its clip, and answers share tasks, voices and labellers. So the bound over items is the more cautious number, and neither is a false-pass probability for real workers.

