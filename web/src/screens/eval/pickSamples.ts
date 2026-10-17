import type { EvalItem } from '../../api/types.ts'

// The Sample page's curated clips (at most three, each with its audio on the server):
//   1. the lead demo answer with a mixed result: lifting-zone first, else any scripted demo answer;
//   2. a hard wrong answer: a negation, a contradiction or a fluent wrong answer;
//   3. an answer the check must abstain on: the wrong language, or silence.

const LEAD_TASK = 'lifting-zone'
const HARD = ['negation', 'fluent_wrong', 'contradicted']
const ABSTAIN = ['wrong_language', 'silence']

/** Some step is not "covered": the answer gets something wrong or leaves it out. */
const notAllCovered = (i: EvalItem) => Object.values(i.gold).some((v) => v !== 'covered')

/** Prefer the lead task, then the order of `patterns`. */
function best(items: EvalItem[], patterns: readonly string[]): EvalItem | undefined {
  const rank = (i: EvalItem) => (i.taskId === LEAD_TASK ? 0 : 100) + patterns.indexOf(i.pattern)
  return items.filter((i) => patterns.includes(i.pattern)).sort((a, b) => rank(a) - rank(b))[0]
}

export function pickSamples(items: readonly EvalItem[]): EvalItem[] {
  const playable = items.filter((i) => i.hasAudio === true)
  const demos = playable.filter((i) => i.pattern === 'demo')
  const lead =
    demos.find((i) => i.taskId === LEAD_TASK && notAllCovered(i)) ?? demos.find(notAllCovered) ?? demos.find((i) => i.taskId === LEAD_TASK) ?? demos[0]
  const picks = [lead, best(playable, HARD), best(playable, ABSTAIN)]
  return picks.filter((i, at): i is EvalItem => i !== undefined && picks.indexOf(i) === at)
}
