// Privacy (16 Oct): which consent screen, if any, the worker_ready stage shows (see ConsentStep.tsx and BriefScreen.tsx). Plain data and
// functions, so the rules are tested without a DOM:
//
//   none                  no consent step: Start (WorkerReady) as before. The worker already agreed, or no person's voice is recorded
//                         (every question of the round is answered by a stored sample: the evaluator's path), or it is another stage
//   ask                   one calm screen in the worker's language: "I agree" or "Not now"
//   failed                "I agree" could not be saved: the worker is asked to give the phone to the supervisor, as for any failure
//   declined              after "Not now": thank you, give the phone to your supervisor (worker language only)
//   declined_supervisor   the supervisor held "I'm the supervisor": brief in person; nothing was recorded, no mark against the worker
import type { Stage } from './handover.ts'

export type ConsentChoice = 'pending' | 'given' | 'declined'
export type ConsentView = 'none' | 'ask' | 'failed' | 'declined' | 'declined_supervisor'

export interface ConsentInput {
  stage: Stage
  /** The round's question ids. */
  questionIds: readonly string[]
  /** The questions the supervisor chose to answer with a stored sample (sample.ts `sampleQids`). */
  sampleQids: readonly string[]
  consent: ConsentChoice
  /** Saving "I agree" failed. */
  failed: boolean
  /** The supervisor took the phone back after a "Not now". */
  declinedSeen: boolean
}

/** A person's voice is recorded unless every question of the round is answered by a stored synthetic sample. */
export const needsConsent = (questionIds: readonly string[], sampleQids: readonly string[]): boolean =>
  questionIds.some((q) => !sampleQids.includes(q))

export function consentStep({ stage, questionIds, sampleQids, consent, failed, declinedSeen }: ConsentInput): ConsentView {
  if (stage !== 'worker_ready' || consent === 'given' || !needsConsent(questionIds, sampleQids)) return 'none'
  if (failed) return 'failed'
  if (consent === 'declined') return declinedSeen ? 'declined_supervisor' : 'declined'
  return 'ask'
}
