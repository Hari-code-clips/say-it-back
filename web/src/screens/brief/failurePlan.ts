import type { RunMode } from './useBriefingRun.ts'

export interface FailureInput {
  /** `failed`: the voice session did not run to its end. `submit_failed`: it did, and the check call did not. */
  kind: 'failed' | 'submit_failed'
  /** The mode that failed (only meaningful for `failed`). */
  mode?: RunMode
  /** The HTTP error code, when an API call was what failed. */
  code?: string
  /** The microphone was the problem: a different mode cannot help. */
  micProblem: boolean
}

export interface FailurePlan {
  /** Offer to run the same round turn by turn (recorded voice, then the check: both spend Gemini calls). */
  offerTurn: boolean
  /** The paragraph under the message. */
  hint: 'turn' | 'not_recorded' | null
  offerRetry: boolean
  /** Retry is the quieter button because turn-by-turn leads. */
  retryQuiet: boolean
  /** v0.4: the round's script is not confirmed (409 `script_not_approved`): only the script screen can help. */
  backToScript: boolean
}

/**
 * What the failure screen of a briefing round offers. The rules that matter:
 * - `daily_limit` (the day's Gemini budget is used up until UTC midnight): no turn-by-turn fallback, because TTS and the check draw on
 *   the same budget, and no retry of a session, because it cannot work today. Nothing retries by itself either.
 * - `limit` (both voice tickets for the round are used): trying Live again cannot work, but turn-by-turn needs no ticket.
 * - `live_not_recorded` (the relay never saved the session): the delivery cannot be verified, so turn-by-turn re-reads the script.
 * - `script_not_approved` (v0.4): the script was never confirmed, so nothing may be spoken: back to the script screen.
 */
export function failurePlan({ kind, mode, code, micProblem }: FailureInput): FailurePlan {
  if (code === 'script_not_approved') return { offerTurn: false, hint: null, offerRetry: false, retryQuiet: false, backToScript: true }
  if (kind === 'submit_failed') {
    // The answers are recorded on this device, so Retry (the check call again) always stays.
    const notRecorded = code === 'live_not_recorded'
    return { offerTurn: notRecorded, hint: notRecorded ? 'not_recorded' : null, offerRetry: true, retryQuiet: notRecorded, backToScript: false }
  }
  const dailyLimit = code === 'daily_limit'
  const offerTurn = mode === 'live' && !micProblem && !dailyLimit
  return { offerTurn, hint: offerTurn ? 'turn' : null, offerRetry: code !== 'limit' && !dailyLimit, retryQuiet: offerTurn, backToScript: false }
}
