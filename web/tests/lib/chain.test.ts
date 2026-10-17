import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Round } from '../../src/api/types.ts'
import { chainReasonKey, eventNumber, hasNoChain, samplesByRound, shortHash, verifiedCount } from '../../src/lib/chain.ts'
import { en } from '../../src/i18n/en.ts'

describe('reading the record chain', () => {
  it('shows a short head hash', () => {
    assert.equal(shortHash('3f9a1c0b7e2d'.padEnd(64, '0')), '3f9a1c0b7e2d')
    assert.equal(shortHash(undefined), '')
  })

  it('counts the events the server checked, from the contract\'s number or a list', () => {
    assert.equal(verifiedCount({ events: 14 }, 3), 14)
    assert.equal(verifiedCount({ events: [1, 2] }, 3), 2)
    assert.equal(verifiedCount({ events: 'x' }, 3), 3)
  })

  it('labels round events with their round and hazard events with the problem number', () => {
    assert.equal(eventNumber({ type: 'round_judged', data: { n: 2 } }), '2')
    assert.equal(eventNumber({ type: 'hazard_raised', data: { hazardId: 'h3' } }), '3')
    assert.equal(eventNumber({ type: 'created', data: {} }), '')
  })

  it('lists which answers were stored samples, by round and question number', () => {
    const round = (n: number, qids: string[], sampleAnswers?: string[]) =>
      ({ n, sampleAnswers, script: { questions: qids.map((id) => ({ id })) } }) as unknown as Round
    assert.deepEqual(samplesByRound([round(1, ['q1', 'q2', 'q3'], ['q1']), round(2, ['q4', 'q5'], ['q4']), round(3, ['q6'])]), [
      { round: 1, numbers: [1] },
      { round: 2, numbers: [1] },
    ])
  })
})

describe('why a chain is broken, in words', () => {
  it('every reason code of the backend has its own sentence, and an unknown one still reads as words', () => {
    const codes = ['seq_mismatch', 'prev_hash_mismatch', 'hash_mismatch', 'instruction_mismatch', 'sop_mismatch', 'steps_mismatch', 'script_mismatch',
      'ratings_mismatch', 'round_missing', 'hazard_mismatch', 'hazard_missing', 'decision_mismatch', 'record_hash_mismatch', 'unrecorded_change']
    const keys = codes.map(chainReasonKey)
    assert.equal(new Set(keys).size, codes.length)
    assert.ok(keys.every((k) => k in en && k !== 'chain.reason.other'))
    assert.equal(chainReasonKey('something_new'), 'chain.reason.other')
    assert.equal(chainReasonKey(undefined), 'chain.reason.other')
  })

  it('a record from before v0.4 has no chain: that is said plainly, not as tampering', () => {
    assert.equal(hasNoChain({ reason: 'no_chain', events: 0 }), true)
    assert.equal(hasNoChain({ reason: 'steps_mismatch', events: 9 }), false)
  })
})
