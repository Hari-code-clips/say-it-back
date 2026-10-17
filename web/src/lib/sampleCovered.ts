import type { Briefing, Step } from '../api/types.ts'
import { normalise } from './delivery.ts'

// v0.4 review (docs/API.md, Deviations "v0.4 review fixes"): a stored synthetic sample answer is never the worker's. A step
// whose latest covering rating came only from questions answered with a sample keeps its verdict, is tagged, and counts as open
// when the supervisor decides: Go needs a reason, as for any open step. Re-explain scope is unchanged (verdicts only).

type Source = Pick<Briefing, 'rounds' | 'latestVerdicts'> & Partial<Pick<Briefing, 'sampleCoveredStepIds'>>

/**
 * The rule, from the rounds: for each step whose latest verdict is covered, the latest round that rated it; if every question
 * of that round that checks the step was answered with a stored sample (`round.sampleAnswers`), the cover is the sample's.
 */
export function deriveSampleCovered(b: Pick<Briefing, 'rounds' | 'latestVerdicts'>): string[] {
  const out: string[] = []
  for (const [stepId, verdict] of Object.entries(b.latestVerdicts)) {
    if (verdict !== 'covered') continue
    const round = [...b.rounds].reverse().find((r) => r.ratings.some((x) => x.stepId === stepId))
    if (!round) continue
    const asking = round.script.questions.filter((q) => q.stepIds.includes(stepId))
    const samples = new Set(round.sampleAnswers ?? [])
    if (asking.length > 0 && asking.every((q) => samples.has(q.id))) out.push(stepId)
  }
  return out
}

// The server's quote matching (guards.py `normalise`, `quote_fragments`, `UNCLEAR_SPAN`, `ELLIPSIS`): NFKC, case-folded, no
// punctuation, symbols or format marks (Tamil's joiners), whitespace collapsed; a quote's phrases are split at an ellipsis or
// an [unclear] mark, and a transcript's spans at its [unclear] marks (a phrase never matches across one).
const UNCLEAR = /\[\s*unclear\b[^\]]*\]/giu
const asServer = (text: string): string => normalise(text.replace(/\p{Cf}/gu, ''))
const fragments = (quote: string): string[] =>
  quote.normalize('NFKC').split(UNCLEAR).flatMap((s) => s.split(/\.{3}|…|\[\.\.\.\]/u)).map(asServer).filter(Boolean)
const spans = (transcript: string): string[] => transcript.normalize('NFKC').split(UNCLEAR).map(asServer)

/**
 * Whose words a rating quotes: true when the quote comes from an answer played from a stored sample, so the result must not
 * say "The worker said" above it (16 Oct: every question of a demo round can now be a sample). The quote is verbatim from one
 * transcript (guard rule 2), matched as the server matches it; that transcript's question decides. With no transcript holding
 * it, the quote is the sample's only when every question asking about the step was a sample.
 */
export function quoteFromSample(
  round: Pick<Briefing['rounds'][number], 'transcripts' | 'sampleAnswers' | 'script'>,
  stepId: string,
  quote: string | undefined,
): boolean {
  const samples = new Set(round.sampleAnswers ?? [])
  if (!quote || samples.size === 0) return false
  const parts = fragments(quote)
  const holder = round.transcripts.find((t) => {
    const own = spans(t.original)
    return parts.length > 0 && parts.every((p) => own.some((s) => s.includes(p)))
  })
  if (holder) return samples.has(holder.questionId)
  const asking = round.script.questions.filter((q) => q.stepIds.includes(stepId))
  return asking.length > 0 && asking.every((q) => samples.has(q.id))
}

/** The server's derived list when it sends one, else the same rule applied here (an older server, or a record from before). */
export const sampleCoveredIds = (b: Source): string[] => b.sampleCoveredStepIds ?? deriveSampleCovered(b)

/** Steps the decision treats as open: not covered, or covered only by a stored sample. In the briefing's step order. */
export function decisionOpenSteps(b: Source & Pick<Briefing, 'steps'>): Step[] {
  const sample = new Set(sampleCoveredIds(b))
  return b.steps.filter((s) => b.latestVerdicts[s.id] !== 'covered' || sample.has(s.id))
}

/** 2026-10-17, an in-person check (the worker declined the latest round): no model checked that round, so its whole scope is open too. */
export function inPersonOpenSteps(b: Source & Pick<Briefing, 'steps'>): Step[] {
  const open = new Set([...decisionOpenSteps(b).map((s) => s.id), ...(b.rounds[b.rounds.length - 1]?.stepIds ?? [])])
  return b.steps.filter((s) => open.has(s.id))
}
