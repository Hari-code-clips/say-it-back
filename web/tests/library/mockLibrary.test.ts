import assert from 'node:assert/strict'
import { beforeEach, describe, it } from 'node:test'
import { publicCatalog, rawTask } from '../../src/mock/catalog.ts'
import * as library from '../../src/mock/library.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'

// dev:mock serves the SOP library as the backend does (sop_library.py): catalog seeds read-only, drafts until signed off, and a
// briefing from a signed-off version proposes its steps with no extraction. The mock has no accounts, so a seed takes no new
// version (security fixes A, H3; tests/library/securityFixesA.test.ts): the drafts here are this browser's own SOPs.

const refused = (code: string) => (e: unknown) => e instanceof HttpError && e.code === code
const LIFT = { siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Never go under the load.' } as const
const STEP = { id: 's1', text: 'Stay behind the barricade', hazard: '', essential: [], source: 'sop' as const, speakable: true }

/** This browser's own lifting SOP, v1 with STEP signed off. */
function signedOwn(text = 'Our lifting SOP.'): string {
  const { id } = library.createSop('sg', { title: 'Lifting, our site', text, taskId: 'lifting-zone' })
  library.setSteps('sg', id, 1, [STEP])
  library.approve('sg', id, 1)
  return id
}

beforeEach(() => library.resetLibrary())

describe('mock library: seeds', () => {
  it('lists each catalog task of the site as its signed-off, read-only seed under the catalog SOP number', () => {
    const items = library.listSops('sg')
    const tasks = publicCatalog.tasks.filter((t) => t.demoSite === 'sg')
    assert.deepEqual(items.map((e) => e.taskId), tasks.map((t) => t.id))
    const lift = items.find((e) => e.id === 'SOP-LF-03')
    assert.equal(lift?.versions[0]?.number, 2)
    assert.equal(lift?.versions[0]?.status, 'approved')
    assert.deepEqual(lift?.versions[0]?.steps.map((s) => s.text), rawTask('lifting-zone')?.referenceSteps.map((s) => s.text))
    assert.ok(lift?.versions[0]?.steps.every((s) => s.speakable === true), 'a catalog step without speakable is speakable, as the backend reads it')
  })

  it('never changes a seed version', () => {
    assert.throws(() => library.setSteps('sg', 'SOP-LF-03', 2, [STEP]), refused('read_only'))
    assert.throws(() => library.approve('sg', 'SOP-LF-03', 2), refused('read_only'))
    assert.throws(() => library.listSops('mars'), refused('unknown_site'))
  })
})

describe('mock library: drafts', () => {
  it('a new version is a draft with the signed-off steps, one at a time, then never changes once signed off', () => {
    const own = signedOwn()
    const draft = library.addVersion('sg', own, { text: 'Revised.' }).versions.at(-1)
    assert.deepEqual([draft?.number, draft?.status, draft?.steps.map((s) => s.text)], [2, 'draft', [STEP.text]])
    assert.throws(() => library.addVersion('sg', own, { text: 'Again.' }), refused('draft_exists'))
    library.setSteps('sg', own, 2, [{ ...STEP, text: 'Keep the red barricade closed' }])
    assert.equal(library.approve('sg', own, 2).versions.at(-1)?.status, 'approved')
    assert.throws(() => library.setSteps('sg', own, 2, [STEP]), refused('invalid_state'))
  })

  it('a new SOP needs steps before its sign-off', () => {
    const made = library.createSop('sg', { title: 'Night lifting', text: '1. Lights on.' })
    assert.throws(() => library.approve('sg', made.id, 1), refused('steps_required'))
  })
})

describe('mock library: a briefing from a signed-off version', () => {
  it('proposes the version steps (no extraction) and binds sopRef in the created event', () => {
    const own = signedOwn('Revised lifting SOP.')
    const b = store.createBriefing({ ...LIFT, sopRef: { sopId: own, version: 1 } })
    assert.deepEqual([b.sop.id, b.sop.version, b.sop.text], [own, 'v1', 'Revised lifting SOP.'])
    assert.deepEqual(b.events?.[0]?.data.sopRef, { sopId: own, version: 1 })
    const proposed = store.extractSteps(b.id)
    assert.deepEqual(proposed.steps.map((s) => s.text), [STEP.text])
    assert.deepEqual(proposed.conflicts, [])
  })

  it('refuses a draft, another task and another language, as the backend does', () => {
    const draft = library.createSop('sg', { title: 'Lifting draft', text: 'Draft.', taskId: 'lifting-zone' })
    assert.throws(() => store.createBriefing({ ...LIFT, sopRef: { sopId: draft.id, version: 1 } }), refused('sop_not_approved'))
    assert.throws(() => store.createBriefing({ ...LIFT, sopRef: { sopId: 'SOP-EL-04', version: 4 } }), refused('sop_task_mismatch'))
    assert.throws(() => store.createBriefing({ ...LIFT, supervisorLang: 'zh', sopRef: { sopId: 'SOP-LF-03', version: 2 } }), refused('sop_language_mismatch'))
  })

  it('routes the library paths as the backend names them', () => {
    const list = library.libraryRoute('GET', '/sites/sg/sops', {}) as { items: { id: string }[] }
    assert.ok(list.items.some((e) => e.id === 'SOP-LF-03'))
    const { id } = library.libraryRoute('POST', '/sites/sg/sops', { title: 'Night lifting', text: '1. Lights on.' }) as { id: string }
    library.libraryRoute('PUT', `/sites/sg/sops/${id}/versions/1/steps`, { steps: [STEP] })
    library.libraryRoute('POST', `/sites/sg/sops/${id}/versions/1/approve`, {})
    const made = library.libraryRoute('POST', `/sites/sg/sops/${id}/versions`, { text: 'Revised.' }) as { versions: { number: number }[] }
    assert.equal(made.versions.at(-1)?.number, 2)
    assert.equal(library.libraryRoute('GET', '/briefings', {}), undefined)
  })
})
