import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Script } from '../../src/api/types.ts'
import { deliveryIssues, scriptCoverage, stepsBySentence } from '../../src/lib/coverage.ts'

describe('deliveryIssues', () => {
  it('flags a segment the voice never said, one in the wrong script, and one that strayed from the script', () => {
    const delivery = [
      { segment: 'instruction', similarity: 0.97, scriptOk: true },
      { segment: 'q1', similarity: 0, scriptOk: false }, // never spoken
      { segment: 'q2', similarity: 0.9, scriptOk: false }, // right words, wrong script (Odia drifting to Hindi)
      { segment: 'q3', similarity: 0.55, scriptOk: true }, // paraphrased
      { segment: 'closing', similarity: 0.7, scriptOk: true }, // at the limit still passes
    ]

    assert.deepEqual(deliveryIssues(delivery).map((d) => d.segment), ['q1', 'q2', 'q3'])
  })

  it('has nothing to say about a round with no delivery check (Turn mode)', () => {
    assert.deepEqual(deliveryIssues([]), [])
  })
})

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
