import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Verdict } from '../../src/api/types.ts'
import { en } from '../../src/i18n/en.ts'
import { VERDICT, VERDICT_ORDER } from '../../src/screens/result/verdict.ts'
import { TONE } from '../../src/ui/chipLook.ts'

// The four verdicts of web/design.md ("chroma means a verdict"): word + mark + treatment, so no verdict depends on colour.

const verdicts = Object.keys(VERDICT) as Verdict[]

describe('the four verdicts', () => {
  it('are exactly Got it, Missed, Wrong and Ask again', () => {
    assert.deepEqual(
      VERDICT_ORDER.map((v) => en[VERDICT[v].label]),
      ['Got it', 'Missed', 'Wrong', 'Ask again'],
    )
  })

  it('use these marks: check, refresh, close and an outlined minus in a circle', () => {
    assert.equal(VERDICT.covered.icon, 'check')
    assert.equal(VERDICT.unclear.icon, 'refresh')
    assert.equal(VERDICT.contradicted.icon, 'close')
    assert.equal(VERDICT.missed.icon, 'remove_circle')
    assert.equal(TONE[VERDICT.missed.tone].glyph, 'outline')
    for (const v of ['covered', 'unclear', 'contradicted'] as const) assert.equal(TONE[VERDICT[v].tone].glyph, 'filled')
  })

  it('give every verdict its own mark, its own word and its own tone', () => {
    for (const key of ['icon', 'label', 'tone'] as const) assert.equal(new Set(verdicts.map((v) => VERDICT[v][key])).size, 4, key)
  })

  it('treat Got it and Ask again as tints, Wrong as the one solid fill and Missed as an outline with no fill', () => {
    assert.equal(VERDICT.covered.treatment, 'tint')
    assert.equal(VERDICT.unclear.treatment, 'tint')
    assert.equal(VERDICT.contradicted.treatment, 'solid')
    assert.equal(VERDICT.missed.treatment, 'outline')
  })

  it('draw the chips to match their treatment', () => {
    const box = (v: Verdict) => TONE[VERDICT[v].tone].box
    assert.match(box('contradicted'), /\bbg-error\b/)
    assert.match(box('covered'), /\bbg-success-container\b/)
    assert.match(box('unclear'), /\bbg-warning-container\b/)
    assert.match(box('missed'), /\bborder-2 border-on-surface bg-transparent\b/)
    // The one with no fill has no fill of any colour.
    assert.ok(!/\bbg-(?!transparent)/.test(box('missed')))
  })

  it('make Missed differ from Wrong without any colour: fill, border and mark all differ', () => {
    const missed = TONE[VERDICT.missed.tone]
    const wrong = TONE[VERDICT.contradicted.tone]
    assert.notEqual(VERDICT.missed.treatment, VERDICT.contradicted.treatment)
    assert.notEqual(VERDICT.missed.icon, VERDICT.contradicted.icon)
    assert.notEqual(missed.glyph, wrong.glyph)
    assert.match(missed.box, /\bborder-2\b/)
    assert.ok(!/\bborder/.test(wrong.box))
  })

  it('never rely on colour alone for any pair: every pair differs in its mark and its word', () => {
    for (const a of verdicts) {
      for (const b of verdicts) {
        if (a >= b) continue
        assert.notEqual(VERDICT[a].icon, VERDICT[b].icon, `${a} vs ${b}`)
        assert.notEqual(en[VERDICT[a].label], en[VERDICT[b].label], `${a} vs ${b}`)
      }
    }
  })

  it('give Missed no alarm colour: it uses ink, not the red of Wrong or the hazard', () => {
    assert.ok(!/error|warning|success/.test(TONE.missed.box))
    assert.ok(!/error|warning|success/.test(VERDICT.missed.band))
  })

  it('keep amber for Ask again alone: the generic warning tone is a neutral outline', () => {
    assert.ok(!/warning/.test(TONE.warning.box))
    assert.match(TONE.warning.box, /border-\[1\.5px\] border-on-surface/)
    for (const [tone, look] of Object.entries(TONE)) if (/warning/.test(look.box)) assert.equal(tone, 'ask')
  })

  it('make Ink the one solid neutral chip (a recorded decision is the supervisor’s, so no hue), and Primary the action blue’s tint', () => {
    assert.match(TONE.ink.box, /\bbg-inverse-surface\b/)
    assert.ok(!/\bbg-primary\b/.test(TONE.ink.box), 'a recorded Go is not a button')
    assert.match(TONE.primary.box, /\bbg-primary-container\b/)
    assert.ok(!/success|warning|error/.test(TONE.primary.box))
  })

  it('keep the Mock chip neutral: the neutral tone carries no verdict colour', () => {
    assert.ok(!/success|warning|error/.test(TONE.neutral.box))
  })
})
