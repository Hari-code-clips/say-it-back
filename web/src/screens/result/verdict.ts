import type { Rating, Verdict } from '../../api/types.ts'
import type { StringKey } from '../../i18n/index.tsx'
import type { IconName } from '../../theme/iconNames.ts'
import type { ChipTone } from '../../ui/chipLook.ts'

// Verdicts are always shown as a word AND a mark AND a treatment (never colour alone; web/design.md, "chroma means a verdict"):
//   covered -> "Got it" (check, green tint), unclear -> "Ask again" (refresh, amber tint), contradicted -> "Wrong" (close, solid red),
//   missed -> "Missed" (minus in a circle, no fill, an ink outline: the step was not said, so no alarm colour).
// The tool never says a step or the work is "safe" or signed off; it only reports what the answer covered.

export interface VerdictLook {
  label: StringKey
  icon: IconName
  tone: ChipTone
  /** How the chip is filled. Missed is the only one with no fill, so it differs from Wrong without colour. */
  treatment: 'tint' | 'outline' | 'solid'
  /** Header band of a result card. */
  band: string
}

export const VERDICT: Record<Verdict, VerdictLook> = {
  covered: { label: 'verdict.covered', icon: 'check', tone: 'got', treatment: 'tint', band: 'bg-success-container text-on-success-container' },
  missed: { label: 'verdict.missed', icon: 'remove_circle', tone: 'missed', treatment: 'outline', band: 'border-b-2 border-on-surface bg-surface text-on-surface' },
  contradicted: { label: 'verdict.contradicted', icon: 'close', tone: 'wrong', treatment: 'solid', band: 'bg-error text-on-error' },
  unclear: { label: 'verdict.unclear', icon: 'refresh', tone: 'ask', treatment: 'tint', band: 'bg-warning-container text-on-warning-container' },
}

/** Rating and transcript flags from the contract, as labels; unknown flags show as written. */
export const FLAG_LABEL: Record<string, StringKey> = {
  passes_disagreed: 'flag.passes_disagreed',
  quote_not_found: 'flag.quote_not_found',
  low_confidence: 'flag.low_confidence',
  language_mismatch: 'flag.language_mismatch',
  no_speech: 'flag.no_speech',
  not_asked: 'flag.not_asked',
  low_audio: 'flag.low_audio',
  partly_unclear: 'flag.partly_unclear',
  delivery_mismatch: 'flag.delivery_mismatch',
  // v0.5.1: the model's safety filter blocked the clip; the step reads as "Ask again".
  model_refused: 'flag.model_refused',
}

/**
 * A transcript's flags that need a sentence, not just a chip, where the transcript would be: a clip the model refused
 * to process has no transcript, and "No speech" would be wrong. Null when the flags need none.
 */
export function transcriptNote(flags: readonly string[]): StringKey | null {
  return flags.includes('model_refused') ? 'result.modelRefused' : null
}

export const VERDICT_ORDER: readonly Verdict[] = ['covered', 'missed', 'contradicted', 'unclear']

/** A rating's verdict. No rating means the step was never asked about: "Ask again", never "Got it". */
export const ratingVerdict = (rating: Pick<Rating, 'verdict'> | undefined): Verdict => rating?.verdict ?? 'unclear'

/** A step's verdict in a round's ratings (see ratingVerdict). */
export const verdictOf = (ratings: readonly Pick<Rating, 'stepId' | 'verdict'>[], stepId: string): Verdict =>
  ratingVerdict(ratings.find((r) => r.stepId === stepId))

/**
 * The worker's own words for a step, for one line of the result's "At a glance" list: the quote's translation into the
 * supervisor's language when there is one, else the quote as said. Null when the rating has no quote.
 */
export function quoteLine(rating: Pick<Rating, 'quote' | 'quoteTranslation'> | undefined): { text: string; translated: boolean } | null {
  const translated = rating?.quoteTranslation?.trim()
  if (rating?.quote?.trim() && translated) return { text: translated, translated: true }
  const said = rating?.quote?.trim()
  return said ? { text: said, translated: false } : null
}

/**
 * What to do when the two judges split (flag `passes_disagreed`), from the rule of v0.5.3: a contradiction in either stands, any
 * other split is "Ask again", and a split is never "Got it". Only those two outcomes get a sentence; a record from before
 * v0.5.3 can show another verdict with the flag, and it must not be told it "reads Ask again".
 */
export function disagreementHint(verdict: Verdict, flags: readonly string[]): StringKey | null {
  if (!flags.includes('passes_disagreed')) return null
  return verdict === 'unclear' ? 'result.disagreedAsk' : verdict === 'contradicted' ? 'result.disagreedWrong' : null
}

/** The questions of a round that check a step, with their number in the round (the answers that are the step's evidence). */
export function askedAbout<Q extends { stepIds: readonly string[] }>(questions: readonly Q[], stepId: string): { question: Q; number: number }[] {
  return questions.flatMap((question, i) => (question.stepIds.includes(stepId) ? [{ question, number: i + 1 }] : []))
}
