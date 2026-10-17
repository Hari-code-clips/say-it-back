import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Briefing, Round } from '../../src/api/types.ts'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { briefingFacts, factsLine, formatDuration, secondsToDecision } from '../../src/lib/briefingFacts.ts'

// v0.5.1: "Instruction to decision: 6 min 12 s · 2 rounds · 3 steps re-explained · 1 problem reported", read from the
// briefing's own record. No number may be made up: when one cannot be read, there is no line.

/** The lines keep a number and its unit together with a no-break space; compare them as plain text. */
const plain = (text: string) => text.replace(/\u00a0/g, ' ')

const round = (n: number, kind: Round['kind'], stepIds: string[]) => ({ n, kind, stepIds }) as Round
const hazard = (id: string) => ({ id, kind: 'tap' as const, original: '', translation: '', detectedLang: 'none' as const, raisedAt: '2026-10-15T10:01:00Z' })

function briefing(over: Partial<Briefing> = {}): Pick<Briefing, 'createdAt' | 'decision' | 'rounds' | 'hazards'> {
  return {
    createdAt: '2026-10-15T10:00:00Z',
    decision: { value: 'go', openStepIds: [], at: '2026-10-15T10:06:12Z' },
    rounds: [round(1, 'initial', ['s1', 's2', 's3', 's4']), round(2, 'reexplain', ['s2', 's3', 's4'])],
    hazards: [hazard('h1')],
    ...over,
  }
}

describe('briefingFacts', () => {
  it('reads the time, the rounds, the distinct re-explained steps and the reports from the record', () => {
    assert.deepEqual(briefingFacts(briefing()), { seconds: 372, rounds: 2, reexplained: 3, problems: 1, decided: true })
  })

  it('counts a step re-explained twice once', () => {
    const b = briefing({ rounds: [round(1, 'initial', ['s1', 's2']), round(2, 'reexplain', ['s1', 's2']), round(3, 'reexplain', ['s2'])] })
    assert.equal(briefingFacts(b)?.reexplained, 2)
  })

  it('runs to now before a decision, and says so', () => {
    const facts = briefingFacts(briefing({ decision: undefined }), new Date('2026-10-15T10:02:05Z'))
    assert.deepEqual(facts && { seconds: facts.seconds, decided: facts.decided }, { seconds: 125, decided: false })
  })

  it('has no line when a number cannot be read', () => {
    assert.equal(briefingFacts(briefing({ decision: undefined })), null, 'undecided, and no now')
    assert.equal(briefingFacts(briefing({ createdAt: '' })), null, 'no creation time')
    assert.equal(briefingFacts(briefing({ createdAt: 'not a date' })), null, 'an invalid creation time')
    assert.equal(briefingFacts(briefing({ decision: { value: 'no_go', openStepIds: [], at: '2026-10-15T09:00:00Z' } })), null, 'decided before created')
  })

  it('reads a record made before v0.4, which has no hazards field, as no problem reported', () => {
    assert.equal(briefingFacts(briefing({ hazards: undefined }))?.problems, 0)
  })
})

describe('secondsToDecision (the Records list)', () => {
  it('is the time from creation to decision, or null without both', () => {
    assert.equal(secondsToDecision('2026-10-15T10:00:00Z', '2026-10-15T10:06:12Z'), 372)
    assert.equal(secondsToDecision('2026-10-15T10:00:00Z', undefined), null)
    assert.equal(secondsToDecision(undefined, '2026-10-15T10:06:12Z'), null)
    assert.equal(secondsToDecision('2026-10-15T10:06:12Z', '2026-10-15T10:00:00Z'), null)
  })
})

describe('formatDuration', () => {
  it('writes seconds, minutes and seconds, or hours and minutes, in each UI language', () => {
    assert.deepEqual([45, 372, 3900, 0, -5].map((s) => plain(formatDuration(s, 'en'))), ['45 s', '6 min 12 s', '1 h 5 min', '0 s', '0 s'])
    assert.equal(plain(formatDuration(372, 'ta')), '6 நிமி 12 வி')
    assert.equal(plain(formatDuration(372, 'zh')), '6 分 12 秒')
    assert.equal(plain(formatDuration(3900, 'zh')), '1 小时 5 分')
  })

  it('never breaks a line between a number and its unit ("46" above "s" at 320 px)', () => {
    for (const lang of ['en', 'ta', 'zh'] as const) {
      assert.doesNotMatch(formatDuration(46, lang), /\d /, lang)
      assert.doesNotMatch(formatDuration(372, lang), /\d /, lang)
      assert.doesNotMatch(factsLine(briefingFacts(briefing())!, lang), /\d /, lang)
    }
  })
})

describe('factsLine', () => {
  it('reads as the plan words it, in English', () => {
    assert.equal(plain(factsLine(briefingFacts(briefing())!, 'en')), 'Instruction to decision: 6 min 12 s · 2 rounds · 3 steps re-explained · 1 problem reported')
  })

  it('leaves out what is zero, and says one round in the singular', () => {
    const facts = briefingFacts(briefing({ rounds: [round(1, 'initial', ['s1'])], hazards: [] }))!
    assert.equal(plain(factsLine(facts, 'en')), 'Instruction to decision: 6 min 12 s · 1 round')
  })

  it('says "so far" before a decision', () => {
    const facts = briefingFacts(briefing({ decision: undefined }), new Date('2026-10-15T10:00:45Z'))!
    assert.match(plain(factsLine(facts, 'en')), /^Briefing so far: 45 s · 2 rounds/)
  })

  it('is written in Tamil and Chinese too, with the same numbers', () => {
    const facts = briefingFacts(briefing())!
    for (const lang of ['ta', 'zh'] as const) {
      const line = factsLine(facts, lang)
      for (const n of ['6', '12', '2', '3', '1']) assert.ok(line.includes(n), `${lang}: ${n} in ${line}`)
      assert.doesNotMatch(line, /\{\w+\}/)
    }
  })

  it('says nothing Rule 2 bans, in any language', () => {
    const keys = Object.keys(en).filter((k) => k.startsWith('facts.')) as (keyof typeof en)[]
    assert.ok(keys.length >= 11)
    for (const k of keys) {
      assert.doesNotMatch(en[k], /\b(approved|passed|understood)\b/i, k)
      assert.doesNotMatch(ta[k], /புரிந்த|அங்கீகரி|ஒப்புதல்|தேர்ச்சி/u, k)
      assert.doesNotMatch(zh[k], /理解|明白|通过|批准|审批|合格/u, k)
    }
  })
})
