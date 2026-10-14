import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Briefing, Round, Status, Step } from '../../src/api/types.ts'
import { allowedPhases, canReexplain, defaultPhase, isPhase, openSteps } from '../../src/flow/phases.ts'

const step = (id: string): Step => ({ id, text: id, hazard: '', essential: [], source: 'instruction', speakable: true })

function briefing(status: Status, over: Partial<Briefing> = {}): Briefing {
  return {
    id: 'b_x', siteId: 'sg', taskId: 't', sop: { id: 'S', version: 'v1', title: '', text: '' }, supervisorLang: 'en', workerLang: 'ta',
    instruction: '', status, steps: [step('s1'), step('s2')], stepsVersion: 1, conflicts: [], rounds: [], latestVerdicts: {},
    promptVersion: 'p', createdAt: '', updatedAt: '', ...over,
  }
}

const rounds = (n: number): Round[] => Array.from({ length: n }, (_, i) => ({ n: i + 1 }) as Round)

describe('allowedPhases / defaultPhase follow the server state machine', () => {
  const cases: [Status, string[], string][] = [
    ['draft', ['instruction', 'steps'], 'steps'],
    ['steps_proposed', ['instruction', 'steps'], 'steps'],
    ['steps_confirmed', ['steps'], 'steps'],
    ['briefing', ['script', 'brief'], 'script'],
    ['judged', ['result', 'reexplain', 'decision'], 'result'],
    ['decided', ['record'], 'record'],
  ]
  for (const [status, allowed, def] of cases) {
    it(`${status}: ${allowed.join(', ')} (default ${def})`, () => {
      assert.deepEqual(allowedPhases(briefing(status)), allowed)
      assert.equal(defaultPhase(briefing(status)), def)
    })
  }

  it('nothing but the record is reachable once decided', () => {
    assert.equal(allowedPhases(briefing('decided')).includes('decision'), false)
  })
})

describe('isPhase', () => {
  it('accepts route segments of the flow and rejects anything else', () => {
    assert.equal(isPhase('result'), true)
    assert.equal(isPhase('admin'), false)
    assert.equal(isPhase(undefined), false)
  })
})

describe('openSteps / canReexplain', () => {
  it('a step is open unless its latest verdict is covered', () => {
    const b = briefing('judged', { latestVerdicts: { s1: 'covered', s2: 'missed' } })
    assert.deepEqual(openSteps(b).map((s) => s.id), ['s2'])
  })

  it('a step that was never rated counts as open', () => {
    assert.deepEqual(openSteps(briefing('judged', { latestVerdicts: { s1: 'covered' } })).map((s) => s.id), ['s2'])
  })

  it('re-explain needs a judged round, an open step and fewer than 3 rounds', () => {
    const open = { latestVerdicts: { s1: 'covered', s2: 'unclear' } } as const
    assert.equal(canReexplain(briefing('judged', { ...open, rounds: rounds(1) })), true)
    assert.equal(canReexplain(briefing('judged', { ...open, rounds: rounds(3) })), false)
    assert.equal(canReexplain(briefing('judged', { latestVerdicts: { s1: 'covered', s2: 'covered' }, rounds: rounds(1) })), false)
    assert.equal(canReexplain(briefing('briefing', { ...open, rounds: rounds(1) })), false)
  })
})
