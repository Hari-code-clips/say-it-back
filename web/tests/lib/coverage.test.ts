import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Script } from '../../src/api/types.ts'
import { scriptCoverage, stepsBySentence } from '../../src/lib/coverage.ts'

const script = (over: Partial<Script> = {}): Script => ({
  instruction: 'Switch off. Lock it. Test it.',
  instructionBackTranslation: '',
  questions: [
    { id: 'q1', text: '', backTranslation: '', stepIds: ['s1', 's2'] },
    { id: 'q2', text: '', backTranslation: '', stepIds: ['s3'] },
  ],
  stepMap: { s1: [0], s2: [1], s3: [2] },
  closing: '',
  ...over,
})

describe('scriptCoverage', () => {
  it('is complete when every step is delivered and asked about', () => {
    assert.deepEqual(scriptCoverage(['s1', 's2', 's3'], script()), { notDelivered: [], notAsked: [] })
  })

  it('names steps the instruction does not deliver and no question asks about', () => {
    const gap = script({ stepMap: { s1: [0], s2: [], s3: [2] }, questions: [{ id: 'q1', text: '', backTranslation: '', stepIds: ['s1', 's3'] }] })
    assert.deepEqual(scriptCoverage(['s1', 's2', 's3'], gap), { notDelivered: ['s2'], notAsked: ['s2'] })
  })

  it('only looks at the steps in scope (re-explain rounds)', () => {
    assert.deepEqual(scriptCoverage(['s3'], script()), { notDelivered: [], notAsked: [] })
  })
})

describe('stepsBySentence', () => {
  it('lists the steps each instruction sentence delivers', () => {
    const { sentences, stepIds } = stepsBySentence(script({ stepMap: { s1: [0], s2: [0, 1], s3: [2] } }))
    assert.equal(sentences.length, 3)
    assert.deepEqual(stepIds, [['s1', 's2'], ['s2'], ['s3']])
  })

  it('indexes the lines of a generated script, whatever their punctuation', () => {
    const lines = script({ instruction: 'Switch off the breaker\nLock it. Tag it.\nTest it', stepMap: { s1: [0], s2: [1], s3: [2] } })

    const { sentences, stepIds } = stepsBySentence(lines)

    assert.deepEqual(sentences, ['Switch off the breaker', 'Lock it. Tag it.', 'Test it'])
    assert.deepEqual(stepIds, [['s1'], ['s2'], ['s3']])
  })
})
