import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Briefing, Round, Status, Step } from '../../src/api/types.ts'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { REASON_MIN, decisionGate, resultBar } from '../../src/screens/result/gates.ts'

// F4 and F5 (build-notes/25): Re-explain and Decide are in the result's sticky bar on every round; Record decision says why it is
// off. Both are decided here as data and drawn by the screens.

const step = (id: string): Step => ({ id, text: id, hazard: '', essential: [], source: 'instruction', speakable: true })
const rounds = (n: number): Round[] => Array.from({ length: n }, (_, i) => ({ n: i + 1 }) as Round)

function briefing(status: Status, over: Partial<Briefing> = {}): Briefing {
  return {
    id: 'b_x', siteId: 'sg', taskId: 't', sop: { id: 'S', version: 'v1', title: '', text: '' }, supervisorLang: 'en', workerLang: 'ta',
    instruction: '', status, steps: [step('s1'), step('s2')], stepsVersion: 1, conflicts: [], rounds: [], latestVerdicts: {},
    promptVersion: 'p', createdAt: '', updatedAt: '', ...over,
  }
}

const OPEN = { s1: 'covered', s2: 'unclear' } as const
const ALL = { s1: 'covered', s2: 'covered' } as const

describe('the result bar (F4)', () => {
  it('round 1 with an open step: Re-explain leads, Decide waits beside it', () => {
    assert.deepEqual(resultBar(briefing('judged', { latestVerdicts: OPEN, rounds: rounds(1) })), { primary: 'reexplain', secondary: 'decide' })
  })

  it('round 2 with an open step: the same two actions', () => {
    assert.deepEqual(resultBar(briefing('judged', { latestVerdicts: OPEN, rounds: rounds(2) })), { primary: 'reexplain', secondary: 'decide' })
  })

  it('every step covered: Decide is the only action, on every round', () => {
    for (const n of [1, 2, 3]) assert.deepEqual(resultBar(briefing('judged', { latestVerdicts: ALL, rounds: rounds(n) })), { primary: 'decide', secondary: null })
  })

  it('no round left (3 rounds): Decide is the only action even with open steps', () => {
    assert.deepEqual(resultBar(briefing('judged', { latestVerdicts: OPEN, rounds: rounds(3) })), { primary: 'decide', secondary: null })
  })

  it('"Decide: Go or No-go" is the one decide label in all three languages (no "Decide now")', () => {
    assert.equal(en['result.decide'], 'Decide: Go or No-go')
    for (const table of [en, ta, zh]) assert.ok(!('result.decideNow' in table), 'result.decideNow is gone')
    assert.match(zh['result.decide'], /决定/)
    assert.match(ta['result.decide'], /Go/)
  })
})

describe('Record decision and its reason (F5)', () => {
  const base = { choice: null, reason: '', openStepCount: 0, goLocked: false } as const

  it('nothing chosen: off, and it says "Choose Go or No-go"', () => {
    const gate = decisionGate(base)
    assert.equal(gate.valid, false)
    assert.equal(gate.need, 'choice')
    assert.equal(gate.reasonKey && en[gate.reasonKey], 'Choose Go or No-go')
  })

  it('Go with an open step and no reason: off, and it says why work can start must be written', () => {
    const gate = decisionGate({ ...base, choice: 'go', openStepCount: 2, reason: 'ok' })
    assert.equal(gate.valid, false)
    assert.equal(gate.reasonKey && en[gate.reasonKey], 'Write why work can start with open steps')
  })

  it(`Go with an open step and a reason of ${REASON_MIN} characters: on`, () => {
    assert.equal(decisionGate({ ...base, choice: 'go', openStepCount: 2, reason: 'x'.repeat(REASON_MIN) }).valid, true)
    assert.equal(decisionGate({ ...base, choice: 'go', openStepCount: 2, reason: `  ${'x'.repeat(REASON_MIN - 1)}  ` }).valid, false, 'spaces do not count')
  })

  it('Go with every step covered needs no reason', () => {
    assert.deepEqual(decisionGate({ ...base, choice: 'go' }), { valid: true, need: null, reasonKey: null })
  })

  it('Go while a reported problem has no note: locked, and it says what to do', () => {
    const gate = decisionGate({ ...base, choice: 'go', goLocked: true, reason: 'a long enough reason' })
    assert.equal(gate.valid, false)
    assert.equal(gate.reasonKey && en[gate.reasonKey], 'Note what you did about the reported problem')
  })

  it('No-go is always open, with open steps, no reason and a reported problem', () => {
    assert.equal(decisionGate({ ...base, choice: 'no_go', openStepCount: 3, goLocked: true }).valid, true)
  })

  it('every reason exists in Tamil and Chinese too', () => {
    for (const key of ['decision.need.choice', 'decision.need.reason', 'decision.need.hazard'] as const) {
      for (const table of [en, ta, zh]) assert.match(table[key], /\S/)
    }
  })
})

describe('the confirm before Record decision (F5)', () => {
  it('says the decision is final and the record cannot be edited, and names both buttons', () => {
    assert.equal(en['decision.confirm.body'], "This is final. The record can't be edited.")
    assert.equal(en['decision.confirm.go'], 'Record Go')
    assert.equal(en['decision.confirm.noGo'], 'Record No-go')
    assert.equal(en['decision.confirm.cancel'], 'Keep editing')
    for (const table of [ta, zh]) for (const key of ['decision.confirm.title', 'decision.confirm.body', 'decision.confirm.go', 'decision.confirm.noGo', 'decision.confirm.cancel'] as const) assert.match(table[key], /\S/)
  })
})
