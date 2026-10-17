import type { ChainEvent, ChainEventType, Round, VerifyResult } from '../api/types.ts'
import type { StringKey } from '../i18n/en.ts'

// Reading the record chain (docs/API.md, "Record chain"). The server writes and verifies it (endpoint 25); the browser only
// shows what the server found, and never claims a verification it did not get.

/** The first `n` hex characters of a SHA-256, for display ("3f9a1c0b7e2d"). */
export const shortHash = (hash: string | undefined, n = 12): string => (hash ?? '').slice(0, n)

/** How many events the verify call checked: the contract's count, or the length if a list came back. */
export function verifiedCount(v: Pick<VerifyResult, 'events'> | { events: unknown }, fallback: number): number {
  const e = (v as { events: unknown }).events
  if (typeof e === 'number' && Number.isFinite(e)) return e
  if (Array.isArray(e)) return e.length
  return fallback
}

/** The number an event's label carries: the round for round events, the problem's number for hazard events. */
export function eventNumber(event: Pick<ChainEvent, 'type' | 'data'>): string {
  const n = event.data.n
  if (typeof n === 'number') return String(n)
  const id = event.data.hazardId
  if (typeof id === 'string') return /^h(\d+)$/.exec(id)?.[1] ?? id
  return ''
}

/** Event types whose label names a round or a reported problem. */
export const NUMBERED_EVENTS: ReadonlySet<ChainEventType> = new Set(['round_created', 'script_approved', 'round_judged', 'hazard_raised', 'hazard_acknowledged', 'consent'])

/** Each round's answers that were stored synthetic samples, in round order: [{round: 1, qids: ['q1'], numbers: [1]}]. */
export function samplesByRound(rounds: readonly Pick<Round, 'n' | 'sampleAnswers' | 'script'>[]): { round: number; numbers: number[] }[] {
  return rounds
    .map((r) => ({
      round: r.n,
      numbers: (r.sampleAnswers ?? []).map((qid) => r.script.questions.findIndex((q) => q.id === qid) + 1).filter((n) => n > 0),
    }))
    .filter((r) => r.numbers.length > 0)
}

/** Endpoint 25's `reason` codes (docs/API.md, Deviations 2026-10-14, record chain), in words. Never shown as the raw code. */
const REASONS: Record<string, StringKey> = {
  seq_mismatch: 'chain.reason.seq_mismatch',
  prev_hash_mismatch: 'chain.reason.prev_hash_mismatch',
  hash_mismatch: 'chain.reason.hash_mismatch',
  instruction_mismatch: 'chain.reason.instruction_mismatch',
  sop_mismatch: 'chain.reason.sop_mismatch',
  steps_mismatch: 'chain.reason.steps_mismatch',
  script_mismatch: 'chain.reason.script_mismatch',
  ratings_mismatch: 'chain.reason.ratings_mismatch',
  round_missing: 'chain.reason.round_missing',
  hazard_mismatch: 'chain.reason.hazard_mismatch',
  hazard_missing: 'chain.reason.hazard_missing',
  decision_mismatch: 'chain.reason.decision_mismatch',
  record_hash_mismatch: 'chain.reason.record_hash_mismatch',
  unrecorded_change: 'chain.reason.unrecorded_change',
}

export const chainReasonKey = (reason: string | undefined): StringKey => (reason && REASONS[reason]) || 'chain.reason.other'

/** A record made before v0.4 has no chain at all: that is not a broken one, and is said so plainly. */
export const hasNoChain = (v: Pick<VerifyResult, 'reason' | 'events'>): boolean => v.reason === 'no_chain' || (!v.reason && v.events === 0)
