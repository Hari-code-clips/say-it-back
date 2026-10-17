import type { EvalItem, EvalReport, EvalTryResult, Verdict } from '../../api/types.ts'

/** What the worker said for a step and why the check rated it so (English, the eval's supervisor language). */
export interface StepEvidence {
  quote?: string
  quoteTranslation?: string
  reason?: string
}

// The Sample page's instant result (v0.5.1): the evaluation run already judged every stored clip on real Gemini, so the
// page shows that result at once instead of a 16-105 s live check. No React here, so it is unit-tested.

/** What a result panel shows, from a live try (endpoint 19) or from the stored evaluation report (endpoint 16). */
export interface ResultView {
  verdicts: Record<string, Verdict | undefined>
  agreement: Record<string, boolean>
  unsafe: boolean
  flags: string[]
  /** The transcriber's text in the worker's language, and its English translation. */
  original?: string
  translation?: string
  /** Per step: the quote in the worker's language, its translation and the reason, when the result has them. */
  evidence: Record<string, StepEvidence>
  /** The two judge passes, when known (a live try only). */
  passes?: { a: Record<string, Verdict | undefined>; b: Record<string, Verdict | undefined> }
}

/** Where a stored result comes from: shown with it, so nobody takes it for a live run. */
export interface StoredResult {
  view: ResultView
  generatedAt: string
  models: Record<string, string>
}

const byStep = (ratings: readonly { stepId: string; verdict: Verdict }[]) => Object.fromEntries(ratings.map((r) => [r.stepId, r.verdict]))

/** Each rating's quote, translation and reason, leaving out what is empty. */
const evidenceOf = (ratings: readonly ({ stepId: string } & StepEvidence)[]): Record<string, StepEvidence> =>
  Object.fromEntries(
    ratings.map(({ stepId, quote, quoteTranslation, reason }) => [
      stepId,
      { ...(quote?.trim() ? { quote } : {}), ...(quoteTranslation?.trim() ? { quoteTranslation } : {}), ...(reason?.trim() ? { reason } : {}) },
    ]),
  )

export function liveView(result: EvalTryResult): ResultView {
  const transcript = result.round.transcripts[0]
  return {
    verdicts: byStep(result.round.ratings),
    agreement: result.agreement,
    unsafe: result.unsafe,
    flags: [...new Set([...result.round.ratings.flatMap((r) => r.flags), ...(transcript?.flags ?? [])])],
    original: transcript?.original,
    translation: transcript?.translation,
    evidence: evidenceOf(result.round.ratings),
    passes: result.round.passB.length > 0 ? { a: byStep(result.round.passA), b: byStep(result.round.passB) } : undefined,
  }
}

const sameLabels = (a: Record<string, Verdict>, b: Record<string, Verdict>): boolean =>
  Object.keys(a).length === Object.keys(b).length && Object.entries(a).every(([id, v]) => b[id] === v)

/**
 * The report's result for `item`, or null when there is none to trust: no report, no entry for the item, no prediction,
 * gold labels that changed since the run (the result would be scored against old labels), or a clip that is not current
 * (`hasAudio` false: the clip that was judged may voice an older answer).
 */
export function storedResult(report: EvalReport | undefined, item: EvalItem): StoredResult | null {
  const entry = report?.items.find((i) => i.id === item.id)
  if (!report || !entry || item.hasAudio === false) return null
  if (Object.keys(entry.pred).length === 0 || !sameLabels(entry.gold, item.gold)) return null
  return {
    view: {
      verdicts: entry.pred,
      agreement: Object.fromEntries(Object.keys(item.gold).map((id) => [id, entry.pred[id] === item.gold[id]])),
      unsafe: entry.unsafe,
      flags: [...new Set([...Object.values(entry.flags ?? {}).flat(), ...(entry.ratings ?? []).flatMap((r) => r.flags ?? [])])],
      // An empty transcript is kept (it reads as no speech); only a report without the field has none.
      original: entry.original,
      translation: entry.translation || undefined,
      evidence: evidenceOf(entry.ratings ?? []),
    },
    generatedAt: report.generatedAt,
    models: report.models,
  }
}
