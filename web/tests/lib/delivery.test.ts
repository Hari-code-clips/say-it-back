import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { DeliveryCheck, Round } from '../../src/api/types.ts'
import { affectedSteps, causedEarlier, countNegations, deliveryCauses, failedDeliveries, negationChange, parseSegment } from '../../src/lib/delivery.ts'
import { en as EN } from '../../src/i18n/en.ts'
import { issueSentences } from '../../src/screens/result/deliveryText.ts'

const check = (segment: string, over: Partial<DeliveryCheck> = {}): DeliveryCheck => ({ segment, similarity: 0.97, scriptOk: true, ok: true, issues: [], ...over })

const round: Pick<Round, 'stepIds' | 'script' | 'delivery' | 'live'> = {
  stepIds: ['s1', 's2', 's3', 's4'],
  script: {
    instruction: 'Never go under the load.\nStay outside the barrier.\nFollow only the signalman.\nUse the tag line.',
    instructionBackTranslation: '',
    questions: [
      { id: 'q1', text: 'Where will you be while the load is moving?', backTranslation: '', stepIds: ['s1', 's2'] },
      { id: 'q2', text: 'Who will you take directions from?', backTranslation: '', stepIds: ['s3'] },
      { id: 'q3', text: 'If the load swings, what will you do?', backTranslation: '', stepIds: ['s4'] },
    ],
    stepMap: { s1: [0], s2: [1], s3: [2], s4: [3] },
    closing: 'Thank you.',
  },
  delivery: [],
}

describe('the delivery check is the server\'s', () => {
  it('a segment is a problem only when the server says it is not ok, whatever its similarity', () => {
    const delivery = [
      check('instruction', { similarity: 0.55 }), // low similarity, but the server says ok: the browser has no threshold of its own
      check('q1', { similarity: 0.95, ok: false, issues: ['negation_changed'] }), // a dropped "not" barely moves the similarity
      check('closing', { similarity: 0.99 }),
    ]
    assert.deepEqual(failedDeliveries(delivery).map((d) => d.segment), ['q1'])
  })

  it('a round with no delivery check (Turn mode) has nothing to report', () => {
    assert.deepEqual(failedDeliveries([]), [])
    assert.deepEqual(failedDeliveries(undefined), [])
  })
})

describe('which steps a failed segment turns into "Ask again" (guard rule 8)', () => {
  const ids = round.script.questions.map((q) => q.id)
  it('the instruction affects every step in scope, a question the steps it checks, the closing none', () => {
    assert.deepEqual(affectedSteps(parseSegment('instruction', ids), round), ['s1', 's2', 's3', 's4'])
    assert.deepEqual(affectedSteps(parseSegment('q1', ids), round), ['s1', 's2'])
    assert.deepEqual(affectedSteps(parseSegment('closing', ids), round), [])
  })

  it('the reply after question N affects the steps of question N and of every later question (v0.4 review)', () => {
    assert.deepEqual(affectedSteps(parseSegment('q2.reply', ids), round), ['s3', 's4'])
    assert.deepEqual(affectedSteps(parseSegment('q1.reply', ids), round), ['s1', 's2', 's3', 's4'])
    assert.deepEqual(affectedSteps(parseSegment('q3.reply', ids), round), ['s4'])
  })

  it('says when the cause came before the step\'s own question', () => {
    const ref = parseSegment('q2.reply', ids)
    assert.equal(causedEarlier(ref, 's4', round), true)
    assert.equal(causedEarlier(ref, 's3', round), false)
    assert.equal(causedEarlier(parseSegment('instruction', ids), 's1', round), false)
  })

  it('names the cause of a step\'s delivery_mismatch', () => {
    const r = { ...round, delivery: [check('q2.reply', { ok: false, issues: ['reply_too_long'], said: 'Thank you. Right answer, follow only the signalman.' })] }
    assert.deepEqual(deliveryCauses('s3', r).map((c) => c.check.segment), ['q2.reply'])
    assert.deepEqual(deliveryCauses('s4', r).map((c) => c.check.segment), ['q2.reply']) // a later question
    assert.deepEqual(deliveryCauses('s1', r), [])
  })

  it('reads a segment as its part of the round, numbered as the supervisor sees it', () => {
    assert.deepEqual(parseSegment('q2.reply', ids), { kind: 'reply', qid: 'q2', n: 2 })
    assert.deepEqual(parseSegment('q3', ids), { kind: 'question', qid: 'q3', n: 3 })
    assert.deepEqual(parseSegment('weird', ids), { kind: 'other', raw: 'weird' })
  })
})

describe('the plain words the supervisor reads', () => {
  const t = (key: keyof typeof EN, vars?: Record<string, string | number>) => EN[key].replace(/\{(\w+)\}/g, (_, k: string) => String(vars?.[k] ?? `{${k}}`))
  const en = { name: 'English', native: 'English', bcp47: 'en', script: 'Latn', unicodeRanges: [] as [string, string][], match: 'word' as const, negationMarkers: ['not', 'never', "don't"] }

  it('says the voice left out a "not" when what it said has fewer negations than the script', () => {
    const r = { ...round, script: { ...round.script, instruction: 'Do not go under the load.' } }
    const lines = issueSentences(t, check('instruction', { ok: false, issues: ['negation_changed'], said: 'Do go under the load.' }), r, en)
    assert.deepEqual(lines, ['The voice left out a "not" in the instruction.'])
  })

  it('says a number changed, and that the voice said more than a thank-you after question 2', () => {
    assert.deepEqual(issueSentences(t, check('q1', { ok: false, issues: ['number_changed'] }), round, en), ['A number changed in question 1.'])
    assert.deepEqual(issueSentences(t, check('q2.reply', { ok: false, issues: ['reply_too_long'], said: 'Thanks, that is right.' }), round, en), [
      'The voice said more than a thank-you after question 2.',
    ])
  })

  it('says the voice used words from the script after a question, not just a thank-you (reply_not_neutral)', () => {
    assert.deepEqual(issueSentences(t, check('q2.reply', { ok: false, issues: ['reply_not_neutral'], said: 'Thanks. Only the signalman.' }), round, en), [
      'After question 2 the voice said words from the script, not just a thank-you.',
    ])
  })

  it('never shows a raw issue code, even one this build does not know', () => {
    const lines = issueSentences(t, check('q3', { ok: false, issues: ['brand_new_issue' as never] }), round, en)
    assert.deepEqual(lines, ['The voice said question 3 in other words than your script.'])
  })
})

describe('a delivery check stored before v0.4 (not ok, no issue codes)', () => {
  it('says only that it did not match, never a reason it does not know', () => {
    const t = (key: keyof typeof EN, vars?: Record<string, string | number>) => EN[key].replace(/\{(\w+)\}/g, (_, k: string) => String(vars?.[k] ?? `{${k}}`))
    assert.deepEqual(issueSentences(t, check('instruction', { ok: false, issues: [] }), round), ['What the voice said for the instruction did not match your script.'])
  })
})

describe('counting negations', () => {
  it('normalises as the backend does: punctuation is removed, so "don\'t" is "dont"', () => {
    assert.equal(countNegations("Don't go under it.", ['dont'], 'word'), 1)
  })

  it('English: whole words only, so "nothing" is not a "not"', () => {
    assert.equal(countNegations('Do not touch. Nothing else.', ['not'], 'word'), 1)
  })

  it('Tamil: markers inside words (negation is often a suffix)', () => {
    const markers = ['இல்லை', 'ாதீர்கள்', 'ாமல்']
    assert.equal(countNegations('லோடுக்கு அடியில் போகாதீர்கள்', markers), 1)
    assert.equal(negationChange('லோடுக்கு அடியில் போங்கள்', 'லோடுக்கு அடியில் போகாதீர்கள்', markers), 'dropped')
    assert.equal(negationChange('a', 'a', markers), 'changed') // same count: say only that it changed
    assert.equal(negationChange(undefined, 'x', markers), 'changed')
  })
})
