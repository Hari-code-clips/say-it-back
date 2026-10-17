import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { failurePlan } from '../../src/screens/brief/failurePlan.ts'

describe('failurePlan: a voice session that failed', () => {
  it('offers turn by turn first and a quieter retry after a Live failure', () => {
    const plan = failurePlan({ kind: 'failed', mode: 'live', code: undefined, micProblem: false })
    assert.deepEqual(plan, { offerTurn: true, hint: 'turn', offerRetry: true, retryQuiet: true, backToScript: false })
  })

  it('only retries after a turn-by-turn failure, and after a microphone problem', () => {
    assert.deepEqual(failurePlan({ kind: 'failed', mode: 'turn', micProblem: false }), { offerTurn: false, hint: null, offerRetry: true, retryQuiet: false, backToScript: false })
    assert.deepEqual(failurePlan({ kind: 'failed', mode: 'live', micProblem: true }), { offerTurn: false, hint: null, offerRetry: true, retryQuiet: false, backToScript: false })
  })

  it('after both voice tickets are used (limit), offers turn by turn, which needs no ticket, but no retry', () => {
    const plan = failurePlan({ kind: 'failed', mode: 'live', code: 'limit', micProblem: false })
    assert.equal(plan.offerTurn, true)
    assert.equal(plan.offerRetry, false)
  })

  it('on daily_limit offers neither turn by turn (it spends the same budget) nor a retry (it cannot work today)', () => {
    const plan = failurePlan({ kind: 'failed', mode: 'live', code: 'daily_limit', micProblem: false })
    assert.deepEqual(plan, { offerTurn: false, hint: null, offerRetry: false, retryQuiet: false, backToScript: false })
  })

  it('on daily_limit while turn by turn was running (its TTS call was refused) offers no retry either', () => {
    const plan = failurePlan({ kind: 'failed', mode: 'turn', code: 'daily_limit', micProblem: false })
    assert.deepEqual(plan, { offerTurn: false, hint: null, offerRetry: false, retryQuiet: false, backToScript: false })
  })
})

describe('failurePlan: the answers were recorded but the check failed', () => {
  it('keeps Retry, because the recordings are on the device', () => {
    assert.deepEqual(failurePlan({ kind: 'submit_failed', micProblem: false }), { offerTurn: false, hint: null, offerRetry: true, retryQuiet: false, backToScript: false })
  })

  it('offers turn by turn, and says why, when the relay never saved the Live session', () => {
    const plan = failurePlan({ kind: 'submit_failed', code: 'live_not_recorded', micProblem: false })
    assert.deepEqual(plan, { offerTurn: true, hint: 'not_recorded', offerRetry: true, retryQuiet: true, backToScript: false })
  })

  it('does not offer turn by turn on daily_limit, and Retry stays as the one control', () => {
    const plan = failurePlan({ kind: 'submit_failed', code: 'daily_limit', micProblem: false })
    assert.deepEqual(plan, { offerTurn: false, hint: null, offerRetry: true, retryQuiet: false, backToScript: false })
  })
})

describe('failurePlan: v0.4, the script was never confirmed (409 script_not_approved)', () => {
  for (const kind of ['failed', 'submit_failed'] as const) {
    it(`${kind}: offers only the way back to the script, never turn by turn or a retry (nothing may be spoken first)`, () => {
      assert.deepEqual(failurePlan({ kind, mode: 'live', code: 'script_not_approved', micProblem: false }), {
        offerTurn: false,
        hint: null,
        offerRetry: false,
        retryQuiet: false,
        backToScript: true,
      })
    })
  }
})
