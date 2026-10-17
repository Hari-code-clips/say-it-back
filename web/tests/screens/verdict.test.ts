import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { FLAG_LABEL, VERDICT, quoteLine, ratingVerdict, transcriptNote, verdictOf } from '../../src/screens/result/verdict.ts'

// Product rule 1: never show a step as said back unless the check said so. The result screen's "At a glance" list and
// each step's card read their verdicts through these helpers.

const ratings = [
  { stepId: 's1', verdict: 'covered' as const },
  { stepId: 's2', verdict: 'contradicted' as const },
]

describe('a step with no rating', () => {
  it('reads as Ask again (unclear), never Got it, in the round and on its card', () => {
    assert.equal(verdictOf(ratings, 's3'), 'unclear')
    assert.equal(ratingVerdict(undefined), 'unclear')
    assert.equal(en[VERDICT[verdictOf(ratings, 's3')].label], 'Ask again')
  })

  it('does not change what a rated step shows', () => {
    assert.equal(verdictOf(ratings, 's1'), 'covered')
    assert.equal(verdictOf(ratings, 's2'), 'contradicted')
    assert.equal(verdictOf([], 's1'), 'unclear')
  })
})

describe('quoteLine: the worker\'s words on an At a glance row', () => {
  it('prefers the translation into the supervisor\'s language', () => {
    assert.deepEqual(quoteLine({ quote: 'லோடுக்கு அடியில நின்னு', quoteTranslation: "I'll stand under the load" }), { text: "I'll stand under the load", translated: true })
  })

  it('falls back to the quote as said when there is no translation', () => {
    assert.deepEqual(quoteLine({ quote: 'லோடுக்கு அடியில நின்னு' }), { text: 'லோடுக்கு அடியில நின்னு', translated: false })
    assert.deepEqual(quoteLine({ quote: 'x y z', quoteTranslation: '  ' }), { text: 'x y z', translated: false })
  })

  it('shows nothing when there is no quote, even with a translation', () => {
    assert.equal(quoteLine(undefined), null)
    assert.equal(quoteLine({}), null)
    assert.equal(quoteLine({ quote: ' ', quoteTranslation: 'something' }), null)
  })
})

describe('model_refused (v0.5.1): a clip the model\'s safety filter blocked', () => {
  it('has a chip label in every UI language', () => {
    const key = FLAG_LABEL.model_refused!
    for (const table of [en, ta, zh]) assert.match(table[key], /\S/)
  })

  it('is explained in a sentence where the transcript would be, instead of "No speech"', () => {
    assert.equal(transcriptNote(['model_refused']), 'result.modelRefused')
    assert.equal(en['result.modelRefused'], 'The checker could not process this answer. Ask again or check in person.')
    for (const table of [ta, zh]) assert.notEqual(table['result.modelRefused'], en['result.modelRefused'])
  })

  it('leaves other flags to their chips', () => {
    assert.equal(transcriptNote(['no_speech', 'low_audio']), null)
    assert.equal(transcriptNote([]), null)
  })
})
