import { DEVICE_HEADER, isDeviceKey } from '../api/deviceKey.ts'
import type { CreateBriefingBody, CreateRoundBody, DecisionBody, Health, LiveTicket, Step } from '../api/types.ts'
import { speechWav, seedOf, spokenSeconds } from './audio.ts'
import { publicCatalog, rawTask } from './catalog.ts'
import { evalItems, evalReport, evalTry, MOCK_EVAL_ITEMS } from './eval.ts'
import * as store from './store.ts'
import { HttpError, delay, errorResponse, jsonResponse, partOfScript } from './util.ts'

// The whole REST contract (docs/API.md endpoints 1-19) served in the browser. Endpoint 20, the
// Live WebSocket, is the mock socket in ./liveSocket.ts. Everything here is canned: no model runs.

const MOCK = 'mock'
const HEALTH: Health = {
  ok: true,
  models: { flash: 'gemini-3.8-flash', live: 'gemini-3.8-live', tts: 'gemini-3.8-flash-tts' },
  backends: { flash: MOCK, live: MOCK, tts: MOCK },
  store: 'browser sessionStorage',
  judgePasses: 2,
  promptVersion: 'mock-2026-10-13',
}

/** What dictation returns, by language: the lead demo sentence. */
const SPOKEN: Record<string, string> = {
  zh: '打开配电箱前，先断开断路器、上锁挂牌，并验电确认无电。',
}

/**
 * The Gemini-backed endpoints (3, 8, 10, 11, 12, 13, 19). QA flag `sib.mock.dailyLimit` = "1" makes them answer
 * 429 `daily_limit`, as the backend does once its day's call budget is used up (docs/API.md, "Daily cap").
 */
const GEMINI_BACKED = /^\/(transcribe|tts)$|\/steps\/extract$|\/rounds$|\/live-session$|\/check$|^\/eval\/items\/[^/]+\/try$/

const json = async <T>(init: RequestInit): Promise<T> => {
  if (typeof init.body !== 'string') throw new HttpError(400, 'bad_request', 'Expected a JSON body.')
  return JSON.parse(init.body) as T
}

const form = (init: RequestInit): FormData => {
  if (!(init.body instanceof FormData)) throw new HttpError(400, 'bad_request', 'Expected multipart form data.')
  return init.body
}

const audioResponse = (blob: Blob): Response => new Response(blob, { status: 200, headers: { 'Content-Type': 'audio/wav' } })

/** What the backend's device-key middleware does (docs/API.md, "Callers and ownership"): every route but health needs a well-formed key. */
function requireDeviceKey(path: string, init: RequestInit): void {
  if (path === '/health') return
  if (!isDeviceKey(new Headers(init.headers).get(DEVICE_HEADER))) {
    throw new HttpError(401, 'device_required', 'Send your device key in the X-SIB-Device header (22 to 64 characters of A-Z, a-z, 0-9, _ and -).')
  }
}

async function route(path: string, method: string, query: URLSearchParams, init: RequestInit): Promise<Response> {
  let m: RegExpExecArray | null

  requireDeviceKey(path, init)

  if (method === 'POST' && GEMINI_BACKED.test(path) && localStorage.getItem('sib.mock.dailyLimit') === '1') {
    throw new HttpError(429, 'daily_limit', "Today's Gemini call budget is used up. Try again after midnight UTC.")
  }

  if (method === 'GET' && path === '/health') return jsonResponse(HEALTH)
  if (method === 'GET' && path === '/catalog') return jsonResponse(publicCatalog)

  if (method === 'POST' && path === '/transcribe') {
    const lang = String(form(init).get('lang') ?? 'en')
    await delay(900)
    const sample = rawTask('panel-isolation')?.sampleInstruction[lang as 'en' | 'ta'] ?? SPOKEN[lang] ?? rawTask('panel-isolation')?.sampleInstruction.en ?? ''
    return jsonResponse({ text: sample })
  }

  if (path === '/briefings') {
    if (method === 'POST') {
      await delay(250)
      return jsonResponse(store.createBriefing(await json<CreateBriefingBody>(init)), 201)
    }
    if (method === 'GET') return jsonResponse({ items: store.listSummaries(Number(query.get('limit') ?? 20)) })
  }

  if ((m = /^\/briefings\/([^/]+)$/.exec(path))) {
    const id = m[1] ?? ''
    if (method === 'GET') return jsonResponse(store.getBriefing(id))
    if (method === 'PATCH') return jsonResponse(store.patchInstruction(id, (await json<{ instruction: string }>(init)).instruction))
  }

  if ((m = /^\/briefings\/([^/]+)\/steps\/extract$/.exec(path)) && method === 'POST') {
    await delay(1000)
    return jsonResponse(store.extractSteps(m[1] ?? ''))
  }
  if ((m = /^\/briefings\/([^/]+)\/steps$/.exec(path)) && method === 'PUT') {
    return jsonResponse(store.confirmSteps(m[1] ?? '', (await json<{ steps: Step[] }>(init)).steps))
  }
  if ((m = /^\/briefings\/([^/]+)\/rounds$/.exec(path)) && method === 'POST') {
    await delay(1400)
    return jsonResponse(store.createRound(m[1] ?? '', await json<CreateRoundBody>(init)), 201)
  }
  if ((m = /^\/briefings\/([^/]+)\/rounds\/(\d+)\/live-session$/.exec(path)) && method === 'POST') {
    const id = m[1] ?? ''
    const n = Number(m[2])
    store.issueTicket(id, n)
    await delay(150)
    // `mock-fail` makes the mock relay reject the ticket, to exercise the Turn-mode fallback.
    const fail = localStorage.getItem('sib.mock.liveFail') === '1'
    const ticket: LiveTicket = {
      wsUrl: `/api/live/${id}/${n}`,
      ticket: fail ? 'mock-fail' : `mock-${crypto.randomUUID()}`,
      model: `gemini-3.8-live (${MOCK})`,
      expiresAt: new Date(Date.now() + 120_000).toISOString(),
    }
    return jsonResponse(ticket)
  }
  if ((m = /^\/briefings\/([^/]+)\/rounds\/(\d+)\/check$/.exec(path)) && method === 'POST') {
    const data = form(init)
    const clips: Record<string, Blob> = {}
    let mode: 'live' | 'turn' = 'live'
    for (const [name, value] of data.entries()) {
      if (typeof value !== 'string') clips[name] = value
      else if (name === 'meta') mode = (JSON.parse(value) as { mode?: 'live' | 'turn' }).mode === 'turn' ? 'turn' : 'live'
    }
    // `sib.mock.notRecorded` = the relay never wrote round.live: a live check answers 409, as the real backend does after its 5 s wait.
    if (mode === 'live' && localStorage.getItem('sib.mock.notRecorded') === '1') {
      await delay(600)
      throw new HttpError(409, 'live_not_recorded', 'The live session was not recorded. Use turn mode.')
    }
    await delay(1700)
    return jsonResponse(store.checkRound(m[1] ?? '', Number(m[2]), clips, mode))
  }
  if ((m = /^\/briefings\/([^/]+)\/decision$/.exec(path)) && method === 'POST') {
    await delay(250)
    return jsonResponse(store.decide(m[1] ?? '', await json<DecisionBody>(init)))
  }

  if (method === 'POST' && path === '/tts') {
    // The body is {briefingId, n, text}; as on the backend, only a line of the round's own script is spoken.
    const { briefingId, n, text } = await json<{ briefingId: string; n: number; text: string }>(init)
    if (!text || text.length > 600) throw new HttpError(422, 'invalid_text', 'Text must be 1 to 600 characters.')
    const round = store.getBriefing(briefingId).rounds.find((r) => r.n === n)
    if (!round) throw new HttpError(404, 'round_not_found', 'Round not found.')
    if (!partOfScript(round.script, text)) throw new HttpError(422, 'tts_text_not_in_script', "text is not part of this round's script.")
    await delay(450)
    return audioResponse(speechWav(spokenSeconds(text), 24_000, seedOf(text)))
  }

  if (method === 'GET' && path === '/export/briefings.csv') return new Response(new Blob([store.csv()], { type: 'text/csv' }), { headers: { 'Content-Type': 'text/csv' } })

  if (method === 'GET' && path === '/eval/latest') return jsonResponse(evalReport())
  if (method === 'GET' && path === '/eval/items') return jsonResponse({ items: evalItems() })
  if ((m = /^\/eval\/items\/([^/]+)\/audio$/.exec(path)) && method === 'GET') {
    const found = MOCK_EVAL_ITEMS.find((i) => i.id === decodeURIComponent(m?.[1] ?? ''))
    if (!found) throw new HttpError(404, 'not_found', 'No such evaluation item.')
    return audioResponse(speechWav(Math.min(6, 1.5 + found.original.length / 16), 16_000, seedOf(found.id)))
  }
  if ((m = /^\/eval\/items\/([^/]+)\/try$/.exec(path)) && method === 'POST') {
    await delay(1500)
    return jsonResponse(evalTry(decodeURIComponent(m[1] ?? '')))
  }

  throw new HttpError(404, 'not_found', `No mock route for ${method} ${path}.`)
}

/** Drop-in for fetch() on /api/** in mock mode. */
export async function mockFetch(url: string, init: RequestInit = {}): Promise<Response> {
  try {
    const parsed = new URL(url, window.location.origin)
    const path = parsed.pathname.replace(/^\/api/, '')
    return await route(path, (init.method ?? 'GET').toUpperCase(), parsed.searchParams, init)
  } catch (e) {
    return errorResponse(e)
  }
}
