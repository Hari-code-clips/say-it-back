import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { LibraryEntry, LibraryVersion } from '../../src/api/types.ts'
import { numbered, offeredVersions, openDraft, refOf, sameRef, stillOffered } from '../../src/screens/library/libraryModel.ts'

// The SOP library's rules on the client (docs/API.md Deviations 2026-10-16): only signed-off versions in the supervisor's language
// are offered for a task, newest first; a stale choice falls back to the SOP.

const version = (number: number, patch: Partial<LibraryVersion> = {}): LibraryVersion => ({
  number, text: `v${number}`, lang: 'en', createdAt: '2026-10-16T00:00:00Z', createdBy: 'device', changeNote: '', status: 'approved',
  steps: [], readOnly: false, ...patch,
})
const entry = (id: string, taskId: string | undefined, versions: LibraryVersion[]): LibraryEntry => ({
  id, siteId: 'sg', title: id, ...(taskId ? { taskId } : {}), seeded: false, versions,
})

const LIFT = entry('SOP-LF-03', 'lifting-zone', [version(2, { readOnly: true }), version(3), version(4, { status: 'draft' })])
const OTHER = entry('SOP-EL-04', 'panel-isolation', [version(4)])
const ZH = entry('sop_zh', 'lifting-zone', [version(1, { lang: 'zh' })])

describe('offeredVersions', () => {
  it('offers the signed-off versions of the task, newest first, and never a draft', () => {
    const offers = offeredVersions([LIFT, OTHER, ZH], 'lifting-zone', 'en')
    assert.deepEqual(offers.map(refOf), [{ sopId: 'SOP-LF-03', version: 3 }, { sopId: 'SOP-LF-03', version: 2 }])
  })

  it('offers only versions whose steps are in the supervisor language', () => {
    assert.deepEqual(offeredVersions([LIFT, ZH], 'lifting-zone', 'zh').map(refOf), [{ sopId: 'sop_zh', version: 1 }])
    assert.deepEqual(offeredVersions([LIFT], 'lifting-zone', 'ta'), [])
  })

  it('offers nothing for a task the library has no SOP for, or for a task-less SOP', () => {
    assert.deepEqual(offeredVersions([LIFT, entry('sop_x', undefined, [version(1)])], 'custom', 'en'), [])
  })
})

describe('choices', () => {
  it('keeps a choice only while it is on offer', () => {
    const offers = offeredVersions([LIFT], 'lifting-zone', 'en')
    assert.deepEqual(stillOffered(offers, { sopId: 'SOP-LF-03', version: 3 }), { sopId: 'SOP-LF-03', version: 3 })
    assert.equal(stillOffered(offers, { sopId: 'SOP-LF-03', version: 4 }), null) // a draft
    assert.equal(stillOffered([], { sopId: 'SOP-LF-03', version: 3 }), null)
    assert.equal(stillOffered(offers, null), null)
  })

  it('compares references by SOP and number', () => {
    assert.ok(sameRef({ sopId: 'a', version: 1 }, { sopId: 'a', version: 1 }))
    assert.ok(!sameRef({ sopId: 'a', version: 1 }, { sopId: 'a', version: 2 }))
    assert.ok(!sameRef(null, null))
  })

  it('finds the one open draft', () => {
    assert.equal(openDraft(LIFT)?.number, 4)
    assert.equal(openDraft(OTHER), undefined)
  })
})

describe('the draft steps editor', () => {
  it('numbers the steps it saves in order and drops empty rows', () => {
    const step = (id: string, text: string) => ({ id, text, hazard: ' ', essential: [], source: 'sop' as const, speakable: true })
    assert.deepEqual(
      numbered([step('', ' Stay behind the barricade '), step('s9', ''), step('x', 'Follow the signaller')]).map((s) => [s.id, s.text, s.hazard]),
      [['s1', 'Stay behind the barricade', ''], ['s2', 'Follow the signaller', '']],
    )
  })
})
