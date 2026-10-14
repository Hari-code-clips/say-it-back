import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { nextFit, START, type Fit } from '../../src/screens/brief/captionFit.ts'

const LAST = 2 // three type sizes: large, medium, the 22 px floor

describe('nextFit', () => {
  it('keeps the large size, and the very same object, while the text fits', () => {
    assert.equal(nextFit(START, true, false, LAST), START)
  })

  it('steps down one size per measurement while the text overflows, then marks it clipped at the floor', () => {
    let fit: Fit = START
    fit = nextFit(fit, true, true, LAST)
    assert.deepEqual(fit, { step: 1, clipped: false })
    fit = nextFit(fit, true, true, LAST)
    assert.deepEqual(fit, { step: 2, clipped: false })
    fit = nextFit(fit, true, true, LAST)
    assert.deepEqual(fit, { step: 2, clipped: true })
  })

  it('never goes past the smallest size, however long the text gets', () => {
    let fit: Fit = { step: LAST, clipped: true }
    for (let i = 0; i < 5; i++) fit = nextFit(fit, true, true, LAST)
    assert.deepEqual(fit, { step: LAST, clipped: true })
  })

  it('settles at the first size where the whole text fits', () => {
    const fit = nextFit({ step: 1, clipped: false }, true, false, LAST)
    assert.deepEqual(fit, { step: 1, clipped: false })
  })

  it('does not step back up when a revised transcription gets shorter, so a long read-out never flickers between sizes', () => {
    const fit = nextFit({ step: 2, clipped: true }, true, false, LAST)
    assert.deepEqual(fit, { step: 2, clipped: false })
  })

  it('a caption with a single size (the worker line) is clipped at once instead of stepping', () => {
    assert.deepEqual(nextFit(START, true, true, 0), { step: 0, clipped: true })
  })

  it('an empty caption (a new cue) starts again from the large size', () => {
    assert.equal(nextFit({ step: 2, clipped: true }, false, true, LAST), START)
    assert.equal(nextFit({ step: 1, clipped: false }, false, false, LAST), START)
  })

  it('an empty caption already at the start is left alone (same object, so no re-render)', () => {
    assert.equal(nextFit(START, false, false, LAST), START)
  })
})
