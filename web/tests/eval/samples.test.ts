import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { DemoAnswer, EvalItem } from '../../src/api/types.ts'
import { en } from '../../src/i18n/en.ts'
import { humanize, noiseLabel, patternLabel, sourceLabel, stepText } from '../../src/screens/eval/labels.ts'
import { pickSamples } from '../../src/screens/eval/pickSamples.ts'
import { samplesFor, sampleStillWanted } from '../../src/screens/brief/sample.ts'

const t = (key: keyof typeof en, vars?: Record<string, string | number>) => en[key].replace(/\{(\w+)\}/g, (_, k: string) => String(vars?.[k] ?? ''))

const item = (id: string, over: Partial<EvalItem>): EvalItem => ({
  id, taskId: 'panel-isolation', questionId: 'q1', workerLang: 'ta', pattern: 'complete', noise: 'clean', source: 'synthetic_tts',
  answerGloss: '', gold: { s1: 'covered' }, hasAudio: true, ...over,
})

describe('pickSamples: the Sample page\'s curated clips', () => {
  const items = [
    item('panel.demo.r1', { pattern: 'demo', gold: { s1: 'covered', s2: 'missed' } }),
    item('lift.demo.r2', { taskId: 'lifting-zone', pattern: 'demo', gold: { s1: 'covered', s2: 'covered' } }),
    item('lift.demo.r1', { taskId: 'lifting-zone', pattern: 'demo', gold: { s1: 'contradicted', s2: 'missed' } }),
    item('hot.contradicted', { pattern: 'contradicted', gold: { s3: 'contradicted' } }),
    item('lift.negation.noaudio', { taskId: 'lifting-zone', pattern: 'negation', gold: { s1: 'contradicted' }, hasAudio: false }),
    item('lift.fluent', { taskId: 'lifting-zone', pattern: 'fluent_wrong', gold: { s3: 'contradicted' } }),
    item('zh.silence', { workerLang: 'zh', pattern: 'silence', gold: { s1: 'unclear' } }),
  ]

  it('picks the lead demo with a mixed result, a hard wrong answer and one to abstain on, each with its audio', () => {
    assert.deepEqual(pickSamples(items).map((i) => i.id), ['lift.demo.r1', 'lift.fluent', 'zh.silence'])
  })

  it('falls back to any scripted demo answer when the lead has none', () => {
    assert.deepEqual(pickSamples(items.filter((i) => i.taskId !== 'lifting-zone')).map((i) => i.id), ['panel.demo.r1', 'hot.contradicted', 'zh.silence'])
  })

  it('never offers a clip that is not on the server, and offers nothing on a fresh deployment', () => {
    assert.ok(!pickSamples(items).some((i) => i.hasAudio !== true))
    assert.deepEqual(pickSamples(items.map((i) => ({ ...i, hasAudio: false }))), [])
    assert.deepEqual(pickSamples([]), [])
  })
})

describe('labels: the evaluator never reads a raw enum', () => {
  it('names patterns, noise and sources in words', () => {
    assert.equal(sourceLabel(t, 'synthetic_tts'), 'Synthetic voice')
    assert.equal(patternLabel(t, 'demo'), 'Scripted demo answer')
    assert.equal(noiseLabel(t, 'clean'), 'Clean audio')
    assert.equal(noiseLabel(t, 'snr10'), 'Noisy (10 dB)')
  })

  it('a code with no label yet is still shown as words', () => {
    assert.equal(patternLabel(t, 'brand_new_pattern'), 'Brand new pattern')
    assert.equal(humanize('snr_3'), 'Snr 3')
  })

  it('shows a step\'s text from endpoint 17, and its number, never its id, when the text is missing', () => {
    const it2 = item('x', { gold: { s1: 'covered', s2: 'missed' }, steps: { s1: 'Never stand or walk under the load' } })
    assert.equal(stepText(t, it2, 's1'), 'Never stand or walk under the load')
    assert.equal(stepText(t, it2, 's2'), 'Step 2')
  })
})

describe('samplesFor: which stored answers a round offers', () => {
  const list: DemoAnswer[] = [
    { taskId: 'lifting-zone', workerLang: 'ta', round: 1, gloss: 'r1' },
    { taskId: 'lifting-zone', workerLang: 'ta', round: 2, gloss: 'r2' },
    { taskId: 'lifting-zone', workerLang: 'ta', round: 2, gloss: 'r2 q2', questionId: 'q2', stepIds: ['s3'] },
  ]
  const glosses = (n: number, lang = 'ta') => samplesFor(list, 'lifting-zone', lang, n).map((d) => d.gloss)
  it('round 1 uses the first, round 2 and every later round the second, in the server\'s order; none for another language', () => {
    assert.deepEqual(glosses(1), ['r1'])
    assert.deepEqual(glosses(2), ['r2', 'r2 q2'])
    assert.deepEqual(glosses(3), ['r2', 'r2 q2'])
    assert.deepEqual(glosses(1, 'bn'), [])
    assert.deepEqual(samplesFor(undefined, 'lifting-zone', 'ta', 1), [])
  })
})

describe('sampleStillWanted: a clip that arrives late is dropped (v0.4 review)', () => {
  it('only while the tapped question\'s window is still the open one', () => {
    assert.equal(sampleStillWanted('q1', { kind: 'listening', qid: 'q1' }), true)
    assert.equal(sampleStillWanted('q1', { kind: 'listening', qid: 'q2' }), false)
    assert.equal(sampleStillWanted('q1', { kind: 'speaking', qid: 'q1' }), false)
    assert.equal(sampleStillWanted(null, { kind: 'listening', qid: 'q1' }), false)
  })
})
