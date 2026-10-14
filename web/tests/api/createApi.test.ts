import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { createApi, type Api } from '../../src/api/createApi.ts'
import { createTransport } from '../../src/api/transport.ts'
import type { Step } from '../../src/api/types.ts'

const KEY = 'device-key-'.padEnd(32, 'k')
const BASE = 'https://say-it-back-api-x.a.run.app/api'

interface Sent {
  url: string
  init: RequestInit
}

function setup() {
  const sent: Sent[] = []
  const api = createApi(
    createTransport({
      base: BASE,
      deviceKey: () => KEY,
      send: async (url, init) => {
        sent.push({ url, init })
        return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
      },
    }),
  )
  return { api, sent }
}

const wav = new Blob(['RIFF....WAVE'], { type: 'audio/wav' })
const step: Step = { id: 's1', text: 'Switch it off', hazard: 'Shock', essential: ['breaker off'], source: 'instruction', speakable: true }

/** Every endpoint function, called once. Typed as a record over the API's keys, so a new endpoint is a compile error until it is listed here. */
const CALLS: Record<keyof Api, (api: Api) => Promise<unknown>> = {
  health: (a) => a.health(),
  catalog: (a) => a.catalog(),
  transcribe: (a) => a.transcribe(wav, 'en'),
  createBriefing: (a) => a.createBriefing({ siteId: 'sg', taskId: 'panel-isolation', supervisorLang: 'en', workerLang: 'ta', instruction: 'Switch it off.' }),
  listBriefings: (a) => a.listBriefings(),
  getBriefing: (a) => a.getBriefing('b_abcdefghijkl'),
  patchInstruction: (a) => a.patchInstruction('b_abcdefghijkl', 'Switch it off.'),
  extractSteps: (a) => a.extractSteps('b_abcdefghijkl'),
  confirmSteps: (a) => a.confirmSteps('b_abcdefghijkl', [step]),
  createRound: (a) => a.createRound('b_abcdefghijkl'),
  liveSession: (a) => a.liveSession('b_abcdefghijkl', 1),
  tts: (a) => a.tts('b_abcdefghijkl', 1, 'Switch off the breaker.'),
  check: (a) => a.check('b_abcdefghijkl', 1, { q1: wav }, 'turn'),
  decide: (a) => a.decide('b_abcdefghijkl', { value: 'no_go' }),
  exportCsv: (a) => a.exportCsv(),
  evalLatest: (a) => a.evalLatest(),
  evalItems: (a) => a.evalItems(),
  evalAudio: (a) => a.evalAudio('panel-isolation.q1.ta.demo.clean'),
  evalTry: (a) => a.evalTry('panel-isolation.q1.ta.demo.clean'),
}

describe('every endpoint of the API client', () => {
  for (const [name, call] of Object.entries(CALLS)) {
    it(`${name} sends one request to the API base with the device key in a header and not in the URL`, async () => {
      const { api, sent } = setup()

      await call(api)

      assert.equal(sent.length, 1)
      assert.ok(sent[0]!.url.startsWith(`${BASE}/`), sent[0]!.url)
      assert.equal(new Headers(sent[0]!.init.headers).get('X-SIB-Device'), KEY)
      assert.ok(!sent[0]!.url.includes(KEY))
    })
  }

  it('is listed in full above', () => {
    const { api } = setup()

    assert.deepEqual(Object.keys(CALLS).sort(), Object.keys(api).sort())
  })
})

describe('tts', () => {
  it('posts {briefingId, n, text} to /tts and nothing else: the voice is the round’s worker language, not the caller’s to choose', async () => {
    const { api, sent } = setup()

    await api.tts('b_abcdefghijkl', 2, 'Switch off the breaker.')

    assert.equal(sent[0]!.url, `${BASE}/tts`)
    assert.equal(sent[0]!.init.method, 'POST')
    assert.equal(new Headers(sent[0]!.init.headers).get('Content-Type'), 'application/json')
    assert.deepEqual(JSON.parse(sent[0]!.init.body as string), { briefingId: 'b_abcdefghijkl', n: 2, text: 'Switch off the breaker.' })
  })

  it('asks for a blob: the answer is audio', async () => {
    const { api } = setup()

    assert.ok((await api.tts('b_abcdefghijkl', 1, 'Hello.')) instanceof Blob)
  })
})

describe('the CSV export', () => {
  it('is fetched, as a GET of /export/briefings.csv, so that it carries the key a plain link could not', async () => {
    const { api, sent } = setup()

    const csv = await api.exportCsv()

    assert.ok(csv instanceof Blob)
    assert.equal(sent[0]!.url, `${BASE}/export/briefings.csv`)
    assert.equal(sent[0]!.init.method, 'GET')
  })
})

describe('the check upload', () => {
  it('is multipart: one WAV per question under the question id, and the mode in `meta`', async () => {
    const { api, sent } = setup()

    await api.check('b_abcdefghijkl', 2, { q1: wav, q2: wav }, 'live')

    const body = sent[0]!.init.body
    assert.ok(body instanceof FormData)
    assert.deepEqual([...body.keys()].sort(), ['meta', 'q1', 'q2'])
    assert.deepEqual(JSON.parse(body.get('meta') as string), { mode: 'live' })
    assert.equal(sent[0]!.url, `${BASE}/briefings/b_abcdefghijkl/rounds/2/check`)
  })
})
