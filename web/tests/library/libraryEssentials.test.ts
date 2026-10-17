import assert from 'node:assert/strict'
import { beforeEach, describe, it } from 'node:test'
import type { Step } from '../../src/api/types.ts'
import * as library from '../../src/mock/library.ts'
import * as store from '../../src/mock/store.ts'

// 17 Oct (build-notes/37-review-remainder.md; note 36-a, open issue 3), as the backend's tests/test_library_essentials.py: a library
// step signed off with no essentials gets its own text as its one essential, so a briefing from it is never judged against
// "(none given)". A draft keeps what was saved; the text is written at sign-off.

const LIFT = { siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Never go under the load.' } as const
const step = (id: string, text: string, essential: string[] = []): Step => ({ id, text, hazard: '', essential, source: 'sop', speakable: true })
const BARE = step('s1', '  Keep the red barricade closed  ')
const BLANKS = step('s2', 'Tag lines only', ['  ', ''])
const KEPT = step('s3', 'Follow the signalman', ['only the signalman'])

/** This browser's own lifting SOP, its v1 draft holding `steps`. */
function drafted(steps: Step[]): string {
  const { id } = library.createSop('sg', { title: 'Lifting, our site', text: 'Our lifting SOP.', taskId: 'lifting-zone' })
  library.setSteps('sg', id, 1, steps)
  return id
}

const v1 = (id: string) => library.listSops('sg').find((e) => e.id === id)?.versions.find((v) => v.number === 1)

beforeEach(() => library.resetLibrary())

describe('mock library: essentials at sign-off', () => {
  it('a draft keeps the essentials it was saved with', () => {
    const id = drafted([BARE, BLANKS, KEPT])

    assert.deepEqual(v1(id)?.steps.map((s) => s.essential), [[], ['  ', ''], ['only the signalman']])
  })

  it('sign-off gives a step with no essentials its own text (trimmed); blank essentials count as none; a set one is kept', () => {
    const id = drafted([BARE, BLANKS, KEPT])

    library.approve('sg', id, 1)

    assert.deepEqual(v1(id)?.steps.map((s) => s.essential), [['Keep the red barricade closed'], ['Tag lines only'], ['only the signalman']])
    assert.equal(v1(id)?.status, 'approved')
  })

  it('the essential is the text as it was signed off, after a late edit of the draft', () => {
    const id = drafted([BARE])
    library.setSteps('sg', id, 1, [{ ...BARE, text: 'Keep the red barricade closed and locked' }])

    library.approve('sg', id, 1)

    assert.deepEqual(v1(id)?.steps[0]?.essential, ['Keep the red barricade closed and locked'])
  })

  it('a briefing from the version proposes the steps with their essentials, and confirming them unchanged is accepted', () => {
    const id = drafted([BARE, KEPT])
    library.approve('sg', id, 1)
    const b = store.createBriefing({ ...LIFT, sopRef: { sopId: id, version: 1 } })

    const proposed = store.extractSteps(b.id).steps
    const confirmed = store.confirmSteps(b.id, proposed)

    assert.deepEqual(proposed.map((s) => s.essential), [['Keep the red barricade closed'], ['only the signalman']])
    assert.equal(confirmed.status, 'steps_confirmed')
  })
})
