import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { clipKey, dropClipsIfDecided, getClips, saveClips } from '../../src/audio/clips.ts'

// The worker's answer clips live in memory for the result screen only. Once the briefing is decided they are dropped,
// also when the decision screen learns it from a 409 (a lost response, or a decision made on another device).

const clip = () => ({ q1: new Blob(['RIFF....WAVE'], { type: 'audio/wav' }) })

describe('dropClipsIfDecided', () => {
  it('keeps the clips while the briefing is not decided', () => {
    saveClips(clipKey('b_keep', 1), clip())
    dropClipsIfDecided({ id: 'b_keep', status: 'judged' })

    assert.ok(getClips(clipKey('b_keep', 1)))
  })

  it('drops every round of a decided briefing, and only that briefing', () => {
    saveClips(clipKey('b_done', 1), clip())
    saveClips(clipKey('b_done', 2), clip())
    saveClips(clipKey('b_other', 1), clip())
    dropClipsIfDecided({ id: 'b_done', status: 'decided' })

    assert.equal(getClips(clipKey('b_done', 1)), undefined)
    assert.equal(getClips(clipKey('b_done', 2)), undefined)
    assert.ok(getClips(clipKey('b_other', 1)))
  })
})
