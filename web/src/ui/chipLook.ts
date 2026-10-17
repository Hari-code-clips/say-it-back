// Chip tones as data (no JSX), so tests/ui can check the verdict contract of web/design.md: the four verdict tones are
// four visibly different treatments (tint, tint, solid, outline) and Missed has no fill at all.

export type ChipTone =
  | 'neutral'
  | 'primary'
  | 'ink'
  | 'success'
  | 'warning'
  | 'error'
  | 'strong-error'
  // The four verdicts. Only these carry chroma on a supervisor screen (apart from error and hazard).
  | 'got'
  | 'ask'
  | 'wrong'
  | 'missed'

export interface ToneLook {
  /** Colour classes: fill, text, border. */
  box: string
  /** The leading mark is drawn filled (a solid glyph) or as an outline. */
  glyph: 'filled' | 'outline'
}

export const TONE: Record<ChipTone, ToneLook> = {
  neutral: { box: 'bg-surface-container-high text-on-surface-variant', glyph: 'filled' },
  // A label that matters a little more than neutral: the action blue's tint (blue is never a verdict).
  primary: { box: 'bg-primary-container text-on-primary-container', glyph: 'filled' },
  // Ink fill, paper text: the one solid neutral, for a decision that was recorded (Go). The supervisor's act, so no hue.
  ink: { box: 'bg-inverse-surface text-inverse-on-surface', glyph: 'filled' },
  success: { box: 'bg-success-container text-on-success-container', glyph: 'filled' },
  // Caution without amber: amber is Ask again. A neutral label with an ink outline and its own mark.
  warning: { box: 'border-[1.5px] border-on-surface bg-transparent text-on-surface', glyph: 'filled' },
  error: { box: 'bg-error-container text-on-error-container', glyph: 'filled' },
  'strong-error': { box: 'bg-error text-on-error', glyph: 'filled' },
  // Got it: green tint. Ask again: amber tint. Wrong: the only solid verdict. Missed: no fill, an ink outline.
  got: { box: 'bg-success-container text-on-success-container', glyph: 'filled' },
  ask: { box: 'bg-warning-container text-on-warning-container', glyph: 'filled' },
  wrong: { box: 'bg-error text-on-error', glyph: 'filled' },
  missed: { box: 'border-2 border-on-surface bg-transparent text-on-surface', glyph: 'outline' },
}

export const CHIP_BASE = 'inline-flex min-h-8 items-center gap-2 rounded-sm px-3 text-label-lg'
