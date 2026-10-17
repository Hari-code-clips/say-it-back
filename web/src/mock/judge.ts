import type { Briefing, DeliveryCheck, DeliveryIssue, Question, Rating, Round, Transcript } from '../api/types.ts'
import { normalise } from '../lib/delivery.ts'
import { publicCatalog } from './catalog.ts'
import { NEUTRAL_THANKS_TA, demoFor, demoRating, type DemoScript, type Said } from './demos.ts'
import { NEUTRAL_THANKS } from './script.ts'

// Canned "check": what the blind transcriber, the two judges and the guard rules would return, then guard rule 8 (v0.4) over the
// delivery check in Live mode. Demo pairs follow their scripts (demos.ts): the lifting lead's round 1 is s1 "Wrong", s2 "Missed",
// s3 "Ask again" because the voice said more than a thank-you after q2, s4 "Wrong"; a re-explain round covers what it asks.
// Other pairs follow the same shape. The clip itself is only inspected for length: a clip shorter than 0.8 s is reported as
// "no speech", as the real guard does.

const MIN_CLIP_BYTES = 44 + 16_000 * 2 * 0.8

export interface JudgeInput {
  briefing: Briefing
  round: Round
  clips: Record<string, Blob>
  mode: 'live' | 'turn'
  /** v0.4: question ids answered with the stored sample (meta.sampleAnswers). */
  sampleAnswers?: string[]
}

/** What the worker said to a question in this round of a demo. */
export function demoAnswer(demo: DemoScript, round: Pick<Round, 'n'>, q: Question): Said {
  return round.n === 1 ? (demo.answers[q.id] ?? { original: '', translation: '' }) : demo.reexplainAnswer(q)
}

function transcriptFor(b: Briefing, round: Round, q: Question, blob: Blob | undefined): Transcript | undefined {
  if (!blob) return undefined
  if (blob.size < MIN_CLIP_BYTES) return { questionId: q.id, original: '', detectedLang: 'none', translation: '', flags: ['no_speech'] }
  const demo = demoFor(b)
  if (demo) {
    const said = demoAnswer(demo, round, q)
    return { questionId: q.id, original: said.original, detectedLang: demo.workerLang, translation: said.translation, flags: [] }
  }
  const text = round.kind === 'initial' ? 'I would do the first thing only.' : 'I would do exactly that before starting.'
  return { questionId: q.id, original: text, detectedLang: b.workerLang, translation: text, flags: [] }
}

const rating = (stepId: string, verdict: Rating['verdict'], parts: Partial<Rating>): Rating => ({ stepId, verdict, reason: '', flags: [], ...parts })

function demoRatings(demo: DemoScript, round: Round, stepId: string): { final: Rating; a: Rating; b: Rating } {
  const scripted = round.n === 1 ? demo.round1[stepId] : undefined
  if (scripted) return demoRating(stepId, scripted)
  const step = demo.steps[stepId]
  const covered = rating(stepId, 'covered', {
    quote: step?.quote ?? '',
    quoteTranslation: step?.quoteEn ?? '',
    reason: 'The worker states the action and its condition in their own words.',
    confidence: 0.91,
  })
  return { final: covered, a: covered, b: covered }
}

function genericRating(round: Round, stepId: string, index: number): Rating {
  if (round.kind === 'initial' && index > 0) return rating(stepId, 'missed', { reason: 'The answer does not address this step.', confidence: 0.85 })
  return rating(stepId, 'covered', {
    quote: round.kind === 'initial' ? 'I would do the first thing' : 'I would do exactly that',
    quoteTranslation: round.kind === 'initial' ? 'I would do the first thing' : 'I would do exactly that',
    reason: 'The answer states the step.',
    confidence: 0.88,
  })
}

const REPLY_MAX_CHARS = 60

/**
 * The backend's reply rules (Deviations 2026-10-14, review fixes): longer than SIB_REPLY_MAX_CHARS after normalising, or a word of 3+
 * letters that is also in the approved instruction or questions and is not one of the language's catalog `thanksWords`.
 */
export function replyIssues(said: string, script: Round['script'], lang: string): DeliveryIssue[] {
  const words = (t: string) => normalise(t).split(' ').filter((w) => [...w].length >= 3)
  const thanks = new Set((publicCatalog.languages[lang as keyof typeof publicCatalog.languages]?.thanksWords ?? []).map(normalise))
  const scriptWords = new Set(words([script.instruction, ...script.questions.map((q) => q.text)].join(' ')))
  const issues: DeliveryIssue[] = []
  if ([...normalise(said)].length > REPLY_MAX_CHARS) issues.push('reply_too_long')
  if (words(said).some((w) => scriptWords.has(w) && !thanks.has(w))) issues.push('reply_not_neutral')
  return issues
}

/** Live mode: each approved segment against what the voice said, as the backend's delivery check reports it (v0.4). */
function deliveryFor(b: Briefing, round: Round): { delivery: DeliveryCheck[]; delivered: Record<string, string> } {
  const demo = demoFor(b)
  const off = round.n === 1 ? (demo?.round1Delivery ?? {}) : {}
  // The mock Live voice's own words after an answer (liveSocket.ts), so Bengali and Odia replies read in their language (16 Oct breadth).
  const thanks = b.workerLang === 'ta' ? NEUTRAL_THANKS_TA : (NEUTRAL_THANKS[b.workerLang] ?? 'Thank you.')
  const delivery: DeliveryCheck[] = []
  const delivered: Record<string, string> = {}
  const add = (segment: string, approved: string | undefined, similarity: number) => {
    const wrong = off[segment]
    const said = wrong?.said ?? approved ?? thanks
    delivered[segment] = said
    // A reply has no approved text: its issues come from what was said, by the backend's rules.
    const issues = approved === undefined ? replyIssues(said, round.script, b.workerLang) : (wrong?.issues ?? [])
    delivery.push({
      segment,
      similarity: approved === undefined ? 1 : wrong ? 0.71 : similarity,
      scriptOk: true,
      ok: issues.length === 0,
      issues,
      ...(approved === undefined || wrong ? { said } : {}),
    })
  }
  add('instruction', round.script.instruction, 0.98)
  for (const q of round.script.questions) {
    add(q.id, q.text, 0.97)
    add(`${q.id}.reply`, undefined, 1)
  }
  add('closing', round.script.closing, 0.99)
  return { delivery, delivered }
}

/**
 * Guard rule 8: a segment that is not ok turns the covered steps it delivers or asks about into "Ask again" (`delivery_mismatch`):
 * the instruction affects every step in scope, a question the steps it checks, the reply after question N the steps of question
 * N and of every later question (v0.4 review), the closing none.
 */
export function applyDeliveryRule(round: Pick<Round, 'stepIds' | 'script'>, ratings: Rating[], delivery: readonly DeliveryCheck[]): Rating[] {
  const hit = new Set<string>()
  const qs = round.script.questions
  for (const d of delivery) {
    if (d.ok) continue
    if (d.segment === 'instruction') round.stepIds.forEach((s) => hit.add(s))
    const reply = d.segment.endsWith('.reply')
    const at = qs.findIndex((q) => q.id === d.segment.replace(/\.reply$/, ''))
    if (at >= 0) for (const q of reply ? qs.slice(at) : [qs[at]!]) q.stepIds.forEach((s) => hit.add(s))
  }
  return ratings.map((r) => (r.verdict === 'covered' && hit.has(r.stepId) ? { ...r, verdict: 'unclear', flags: [...r.flags, 'delivery_mismatch'] } : r))
}

/** Fills the round the way endpoint 13 does: transcripts, both passes, guarded final ratings, the delivery check. */
export function judgeRound({ briefing: b, round, clips, mode, sampleAnswers = [] }: JudgeInput): Round {
  const demo = demoFor(b)
  const transcripts = round.script.questions.map((q) => transcriptFor(b, round, q, clips[q.id])).filter((t): t is Transcript => t !== undefined)

  const passA: Rating[] = []
  const passB: Rating[] = []
  let ratings: Rating[] = []
  round.stepIds.forEach((stepId, i) => {
    const asking = round.script.questions.filter((q) => q.stepIds.includes(stepId))
    const heard = asking.map((q) => transcripts.find((t) => t.questionId === q.id)).filter((t): t is Transcript => t !== undefined)
    if (asking.length === 0 || heard.length === 0) {
      ratings.push(rating(stepId, 'unclear', { reason: 'No answer was recorded for a question about this step.', flags: ['not_asked'] }))
      return
    }
    if (heard.every((t) => !t.original)) {
      ratings.push(rating(stepId, 'unclear', { reason: 'No speech was heard in the answer.', flags: ['no_speech'] }))
      return
    }
    if (demo && demo.steps[stepId]) {
      const r = demoRatings(demo, round, stepId)
      ratings.push(r.final)
      passA.push(r.a)
      passB.push(r.b)
      return
    }
    const final = genericRating(round, stepId, i)
    ratings.push(final)
    passA.push({ ...final, flags: [] })
    passB.push({ ...final, flags: [] })
  })

  const now = new Date().toISOString()
  const live = mode === 'live' ? deliveryFor(b, round) : undefined
  if (live) ratings = applyDeliveryRule(round, ratings, live.delivery)
  const heardMap: Record<string, string> = {}
  for (const t of transcripts) heardMap[t.questionId] = t.original
  const askedIds = new Set(round.script.questions.map((q) => q.id))

  return {
    ...round,
    mode,
    transcripts,
    passA,
    passB,
    ratings,
    delivery: live?.delivery ?? [],
    live: live ? { model: 'gemini-3.8-live (mock)', startedAt: round.createdAt, endedAt: now, delivered: live.delivered, heard: heardMap } : undefined,
    nextAction: ratings.every((r) => r.verdict === 'covered') ? 'decide' : 'reexplain',
    modelIds: {
      ...round.modelIds,
      transcribe: 'gemini-3.8-flash (mock)',
      judge_a: 'gemini-3.8-flash (mock)',
      judge_b: 'gemini-3.1-flash-lite (mock)',
    },
    timingsMs: { ...round.timingsMs, transcribe: 1800, judge_a: 2300, judge_b: 1400, check_total: 4100 },
    ...(sampleAnswers.length ? { sampleAnswers: sampleAnswers.filter((q) => askedIds.has(q)) } : {}),
    judgedAt: now,
  }
}
