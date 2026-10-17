import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { ANNOUNCE_EVERY_S, SLOW_AFTER_S, announcedElapsed, clock, waitCopy } from '../../src/lib/waitCopy.ts'

// Review focus 4 (build-notes/22): a 90 s Gemini wait must not look like a hang. The counter keeps counting, and from 45 s
// a line says it is still working and can take up to 2 minutes.

const LANGS = ['en', 'ta', 'zh'] as const
const tables = { en, ta, zh } as const

// Rule 2 (PROJECT_CONTEXT.md), the same patterns as tests/i18n/rule2.test.ts.
const BANNED: Record<(typeof LANGS)[number], RegExp> = {
  en: /\b(approved|passed|understood)\b/i,
  ta: /புரிந்த/u,
  zh: /理解|明白|通过|批准/u,
}

describe('clock', () => {
  it('shows minutes and whole seconds', () => {
    assert.deepEqual([0, 7, 44.9, 45, 59, 60, 90, 125].map(clock), ['0:00', '0:07', '0:44', '0:45', '0:59', '1:00', '1:30', '2:05'])
  })

  it('never goes below zero (a clock that steps back)', () => {
    assert.equal(clock(-3), '0:00')
  })
})

describe('waitCopy', () => {
  for (const lang of LANGS) {
    it(`${lang}: at 0 s the counter shows 0:00 and there is no still-working line`, () => {
      const copy = waitCopy(0, lang)

      assert.match(copy.counter, /0:00/)
      assert.equal(copy.slow, null)
    })

    it(`${lang}: at 44 s it is still the counter alone`, () => {
      const copy = waitCopy(44, lang)

      assert.match(copy.counter, /0:44/)
      assert.equal(copy.slow, null)
    })

    it(`${lang}: from 45 s it says it is still working, up to 2 minutes, and to keep the page open`, () => {
      const copy = waitCopy(45, lang)

      assert.match(copy.counter, /0:45/)
      assert.equal(copy.slow, tables[lang]['wait.slow'])
      assert.match(copy.slow ?? '', /2/)
    })

    it(`${lang}: at 90 s (the slow case of the review) the counter still counts and the line stays`, () => {
      const copy = waitCopy(90, lang)

      assert.match(copy.counter, /1:30/)
      assert.notEqual(copy.slow, null)
    })

    it(`${lang}: says nothing rule 2 bans, at any second of a 2-minute wait`, () => {
      for (let s = 0; s <= 125; s++) {
        const { counter, slow } = waitCopy(s, lang)
        assert.doesNotMatch(`${counter} ${slow ?? ''}`, BANNED[lang], `${lang} at ${s} s`)
      }
    })
  }

  it('the line comes at exactly 45 s', () => {
    assert.equal(SLOW_AFTER_S, 45)
    assert.equal(waitCopy(44.99, 'en').slow, null)
    assert.notEqual(waitCopy(45, 'en').slow, null)
  })

  it('reads in English as the plan words it', () => {
    assert.equal(waitCopy(12, 'en').counter, '0:12 elapsed')
    assert.equal(waitCopy(45, 'en').slow, 'Still working. Gemini is busy; this can take up to 2 minutes. Keep this page open.')
  })
})

describe('the wait hints say what a wait usually takes', () => {
  const HINTS = ['instr.extractingHint', 'steps.writingHint', 'brief.checkingHint', 'eval.running'] as const
  const USUALLY = { en: 'Usually 15–40 seconds.', ta: 'வழக்கமாக 15–40 வினாடிகள் ஆகும்.', zh: '通常需要 15–40 秒。' } as const

  for (const lang of LANGS) {
    it(`${lang}: every hint ends with the usual range, and none promises 10, 15 or 30 seconds`, () => {
      for (const key of HINTS) {
        const text = tables[lang][key]
        assert.ok(text.endsWith(USUALLY[lang]), `${key}: ${text}`)
        assert.doesNotMatch(text.replace(USUALLY[lang], ''), /\d/, `${key}: ${text}`)
      }
    })
  }
})

describe('announcedElapsed', () => {
  it('tells a screen reader nothing for the first 15 s, then every 15 s at most', () => {
    assert.equal(ANNOUNCE_EVERY_S, 15)
    assert.deepEqual([0, 1, 14, 15, 16, 29, 30, 44, 45, 90].map(announcedElapsed), [null, null, null, 15, 15, 15, 30, 30, 45, 90])
  })

  it('changes at most 8 times in a 2-minute wait, against 120 for the visible counter', () => {
    const changes = new Set(Array.from({ length: 121 }, (_, s) => announcedElapsed(s)))
    assert.equal(changes.size - 1, 8)
  })
})
