import type { DemoAnswer } from '../../api/types.ts'

/** A question of the round's script, as the pairing reads it. */
export interface RoundQuestion {
  id: string
  stepIds: readonly string[]
}

/** A question of the round and the stored answer it gets. */
export interface SamplePair {
  qid: string
  item: DemoAnswer
}

/**
 * Endpoint 24's stored sample answers for round `n` of this task and worker language, in the server's order (a round's answers
 * in reference question order): round 1 uses the demo script's first round, round 2 and every later round its second.
 */
export function samplesFor(items: readonly DemoAnswer[] | undefined, taskId: string, workerLang: string, n: number): DemoAnswer[] {
  const want = n === 1 ? 1 : 2
  return (items ?? []).filter((d) => d.taskId === taskId && d.workerLang === workerLang && d.round === want)
}

const sharedSteps = (q: RoundQuestion, d: DemoAnswer): number => q.stepIds.filter((s) => d.stepIds?.includes(s)).length

interface Pairing {
  score: number
  picks: (DemoAnswer | undefined)[]
}

/** The pairing of `questions` (in order) with the answers still `free` that shares the most steps in all. */
function bestPairing(questions: readonly RoundQuestion[], free: readonly DemoAnswer[]): Pairing {
  const [q, ...rest] = questions
  if (!q) return { score: 0, picks: [] }
  let best: Pairing = { score: -1, picks: [] }
  // Answers in list order, then none: only a strictly better total replaces the best, so a tie goes to the answer listed first.
  for (const d of [...free, undefined]) {
    const gain = d ? sharedSteps(q, d) : 0
    if (d && gain === 0) continue // an answer goes only to a question it shares a step with
    const tail = bestPairing(rest, free.filter((x) => x !== d))
    if (gain + tail.score > best.score) best = { score: gain + tail.score, picks: [d, ...tail.picks] }
  }
  return best
}

/**
 * Which stored answer each question of the round gets (docs/API.md, Deviations 2026-10-16): each answer at most once, only to a
 * question it shares a step with, so that the most steps are answered in all; on a tie the earlier question gets the answer
 * listed first. A question left without one is answered by the worker's own voice. An older server lists no `questionId`: its
 * one answer goes to the round's first question, as before.
 */
export function pairSamples(questions: readonly RoundQuestion[], samples: readonly DemoAnswer[]): SamplePair[] {
  const [first] = questions
  const [legacy] = samples
  if (samples.every((d) => d.questionId === undefined)) return first && legacy ? [{ qid: first.id, item: legacy }] : []
  const { picks } = bestPairing(questions, samples)
  return questions.flatMap((q, i) => {
    const item = picks[i]
    return item ? [{ qid: q.id, item }] : []
  })
}

/**
 * The question a sample answer was tapped for is still the one whose window is open (v0.4 review): a clip that arrives after
 * that window closed is dropped, never played into the next question's window.
 */
export const sampleStillWanted = (tappedQid: string | null, now: { kind: string; qid?: string }): boolean =>
  tappedQid !== null && now.kind === 'listening' && now.qid === tappedQid

/**
 * What the supervisor's "Use stored sample answers for this round" can honestly promise (docs/API.md, "Sample answers"): which
 * questions of the round get a stored answer (all of them, for the two demos on a server from 16 Oct on), and that the worker
 * answers any other question by voice.
 */
export type SampleChoice =
  | { kind: 'loading' }
  | { kind: 'none' }
  | {
      kind: 'available'
      /** The questions that get a stored answer, in question order, each with its answer. */
      pairs: SamplePair[]
      /** The same questions as the numbers the supervisor reads (1-based). */
      numbers: number[]
      /** Every question of the round gets one, and together they speak to every step it asks about: nobody has to speak. */
      all: boolean
      /** Every question gets one, but some step it asks about is in none of them, so that step may need another round. */
      stepsLeft: boolean
    }

/**
 * A step the round asks about that no paired answer speaks to (review of 16 Oct: a question about s3 and s4 can only get the
 * s3 answer). Known only when the server lists `stepIds`; an older server's answer is taken at its word.
 */
function stepLeftOut(questions: readonly RoundQuestion[], pairs: readonly SamplePair[]): boolean {
  if (pairs.some((p) => p.item.stepIds === undefined)) return false
  const answered = new Set(pairs.flatMap((p) => p.item.stepIds ?? []))
  return questions.some((q) => q.stepIds.some((s) => !answered.has(s)))
}

/**
 * `items` is endpoint 24's list (undefined while it loads, or when it failed); `loaded` says the request finished, so a failed
 * request reads as "none" rather than "loading" forever.
 */
export function sampleChoice(
  items: readonly DemoAnswer[] | undefined,
  loaded: boolean,
  taskId: string,
  workerLang: string,
  n: number,
  questions: readonly RoundQuestion[],
): SampleChoice {
  if (!loaded) return { kind: 'loading' }
  const pairs = pairSamples(questions, samplesFor(items, taskId, workerLang, n))
  if (pairs.length === 0) return { kind: 'none' }
  const numbers = pairs.map((p) => questions.findIndex((q) => q.id === p.qid) + 1)
  const everyQuestion = pairs.length === questions.length
  const left = everyQuestion && stepLeftOut(questions, pairs)
  return { kind: 'available', pairs, numbers, all: everyQuestion && !left, stepsLeft: left }
}

/**
 * The questions whose answer window gets a stored answer, given the supervisor's choice for this round: none unless it was
 * chosen and the server has a clip. Every other window, and every round without a choice, is the worker's own voice.
 */
export const sampleQids = (chosen: boolean, choice: SampleChoice): readonly string[] =>
  chosen && choice.kind === 'available' ? choice.pairs.map((p) => p.qid) : []

/**
 * The clip of each paired question, fetched once: `load(qid)` gives the same promise every time, a failed fetch is tried again
 * on the next call, and a question with no stored answer gets undefined (its window is the worker's own voice).
 */
export function sampleLoader(pairs: readonly SamplePair[], fetchClip: (item: DemoAnswer) => Promise<Blob>): (qid: string) => Promise<Blob> | undefined {
  const fetched = new Map<string, Promise<Blob>>()
  return (qid) => {
    const item = pairs.find((p) => p.qid === qid)?.item
    if (!item) return undefined
    const known = fetched.get(qid)
    if (known) return known
    const clip = fetchClip(item)
    fetched.set(qid, clip)
    clip.catch(() => fetched.get(qid) === clip && fetched.delete(qid))
    return clip
  }
}

/** The stored sample is played the moment an answer window of one of those questions opens (and at no other moment). */
export const shouldAutoPlay = (qids: readonly string[], phase: { kind: string; qid?: string }): boolean =>
  phase.kind === 'listening' && phase.qid !== undefined && qids.includes(phase.qid)
