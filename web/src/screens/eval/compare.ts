import type { EvalBreakdown, EvalReport } from '../../api/types.ts'
import type { StringKey } from '../../i18n/index.tsx'

// The Eval page's v0.5 evidence, without React (unit-tested): the checker on all items and on the two held-out tasks,
// beside the keyword baselines scored on the same English translations. Reports from before v0.5 have none of it.

export type CompareKey = 'all' | 'heldOut' | 'keyword' | 'keywordNegation'

export const COMPARE_LABEL: Record<CompareKey, StringKey> = {
  all: 'eval.cmp.all',
  heldOut: 'eval.cmp.heldOut',
  keyword: 'eval.cmp.keyword',
  keywordNegation: 'eval.cmp.keywordNegation',
}

/**
 * Rows for the comparison table, in this order: the checker on every item, on the held-out tasks, then the keyword
 * baseline and the keyword baseline with negation. Only the rows the report has; null when it has neither the held-out
 * split nor a baseline (a report from before v0.5), so the table is left out rather than showing the checker alone.
 */
export function comparisonRows(report: EvalReport): Record<string, EvalBreakdown> | null {
  const held = report.byHeldOut?.heldOut
  const keyword = report.baseline?.keyword
  const negation = report.baseline?.keywordNegation
  if (!held && !keyword && !negation) return null
  const rows: Record<string, EvalBreakdown> = {
    all: { n: report.nStepRatings, exactAccuracy: report.metrics.exactAccuracy, unsafeErrors: report.metrics.unsafeErrors },
  }
  if (held && held.n > 0) rows.heldOut = held
  if (keyword) rows.keyword = keyword
  if (negation) rows.keywordNegation = negation
  return rows
}

/** The pass bar's sentence: with the v0.5 condition on correct answers when the report has it, else the older one. */
export function passBarKey(report: EvalReport): StringKey {
  return report.passBar.correctPassMin === undefined ? 'eval.passBar' : 'eval.passBarCorrect'
}
