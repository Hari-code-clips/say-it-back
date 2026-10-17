import type { Briefing } from '../api/types.ts'
import { translate, type UiLang } from '../i18n/translate.ts'

// What a briefing cost, from its own record and nothing else (v0.5.1): how long from the instruction to the decision,
// how many rounds, how many steps had to be explained again, how many problems the worker reported. Every number is
// read from the briefing's timestamps, rounds and hazards; when one cannot be read, the line is not shown at all.

export interface BriefingFacts {
  /** Whole seconds from the briefing's creation to its decision (or to `now` before there is one). */
  seconds: number
  rounds: number
  /** Distinct steps that a re-explanation round covered. */
  reexplained: number
  problems: number
  /** True when the time runs to the decision; false when it runs to now (the decision screen). */
  decided: boolean
}

const time = (iso: string | undefined): number | null => {
  if (!iso) return null
  const ms = new Date(iso).getTime()
  return Number.isNaN(ms) ? null : ms
}

/** Whole seconds from `createdAt` to `decidedAt`, or null when either is missing or invalid, or the order is wrong. */
export function secondsToDecision(createdAt: string | undefined, decidedAt: string | undefined): number | null {
  const start = time(createdAt)
  const end = time(decidedAt)
  return start === null || end === null || end < start ? null : Math.floor((end - start) / 1000)
}

/**
 * The facts of `b`, or null when they cannot be read: no valid creation time, or a decision time before it. Before a
 * decision, `now` ends the time (the decision screen says "so far"); without `now`, an undecided briefing has no line.
 */
export function briefingFacts(b: Pick<Briefing, 'createdAt' | 'decision' | 'rounds' | 'hazards'>, now?: Date): BriefingFacts | null {
  const start = time(b.createdAt)
  const decidedAt = time(b.decision?.at)
  const end = decidedAt ?? (now ? now.getTime() : null)
  if (start === null || end === null || end < start) return null
  const reexplained = new Set(b.rounds.filter((r) => r.kind === 'reexplain').flatMap((r) => r.stepIds))
  return {
    seconds: Math.floor((end - start) / 1000),
    rounds: b.rounds.length,
    reexplained: reexplained.size,
    problems: (b.hazards ?? []).length,
    decided: decidedAt !== null,
  }
}

/** "45 s", "6 min 12 s", "1 h 5 min", in the UI language. */
export function formatDuration(seconds: number, lang: UiLang): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return translate(lang, 'facts.s', { s })
  if (s < 3600) return translate(lang, 'facts.ms', { m: Math.floor(s / 60), s: s % 60 })
  return translate(lang, 'facts.hm', { h: Math.floor(s / 3600), m: Math.floor((s % 3600) / 60) })
}

/**
 * "Instruction to decision: 6 min 12 s · 2 rounds · 3 steps re-explained · 1 problem reported". Parts that are zero
 * (no re-explanation, no problem) are left out; the time and the rounds always show.
 */
export function factsLine(facts: BriefingFacts, lang: UiLang): string {
  const count = (n: number, one: 'facts.round1' | 'facts.reexplained1' | 'facts.problem1', many: 'facts.rounds' | 'facts.reexplained' | 'facts.problems') =>
    n === 1 ? translate(lang, one) : translate(lang, many, { n })
  const parts = [
    translate(lang, facts.decided ? 'facts.decided' : 'facts.soFar', { time: formatDuration(facts.seconds, lang) }),
    count(facts.rounds, 'facts.round1', 'facts.rounds'),
    ...(facts.reexplained > 0 ? [count(facts.reexplained, 'facts.reexplained1', 'facts.reexplained')] : []),
    ...(facts.problems > 0 ? [count(facts.problems, 'facts.problem1', 'facts.problems')] : []),
  ]
  return parts.join(' · ')
}
