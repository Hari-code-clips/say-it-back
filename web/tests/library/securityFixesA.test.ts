import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, beforeEach, describe, it } from 'node:test'
import type { LibraryEntry, Step } from '../../src/api/types.ts'
import { mockFetch } from '../../src/mock/handlers.ts'
import * as library from '../../src/mock/library.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'
import { takesNewVersion } from '../../src/screens/library/libraryModel.ts'

// Security fixes A (docs/API.md Deviations 2026-10-16; build-notes/36-security-fixes-a.md), as dev:mock and the library screen
// play them. H2: a library briefing confirms only its signed-off steps, unchanged and in order, else 409 sop_steps_locked.
// H3: the mock has no accounts, so a catalogue SOP takes no new version (403 forbidden), and the screen hides "New version" on it.

const LIFT = { siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Never go under the load.' } as const
const LOCKED = (sop: string) =>
  `These steps are signed off in ${sop}. To change them, a safety officer signs off a new version, or start the briefing with Gemini's steps.`
const refused = (status: number, code: string, message?: string) => (e: unknown) =>
  e instanceof HttpError && e.status === status && e.code === code && (message === undefined || e.message === message)

beforeEach(() => library.resetLibrary())

/** A briefing from the lifting seed (SOP-LF-03 v2) and the steps endpoint 8 proposed for it. */
function fromSeed(): { id: string; steps: Step[] } {
  const b = store.createBriefing({ ...LIFT, sopRef: { sopId: 'SOP-LF-03', version: 2 } })
  return { id: b.id, steps: store.extractSteps(b.id).steps }
}

const edit = (i: number, change: Partial<Step>) => (steps: Step[]): Step[] => steps.map((s, j) => (j === i ? { ...s, ...change } : s))
const ADDED: Step = { id: 's5', text: 'Wave at the crane driver.', hazard: '', essential: [], source: 'instruction', speakable: true }
const CHANGED: Record<string, (steps: Step[]) => Step[]> = {
  text: edit(0, { text: 'Wear a hat.' }),
  hazard: edit(1, { hazard: 'Nothing much' }),
  'an essential added': (st) => edit(0, { essential: [...st[0].essential, 'wave'] })(st),
  'the essentials emptied': edit(1, { essential: [] }),
  source: (st) => edit(0, { source: st[0].source === 'sop' ? 'instruction' : 'sop' })(st),
  sopQuote: edit(2, { sopQuote: 'Stand where you like.' }),
  speakable: edit(3, { speakable: false }),
  id: edit(0, { id: 's9' }),
  order: (st) => [st[1], st[0], ...st.slice(2)],
  'one removed': (st) => st.slice(0, -1),
  'one added': (st) => [...st, ADDED],
  'all replaced (the review’s probe)': () => [{ ...ADDED, id: 's1', text: 'Wear a hat.' }],
}

describe('mock: a library briefing confirms only its signed-off steps (H2)', () => {
  it('takes the proposed steps as they came', () => {
    const { id, steps } = fromSeed()
    assert.equal(store.confirmSteps(id, structuredClone(steps)).status, 'steps_confirmed')
  })

  for (const [name, change] of Object.entries(CHANGED)) {
    it(`refuses a changed list (${name}) with 409 sop_steps_locked, and changes nothing`, () => {
      const { id, steps } = fromSeed()
      const before = structuredClone(store.getBriefing(id))
      assert.throws(() => store.confirmSteps(id, change(structuredClone(steps))), refused(409, 'sop_steps_locked', LOCKED('SOP-LF-03 v2')))
      assert.deepEqual(store.getBriefing(id), before)
    })
  }

  it('compares after the backend’s cleaning: spaces and an empty essential are the same steps', () => {
    const { id, steps } = fromSeed()
    const spaced = edit(0, { text: `  ${steps[0].text} `, essential: [...steps[0].essential, ' '] })(steps)
    assert.equal(store.confirmSteps(id, spaced).status, 'steps_confirmed')
  })

  it('locks this browser’s own signed-off version too, under its own id', () => {
    const own = library.createSop('sg', { title: 'Lifting, our site', text: 'Our SOP.', taskId: 'lifting-zone' })
    library.setSteps('sg', own.id, 1, [{ ...ADDED, id: 's1' }])
    library.approve('sg', own.id, 1)
    const b = store.createBriefing({ ...LIFT, sopRef: { sopId: own.id, version: 1 } })
    const steps = store.extractSteps(b.id).steps
    assert.throws(() => store.confirmSteps(b.id, CHANGED.text(steps)), refused(409, 'sop_steps_locked', LOCKED(`${own.id} v1`)))
  })

  it('leaves a briefing without sopRef as it was: edited steps are confirmed', () => {
    const b = store.createBriefing(LIFT)
    const steps = store.extractSteps(b.id).steps
    assert.equal(store.confirmSteps(b.id, CHANGED.text(steps)).steps[0]?.text, 'Wear a hat.')
  })
})

describe('mock: no new version of a catalogue SOP without accounts (H3)', () => {
  it('refuses a new version of every seed with 403 forbidden, and keeps nothing', () => {
    for (const site of ['sg', 'chennai']) {
      for (const seed of library.listSops(site)) {
        assert.throws(() => library.addVersion(site, seed.id, { text: 'Stand under the load.' }), refused(403, 'forbidden', library.CATALOGUE_READ_ONLY))
      }
      assert.ok(library.listSops(site).every((e) => e.seeded && e.versions.length === 1))
    }
    assert.equal(library.CATALOGUE_READ_ONLY, 'Catalogue SOPs are read-only in this demo. Add your own SOP instead.')
  })
})

describe('mock routes answer both refusals as the backend does', () => {
  // The routes read window.location and localStorage, which node does not have (as tests/privacy/mockConsent.test.ts does).
  const globals = ['window', 'localStorage'] as const
  const saved = globals.map((name) => Object.getOwnPropertyDescriptor(globalThis, name))
  before(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { origin: 'http://localhost' } } })
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => null, setItem: () => undefined } })
  })
  after(() => {
    globals.forEach((name, i) => {
      const descriptor = saved[i]
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else Reflect.deleteProperty(globalThis, name)
    })
  })
  const call = (path: string, method: string, body: unknown) =>
    mockFetch(`/api${path}`, { method, body: JSON.stringify(body), headers: { 'X-SIB-Device': 'mock-test-device-key-0001', 'Content-Type': 'application/json' } })

  it('PUT …/steps with a changed list is 409 sop_steps_locked', async () => {
    const { id, steps } = fromSeed()
    const reply = await call(`/briefings/${id}/steps`, 'PUT', { steps: CHANGED.order(steps) })
    assert.equal(reply.status, 409)
    assert.deepEqual(await reply.json(), { error: { code: 'sop_steps_locked', message: LOCKED('SOP-LF-03 v2') } })
  })

  it('POST …/versions on a catalogue SOP is 403 forbidden', async () => {
    const reply = await call('/sites/sg/sops/SOP-LF-03/versions', 'POST', { text: 'Stand under the load.' })
    assert.equal(reply.status, 403)
    assert.deepEqual(await reply.json(), { error: { code: 'forbidden', message: library.CATALOGUE_READ_ONLY } })
  })
})

describe('the library offers "New version" (H3)', () => {
  const seed = library.seeds('sg')[0] as LibraryEntry
  const own: LibraryEntry = { ...seed, id: 'sop_own', seeded: false, versions: seed.versions.map((v) => ({ ...v, readOnly: false })) }
  const drafting = (entry: LibraryEntry): LibraryEntry => ({ ...entry, versions: [...entry.versions, { ...entry.versions[0], number: 9, status: 'draft' }] })

  it('never on a catalogue SOP without accounts; with accounts the roles decide on the server', () => {
    assert.equal(takesNewVersion(seed, false), false)
    assert.equal(takesNewVersion(seed, true), true)
    assert.equal(takesNewVersion(own, false), true)
  })

  it('never while a draft is open', () => {
    assert.equal(takesNewVersion(drafting(own), false), false)
    assert.equal(takesNewVersion(drafting(seed), true), false)
  })

  it('the screen asks the rule with the build’s own mode', () => {
    const screen = readFileSync(new URL('../../src/screens/library/LibraryScreen.tsx', import.meta.url), 'utf8')
    assert.match(screen, /const ACCOUNTS = import\.meta\.env\.VITE_AUTH_MODE === 'firebase'/)
    assert.match(screen, /\{takesNewVersion\(entry, ACCOUNTS\) && !adding && \(/)
  })
})
