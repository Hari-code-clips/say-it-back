import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { describe, it } from 'node:test'
import type { Briefing } from '../../src/api/types.ts'
import { canonical, sha256Hex, verifyChain, withEvent, ZERO_HASH } from '../../src/mock/chain.ts'

const nodeSha = (s: string) => createHash('sha256').update(s, 'utf8').digest('hex')

describe('the mock chain hashes like the contract', () => {
  it('SHA-256 matches node:crypto, across block boundaries and non-Latin text', () => {
    for (const text of ['', 'abc', 'a'.repeat(55), 'a'.repeat(56), 'a'.repeat(64), 'x'.repeat(1000), 'லோடுக்கு அடியில நின்னு', '吊物落地前待在围栏外']) {
      assert.equal(sha256Hex(text), nodeSha(text), JSON.stringify(text.slice(0, 20)))
    }
  })

  it('canonical JSON sorts keys, drops whitespace and leaves characters unescaped', () => {
    assert.equal(canonical({ b: 1, a: [true, null, 'லோ'], c: { z: 2, y: 'x' } }), '{"a":[true,null,"லோ"],"b":1,"c":{"y":"x","z":2}}')
  })
})

function briefing(): Briefing {
  const b: Briefing = {
    id: 'b_x', siteId: 'sg', taskId: 'lifting-zone', sop: { id: 'S', version: 'v1', title: '', text: '' }, supervisorLang: 'en', workerLang: 'ta',
    instruction: 'Never go under the load.', status: 'steps_confirmed', steps: [{ id: 's1', text: 'Never stand under the load', hazard: '', essential: [], source: 'instruction', speakable: true }],
    stepsVersion: 1, conflicts: [], rounds: [], latestVerdicts: {}, hazards: [], events: [], recordHash: '', promptVersion: 'p', createdAt: '', updatedAt: '',
  }
  const created = withEvent(b, 'created', { instructionSha256: sha256Hex(b.instruction) }, '2026-10-14T10:00:00Z')
  return withEvent(created, 'steps_confirmed', { stepsVersion: 1, stepsSha256: sha256Hex(canonical(b.steps)) }, '2026-10-14T10:01:00Z')
}

describe('verify (endpoint 25) in the mock', () => {
  it('links each event to the one before, from 64 zeros, and the record hash is the last link', () => {
    const b = briefing()
    assert.equal(b.events?.[0]?.prevHash, ZERO_HASH)
    assert.equal(b.events?.[1]?.prevHash, b.events?.[0]?.hash)
    assert.equal(b.recordHash, b.events?.[1]?.hash)
    assert.deepEqual(verifyChain(b), { ok: true, events: 2, recordHash: b.recordHash })
  })

  it('catches an edit to a bound field and says at which event', () => {
    const b = briefing()
    const edited = { ...b, steps: [{ ...b.steps[0]!, text: 'Stand under the load' }] }
    const v = verifyChain(edited)
    assert.equal(v.ok, false)
    assert.equal(v.brokenAt, 2)
    assert.equal(v.reason, 'steps_mismatch') // the backend's code (Deviations 2026-10-14, record chain)
  })

  it('a record with no events verifies as no_chain, as one made before v0.4 does', () => {
    assert.deepEqual(verifyChain({ ...briefing(), events: [], recordHash: '' }), { ok: false, events: 0, recordHash: '', reason: 'no_chain' })
  })

  it('catches a rewritten event', () => {
    const b = briefing()
    const events = b.events!.map((e) => (e.seq === 1 ? { ...e, data: { instructionSha256: 'f'.repeat(64) } } : e))
    assert.equal(verifyChain({ ...b, events }).brokenAt, 1)
  })
})
