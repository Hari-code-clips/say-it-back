import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { createApi, type Api } from '../../src/api/createApi.ts'
import { GEMINI_TIMEOUT_MS, createTransport, type RequestOptions, type Transport } from '../../src/api/transport.ts'
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
  reportHazard: (a) => a.reportHazard('b_abcdefghijkl', { audio: wav, round: 1 }),
  ackHazard: (a) => a.ackHazard('b_abcdefghijkl', 'h1', { note: 'Fixed the barrier.' }),
  approveRound: (a) => a.approveRound('b_abcdefghijkl', 1),
  demoAnswers: (a) => a.demoAnswers(),
  demoAnswerAudio: (a) => a.demoAnswerAudio('lifting-zone', 'ta', 1),
  verify: (a) => a.verify('b_abcdefghijkl'),
  consent: (a) => a.consent('b_abcdefghijkl', 1, true), // privacy, 16 Oct
  deleteBriefing: (a) => a.deleteBriefing('b_abcdefghijkl'), // privacy, 16 Oct
  // The SOP library (16 Oct)
  listSops: (a) => a.listSops('sg'),
  createSop: (a) => a.createSop('sg', { title: 'Night lifting', text: '1. Lights on.' }),
  createSopVersion: (a) => a.createSopVersion('sg', 'SOP-LF-03', { text: 'Revised.' }),
  setSopSteps: (a) => a.setSopSteps('sg', 'SOP-LF-03', 3, [step]),
  approveSopVersion: (a) => a.approveSopVersion('sg', 'SOP-LF-03', 3),
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

describe('v0.4 endpoints', () => {
  it('the check names the questions answered with a stored sample in meta.sampleAnswers (and leaves it out when there are none)', async () => {
    const { api, sent } = setup()

    await api.check('b_abcdefghijkl', 1, { q1: wav, q2: wav }, 'live', ['q1'])
    await api.check('b_abcdefghijkl', 2, { q4: wav }, 'turn')

    assert.deepEqual(JSON.parse((sent[0]!.init.body as FormData).get('meta') as string), { mode: 'live', sampleAnswers: ['q1'] })
    assert.deepEqual(JSON.parse((sent[1]!.init.body as FormData).get('meta') as string), { mode: 'turn' })
  })

  it('a problem report is multipart: the WAV under `audio` and the round, or the round alone for a tap', async () => {
    const { api, sent } = setup()

    await api.reportHazard('b_abcdefghijkl', { audio: wav, round: 2 })
    await api.reportHazard('b_abcdefghijkl', { round: 2 })

    assert.equal(sent[0]!.url, `${BASE}/briefings/b_abcdefghijkl/hazards`)
    const voice = sent[0]!.init.body as FormData
    assert.deepEqual([...voice.keys()].sort(), ['audio', 'round'])
    assert.equal(voice.get('round'), '2')
    assert.deepEqual([...(sent[1]!.init.body as FormData).keys()], ['round'])
  })

  it('approve, acknowledge, verify and the sample clip go to the contract paths', async () => {
    const { api, sent } = setup()

    await api.approveRound('b_abcdefghijkl', 2)
    await api.ackHazard('b_abcdefghijkl', 'h1', { note: 'Fixed the barrier.' })
    await api.verify('b_abcdefghijkl')
    await api.demoAnswerAudio('lifting-zone', 'ta', 2)
    await api.demoAnswerAudio('lifting-zone', 'ta', 1, 'q3') // 16 Oct: one question's stored answer

    assert.deepEqual(
      sent.map((x) => [x.init.method, x.url.slice(BASE.length)]),
      [
        ['POST', '/briefings/b_abcdefghijkl/rounds/2/approve'],
        ['POST', '/briefings/b_abcdefghijkl/hazards/h1/ack'],
        ['GET', '/briefings/b_abcdefghijkl/verify'],
        ['GET', '/demo-answers/lifting-zone/ta/2/audio'],
        ['GET', '/demo-answers/lifting-zone/ta/1/q3/audio'],
      ],
    )
    assert.deepEqual(JSON.parse(sent[1]!.init.body as string), { note: 'Fixed the barrier.' })
  })
})

describe('how long a call waits', () => {
  /** A transport that records the options of each call instead of sending it. */
  function recording() {
    const opts: { path: string; timeoutMs?: number }[] = []
    const fake: Transport = {
      request: async <T,>(path: string, o: RequestOptions = {}) => {
        opts.push({ path, timeoutMs: o.timeoutMs })
        return {} as T
      },
      requestBlob: async (path: string, o: RequestOptions = {}) => {
        opts.push({ path, timeoutMs: o.timeoutMs })
        return new Blob()
      },
    }
    return { api: createApi(fake), opts }
  }

  it('Gemini-backed calls wait 125 s, past the backend\'s own 120 s answer (v0.4)', () => {
    assert.equal(GEMINI_TIMEOUT_MS, 125_000)
  })

  it('every Gemini-backed call, a voiced problem report included, uses that wait; free calls keep the default', async () => {
    const { api, opts } = recording()
    const gemini: Array<keyof Api> = ['transcribe', 'extractSteps', 'createRound', 'tts', 'check', 'evalTry']
    for (const name of gemini) await CALLS[name](api)
    await api.reportHazard('b_abcdefghijkl', { audio: wav })
    const free: Array<keyof Api> = ['approveRound', 'ackHazard', 'verify', 'demoAnswers', 'getBriefing', 'decide']
    for (const name of free) await CALLS[name](api)
    await api.reportHazard('b_abcdefghijkl', { round: 1 }) // a tap: no Gemini call

    const waits = opts.map((o) => o.timeoutMs)
    assert.deepEqual(waits.slice(0, gemini.length + 1), Array(gemini.length + 1).fill(125_000))
    assert.deepEqual(waits.slice(gemini.length + 1), Array(free.length + 1).fill(undefined))
  })
})
