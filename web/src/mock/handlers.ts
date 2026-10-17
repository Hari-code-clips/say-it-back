import { DEVICE_HEADER, isDeviceKey } from '../api/deviceKey.ts'
import type { CreateBriefingBody, CreateRoundBody, DecisionBody, DemoAnswer, Health, Lang, LiveTicket, Step } from '../api/types.ts'
import { encodeWav } from '../audio/wav.ts'
import { speechWav, seedOf, spokenSeconds } from './audio.ts'
import { publicCatalog, rawDemoScripts, rawTask, roundAnswers } from './catalog.ts'
import { evalItems, evalReport, evalTry, MOCK_EVAL_ITEMS } from './eval.ts'
import * as library from './library.ts'
import * as store from './store.ts'
import { HttpError, delay, errorResponse, jsonResponse, partOfScript } from './util.ts'

export { MOCK_BUNDLE_SENTINEL } from './sentinel.ts'

// The whole REST contract (docs/API.md v0.4, endpoints 1-19 and 21-25) served in the browser. Endpoint 20, the
// Live WebSocket, is the mock socket in ./liveSocket.ts. Everything here is canned: no model runs.

const MOCK = 'mock'
const HEALTH: Health = {
  ok: true,
  models: { flash: 'gemini-3.8-flash', judgeB: 'gemini-3.1-flash-lite', live: 'gemini-3.8-live', tts: 'gemini-3.8-flash-tts' },
  backends: { flash: MOCK, live: MOCK, tts: MOCK },
  store: 'browser sessionStorage',
  judgePasses: 2,
  promptVersion: 'mock-2026-10-14',
}

/**
 * Endpoint 24: the catalog's scripted demo answers, one per question of a round since 16 Oct (the round's own answer and its
 * follow-ups), each with a synthetic clip in mock mode. As on the server: `questionId`, the reference question's `stepIds`, and a
 * round's answers in reference question order.
 */
const DEMO_ANSWERS: DemoAnswer[] = rawDemoScripts.flatMap((d) => {
  const questions = rawTask(d.taskId)?.referenceQuestions ?? []
  const order = (qid: string) => questions.findIndex((q) => q.id === qid)
  return d.rounds.slice(0, 2).flatMap((r, i) =>
    [...roundAnswers(r)]
      .sort((a, b) => order(a.questionId) - order(b.questionId))
      .map((a) => ({
        taskId: d.taskId,
        workerLang: d.workerLang,
        round: i + 1,
        gloss: a.answer.en ?? '',
        questionId: a.questionId,
        stepIds: questions.find((q) => q.id === a.questionId)?.stepIds ?? [],
      })),
  )
})

/** The scripted answer a clip says: one question's, or with no question the round's own first answer (the older route). */
const demoAnswerText = (taskId: string, lang: string, round: number, questionId?: string): string | undefined => {
  const r = rawDemoScripts.find((x) => x.taskId === taskId && x.workerLang === lang)?.rounds[round - 1]
  const answer = questionId === undefined ? r : roundAnswers(r).find((a) => a.questionId === questionId)
  return answer?.answer[lang as Lang]
}

/** What dictation returns, by language: the lead demo sentence. */
const SPOKEN: Record<string, string> = {
  zh: '绝不要走到吊物下面，吊物落地前待在围栏外，只听信号员的指挥。',
}

/**
 * The Gemini-backed endpoints (3, 8, 10, 11, 12, 13, 19). QA flag `sib.mock.dailyLimit` = "1" makes them answer
 * 429 `daily_limit`, as the backend does once its day's call budget is used up (docs/API.md, "Daily cap").
 */
const GEMINI_BACKED = /^\/(transcribe|tts)$|\/steps\/extract$|\/rounds$|\/live-session$|\/check$|^\/eval\/items\/[^/]+\/try$/
const LEAD_TASK = 'lifting-zone'

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
    const sample = rawTask(LEAD_TASK)?.sampleInstruction[lang as 'en' | 'ta'] ?? SPOKEN[lang] ?? rawTask(LEAD_TASK)?.sampleInstruction.en ?? ''
    return jsonResponse({ text: sample })
  }

  if (path.startsWith('/sites/')) {
    // The SOP library (Deviations 2026-10-16, mock/library.ts): no Gemini call.
    const found = library.libraryRoute(method, path, method === 'GET' ? {} : await json<Record<string, unknown>>(init))
    if (found !== undefined) return jsonResponse(found)
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
    if (method === 'DELETE') return jsonResponse(store.deleteBriefing(id)) // privacy, 16 Oct
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
  if ((m = /^\/briefings\/([^/]+)\/rounds\/(\d+)\/consent$/.exec(path)) && method === 'POST') {
    // Privacy (16 Oct): the worker's choice; only a JSON boolean is a choice, as on the backend.
    const body = await json<{ given?: unknown }>(init)
    if (typeof body.given !== 'boolean') throw new HttpError(422, 'validation_error', 'Invalid request: given.')
    await delay(150)
    return jsonResponse(store.recordConsent(m[1] ?? '', Number(m[2]), body.given))
  }
  if ((m = /^\/briefings\/([^/]+)\/rounds\/(\d+)\/approve$/.exec(path)) && method === 'POST') {
    const body = typeof init.body === 'string' && init.body ? (JSON.parse(init.body) as { by?: string }) : {}
    await delay(200)
    return jsonResponse(store.approveRound(m[1] ?? '', Number(m[2]), body.by))
  }
  if ((m = /^\/briefings\/([^/]+)\/rounds\/(\d+)\/live-session$/.exec(path)) && method === 'POST') {
    const id = m[1] ?? ''
    const n = Number(m[2])
    // Security fixes B: an optional {samplesOnly: boolean}, a JSON boolean and no other key, as on the backend; then the consent rule.
    const body: unknown = (typeof init.body === 'string' && init.body ? JSON.parse(init.body) : null) ?? {}
    const fields = typeof body === 'object' && !Array.isArray(body) ? Object.entries(body as object) : null
    if (!fields || fields.some(([k, v]) => k !== 'samplesOnly' || typeof v !== 'boolean')) throw new HttpError(422, 'validation_error', 'Invalid request: samplesOnly.')
    store.requireTicketConsent(id, n, fields.some(([, v]) => v === true))
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
    let sampleAnswers: string[] = []
    for (const [name, value] of data.entries()) {
      if (typeof value !== 'string') clips[name] = value
      else if (name === 'meta') {
        const meta = JSON.parse(value) as { mode?: 'live' | 'turn'; sampleAnswers?: unknown }
        mode = meta.mode === 'turn' ? 'turn' : 'live'
        sampleAnswers = Array.isArray(meta.sampleAnswers) ? meta.sampleAnswers.filter((q): q is string => typeof q === 'string') : []
      }
    }
    store.requireApproved(m[1] ?? '', Number(m[2]))
    store.requireConsent(m[1] ?? '', Number(m[2]), Object.keys(clips), sampleAnswers) // privacy, 16 Oct
    // `sib.mock.notRecorded` = the relay never wrote round.live: a live check answers 409, as the real backend does after its 5 s wait.
    if (mode === 'live' && localStorage.getItem('sib.mock.notRecorded') === '1') {
      await delay(600)
      throw new HttpError(409, 'live_not_recorded', 'The live session was not recorded. Use turn mode.')
    }
    await delay(1700)
    return jsonResponse(store.checkRound(m[1] ?? '', Number(m[2]), clips, mode, sampleAnswers))
  }
  if ((m = /^\/briefings\/([^/]+)\/hazards$/.exec(path)) && method === 'POST') {
    // QA flag `sib.mock.hazardFail` = "1": the report does not get through (a dropped connection), so the held state can be seen.
    if (localStorage.getItem('sib.mock.hazardFail') === '1') {
      await delay(400)
      throw new HttpError(503, 'upstream_busy', 'The service is busy. Try again in a moment.')
    }
    const data = form(init)
    const audio = data.get('audio')
    const round = data.get('round')
    const voice = audio instanceof Blob && audio.size > 0
    if (voice && localStorage.getItem('sib.mock.dailyLimit') === '1') throw new HttpError(429, 'daily_limit', "Today's Gemini call budget is used up. Try again after midnight UTC.")
    await delay(voice ? 1200 : 250)
    return jsonResponse(store.reportHazard(m[1] ?? '', { ...(voice ? { audio } : {}), ...(typeof round === 'string' && round ? { round: Number(round) } : {}) }))
  }
  if ((m = /^\/briefings\/([^/]+)\/hazards\/([^/]+)\/ack$/.exec(path)) && method === 'POST') {
    await delay(250)
    return jsonResponse(store.ackHazard(m[1] ?? '', decodeURIComponent(m[2] ?? ''), await json<{ note?: string; by?: string }>(init)))
  }
  if ((m = /^\/briefings\/([^/]+)\/verify$/.exec(path)) && method === 'GET') {
    await delay(200)
    return jsonResponse(store.verify(m[1] ?? ''))
  }
  if (method === 'GET' && path === '/demo-answers') return jsonResponse({ items: localStorage.getItem('sib.mock.freshDeploy') === '1' ? [] : DEMO_ANSWERS })
  if ((m = /^\/demo-answers\/([^/]+)\/([^/]+)\/(\d+)(?:\/([^/]+))?\/audio$/.exec(path)) && method === 'GET') {
    const [taskId, lang, round] = [decodeURIComponent(m[1] ?? ''), decodeURIComponent(m[2] ?? ''), Math.min(2, Number(m[3]))]
    const text = demoAnswerText(taskId, lang, round, m[4] === undefined ? undefined : decodeURIComponent(m[4]))
    if (!text) throw new HttpError(404, 'no_demo_answer', 'No stored sample answer for that task, language, round and question.')
    await delay(150)
    return audioResponse(speechWav(Math.min(9, 1.5 + text.length / 14), 16_000, seedOf(text)))
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
    store.requireApproved(briefingId, n)
    await delay(450)
    return audioResponse(speechWav(spokenSeconds(text), 24_000, seedOf(text)))
  }

  if (method === 'GET' && path === '/export/briefings.csv') return new Response(new Blob([store.csv()], { type: 'text/csv' }), { headers: { 'Content-Type': 'text/csv' } })

  // QA flag `sib.mock.freshDeploy` = "1": no test set and no report on the server, as on a fresh deployment (404 on 16 and 17).
  const fresh = localStorage.getItem('sib.mock.freshDeploy') === '1'
  if (method === 'GET' && path === '/eval/latest') {
    if (fresh) throw new HttpError(404, 'no_report', 'No evaluation report on this server.')
    return jsonResponse(evalReport())
  }
  if (method === 'GET' && path === '/eval/items') {
    if (fresh) throw new HttpError(404, 'not_found', 'No test set on this server.')
    return jsonResponse({ items: evalItems() })
  }
  if ((m = /^\/eval\/items\/([^/]+)\/audio$/.exec(path)) && method === 'GET') {
    const found = MOCK_EVAL_ITEMS.find((i) => i.id === decodeURIComponent(m?.[1] ?? ''))
    if (!found) throw new HttpError(404, 'not_found', 'No such evaluation item.')
    // A silence item is silence: two seconds of near-zero samples.
    if (!found.original) return audioResponse(encodeWav(new Int16Array(32_000)))
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
