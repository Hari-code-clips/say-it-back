import type { Briefing } from '../../api/types.ts'
import type { StringKey } from '../../i18n/en.ts'
import { canReexplain, openHazards, openSteps } from '../../flow/phases.ts'

// What a supervisor can do from the result and the decision screens, as data (no React), so it is unit-tested and the
// screens only draw it. web/design.md: a disabled primary says why, in visible text.

export type ResultAction = 'reexplain' | 'decide'

export interface ResultBar {
  /** The dominant action (64 px). */
  primary: ResultAction
  /** The quieter one above it on a phone, beside it from 600 px (48 px). Null when only one action is possible. */
  secondary: ResultAction | null
}

/**
 * The sticky bar of the result, on every round. With open steps and a round left, Re-explain leads and Decide waits beside it;
 * with every step covered, or no round left, Decide is the only action. Decide is never hidden: a No-go is always possible.
 */
export function resultBar(b: Briefing): ResultBar {
  return canReexplain(b) ? { primary: 'reexplain', secondary: 'decide' } : { primary: 'decide', secondary: null }
}

/** The contract's minimum for a reason (endpoint 14) and for a note on a reported problem (endpoint 22). */
export const REASON_MIN = 5

export type DecisionChoice = 'go' | 'no_go'
export type DecisionNeed = 'choice' | 'reason' | 'hazard'

export interface DecisionGate {
  valid: boolean
  /** What is missing, first thing first; null when the decision can be recorded. */
  need: DecisionNeed | null
  /** The visible sentence for `need`. */
  reasonKey: StringKey | null
}

const NEED_KEY: Record<DecisionNeed, StringKey> = {
  choice: 'decision.need.choice',
  reason: 'decision.need.reason',
  hazard: 'decision.need.hazard',
}

/**
 * Whether `Record decision` is on, and if not, what the supervisor still has to do. Go with a step that is not covered needs a
 * reason; Go while a reported problem has no note is locked; No-go is always open. 2026-10-17: a Go after an in-person check
 * (`inPerson`) always needs the reason, as the server does.
 */
export function decisionGate(input: { choice: DecisionChoice | null; reason: string; openStepCount: number; goLocked: boolean; inPerson?: boolean }): DecisionGate {
  const { choice, reason, openStepCount, goLocked, inPerson = false } = input
  const reasonNeeded = openStepCount > 0 || inPerson
  const need: DecisionNeed | null =
    choice === null ? 'choice' : choice === 'go' && goLocked ? 'hazard' : choice === 'go' && reasonNeeded && reason.trim().length < REASON_MIN ? 'reason' : null
  return { valid: need === null, need, reasonKey: need && NEED_KEY[need] }
}

/** Reported problems nobody has noted yet: each one locks Go. */
export const openHazardCount = (b: Pick<Briefing, 'hazards'>): number => openHazards(b).length

/** Steps still not `covered` (a step never rated counts as open), as a count. */
export const openStepCount = (b: Briefing): number => openSteps(b).length
