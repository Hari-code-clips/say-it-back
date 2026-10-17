// 17 Oct: Google's Live API language table (Agent Platform, "Configure language and voice", updated 2026-10-15) lists no
// Mandarin, Burmese or Odia (build-notes/37-telugu-consent.md, Sources). A briefing in one of them starts turn by turn,
// whose voice (Gemini TTS) does list them; live voice stays one tap away, and the delivery check still guards it.
import type { RunMode } from './useBriefingRun.ts'

export const LIVE_UNLISTED: ReadonlySet<string> = new Set(['zh', 'my', 'or'])

export const liveListed = (workerLang: string): boolean => !LIVE_UNLISTED.has(workerLang)

export const defaultMode = (workerLang: string): RunMode => (liveListed(workerLang) ? 'live' : 'turn')
