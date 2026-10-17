import type { EvalItem } from '../../api/types.ts'
import type { StringKey, Translate } from '../../i18n/index.tsx'

// Human labels for the test set's enums (docs/API.md, "Eval test set"): the evaluator reads "Synthetic voice" and "Noisy (10 dB)",
// never `synthetic_tts` or `snr10`. A value this build does not know yet is shown in words, never as the raw code.

const PATTERN: Record<string, StringKey> = {
  complete: 'eval.pattern.complete',
  one_missing: 'eval.pattern.one_missing',
  two_missing: 'eval.pattern.two_missing',
  contradicted: 'eval.pattern.contradicted',
  vague: 'eval.pattern.vague',
  echo: 'eval.pattern.echo',
  fluent_wrong: 'eval.pattern.fluent_wrong',
  negation: 'eval.pattern.negation',
  numbers: 'eval.pattern.numbers',
  code_switch: 'eval.pattern.code_switch',
  wrong_language: 'eval.pattern.wrong_language',
  silence: 'eval.pattern.silence',
  demo: 'eval.pattern.demo',
}

const NOISE: Record<string, StringKey> = {
  clean: 'eval.noise.clean',
  snr10: 'eval.noise.snr10',
  snr5: 'eval.noise.snr5',
}

const SOURCE: Record<string, StringKey> = {
  synthetic_tts: 'eval.source.synthetic_tts',
  recorded: 'eval.source.recorded',
}

/** What a pattern tests, in one line (the Sample page). */
const TESTS: Record<string, StringKey> = {
  demo: 'sample.tests.demo',
  negation: 'sample.tests.negation',
  contradicted: 'sample.tests.contradicted',
  fluent_wrong: 'sample.tests.fluent_wrong',
  wrong_language: 'sample.tests.wrong_language',
  silence: 'sample.tests.silence',
}

/** "snr_10db" -> "Snr 10db": words, at least, for a code with no label yet. */
export const humanize = (code: string): string => {
  const words = code.replace(/[_.-]+/g, ' ').trim()
  return words ? words[0]!.toUpperCase() + words.slice(1) : code
}

const pick = (table: Record<string, StringKey>, t: Translate, code: string): string => {
  const key = table[code]
  return key ? t(key) : humanize(code)
}

export const patternLabel = (t: Translate, code: string): string => pick(PATTERN, t, code)
export const noiseLabel = (t: Translate, code: string): string => pick(NOISE, t, code)
export const sourceLabel = (t: Translate, code: string): string => pick(SOURCE, t, code)
export const testsLine = (t: Translate, code: string): string | undefined => (TESTS[code] ? t(TESTS[code]) : undefined)

/** A step's text from endpoint 17's `steps`, or "Step 2" (its number in the item) when the server sent none. */
export function stepText(t: Translate, item: Pick<EvalItem, 'gold' | 'steps'>, id: string): string {
  const text = item.steps?.[id]
  if (text) return text
  const n = Object.keys(item.gold).indexOf(id) + 1
  return t('eval.stepN', { n: n > 0 ? n : '?' })
}
