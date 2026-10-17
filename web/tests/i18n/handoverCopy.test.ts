import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { WORKER_WORDS } from '../../src/i18n/worker.ts'
import type { Lang } from '../../src/api/types.ts'

// The words of the handover build (F1-F3 of build-notes/25): user copy never says "ticket", the worker's failure line exists in every
// worker language, and every new Tamil, Chinese and worker-language string is marked DRAFT for the native-speaker review.

const read = (path: string) => readFileSync(new URL(`../../src/i18n/${path}`, import.meta.url), 'utf8')

describe('no "ticket" in anything a person reads', () => {
  const all: [string, string][] = [
    ...Object.entries(en).map(([k, v]): [string, string] => [`en ${k}`, v]),
    ...Object.entries(ta).map(([k, v]): [string, string] => [`ta ${k}`, v]),
    ...Object.entries(zh).map(([k, v]): [string, string] => [`zh ${k}`, v]),
    ...Object.entries(WORKER_WORDS).flatMap(([lang, words]) => Object.entries(words).map(([k, v]): [string, string] => [`worker ${lang} ${k}`, v])),
  ]

  it('English, Tamil (டிக்கெட்), Chinese (票, 凭证) and every worker language', () => {
    const offenders = all.filter(([, text]) => /ticket|டிக்கெட்|凭证|票据|门票/iu.test(text))
    assert.deepEqual(offenders, [])
  })

  it('the live-voice connection error says "connection", in all three UI languages', () => {
    assert.equal(en['brief.err.bad_ticket'], 'The live voice connection was not accepted. Try again.')
    assert.match(ta['brief.err.bad_ticket'], /இணைப்பு/)
    assert.match(zh['brief.err.bad_ticket'], /连接/)
  })
})

describe('the worker’s failure line', () => {
  const langs = Object.keys(WORKER_WORDS) as Lang[]

  it('exists in all eight worker languages and says something other than the hand-back line', () => {
    assert.deepEqual(langs.sort(), ['bn', 'en', 'hi', 'my', 'or', 'ta', 'te', 'zh'])
    for (const lang of langs) {
      const w = WORKER_WORDS[lang]
      assert.match(w.giveSupervisor, /\S/, lang)
      assert.notEqual(w.giveSupervisor, w.handBack, lang)
    }
  })

  it('is written in the worker’s own script: no English word in a non-English worker language', () => {
    for (const lang of langs.filter((l) => l !== 'en')) assert.doesNotMatch(WORKER_WORDS[lang].giveSupervisor, /[A-Za-z]/, lang)
  })

  it('is short enough to read at a glance (one sentence, under 60 characters)', () => {
    for (const lang of langs) assert.ok([...WORKER_WORDS[lang].giveSupervisor].length < 60, lang)
  })
})

describe('draft marking for the native-speaker review', () => {
  const NEW_KEYS = [
    'script.title', 'script.titleReexplain', 'script.subtitle', 'script.heardIn', 'script.heardInHint', 'script.closingNoTranslation', 'script.workerText',
    'script.workerTextHint', 'script.approve', 'script.approvalRecorded', 'script.toHandover', 'brief.handoverBody', 'brief.give', 'brief.exitInfo',
    'brief.backToHandover', 'brief.exit', 'brief.exitHint', 'brief.supervisor', 'brief.supervisorHint', 'brief.supervisorTitle', 'brief.supervisorBody',
    'brief.supervisorConfirm', 'brief.holdToContinue', 'brief.haveThePhoneTitle', 'brief.haveThePhoneBody', 'brief.haveThePhoneConfirm', 'brief.checkingHint', 'brief.check.label', 'brief.check.s1', 'brief.check.s2', 'brief.check.s3',
    'brief.check.note', 'brief.err.bad_ticket', 'brief.sample.label', 'brief.sample.checking', 'brief.sample.has', 'brief.sample.rest', 'brief.sample.none',
    'brief.sample.failed', 'brief.reportHeldHint',
    // 16 Oct: a stored answer for every question (build-notes/30)
    'brief.sample.all', 'brief.sample.hasMany', 'brief.sample.synthetic', 'brief.sample.syntheticMany',
  ] as const

  // `brief.useTurn` is the one old key that changed: Tamil only (a shorter label that fits one line at 320 px).
  const CHANGED: Record<'ta' | 'zh', readonly string[]> = { ta: ['brief.useTurn'], zh: [] }

  for (const lang of ['ta', 'zh'] as const) {
    it(`${lang}: every new or changed line carries DRAFT, NEEDS NATIVE-SPEAKER REVIEW`, () => {
      const lines = read(`${lang}/flow.ts`).split('\n')
      const unmarked = [...NEW_KEYS, ...CHANGED[lang]].filter((key) => !lines.find((l) => l.startsWith(`  '${key}':`))?.includes('DRAFT'))
      assert.deepEqual(unmarked, [])
    })
  }

  it('the changed 409 line in core.ts says approve, and its Tamil and Chinese carry DRAFT', () => {
    for (const lang of ['ta', 'zh'] as const) {
      const line = read(`${lang}/core.ts`).split('\n').find((l) => l.startsWith("  'error.script_not_approved':"))
      assert.ok(line?.includes('DRAFT'), lang)
    }
    assert.doesNotMatch(en['error.script_not_approved'], /hand the phone|hand it over/i)
    assert.doesNotMatch(ta['error.script_not_approved'], /போனைக் கொடுங்கள்/)
    assert.doesNotMatch(zh['error.script_not_approved'], /把手机交给工人/)
  })

  it('the worker words carry the DRAFT note for giveSupervisor, next to the v0.4 one', () => {
    const src = read('worker.ts')
    assert.match(src, /handover word `giveSupervisor`[^\n]*DRAFT[^\n]*NATIVE-SPEAKER REVIEW/)
    assert.match(src, /^\/\/ DRAFT: these translations are machine-written/m)
  })

  it('every key in the list exists in all three tables', () => {
    for (const key of NEW_KEYS) for (const table of [en, ta, zh] as Record<string, string>[]) assert.ok(key in table, key)
  })
})

describe('words the handover build removed from the supervisor’s language stay gone', () => {
  it('no status line, no mode chip on the worker screen, no per-button sample copy, no "Hand phone to worker"', () => {
    for (const table of [en, ta, zh] as Record<string, string>[]) {
      for (const gone of ['brief.status.connecting', 'brief.status.listening', 'brief.leave', 'brief.doneSr', 'brief.sample.use', 'brief.sample.useShort', 'brief.sample.caption', 'brief.sample.playing', 'script.handover', 'script.handoverHint', 'script.confirmedAt']) {
        assert.ok(!(gone in table), gone)
      }
    }
    assert.ok(!Object.values(en).includes('Hand phone to worker'))
  })

  it('"Approve script" and "Give phone to worker" are the two acts, in English', () => {
    assert.equal(en['script.approve'], 'Approve script')
    assert.equal(en['brief.give'], 'Give phone to worker')
    assert.equal(en['brief.holdToContinue'], 'Supervisor: hold to continue')
    assert.equal(en['brief.supervisor'], "I'm the supervisor")
  })
})
