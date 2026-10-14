import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { CaptionMerger } from '../../src/live/captions.ts'

describe('CaptionMerger', () => {
  it('replaces the line with each cumulative partial instead of appending (no repeated words)', () => {
    const c = new CaptionMerger()
    assert.equal(c.push('model', 'Switch'), 'Switch')
    assert.equal(c.push('model', 'Switch off'), 'Switch off')
    assert.equal(c.push('model', 'Switch off the breaker'), 'Switch off the breaker')
  })

  it('lets the final frame carry the whole utterance, then a new utterance replaces it', () => {
    const c = new CaptionMerger()
    c.push('model', 'Switch off the')
    assert.equal(c.push('model', 'Switch off the breaker.'), 'Switch off the breaker.')
    assert.equal(c.push('model', 'Lock'), 'Lock')
  })

  it('shows a revised transcription rather than gluing it onto the old one', () => {
    const c = new CaptionMerger()
    c.push('model', 'Cheque the')
    assert.equal(c.push('model', 'Check the lock'), 'Check the lock')
  })

  it('keeps the line when a frame has no text', () => {
    const c = new CaptionMerger()
    c.push('worker', 'ஆஃப்')
    assert.equal(c.push('worker', ''), 'ஆஃப்')
  })

  it('keeps the two roles apart', () => {
    const c = new CaptionMerger()
    c.push('model', 'question')
    assert.equal(c.push('worker', 'answer'), 'answer')
    assert.equal(c.push('model', 'question text'), 'question text')
  })

  it('reset blanks the line for a new cue', () => {
    const c = new CaptionMerger()
    c.push('model', 'old line')
    c.reset('model')
    assert.equal(c.push('model', ''), '')
    assert.equal(c.push('model', 'new'), 'new')
  })
})
