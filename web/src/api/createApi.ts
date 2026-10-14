import { GEMINI_TIMEOUT_MS, type Transport } from './transport.ts'
import type {
  Briefing,
  BriefingSummary,
  Catalog,
  CreateBriefingBody,
  CreateRoundBody,
  DecisionBody,
  EvalItem,
  EvalReport,
  EvalTryResult,
  Health,
  Lang,
  LiveTicket,
  Round,
  Step,
} from './types.ts'

const gemini = { timeoutMs: GEMINI_TIMEOUT_MS }
const enc = encodeURIComponent

/** One function per endpoint of docs/API.md (numbers in comments), over a transport. The Live socket (20) lives in src/live. */
export function createApi({ request, requestBlob }: Transport) {
  return {
    health: () => request<Health>('/health'), // 1
    catalog: () => request<Catalog>('/catalog'), // 2

    transcribe(audio: Blob, lang: Lang) {
      // 3
      const form = new FormData()
      form.append('audio', audio, 'instruction.wav')
      form.append('lang', lang)
      return request<{ text: string }>('/transcribe', { method: 'POST', form, ...gemini })
    },

    createBriefing: (body: CreateBriefingBody) => request<Briefing>('/briefings', { method: 'POST', json: body }), // 4
    listBriefings: (limit = 20) => request<{ items: BriefingSummary[] }>(`/briefings?limit=${limit}`), // 5
    getBriefing: (id: string) => request<Briefing>(`/briefings/${enc(id)}`), // 6
    patchInstruction: (id: string, instruction: string) =>
      request<Briefing>(`/briefings/${enc(id)}`, { method: 'PATCH', json: { instruction } }), // 7
    extractSteps: (id: string) => request<Briefing>(`/briefings/${enc(id)}/steps/extract`, { method: 'POST', ...gemini }), // 8
    confirmSteps: (id: string, steps: Step[]) =>
      request<Briefing>(`/briefings/${enc(id)}/steps`, { method: 'PUT', json: { steps } }), // 9
    createRound: (id: string, body: CreateRoundBody = {}) =>
      request<Round>(`/briefings/${enc(id)}/rounds`, { method: 'POST', json: body, ...gemini }), // 10
    liveSession: (id: string, n: number) =>
      request<LiveTicket>(`/briefings/${enc(id)}/rounds/${n}/live-session`, { method: 'POST' }), // 11

    /** 12: a line of round `n`'s script, spoken in the briefing's worker language. The server refuses any other text. */
    tts: (briefingId: string, n: number, text: string) => requestBlob('/tts', { method: 'POST', json: { briefingId, n, text }, ...gemini }),

    check(id: string, n: number, clips: Record<string, Blob>, mode: 'live' | 'turn') {
      // 13: one WAV per question, field name = question id
      const form = new FormData()
      for (const [qid, blob] of Object.entries(clips)) form.append(qid, blob, `${qid}.wav`)
      form.append('meta', JSON.stringify({ mode }))
      return request<Round>(`/briefings/${enc(id)}/rounds/${n}/check`, { method: 'POST', form, ...gemini })
    },

    decide: (id: string, body: DecisionBody) =>
      request<Briefing>(`/briefings/${enc(id)}/decision`, { method: 'POST', json: body }), // 14
    exportCsv: () => requestBlob('/export/briefings.csv'), // 15 (a download needs the device key too, so it is fetched, not linked)

    evalLatest: () => request<EvalReport>('/eval/latest'), // 16
    evalItems: () => request<{ items: EvalItem[] }>('/eval/items'), // 17
    evalAudio: (id: string) => requestBlob(`/eval/items/${enc(id)}/audio`), // 18
    evalTry: (id: string) => request<EvalTryResult>(`/eval/items/${enc(id)}/try`, { method: 'POST', ...gemini }), // 19
  }
}

export type Api = ReturnType<typeof createApi>
