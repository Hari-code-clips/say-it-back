import type { Briefing, Conflict, Question, Script, Step } from '../api/types.ts'
import { splitSentences } from '../lib/sentences.ts'
import { langNameEn, rawTask } from './catalog.ts'
import { demoFor, type DemoScript } from './demos.ts'
import { longInstruction } from './longScripts.ts'

// Canned "model" output: step extraction and script writing. The demo pairs (demos.ts: the lifting lead and the panel, English
// supervisor, Tamil worker) are written out in full; every other pair is derived from the catalog's reference steps and
// labelled as mock text.

const THANKS: Record<string, string> = {
  ta: 'நன்றி. உங்கள் சூப்பர்வைசருக்காகக் காத்திருங்கள்.',
  hi: 'धन्यवाद। कृपया अपने सुपरवाइज़र का इंतज़ार करें।',
  bn: 'ধন্যবাদ। অনুগ্রহ করে আপনার সুপারভাইজারের জন্য অপেক্ষা করুন।',
  zh: '谢谢。请等待您的主管。',
  my: 'ကျေးဇူးတင်ပါတယ်။ ကျေးဇူးပြု၍ သင့်ကြီးကြပ်သူကို စောင့်ပါ။',
  or: 'ଧନ୍ୟବାଦ। ଦୟାକରି ଆପଣଙ୍କ ସୁପରଭାଇଜରଙ୍କୁ ଅପେକ୍ଷା କରନ୍ତୁ।',
  te: 'ధన్యవాదాలు. దయచేసి మీ సూపర్‌వైజర్ కోసం వేచి ఉండండి.', // DRAFT, 17 Oct (build-notes/37-telugu-consent.md)
  en: 'Thank you. Please wait for your supervisor.',
}
export const closingFor = (b: Briefing): string => THANKS[b.workerLang] ?? THANKS.en ?? ''

/** Short, neutral thanks after an answer (what the briefer says between questions). */
export const NEUTRAL_THANKS: Record<string, string> = {
  ta: 'நன்றி.',
  hi: 'धन्यवाद।',
  bn: 'ধন্যবাদ।',
  zh: '谢谢。',
  my: 'ကျေးဇူးတင်ပါတယ်။',
  or: 'ଧନ୍ୟବାଦ।',
  te: 'ధన్యవాదాలు.',
  en: 'Thank you.',
}

const words = (s: string): Set<string> => new Set(s.toLowerCase().match(/[a-z]{4,}/g) ?? [])

/** The SOP line that shares the most words with a step (a verbatim line, as the contract requires). */
function bestSopLine(sopText: string, stepText: string): string | undefined {
  const lines = sopText.split('\n').map((l) => l.replace(/^\d+\.\s*/, '').trim()).filter((l) => l && !l.startsWith('Hazards'))
  const target = words(stepText)
  let best: { line: string; score: number } | undefined
  for (const line of lines) {
    const score = [...words(line)].filter((w) => target.has(w)).length
    if (!best || score > best.score) best = { line, score }
  }
  return best?.line
}

export interface Proposal {
  steps: Step[]
  conflicts: Conflict[]
}

/** What the extractor agent would return for this briefing. */
export function proposeSteps(b: Briefing): Proposal {
  const task = rawTask(b.taskId)
  const conflicts: Conflict[] = []
  if (task) {
    const steps = task.referenceSteps.map((s) => ({
      ...s,
      speakable: true,
      ...(s.source !== 'instruction' ? { sopQuote: bestSopLine(b.sop.text, s.text) } : {}),
    }))
    // A deterministic conflict to show the red state: hot work with "5 metres" against the SOP's 10.
    if (b.taskId === 'hot-work' && /\b(5|five)\s*(m\b|metre|meter)/i.test(b.instruction)) {
      conflicts.push({
        stepId: 's1',
        message: `Your instruction says 5 metres, but ${b.sop.id} requires combustible material to be cleared or covered within 10 metres.`,
      })
    }
    return { steps, conflicts }
  }
  // Custom SOP: one step per numbered line, at most six.
  const lines = b.sop.text
    .split('\n')
    .map((l) => l.replace(/^\s*\d+[.)]\s*/, '').trim())
    .filter((l) => l.length > 8 && !/^hazards?/i.test(l))
    .slice(0, 6)
  const said = words(b.instruction)
  const steps: Step[] = lines.map((line, i) => ({
    id: `s${i + 1}`,
    text: line,
    hazard: 'See the SOP for the hazard this step controls.',
    essential: [line],
    source: [...words(line)].filter((w) => said.has(w)).length >= 2 ? 'both' : 'sop',
    sopQuote: line,
    speakable: !/\b(inspect|visual|observe)/i.test(line),
  }))
  return { steps, conflicts }
}

/** Worker-language text for pairs without a hand-written script. Clearly marked as mock. */
const mockText = (b: Briefing, text: string): string => (b.workerLang === 'en' ? text : `[${langNameEn(b.workerLang)}, mock] ${text}`)

/** The backend writes one sentence per line; stepMap indexes the lines (docs/API.md, Deviations). */
const LINE = '\n'

function demoScript(b: Briefing, demo: DemoScript, stepIds: string[], firstQuestionNumber: number): Script {
  const questions =
    firstQuestionNumber === 1
      ? // Only steps still in scope (the supervisor may have removed one).
        demo.questions.map((q) => ({ ...q, stepIds: q.stepIds.filter((id) => stepIds.includes(id)) })).filter((q) => q.stepIds.length > 0)
      : demo.reexplain(stepIds, firstQuestionNumber)
  return {
    instruction: stepIds.map((id) => demo.steps[id]?.sentence ?? '').join(LINE),
    instructionBackTranslation: stepIds.map((id) => demo.steps[id]?.sentenceEn ?? '').join(LINE),
    questions,
    stepMap: Object.fromEntries(stepIds.map((id, i) => [id, [i]])),
    closing: closingFor(b),
  }
}

/** Script for a round: round 1 covers all confirmed steps; re-explain rounds cover the open ones. */
export function makeScript(b: Briefing, stepIds: string[], firstQuestionNumber: number): Script {
  const script = baseScript(b, stepIds, firstQuestionNumber)
  // QA flag `sib.mock.longScript`: a long read-out, so the worker screen's caption can be seen overflowing (./longScripts.ts).
  const long = longInstruction(b.workerLang)
  if (!long) return script
  return { ...script, instruction: long.join(LINE), instructionBackTranslation: (longInstruction('en') ?? long).join(LINE) }
}

function baseScript(b: Briefing, stepIds: string[], firstQuestionNumber: number): Script {
  const demo = demoFor(b)
  if (demo && stepIds.every((id) => demo.steps[id])) return demoScript(b, demo, stepIds, firstQuestionNumber)

  const inScope = b.steps.filter((s) => stepIds.includes(s.id))
  const sentences = firstQuestionNumber === 1 && splitSentences(b.instruction).length >= inScope.length ? splitSentences(b.instruction) : inScope.map((s) => `${s.text}.`)
  const task = rawTask(b.taskId)
  const refQs = firstQuestionNumber === 1 && task ? task.referenceQuestions : []
  const questions: Question[] =
    refQs.length > 0
      ? refQs.map((q) => ({ id: q.id, text: mockText(b, q.text), backTranslation: q.text, stepIds: q.stepIds.filter((id) => stepIds.includes(id)) }))
      : inScope.slice(0, 2).map((s, i) => ({
          id: `q${firstQuestionNumber + i}`,
          text: mockText(b, `What will you do about this: ${s.text}?`),
          backTranslation: `What will you do about this: ${s.text}?`,
          stepIds: [s.id],
        }))
  // Every step must be delivered and asked (the backend checks this in code): spread them over the sentences.
  const stepMap = Object.fromEntries(inScope.map((s, i) => [s.id, [Math.min(i, sentences.length - 1)]]))
  const covered = new Set(questions.flatMap((q) => q.stepIds))
  const last = questions[questions.length - 1]
  if (last) for (const s of inScope) if (!covered.has(s.id)) last.stepIds.push(s.id)
  return {
    instruction: sentences.map((s) => mockText(b, s)).join(LINE),
    instructionBackTranslation: sentences.join(LINE),
    questions,
    stepMap,
    closing: closingFor(b),
  }
}
