import type { Verdict } from '../../api/types.ts'
import type { StringKey } from '../../i18n/index.tsx'
import type { IconName } from '../../theme/iconNames.ts'
import type { ChipTone } from '../../ui/Chip.tsx'

// Verdicts are always shown as a word AND an icon AND a colour (never colour alone):
//   covered -> "Got it", missed -> "Missed", contradicted -> "Wrong", unclear -> "Ask again".
// The tool never says a step or the work is "safe" or signed off; it only reports what the answer covered.

export interface VerdictLook {
  label: StringKey
  icon: IconName
  tone: ChipTone
  /** Header band of a result card. */
  band: string
}

export const VERDICT: Record<Verdict, VerdictLook> = {
  covered: { label: 'verdict.covered', icon: 'check_circle', tone: 'success', band: 'bg-success-container text-on-success-container' },
  missed: { label: 'verdict.missed', icon: 'remove_circle', tone: 'error', band: 'bg-error-container text-on-error-container' },
  contradicted: { label: 'verdict.contradicted', icon: 'cancel', tone: 'strong-error', band: 'bg-error text-on-error' },
  unclear: { label: 'verdict.unclear', icon: 'replay', tone: 'warning', band: 'bg-warning-container text-on-warning-container' },
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
}

export const VERDICT_ORDER: readonly Verdict[] = ['covered', 'missed', 'contradicted', 'unclear']
