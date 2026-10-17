import { GEMINI_TIMEOUT_MS, type Transport } from './transport.ts'
import type {
  Briefing,
  BriefingSummary,
  Catalog,
  CreateBriefingBody,
  CreateRoundBody,
  DecisionBody,
  DemoAnswer,
  EvalItem,
  EvalReport,
  EvalTryResult,
  Hazard,
  Health,
  Lang,
  LibraryEntry,
  LiveTicket,
  Round,
  Step,
  VerifyResult,
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
    /**
     * 11: a single-use ticket for the Live socket. `samplesOnly` (security fixes B) declares that every answer of the round is a
     * stored sample, so no consent screen was shown: with SIB_REQUIRE_CONSENT the server issues a ticket for a round with no
     * recorded choice only then. Without it no body is sent, as before.
     */
    liveSession: (id: string, n: number, samplesOnly = false) =>
      request<LiveTicket>(`/briefings/${enc(id)}/rounds/${n}/live-session`, { method: 'POST', ...(samplesOnly ? { json: { samplesOnly: true } } : {}) }),

    /** 12: a line of round `n`'s script, spoken in the briefing's worker language. The server refuses any other text. */
    tts: (briefingId: string, n: number, text: string) => requestBlob('/tts', { method: 'POST', json: { briefingId, n, text }, ...gemini }),

    check(id: string, n: number, clips: Record<string, Blob>, mode: 'live' | 'turn', sampleAnswers: readonly string[] = [], idempotencyKey?: string) {
      // 13: one WAV per question, field name = question id. v0.4: `meta.sampleAnswers` names the questions answered with a stored
      // synthetic sample (endpoint 24), so the record says which answers were not a person's. 2026-10-16: the same Idempotency-Key on
      // every retry of one upload, so a retry after a dropped connection gets the round the first one judged (src/net/retry.ts).
      const form = new FormData()
      for (const [qid, blob] of Object.entries(clips)) form.append(qid, blob, `${qid}.wav`)
      form.append('meta', JSON.stringify(sampleAnswers.length > 0 ? { mode, sampleAnswers: [...sampleAnswers] } : { mode }))
      const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
      return request<Round>(`/briefings/${enc(id)}/rounds/${n}/check`, { method: 'POST', form, ...gemini, ...(headers ? { headers } : {}) })
    },

    decide: (id: string, body: DecisionBody) =>
      request<Briefing>(`/briefings/${enc(id)}/decision`, { method: 'POST', json: body }), // 14
    exportCsv: () => requestBlob('/export/briefings.csv'), // 15 (a download needs the device key too, so it is fetched, not linked)

    evalLatest: () => request<EvalReport>('/eval/latest'), // 16
    evalItems: () => request<{ items: EvalItem[] }>('/eval/items'), // 17
    evalAudio: (id: string) => requestBlob(`/eval/items/${enc(id)}/audio`), // 18
    evalTry: (id: string) => request<EvalTryResult>(`/eval/items/${enc(id)}/try`, { method: 'POST', ...gemini }), // 19

    /** 21: a worker's problem report. With audio it is transcribed and translated (one Gemini call); without, it is a tap. */
    reportHazard(id: string, { audio, round }: { audio?: Blob; round?: number } = {}) {
      const form = new FormData()
      if (audio) form.append('audio', audio, 'hazard.wav')
      if (round !== undefined) form.append('round', String(round))
      return request<Hazard>(`/briefings/${enc(id)}/hazards`, { method: 'POST', form, ...(audio ? gemini : {}) })
    },
    /** 22: what the supervisor did about a reported problem (5+ characters). */
    ackHazard: (id: string, hazardId: string, body: { note: string; by?: string }) =>
      request<Briefing>(`/briefings/${enc(id)}/hazards/${enc(hazardId)}/ack`, { method: 'POST', json: body }),
    /** 23: the supervisor has read the round's script and its back-translation. Nothing is spoken before. */
    approveRound: (id: string, n: number, body: { by?: string } = {}) =>
      request<Round>(`/briefings/${enc(id)}/rounds/${n}/approve`, { method: 'POST', json: body }),
    demoAnswers: () => request<{ items: DemoAnswer[] }>('/demo-answers'), // 24
    /** 24: one question's stored answer; without `questionId` (an older server's item), the round's own first answer. */
    demoAnswerAudio: (taskId: string, workerLang: Lang, round: number, questionId?: string) =>
      requestBlob(`/demo-answers/${enc(taskId)}/${enc(workerLang)}/${round}${questionId === undefined ? '' : `/${enc(questionId)}`}/audio`), // 24
    verify: (id: string) => request<VerifyResult>(`/briefings/${enc(id)}/verify`), // 25

    /** Privacy (16 Oct): the worker's choice before round `n` records any answer, "I agree" (true) or "Not now" (false). */
    consent: (id: string, n: number, given: boolean) =>
      request<Round>(`/briefings/${enc(id)}/rounds/${n}/consent`, { method: 'POST', json: { given } }),
    /** Privacy (16 Oct): remove this record at once. A copy already sent by webhook belongs to the system that received it. */
    deleteBriefing: (id: string) => request<{ ok: boolean; id: string }>(`/briefings/${enc(id)}`, { method: 'DELETE' }),

    // The SOP library of a site (Deviations 2026-10-16). No model call; every write returns the whole entry.
    listSops: (siteId: string) => request<{ items: LibraryEntry[] }>(`/sites/${enc(siteId)}/sops`),
    createSop: (siteId: string, body: { title: string; text: string; changeNote?: string; taskId?: string; lang?: Lang }) =>
      request<LibraryEntry>(`/sites/${enc(siteId)}/sops`, { method: 'POST', json: body }),
    createSopVersion: (siteId: string, sopId: string, body: { text: string; changeNote?: string; lang?: Lang }) =>
      request<LibraryEntry>(`/sites/${enc(siteId)}/sops/${enc(sopId)}/versions`, { method: 'POST', json: body }),
    setSopSteps: (siteId: string, sopId: string, n: number, steps: Step[]) =>
      request<LibraryEntry>(`/sites/${enc(siteId)}/sops/${enc(sopId)}/versions/${n}/steps`, { method: 'PUT', json: { steps } }),
    approveSopVersion: (siteId: string, sopId: string, n: number) =>
      request<LibraryEntry>(`/sites/${enc(siteId)}/sops/${enc(sopId)}/versions/${n}/approve`, { method: 'POST', json: {} }),
  }
}

export type Api = ReturnType<typeof createApi>
