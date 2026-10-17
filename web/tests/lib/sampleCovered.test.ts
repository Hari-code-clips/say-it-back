import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Briefing, Round, Step, Verdict } from '../../src/api/types.ts'
import { decisionOpenSteps, deriveSampleCovered, quoteFromSample, sampleCoveredIds } from '../../src/lib/sampleCovered.ts'
import { canReexplain, openSteps } from '../../src/flow/phases.ts'

const step = (id: string): Step => ({ id, text: id, hazard: '', essential: [], source: 'instruction', speakable: true })

function round(n: number, questions: [string, string[]][], ratings: Record<string, Verdict>, sampleAnswers?: string[]): Round {
  return {
    n, kind: n === 1 ? 'initial' : 'reexplain', stepIds: Object.keys(ratings),
    script: { instruction: '', instructionBackTranslation: '', questions: questions.map(([id, stepIds]) => ({ id, text: '', backTranslation: '', stepIds })), stepMap: {}, closing: '' },
    transcripts: [], passA: [], passB: [], delivery: [], nextAction: 'decide', modelIds: {}, timingsMs: {}, createdAt: '',
    ratings: Object.entries(ratings).map(([stepId, verdict]) => ({ stepId, verdict, reason: '', flags: [] })),
    ...(sampleAnswers ? { sampleAnswers } : {}),
  }
}

function briefing(rounds: Round[], over: Partial<Briefing> = {}): Briefing {
  const latestVerdicts: Record<string, Verdict> = {}
  for (const r of rounds) for (const x of r.ratings) latestVerdicts[x.stepId] = x.verdict
  return {
    id: 'b_x', siteId: 'sg', taskId: 'lifting-zone', sop: { id: 'S', version: 'v1', title: '', text: '' }, supervisorLang: 'en', workerLang: 'ta',
    instruction: '', status: 'judged', steps: ['s1', 's2', 's3', 's4'].map(step), stepsVersion: 1, conflicts: [], rounds, latestVerdicts,
    promptVersion: 'p', createdAt: '', updatedAt: '', ...over,
  }
}

// The lead demo: round 1 opened everything; round 2 asked q4 (s1, s2), answered with the stored sample, and q5 (s3, s4) by voice.
const lead = () =>
  briefing([
    round(1, [['q1', ['s1', 's2']], ['q2', ['s3']], ['q3', ['s4']]], { s1: 'contradicted', s2: 'missed', s3: 'unclear', s4: 'contradicted' }, ['q1']),
    round(2, [['q4', ['s1', 's2']], ['q5', ['s3', 's4']]], { s1: 'covered', s2: 'covered', s3: 'covered', s4: 'covered' }, ['q4']),
  ])

describe('a stored sample answer never counts as the worker\'s (v0.4 review)', () => {
  it('a step covered only by questions answered with the sample is listed; one the worker said is not', () => {
    assert.deepEqual(deriveSampleCovered(lead()), ['s1', 's2'])
  })

  it('a step also asked by a question the worker answered is the worker\'s', () => {
    const b = briefing([round(1, [['q1', ['s1']], ['q2', ['s1']]], { s1: 'covered' }, ['q1'])])
    assert.deepEqual(deriveSampleCovered(b), [])
  })

  it('only the latest round that rated the step counts: a sample cover later re-asked by voice is the worker\'s', () => {
    const b = briefing([
      round(1, [['q1', ['s1']]], { s1: 'covered' }, ['q1']),
      round(2, [['q2', ['s1']]], { s1: 'covered' }),
    ])
    assert.deepEqual(deriveSampleCovered(b), [])
  })

  it('a step that is not covered is open anyway, and is not listed as sample-covered', () => {
    const b = briefing([round(1, [['q1', ['s1', 's2']]], { s1: 'covered', s2: 'missed' }, ['q1'])])
    assert.deepEqual(deriveSampleCovered(b), ['s1'])
  })

  it('the decision treats them as open, in step order; re-explain keeps to the verdicts', () => {
    const b = lead()
    assert.deepEqual(decisionOpenSteps(b).map((s) => s.id), ['s1', 's2'])
    assert.deepEqual(openSteps(b), []) // nothing to re-explain: the scope stays as the verdicts say
    assert.equal(canReexplain(b), false)
  })

  it('the server\'s derived list wins when it sends one', () => {
    const b = lead()
    assert.deepEqual(sampleCoveredIds({ ...b, sampleCoveredStepIds: ['s2'] }), ['s2'])
    assert.deepEqual(decisionOpenSteps({ ...b, sampleCoveredStepIds: [] }).map((s) => s.id), [])
  })
})

// 16 Oct: whose words a quote is. A sample's words are never captioned "The worker said", whatever the verdict.
describe('quoteFromSample: a quote from a stored sample answer is the sample’s, never the worker’s', () => {
  const withTranscripts = (r: Round, t: Record<string, string>): Round => ({
    ...r,
    transcripts: Object.entries(t).map(([questionId, original]) => ({ questionId, original, detectedLang: 'ta', translation: '', flags: [] })),
  })
  const r1 = (samples?: string[]) =>
    withTranscripts(round(1, [['q1', ['s1', 's2']], ['q2', ['s3']], ['q3', ['s4']]], { s1: 'contradicted', s2: 'missed', s3: 'covered', s4: 'contradicted' }, samples), {
      q1: 'லோடுக்கு அடியில நின்னு, கையால பிடிச்சு அதை நேரா வைப்பேன்.',
      q2: 'சிக்னல்மேன் சொல்றதை மட்டும்தான் கேப்பேன்.',
      q3: 'லோடு ஆடுனா, கையால பிடிச்சு ஆடாம நிறுத்துவேன்.',
    })

  it('finds the transcript that holds the quote, and asks whether its question was a sample', () => {
    assert.equal(quoteFromSample(r1(['q1', 'q2', 'q3']), 's4', 'கையால பிடிச்சு ஆடாம நிறுத்துவேன்'), true)
    assert.equal(quoteFromSample(r1(['q1']), 's4', 'கையால பிடிச்சு ஆடாம நிறுத்துவேன்'), false, 'q3 was the worker’s own voice')
    assert.equal(quoteFromSample(r1(['q3']), 's1', 'லோடுக்கு அடியில நின்னு'), false, 'the quote is in q1, which the worker said')
  })

  it('matches phrases joined by "..." (guard rule 2) and ignores spacing', () => {
    assert.equal(quoteFromSample(r1(['q1']), 's1', 'லோடுக்கு அடியில  நின்னு ... நேரா வைப்பேன்'), true)
  })

  it('is false with no quote or no sample, and falls back to "every asking question was a sample" when no transcript holds it', () => {
    assert.equal(quoteFromSample(r1(['q1', 'q2', 'q3']), 's1', undefined), false)
    assert.equal(quoteFromSample(r1(), 's1', 'லோடுக்கு அடியில நின்னு'), false)
    assert.equal(quoteFromSample(r1(['q3']), 's4', 'not in any transcript'), true)
    assert.equal(quoteFromSample(r1(['q1']), 's4', 'not in any transcript'), false)
  })
})

// Review of 16 Oct (MEDIUM): the server accepts a quote that drops punctuation, case or joiners, so the web must too, or a
// sample's words are captioned "The worker said". The reviewer's reproduction: only q1 is a sample; s4 is asked only by q3.
describe('quoteFromSample matches a quote the way the server does', () => {
  const t = (questionId: string, original: string) => ({ questionId, original, detectedLang: 'ta' as const, translation: '', flags: [] })
  const mixed = (): Round => ({
    ...round(1, [['q1', ['s1', 's2']], ['q2', ['s3']], ['q3', ['s4']]], { s1: 'contradicted', s2: 'missed', s3: 'covered', s4: 'contradicted' }, ['q1']),
    transcripts: [t('q1', 'லோடுக்கு அடியில நின்னு, கையால பிடிச்சு அதை நேரா வைப்பேன்.'), t('q2', 'சிக்னல்மேன் மட்டும்'), t('q3', 'தெரியலை')],
  })

  it('finds a quote with its comma dropped in the sample’s transcript (the reviewer’s case)', () => {
    assert.equal(quoteFromSample(mixed(), 's4', 'நின்னு கையால பிடிச்சு'), true)
  })

  it('ignores case, punctuation and format marks, and never matches across an [unclear] mark', () => {
    // s4 is asked only by q3, the worker's own voice, so a quote not found in q1 (the sample) is never the sample's.
    const r: Round = { ...mixed(), transcripts: [t('q1', 'Hold the TAG line, then [unclear] stop it.'), t('q3', 'தெரியலை')] }
    assert.equal(quoteFromSample(r, 's4', 'hold the tag line'), true)
    assert.equal(quoteFromSample(r, 's4', 'hold‍ the tag... stop it'), true)
    assert.equal(quoteFromSample(r, 's4', 'then stop it'), false, 'the quote runs across the mark')
  })
})
