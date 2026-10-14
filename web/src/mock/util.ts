// Shared helpers for the in-browser mock of the API (VITE_API_MOCK=1).
import type { Script } from '../api/types.ts'

export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** Latency that feels like a real call: base plus a little jitter. */
export const delay = (base: number) => sleep(base + Math.random() * base * 0.4)

/** An error the REST mock turns into the contract's {"error": {code, message}} body. */
export class HttpError extends Error {
  readonly status: number
  readonly code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'HttpError'
    this.status = status
    this.code = code
  }
}

const B32 = 'abcdefghijklmnopqrstuvwxyz234567'

/** "b_" + 12 lowercase base32 characters, like the contract. */
export function newBriefingId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(12))
  return `b_${Array.from(bytes, (b) => B32[b % 32]).join('')}`
}

export const nowIso = (): string => new Date().toISOString()

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function errorResponse(e: unknown): Response {
  if (e instanceof HttpError) return jsonResponse({ error: { code: e.code, message: e.message } }, e.status)
  return jsonResponse({ error: { code: 'internal', message: e instanceof Error ? e.message : 'Mock error' } }, 500)
}

/** Whitespace collapsed to single spaces and trimmed, as the backend compares script text. */
const collapse = (text: string): string => text.split(/\s+/).filter(Boolean).join(' ')

/**
 * The backend's rule for what POST /api/tts may speak (docs/API.md, endpoint 12): text inside the round's instruction, or equal
 * to one of its questions or its closing, whitespace collapsed on both sides.
 */
export function partOfScript(script: Pick<Script, 'instruction' | 'questions' | 'closing'>, text: string): boolean {
  const wanted = collapse(text)
  if (!wanted) return false
  return collapse(script.instruction).includes(wanted) || [...script.questions.map((q) => q.text), script.closing].some((line) => collapse(line) === wanted)
}
