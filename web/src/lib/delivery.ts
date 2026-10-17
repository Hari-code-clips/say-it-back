import type { DeliveryCheck, DeliveryIssue, Round, Script } from '../api/types.ts'

// The delivery check of a Live round (docs/API.md, "v0.4 details"): the server compares what the voice said with the approved
// script and decides each segment's `ok`. The browser never applies a threshold of its own; it only says, in the supervisor's
// words, what went wrong and which steps that turned into "Ask again" (guard rule 8, flag `delivery_mismatch`).

/** Which part of the round a delivery segment is. `n` is the question's number in the round (1-based). */
export type SegmentRef =
  | { kind: 'instruction' }
  | { kind: 'question'; qid: string; n: number }
  | { kind: 'reply'; qid: string; n: number }
  | { kind: 'closing' }
  | { kind: 'other'; raw: string }

export function parseSegment(segment: string, questionIds: readonly string[]): SegmentRef {
  if (segment === 'instruction') return { kind: 'instruction' }
  if (segment === 'closing') return { kind: 'closing' }
  const reply = /^(.+)\.reply$/.exec(segment)
  const qid = reply ? (reply[1] ?? '') : segment
  const at = questionIds.indexOf(qid)
  if (at >= 0) return reply ? { kind: 'reply', qid, n: at + 1 } : { kind: 'question', qid, n: at + 1 }
  return { kind: 'other', raw: segment }
}

/** The segments the server found not `ok`, in script order. */
export const failedDeliveries = (delivery: readonly DeliveryCheck[] | undefined): DeliveryCheck[] => (delivery ?? []).filter((d) => d.ok === false)

/** The approved text of a segment; a reply after an answer has none. */
export function approvedText(script: Script, ref: SegmentRef): string | undefined {
  switch (ref.kind) {
    case 'instruction':
      return script.instruction
    case 'closing':
      return script.closing
    case 'question':
      return script.questions.find((q) => q.id === ref.qid)?.text
    default:
      return undefined
  }
}

/** What Live said for a segment: the check's `said`, else the relay's record of it. */
export function saidText(round: Pick<Round, 'live'>, d: DeliveryCheck): string | undefined {
  return d.said ?? round.live?.delivered[d.segment]
}

/**
 * Steps a failed segment affects (guard rule 8): the instruction affects every step in scope; a question the steps it checks;
 * the reply after question N (v0.4 review) the steps of question N and of every later question, since a hint can only help
 * the answers that come after it; the closing none.
 */
export function affectedSteps(ref: SegmentRef, round: Pick<Round, 'stepIds' | 'script'>): string[] {
  switch (ref.kind) {
    case 'instruction':
      return [...round.stepIds]
    case 'question':
      return round.script.questions.find((q) => q.id === ref.qid)?.stepIds ?? []
    case 'reply':
      return [...new Set(round.script.questions.slice(ref.n - 1).flatMap((q) => q.stepIds))]
    default:
      return []
  }
}

/** The reply after an earlier question caused it: the step's own question came after the hint. */
export const causedEarlier = (ref: SegmentRef, stepId: string, round: Pick<Round, 'script'>): boolean =>
  ref.kind === 'reply' && !(round.script.questions.find((q) => q.id === ref.qid)?.stepIds.includes(stepId) ?? false)

/** The failed segments behind a step's `delivery_mismatch`, in script order. */
export function deliveryCauses(stepId: string, round: Pick<Round, 'stepIds' | 'script' | 'delivery'>): { check: DeliveryCheck; ref: SegmentRef }[] {
  const ids = round.script.questions.map((q) => q.id)
  return failedDeliveries(round.delivery)
    .map((check) => ({ check, ref: parseSegment(check.segment, ids) }))
    .filter(({ ref }) => affectedSteps(ref, round).includes(stepId))
}

/** NFKC, case-folded, punctuation removed and whitespace collapsed: as the backend's `guards.normalise` (so "don't" is "dont"). */
export const normalise = (text: string): string =>
  text
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[\p{P}\p{S}]+/gu, '')
    .replace(/\s+/g, ' ')
    .trim()

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** How often the language's negation markers occur: whole words for `word` (English), substrings otherwise. */
export function countNegations(text: string, markers: readonly string[], match: 'word' | 'substring' = 'substring'): number {
  const norm = normalise(text)
  let n = 0
  for (const raw of markers) {
    const marker = normalise(raw)
    if (!marker) continue
    if (match === 'word') n += norm.match(new RegExp(`(?<![\\p{L}\\p{M}\\p{N}])${escapeRe(marker)}(?![\\p{L}\\p{M}\\p{N}])`, 'gu'))?.length ?? 0
    else for (let at = norm.indexOf(marker); at >= 0; at = norm.indexOf(marker, at + marker.length)) n++
  }
  return n
}

/**
 * Which way a `negation_changed` segment went, for the sentence the supervisor reads: fewer markers in what was said means a
 * "not" was left out. Wording only: whether the segment is `ok` is the server's decision, never this count's.
 */
export function negationChange(said: string | undefined, approved: string | undefined, markers: readonly string[] | undefined, match?: 'word' | 'substring'): 'dropped' | 'added' | 'changed' {
  if (said === undefined || approved === undefined || !markers?.length) return 'changed'
  const a = countNegations(said, markers, match)
  const b = countNegations(approved, markers, match)
  return a < b ? 'dropped' : a > b ? 'added' : 'changed'
}

/** The order the issues are explained in: the ones that change meaning first. */
export const ISSUE_ORDER: readonly DeliveryIssue[] = ['negation_changed', 'number_changed', 'reply_not_neutral', 'reply_too_long', 'not_spoken', 'wrong_script', 'low_similarity']

export const sortIssues = (issues: readonly DeliveryIssue[]): DeliveryIssue[] => [...issues].sort((a, b) => ISSUE_ORDER.indexOf(a) - ISSUE_ORDER.indexOf(b))
