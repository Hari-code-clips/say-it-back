import type { Briefing, Question, Rating, Round, Transcript, Verdict } from '../api/types.ts'
import { LEAD, LEAD_ROUND1_ANSWERS, isLeadDemo } from './script.ts'

// Canned "check": what the blind transcriber, the two judges and the guard rules would return.
// Lead demo: round 1 -> s1 covered, s2/s3 missed (s3 with the judges disagreeing); re-explain
// rounds -> covered. Other pairs follow the same shape. The clip itself is only inspected for
// length: a clip shorter than 0.8 s is reported as "no speech", as the real guard does.

const MIN_CLIP_BYTES = 44 + 16_000 * 2 * 0.8

export interface JudgeInput {
  briefing: Briefing
  round: Round
  clips: Record<string, Blob>
  mode: 'live' | 'turn'
}

function transcriptFor(b: Briefing, round: Round, q: Question, blob: Blob | undefined): Transcript | undefined {
  if (!blob) return undefined
  if (blob.size < MIN_CLIP_BYTES) return { questionId: q.id, original: '', detectedLang: 'none', translation: '', flags: ['no_speech'] }
  const step = q.stepIds[0] ? LEAD[q.stepIds[0]] : undefined
  if (isLeadDemo(b)) {
    const first = round.n === 1 ? LEAD_ROUND1_ANSWERS[q.id] : undefined
    if (first) return { questionId: q.id, original: first.original, detectedLang: 'ta', translation: first.translation, flags: [] }
    if (step) return { questionId: q.id, original: step.answer, detectedLang: 'ta', translation: step.answerEn, flags: [] }
  }
  const text = round.kind === 'initial' ? 'I would do the first thing only.' : 'I would do exactly that before starting.'
  return { questionId: q.id, original: text, detectedLang: b.workerLang, translation: text, flags: [] }
}

function rating(stepId: string, verdict: Verdict, parts: Partial<Rating>): Rating {
  return { stepId, verdict, reason: '', flags: [], ...parts }
}

function leadRating(round: Round, stepId: string): Rating {
  const l = LEAD[stepId]
  if (round.n === 1) {
    if (stepId === 's1') {
      return rating(stepId, 'covered', {
        quote: 'ஆஃப் பண்ணிட்டு',
        quoteTranslation: 'switch it off',
        reason: 'The worker says they will switch it off, which covers the step.',
        confidence: 0.86,
      })
    }
    if (stepId === 's2') return rating(stepId, 'missed', { reason: 'The answer does not mention locking or tagging the breaker.', confidence: 0.9 })
    return rating(stepId, 'missed', { reason: 'The answer does not mention testing that the circuit is dead before touching it.', confidence: 0.82, flags: ['passes_disagreed'] })
  }
  return rating(stepId, 'covered', {
    quote: l?.quote ?? '',
    quoteTranslation: l?.quoteEn ?? '',
    reason: 'The worker states the action and its condition in their own words.',
    confidence: 0.91,
  })
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

/** Fills the round the way endpoint 13 does: transcripts, both passes, guarded final ratings. */
export function judgeRound({ briefing: b, round, clips, mode }: JudgeInput): Round {
  const transcripts = round.script.questions.map((q) => transcriptFor(b, round, q, clips[q.id])).filter((t): t is Transcript => t !== undefined)

  const passA: Rating[] = []
  const passB: Rating[] = []
  const ratings: Rating[] = []
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
    const final = isLeadDemo(b) && LEAD[stepId] ? leadRating(round, stepId) : genericRating(round, stepId, i)
    ratings.push(final)
    passA.push(final.flags.includes('passes_disagreed') ? { ...final, verdict: 'unclear', flags: [] } : { ...final, flags: [] })
    passB.push({ ...final, flags: [] })
  })

  const allCovered = ratings.every((r) => r.verdict === 'covered')
  const now = new Date().toISOString()
  const delivered: Record<string, string> = { instruction: round.script.instruction, closing: round.script.closing }
  const heardMap: Record<string, string> = {}
  for (const q of round.script.questions) delivered[q.id] = q.text
  for (const t of transcripts) heardMap[t.questionId] = t.original

  return {
    ...round,
    mode,
    transcripts,
    passA,
    passB,
    ratings,
    delivery:
      mode === 'live'
        ? [
            { segment: 'instruction', similarity: 0.98, scriptOk: true },
            ...round.script.questions.map((q) => ({ segment: q.id, similarity: 0.97, scriptOk: true })),
            { segment: 'closing', similarity: 0.99, scriptOk: true },
          ]
        : [],
    live: mode === 'live' ? { model: 'gemini-3.8-live (mock)', startedAt: round.createdAt, endedAt: now, delivered, heard: heardMap } : undefined,
    nextAction: allCovered ? 'decide' : 'reexplain',
    modelIds: { transcribe: 'gemini-3.8-flash (mock)', judgeA: 'gemini-3.8-flash (mock)', judgeB: 'gemini-3.8-flash (mock)', guard: 'code' },
    timingsMs: { transcribe: 1800, judgeA: 2300, judgeB: 1900, guard: 4 },
    judgedAt: now,
  }
}
