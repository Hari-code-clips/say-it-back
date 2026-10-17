import type { CatalogLanguage, DeliveryCheck, DeliveryIssue, Round } from '../../api/types.ts'
import type { StringKey, Translate } from '../../i18n/index.tsx'
import { approvedText, negationChange, parseSegment, saidText, sortIssues, type SegmentRef } from '../../lib/delivery.ts'

// The delivery check's findings in the supervisor's words (no React here, so it is unit-tested).

/** "the instruction", "question 2", "the closing line": the part of the round, in the supervisor's words. */
export function segmentName(t: Translate, ref: SegmentRef): string {
  switch (ref.kind) {
    case 'instruction':
      return t('delivery.instruction')
    case 'closing':
      return t('delivery.closing')
    case 'question':
    case 'reply':
      return t('delivery.question', { n: ref.n })
    case 'other':
      return ref.raw
  }
}

const ISSUE_KEY: Record<Exclude<DeliveryIssue, 'negation_changed' | 'reply_too_long' | 'reply_not_neutral'>, StringKey> = {
  not_spoken: 'delivery.not_spoken',
  wrong_script: 'delivery.wrong_script',
  low_similarity: 'delivery.low_similarity',
  number_changed: 'delivery.number_changed',
}

/**
 * One plain sentence per issue the server found in a segment, e.g. "The voice left out a "not" in question 1." or "The voice
 * said more than a thank-you after question 2." Which way a negation went is read from the texts; that it changed is the server's.
 */
export function issueSentences(t: Translate, check: DeliveryCheck, round: Pick<Round, 'script' | 'live'>, language?: CatalogLanguage): string[] {
  const ref = parseSegment(check.segment, round.script.questions.map((q) => q.id))
  const what = segmentName(t, ref)
  const issues = sortIssues(check.issues ?? [])
  // Not ok and no reason recorded (a check stored before v0.4 reads that way): say only that it did not match.
  if (issues.length === 0) return [t('delivery.mismatch', { what })]
  return issues.map((issue) => {
    const n = ref.kind === 'reply' || ref.kind === 'question' ? ref.n : '?'
    if (issue === 'reply_too_long') return t('delivery.reply_too_long', { n })
    if (issue === 'reply_not_neutral') return t('delivery.reply_not_neutral', { n })
    if (issue === 'negation_changed') {
      const way = negationChange(saidText(round, check), approvedText(round.script, ref), language?.negationMarkers, language?.match)
      return t(way === 'dropped' ? 'delivery.negation_dropped' : way === 'added' ? 'delivery.negation_added' : 'delivery.negation_changed', { what })
    }
    // An issue code this build does not know yet still reads as the words having differed.
    return t((ISSUE_KEY as Partial<Record<string, StringKey>>)[issue] ?? 'delivery.low_similarity', { what })
  })
}

