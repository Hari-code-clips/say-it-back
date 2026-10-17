import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, describe, it } from 'node:test'
import { createApi } from '../../src/api/createApi.ts'
import { createTransport } from '../../src/api/transport.ts'
import { speechWav } from '../../src/mock/audio.ts'
import { mockFetch } from '../../src/mock/handlers.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'
import { needsConsent } from '../../src/screens/brief/consentFlow.ts'

// Security fixes B, M3 and M4 (build-notes/36-security-fixes-b.md): with SIB_REQUIRE_CONSENT, a round with no recorded choice is
// checked only as all stored samples (every question listed in meta.sampleAnswers), and gets a Live ticket only when the request
// declares {samplesOnly: true}, which the web sends exactly when it shows no consent screen. dev:mock plays both rules, and the
// judges' sample-only path still runs end to end in Turn and in Live mode.

const refused = (code: string) => (e: unknown) => e instanceof HttpError && e.code === code
const answer = () => speechWav(3, 16_000, 7)
const DEVICE = { 'X-SIB-Device': 'mock-test-device-key-0001' }

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

describe('mock: a check of a round with no recorded choice', () => {
  it('runs only as all stored samples, whatever clips are sent', () => {
    const { id, qids } = approvedRound()
    assert.ok(qids.length > 1)
    assert.doesNotThrow(() => store.requireConsent(id, 1, qids, qids))
    const first = qids.slice(0, 1)
    assert.throws(() => store.requireConsent(id, 1, first, first), refused('consent_required')) // the gap: one clip, labelled
    assert.throws(() => store.requireConsent(id, 1, first, qids), refused('consent_required')) // listed, but no clip
  })

  it('after "I agree" any mix runs, and a decline stays a decline', () => {
    const agreed = approvedRound()
    store.recordConsent(agreed.id, 1, true)
    assert.doesNotThrow(() => store.requireConsent(agreed.id, 1, agreed.qids.slice(0, 1), []))
    const declined = approvedRound()
    store.recordConsent(declined.id, 1, false)
    assert.throws(() => store.requireConsent(declined.id, 1, declined.qids, declined.qids), refused('consent_declined'))
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

  const ticket = (id: string, body?: unknown) =>
    mockFetch(`/api/briefings/${id}/rounds/1/live-session`, {
      method: 'POST',
      headers: { ...DEVICE, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
  const check = (id: string, qids: readonly string[], mode: 'live' | 'turn') => {
    const form = new FormData()
    for (const q of qids) form.append(q, answer(), `${q}.wav`)
    form.append('meta', JSON.stringify({ mode, sampleAnswers: qids }))
    return mockFetch(`/api/briefings/${id}/rounds/1/check`, { method: 'POST', headers: DEVICE, body: form })
  }
  const code = async (res: Response) => [res.status, ((await res.json()) as { error?: { code: string } }).error?.code]

  describe('the Live ticket (endpoint 11)', () => {
    it('no choice and no declaration: 409 consent_required', async () => {
      const { id } = approvedRound()
      assert.deepEqual(await code(await ticket(id)), [409, 'consent_required'])
      assert.deepEqual(await code(await ticket(id, { samplesOnly: false })), [409, 'consent_required'])
    })

    it('a samples-only session gets its ticket; after "I agree" none needs declaring', async () => {
      const samples = approvedRound()
      assert.equal((await ticket(samples.id, { samplesOnly: true })).status, 200)
      const agreed = approvedRound()
      store.recordConsent(agreed.id, 1, true)
      assert.equal((await ticket(agreed.id)).status, 200)
    })

    it('a declined round gets none, even samples-only; the round’s own state comes first', async () => {
      const { id } = approvedRound()
      store.recordConsent(id, 1, false)
      assert.deepEqual(await code(await ticket(id, { samplesOnly: true })), [409, 'consent_declined'])
      const b = store.createBriefing({ siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Stay clear of the load.' })
      store.confirmSteps(b.id, store.extractSteps(b.id).steps)
      store.createRound(b.id, {})
      assert.deepEqual(await code(await ticket(b.id)), [409, 'script_not_approved'])
    })

    it('only a JSON boolean declares it, and a refusal uses none of the round’s two tickets', async () => {
      const { id } = approvedRound()
      for (const body of [{ samplesOnly: 'true' }, { samplesOnly: true, x: 1 }, [], true]) {
        assert.deepEqual(await code(await ticket(id, body)), [422, 'validation_error'], JSON.stringify(body))
      }
      for (let i = 0; i < 3; i++) assert.equal((await ticket(id)).status, 409)
      assert.deepEqual([(await ticket(id, { samplesOnly: true })).status, (await ticket(id, { samplesOnly: true })).status], [200, 200])
    })
  })

  describe('the judges’ path, consent on', () => {
    it('Turn mode: every question a stored sample is judged with no consent screen', async () => {
      const { id, qids } = approvedRound()
      const judged = await check(id, qids, 'turn')
      assert.equal(judged.status, 200)
      assert.deepEqual(((await judged.json()) as { sampleAnswers?: string[] }).sampleAnswers, qids)
    })

    it('Live mode: a samples-only ticket, then the check', async () => {
      const { id, qids } = approvedRound()
      assert.equal((await ticket(id, { samplesOnly: true })).status, 200)
      const judged = await check(id, qids, 'live')
      assert.equal(judged.status, 200)
      assert.equal(((await judged.json()) as { mode?: string }).mode, 'live')
    })
  })
})

describe('the web client asks for a samples-only ticket exactly when no consent screen is shown', () => {
  it('liveSession(id, n, true) posts {samplesOnly: true}; without it, no body, as before', async () => {
    const sent: RequestInit[] = []
    const api = createApi(
      createTransport({
        base: '/api',
        deviceKey: () => 'device-key-'.padEnd(32, 'k'),
        send: async (_url, init) => {
          sent.push(init)
          return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
        },
      }),
    )
    await api.liveSession('b_abcdefghijkl', 1, true)
    await api.liveSession('b_abcdefghijkl', 1)
    assert.deepEqual(JSON.parse(sent[0]?.body as string), { samplesOnly: true })
    assert.equal(new Headers(sent[0]?.headers).get('Content-Type'), 'application/json')
    assert.equal(sent[1]?.body, undefined)
  })

  it('useBriefingRun derives it from needsConsent, the rule the consent screen uses (BriefScreen.tsx, consentStep)', () => {
    const source = readFileSync(new URL('../../src/screens/brief/useBriefingRun.ts', import.meta.url), 'utf8')
    assert.match(source, /const samplesOnly = !needsConsent\(script\.questions\.map\(\(q\) => q\.id\), autoQids\.current\)/)
    assert.match(source, /api\.liveSession\(briefing\.id, round\.n, samplesOnly\)/)
    assert.equal(needsConsent(['q1', 'q2'], ['q2', 'q1']), false)
    assert.equal(needsConsent(['q1', 'q2'], ['q1']), true)
  })
})
