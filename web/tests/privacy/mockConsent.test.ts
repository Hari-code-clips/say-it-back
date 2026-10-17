import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { speechWav } from '../../src/mock/audio.ts'
import { verifyChain } from '../../src/mock/chain.ts'
import { mockFetch } from '../../src/mock/handlers.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'

// Privacy, 16 Oct: the mock backend plays the consent and deletion contract as the backend does (consent.py, retention.py), so the
// dev:mock app and its screenshots behave like the service: SIB_REQUIRE_CONSENT is on there by default.

const refused = (code: string) => (e: unknown) => e instanceof HttpError && e.code === code
const answer = () => speechWav(3, 16_000, 7)

function approvedRound() {
  const b = store.createBriefing({
    siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta',
    instruction: "Never go under the load, stay outside the barrier until it's landed, and only follow the signalman.",
  })
  store.confirmSteps(b.id, store.extractSteps(b.id).steps)
  const round = store.createRound(b.id, {})
  store.approveRound(b.id, 1)
  return { id: b.id, qids: round.script.questions.map((q) => q.id) }
}

describe('mock consent', () => {
  it('records the choice on the round with a consent event, and the record verifies', () => {
    const { id } = approvedRound()
    const round = store.recordConsent(id, 1, true)
    assert.equal(round.consent?.given, true)
    const b = store.getBriefing(id)
    const last = b.events?.at(-1)
    assert.deepEqual([last?.type, last?.data], ['consent', { n: 1, given: true }])
    assert.equal(verifyChain(b).ok, true)
  })

  it('the same choice again adds no event', () => {
    const { id } = approvedRound()
    store.recordConsent(id, 1, false)
    const count = store.getBriefing(id).events?.length
    store.recordConsent(id, 1, false)
    assert.equal(store.getBriefing(id).events?.length, count)
  })

  it('a person’s voice needs consent first; stored samples only do not', () => {
    const { id, qids } = approvedRound()
    assert.throws(() => store.requireConsent(id, 1, qids, []), refused('consent_required'))
    assert.doesNotThrow(() => store.requireConsent(id, 1, qids, qids))
    assert.throws(() => store.requireConsent(id, 1, qids, qids.slice(1)), refused('consent_required'))
    store.recordConsent(id, 1, true)
    assert.doesNotThrow(() => store.requireConsent(id, 1, qids, []))
  })

  it('a declined round takes no check and no live ticket, until the worker agrees', () => {
    const { id, qids } = approvedRound()
    store.recordConsent(id, 1, false)
    const clips = Object.fromEntries(qids.map((q) => [q, answer()]))
    assert.throws(() => store.requireConsent(id, 1, qids, qids), refused('consent_declined'))
    assert.throws(() => store.checkRound(id, 1, clips, 'turn'), refused('consent_declined'))
    assert.throws(() => store.issueTicket(id, 1), refused('consent_declined'))
    store.recordConsent(id, 1, true)
    assert.equal(store.checkRound(id, 1, clips, 'turn').n, 1)
  })

  it('needs an approved, unjudged round', () => {
    const b = store.createBriefing({ siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Stay clear of the load.' })
    store.confirmSteps(b.id, store.extractSteps(b.id).steps)
    store.createRound(b.id, {})
    assert.throws(() => store.recordConsent(b.id, 1, true), refused('script_not_approved'))
  })
})

describe('mock routes', () => {
  // The routes read window.location and localStorage, which node does not have (as tests/mock/sampleAnswers.test.ts does).
  const globals = ['window', 'localStorage'] as const
  const saved = globals.map((name) => Object.getOwnPropertyDescriptor(globalThis, name))
  before(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { origin: 'http://localhost' } } })
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => null } })
  })
  after(() => {
    globals.forEach((name, i) => {
      const descriptor = saved[i]
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else Reflect.deleteProperty(globalThis, name)
    })
  })
  const call = (path: string, init: RequestInit = {}) =>
    mockFetch(`/api${path}`, { ...init, headers: { 'X-SIB-Device': 'mock-test-device-key-0001', 'Content-Type': 'application/json', ...(init.headers ?? {}) } })

  it('POST …/consent takes only a JSON boolean', async () => {
    const { id } = approvedRound()
    const bad = await call(`/briefings/${id}/rounds/1/consent`, { method: 'POST', body: JSON.stringify({ given: 'true' }) })
    assert.equal(bad.status, 422)
    const ok = await call(`/briefings/${id}/rounds/1/consent`, { method: 'POST', body: JSON.stringify({ given: true }) })
    assert.equal(ok.status, 200)
    assert.equal(((await ok.json()) as { consent?: { given: boolean } }).consent?.given, true)
  })

  it('DELETE /briefings/{id} removes the record at once', async () => {
    const { id } = approvedRound()
    const gone = await call(`/briefings/${id}`, { method: 'DELETE' })
    assert.deepEqual(await gone.json(), { ok: true, id })
    assert.equal((await call(`/briefings/${id}`)).status, 404)
    assert.equal((await call(`/briefings/${id}`, { method: 'DELETE' })).status, 404)
  })
})
