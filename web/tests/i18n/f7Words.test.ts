import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { GOOGLE_PRODUCTS } from '../../src/screens/about/google.ts'

// F7 (build-notes/25): the words that drifted between screens, and the copy that went stale in v0.5.3.
// docs/API.md, guard rule 1 (v0.5.3): agreement stands, a contradiction in either pass stands, any other disagreement is
// "Ask again", and a disagreement can never give "Got it". "The worse verdict wins" described v0.5.2 and earlier.

const tables = { en, ta, zh } as const
const text = (lang: keyof typeof tables) => Object.entries(tables[lang] as Record<string, string>)

describe('"the worse verdict wins" is gone (F7)', () => {
  // The English, plus the Tamil (மோசமான மதிப்பீடே வெல்லும் = the worse rating wins) and Chinese (取较严重 = take the more severe).
  const STALE = /worse verdict|worse wins|more severe|மோசமான மதிப்பீடே|较严重|较差的结论/i

  for (const lang of ['en', 'ta', 'zh'] as const) {
    it(`${lang}: no string says it`, () => {
      assert.deepEqual(text(lang).filter(([, v]) => STALE.test(v)).map(([k]) => k), [])
    })
  }

  it('the About page says the v0.5.3 rule for judge B', () => {
    const roles = GOOGLE_PRODUCTS.map((p) => p.role)
    assert.deepEqual(roles.filter((r) => STALE.test(r)), [])
    const judgeB = GOOGLE_PRODUCTS.find((p) => p.role.startsWith('Judge B'))
    assert.ok(judgeB, 'judge B is listed')
    assert.match(judgeB.role, /agree/)
    assert.match(judgeB.role, /contradiction/)
    assert.match(judgeB.role, /Ask again/)
    assert.match(judgeB.role, /never Got it/)
  })

  it('the guard hint says it in all three languages: agreement, a contradiction, any other split is Ask again, never Got it', () => {
    assert.match(en['models.guardHint'], /agree/)
    assert.match(en['models.guardHint'], /contradiction/)
    assert.match(en['models.guardHint'], /Ask again, never Got it/)
    assert.match(ta['models.guardHint'], /மீண்டும் கேளுங்கள்/)
    assert.match(ta['models.guardHint'], /சொல்லப்பட்டது/) // never "Got it" (ta: சொல்லப்பட்டது)
    assert.match(zh['models.guardHint'], /再问一次/)
    assert.match(zh['models.guardHint'], /已说到/) // never "Got it" (zh: 已说到)
  })
})

describe('one decide label, and the SOP-only tag (F7)', () => {
  it('"Decide: Go or No-go" is the only decide label; "Decide now" is gone from every language', () => {
    assert.equal(en['result.decide'], 'Decide: Go or No-go')
    assert.deepEqual(text('en').filter(([, v]) => /^decide now$/i.test(v)), [])
    for (const lang of ['en', 'ta', 'zh'] as const) assert.ok(!('result.decideNow' in tables[lang]))
  })

  it('"Not in your briefing" is now "From the SOP, not in your instruction"', () => {
    assert.equal(en['steps.sopOnly'], 'From the SOP, not in your instruction')
    assert.deepEqual(text('en').filter(([, v]) => /Not in your briefing/i.test(v)), [])
  })

  it('Re-explain says what it writes: "Write the re-explanation", not "Write new questions"', () => {
    assert.equal(en['reexplain.write'], 'Write the re-explanation')
    assert.deepEqual(text('en').filter(([, v]) => /Write new questions/i.test(v)), [])
  })
})

describe('new Tamil and Chinese strings are drafts for a native reader (F7)', () => {
  const NEW_KEYS = [
    'start.need.customTitle', 'start.need.customSop', 'start.need.permitRef', 'start.need.permitRefInvalid',
    'steps.sopOnly', 'result.disagreedAsk', 'result.disagreedWrong', 'models.guardHint', 'hazard.banner', 'hazard.bannerMany',
    'hazard.bannerAction', 'reexplain.write', 'decision.need.choice', 'decision.need.reason', 'decision.need.hazard',
    'decision.backToResult', 'decision.confirm.title', 'decision.confirm.body', 'decision.confirm.open', 'decision.confirm.cancel',
    'decision.confirm.go', 'decision.confirm.noGo', 'record.decisionTitle', 'record.rebrief', 'record.rebriefHint',
    'start.subtitle', 'start.changeTask', 'instr.need', 'reexplain.need', 'reexplain.openHint', 'steps.need.none', 'steps.need.text',
  ]

  // DRAFT may sit on the key's own line or on the comment that opens its block: walk up from the key over its block's other lines
  // (no blank line, no other comment) to the first comment line, and that one must say DRAFT.
  const marked = (lines: string[], at: number): boolean => {
    if (/DRAFT/.test(lines[at]!)) return true
    for (let i = at - 1; i >= 0 && lines[i]!.trim() !== ''; i--) {
      if (/^\s*\/\//.test(lines[i]!)) return /DRAFT/.test(lines[i]!)
    }
    return false
  }

  for (const lang of ['ta', 'zh'] as const) {
    it(`${lang}: each new key is marked DRAFT in ${lang}/flow.ts, on its line or in the comment that opens its block`, () => {
      const lines = readFileSync(new URL(`../../src/i18n/${lang}/flow.ts`, import.meta.url), 'utf8').split('\n')
      const unmarked = NEW_KEYS.filter((key) => {
        const at = lines.findIndex((l) => l.trimStart().startsWith(`'${key}'`))
        assert.ok(at >= 0, `${key} is defined`)
        return !marked(lines, at)
      })
      assert.deepEqual(unmarked, [])
    })
  }
})
