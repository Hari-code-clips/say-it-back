import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { EvalItem, EvalReport, EvalTryResult } from '../../src/api/types.ts'
import { evalItems, evalReport } from '../../src/mock/eval.ts'
import { pickSamples } from '../../src/screens/eval/pickSamples.ts'
import { liveView, storedResult } from '../../src/screens/eval/storedResult.ts'

// v0.5.1: the Sample page shows the evaluation run's stored result at once, labelled as such, and keeps the live check
// (16-105 s on real Gemini) as the second action. It must never show a result that no longer fits the clip or its labels.

const ITEM: EvalItem = {
  id: 'lifting-zone.q1.ta.demo.clean.r1', taskId: 'lifting-zone', questionId: 'q1', workerLang: 'ta', pattern: 'demo', noise: 'clean',
  source: 'synthetic_tts', answerGloss: '', gold: { s1: 'contradicted', s2: 'missed' }, hasAudio: true,
}

function report(over: Partial<EvalReport['items'][number]> = {}): EvalReport {
  const base = evalReport()
  return {
    ...base,
    generatedAt: '2026-10-16T09:30:00Z',
    models: { flash: 'gemini-x', judgeB: 'gemini-y' },
    items: [{
      id: ITEM.id, taskId: ITEM.taskId, workerLang: 'ta', pattern: 'demo', noise: 'clean', gold: { ...ITEM.gold },
      pred: { s1: 'contradicted', s2: 'unclear' }, unsafe: false, flags: { s1: [], s2: ['low_confidence'] }, translation: "I'll stand under the load.",
      ...over,
    }],
  }
}

describe('storedResult', () => {
  it('shows the run\'s verdicts, scored against the item\'s labels, with when and on which models', () => {
    const stored = storedResult(report(), ITEM)

    assert.deepEqual(stored?.view.verdicts, { s1: 'contradicted', s2: 'unclear' })
    assert.deepEqual(stored?.view.agreement, { s1: true, s2: false })
    assert.deepEqual([stored?.view.unsafe, stored?.view.flags, stored?.view.translation], [false, ['low_confidence'], "I'll stand under the load."])
    assert.deepEqual([stored?.generatedAt, stored?.models], ['2026-10-16T09:30:00Z', { flash: 'gemini-x', judgeB: 'gemini-y' }])
    assert.equal(stored?.view.original, undefined, 'the report has no worker-language transcript yet')
  })

  it('keeps an unsafe result unsafe', () => {
    assert.equal(storedResult(report({ pred: { s1: 'covered', s2: 'missed' }, unsafe: true }), ITEM)?.view.unsafe, true)
  })

  it('shows the worker-language transcript once the report carries it', () => {
    assert.equal(storedResult(report({ original: 'லோடுக்கு அடியில நின்னு' }), ITEM)?.view.original, 'லோடுக்கு அடியில நின்னு')
  })

  it('shows each step\'s quote, its translation and the reason from the report\'s ratings, as the live result does (v0.5.1)', () => {
    const stored = storedResult(
      report({
        original: 'லோடுக்கு அடியில நின்னு',
        ratings: [
          { stepId: 's1', verdict: 'contradicted', quote: 'லோடுக்கு அடியில நின்னு', quoteTranslation: "I'll stand under the load", reason: 'Stands under the load.' },
          { stepId: 's2', verdict: 'unclear', reason: 'Not mentioned clearly.', flags: ['passes_disagreed'] },
        ],
      }),
      ITEM,
    )

    assert.deepEqual(stored?.view.evidence, {
      s1: { quote: 'லோடுக்கு அடியில நின்னு', quoteTranslation: "I'll stand under the load", reason: 'Stands under the load.' },
      s2: { reason: 'Not mentioned clearly.' },
    })
    assert.deepEqual(stored?.view.flags, ['low_confidence', 'passes_disagreed'])
  })

  it('has no evidence for a report without ratings, so no step shows an empty quote', () => {
    assert.deepEqual(storedResult(report(), ITEM)?.view.evidence, {})
  })

  it('shows nothing it cannot stand behind, so the page runs the live check as before', () => {
    assert.equal(storedResult(undefined, ITEM), null, 'no report')
    assert.equal(storedResult({ ...report(), items: [] }, ITEM), null, 'no entry for the item')
    assert.equal(storedResult(report({ pred: {} }), ITEM), null, 'no prediction')
    assert.equal(storedResult(report({ gold: { s1: 'contradicted', s2: 'covered' } }), ITEM), null, 'labels changed since the run')
    assert.equal(storedResult(report({ gold: { s1: 'contradicted' } }), ITEM), null, 'a step added since the run')
    assert.equal(storedResult(report(), { ...ITEM, hasAudio: false }), null, 'the clip is not current')
  })
})

describe('liveView', () => {
  it('reads a live try the same way the stored result is read', () => {
    const live: EvalTryResult = {
      item: ITEM,
      round: {
        transcripts: [{ questionId: 'q1', original: 'ஓ', detectedLang: 'ta', translation: 'Oh', flags: [] }],
        passA: [{ stepId: 's1', verdict: 'contradicted', reason: '', flags: [] }],
        passB: [{ stepId: 's1', verdict: 'unclear', reason: '', flags: [] }],
        ratings: [{ stepId: 's1', verdict: 'unclear', reason: '', flags: ['passes_disagreed'] }, { stepId: 's2', verdict: 'missed', reason: '', flags: ['passes_disagreed'] }],
      },
      agreement: { s1: false, s2: true },
      unsafe: false,
    }
    const view = liveView(live)

    assert.deepEqual(view.verdicts, { s1: 'unclear', s2: 'missed' })
    assert.deepEqual(view.flags, ['passes_disagreed'])
    assert.deepEqual([view.original, view.translation], ['ஓ', 'Oh'])
    assert.deepEqual(view.passes, { a: { s1: 'contradicted' }, b: { s1: 'unclear' } })
    assert.deepEqual(view.evidence, { s1: {}, s2: {} })
  })
})

describe('mock mode', () => {
  it('stores the worker-language transcript and each step\'s quote and reason, as the real report now does', () => {
    const lead = pickSamples(evalItems())[0]!
    const stored = storedResult(evalReport(), lead)

    assert.ok(stored?.view.original)
    assert.ok(Object.values(stored?.view.evidence ?? {}).some((e) => e.quote && e.quoteTranslation && e.reason))
  })

  it('has a stored result for every sample the page picks, so the mock Sample page shows it at once', () => {
    const samples = pickSamples(evalItems())
    assert.ok(samples.length > 0)
    for (const item of samples) assert.ok(storedResult(evalReport(), item), item.id)
  })
})
