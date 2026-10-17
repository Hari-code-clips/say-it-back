// The hand-written demo pairs of the mock (VITE_API_MOCK=1), following the catalog's demo scripts:
//   - sg-lead  (lifting-zone, English -> Tamil): round 1's answer to q1 is the catalog's hard case, "I'll stand under the load
//     and hold it straight with my hand": s1 contradicted and s2 missed; to q2 "only the signalman" (s3 covered); to q3 "I'll
//     grab it with my hand" (s4 contradicted). In Live mode the voice says more than a thank-you after q2, so s3 is "Ask again"
//     (guard rule 8). Round 2's answers cover every step it asks about.
//   - sg-panel (panel-isolation, English -> Tamil): the earlier lead, kept as it was.
//   - sg-hot-work (hot-work, English -> Bengali) and chennai-trench (trench-entry, Tamil -> Odia), 16 Oct breadth
//     (build-notes/34-breadth.md): the catalog's answers to q1 and q2 in both rounds. Round 1: hot work s3 Wrong (leaves as soon as
//     the cutting ends), trench s1 Missed (the SOP-only shoring); round 2 covers every step.
//   - 17 Oct demo suites (build-notes/37-domain-suites.md), the same shape in four more work domains: sg-hydrojet (hydro-jetting,
//     English -> Bengali; round 1 s2 Wrong, the trigger tied down), sg-steam-line (steam-line-break, English -> Tamil; s1 Wrong, no
//     lock of their own), chennai-press (press-lockout, Tamil -> Hindi; s4 Wrong, the stuck piece pulled out by hand) and
//     chennai-tower (telecom-tower, Tamil -> Telugu; s2 Missed, the SOP-only antenna switch-off). Round 2 covers every step.
// Every other pair is derived from the catalog and labelled as mock text (script.ts).
//
// DRAFT: every Tamil line here is machine-written and NEEDS NATIVE-SPEAKER REVIEW. The scripted answers of sg-lead are the
// catalog's own (backend/sayitback/data/catalog.json, demoScripts: each round's answer and, since 16 Oct, its followUps), so a
// stored sample answer (endpoint 24) says what the mock's worker says.
// The script sentences follow the prompt's rule of 16 Oct (PROMPT_VERSION .12, build-notes/27): the word a worker on site says, never an
// English technical term spelled letter for letter in Tamil script (the tag line is "the rope tied to the load"). A worker's ANSWER keeps
// the words workers really say (டேக் லைன், பிரேக்கர், லாக்): the judge accepts them, and the catalog's scripted answers are not changed.
import type { Briefing, DeliveryIssue, Lang, Question, Rating, Verdict } from '../api/types.ts'
import { rawDemoScript, roundAnswers } from './catalog.ts'

export interface DemoStep {
  /** The instruction sentence that delivers the step (worker language) and its back-translation. */
  sentence: string
  sentenceEn: string
  /** The words that cover the step in a later round, verbatim in that round's answer, and their translation. */
  quote: string
  quoteEn: string
}

export interface Said {
  original: string
  translation: string
}

export interface DemoRating {
  verdict: Verdict
  quote?: string
  quoteTranslation?: string
  reason: string
  confidence: number
  /** Judge B's verdict when it differs (guard rule 1: see `rule1Verdict`; a split is flagged). */
  judgeB?: Verdict
  /** Judge B's own sentence, when it says something other than `reason`. */
  judgeBReason?: string
}

export interface DemoScript {
  taskId: string
  workerLang: Lang
  steps: Record<string, DemoStep>
  /** Round 1's questions, and what the worker says to each. */
  questions: Question[]
  answers: Record<string, Said>
  /** Round 1's final verdicts from both judges and the guard, before the delivery rule. */
  round1: Record<string, DemoRating>
  /** Round 1 in Live mode: what the voice said in place of the approved text, and why that is not ok. */
  round1Delivery: Record<string, { said: string; issues: DeliveryIssue[] }>
  /** Questions for a re-explain round over `open`, numbered from `first`. */
  reexplain: (open: string[], first: number) => Question[]
  /** What the worker says in a re-explain round. */
  reexplainAnswer: (q: Question) => Said
  /** The worker's spoken problem report (endpoint 21). */
  hazard: Said
}

const THANKS_TA = 'நன்றி.'

/**
 * The catalog's scripted answer to question `qid` in round `n` (1 or 2) of a demo script, in the worker language and English: the
 * round's own answer (q1), or since 16 Oct one of its follow-ups.
 */
function scripted(scriptId: string, n: number, qid = 'q1'): Said | undefined {
  const script = rawDemoScript(scriptId)
  const a = roundAnswers(script?.rounds[n - 1]).find((x) => x.questionId === qid)
  const original = script && a?.answer[script.workerLang]
  return original ? { original, translation: a.answer.en ?? '' } : undefined
}

const UNSCRIPTED: Said = { original: '', translation: '' } // only for a catalog copy without the breadth scripts (a test checks the copy)

const LIFT_STEPS: Record<string, DemoStep> = {
  s1: {
    sentence: 'தொங்கும் லோடுக்கு அடியில் ஒருபோதும் நிற்காதீர்கள், நடக்காதீர்கள்.',
    sentenceEn: 'Never stand or walk under a hanging load.',
    quote: 'லோடுக்கு அடியில ஒருபோதும் போக மாட்டேன்',
    quoteEn: "I'll never go under the load",
  },
  s2: {
    sentence: 'லோடு கீழே இறங்கும் வரை பேரிகேடுக்கு வெளியே நில்லுங்கள்.',
    sentenceEn: 'Stay outside the barricade until the load comes down.',
    quote: 'லோடு கீழே இறங்குற வரைக்கும் உள்ள போக மாட்டேன்',
    quoteEn: "I won't go in until the load is down",
  },
  s3: {
    sentence: 'சிக்னல்மேன் சொல்வதை மட்டும் கேளுங்கள்.',
    sentenceEn: 'Follow only what the signalman says.',
    quote: 'சிக்னல்மேன் சொல்றதை மட்டும்தான் கேப்பேன்',
    quoteEn: "I'll listen only to the signalman",
  },
  s4: {
    sentence: 'லோடில் கட்டியிருக்கும் கயிற்றால் அதைக் கட்டுப்படுத்துங்கள்; கையால் ஒருபோதும் பிடிக்காதீர்கள்.',
    sentenceEn: 'Control the load with the rope tied to it; never hold it by hand.',
    quote: 'டேக் லைன் வச்சு மட்டும்தான் நிறுத்துவேன்... லோடை கையால ஒருபோதும் பிடிக்க மாட்டேன்',
    quoteEn: "I'll steady it only with the tag line... I'll never hold the load with my hand",
  },
}

const LIFT_WHERE: Omit<Question, 'id' | 'stepIds'> = {
  text: 'லோடு நகரும்போது நீங்கள் எங்கே இருப்பீர்கள்?',
  backTranslation: 'Where will you be while the load is moving?',
}
const LIFT_WHO: Omit<Question, 'id' | 'stepIds'> = {
  text: 'தூக்கும்போது யாருடைய வழிகாட்டுதலைக் கேட்பீர்கள்?',
  backTranslation: 'During the lift, whose directions will you follow?',
}
const LIFT_SWING: Omit<Question, 'id' | 'stepIds'> = {
  text: 'லோடு ஆடத் தொடங்கினால் என்ன செய்வீர்கள்?',
  backTranslation: 'If the load starts to swing, what will you do?',
}
const LIFT_SWING_WHO: Omit<Question, 'id' | 'stepIds'> = {
  text: 'லோடு ஆடினால் என்ன செய்வீர்கள், யாருடைய சிக்னலைப் பின்பற்றுவீர்கள்?',
  backTranslation: 'If the load swings, what will you do, and whose signals will you follow?',
}

const LIFT_ROUND2_FALLBACK: Said = {
  original: 'லோடு நகரும்போது பேரிகேடுக்கு வெளியே நிப்பேன். லோடு கீழே இறங்குற வரைக்கும் உள்ள போக மாட்டேன். லோடுக்கு அடியில ஒருபோதும் போக மாட்டேன்.',
  translation: "While the load is moving I'll stand outside the barricade. I won't go in until the load is down. I'll never go under the load.",
}
// The catalog's follow-ups (16 Oct), kept here only for a catalog copy that lacks them, as the q1 lines above are.
const LIFT_SIGNALMAN_R1: Said = { original: 'சிக்னல்மேன் சொல்றதை மட்டும்தான் கேப்பேன்.', translation: "I'll listen only to what the signalman says." }
const LIFT_BY_HAND_R1: Said = { original: 'லோடு ஆடுனா, கையால பிடிச்சு ஆடாம நிறுத்துவேன்.', translation: "If the load swings, I'll grab it with my hand and stop it swinging." }
const LIFT_SIGNALMAN_R2: Said = {
  original: 'சிக்னல்மேன் சொல்றதை மட்டும்தான் கேப்பேன். வேற யார் சிக்னல் குடுத்தாலும் கேக்க மாட்டேன்.',
  translation: "I'll listen only to the signalman. I won't follow anyone else's signals.",
}
const LIFT_TAG_LINE_R2: Said = {
  original: 'லோடு ஆடுனா டேக் லைன் வச்சு மட்டும்தான் நிறுத்துவேன். லோடை கையால ஒருபோதும் பிடிக்க மாட்டேன்.',
  translation: "If the load swings, I'll steady it only with the tag line. I'll never hold the load with my hand.",
}

const LIFTING: DemoScript = {
  taskId: 'lifting-zone',
  workerLang: 'ta',
  steps: LIFT_STEPS,
  questions: [
    { id: 'q1', ...LIFT_WHERE, stepIds: ['s1', 's2'] },
    { id: 'q2', ...LIFT_WHO, stepIds: ['s3'] },
    { id: 'q3', ...LIFT_SWING, stepIds: ['s4'] },
  ],
  answers: {
    q1: scripted('sg-lead', 1) ?? { original: 'லோடுக்கு அடியில நின்னு, கையால பிடிச்சு அதை நேரா வைப்பேன்.', translation: "I'll stand under the load and hold it straight with my hand." },
    q2: scripted('sg-lead', 1, 'q2') ?? LIFT_SIGNALMAN_R1,
    q3: scripted('sg-lead', 1, 'q3') ?? LIFT_BY_HAND_R1,
  },
  round1: {
    s1: {
      verdict: 'contradicted',
      quote: 'லோடுக்கு அடியில நின்னு',
      quoteTranslation: "I'll stand under the load",
      reason: 'The worker says they will stand under the load, which this step forbids.',
      confidence: 0.93,
    },
    s2: { verdict: 'missed', reason: 'The answer does not say where the worker will stay while the load moves, or until when.', confidence: 0.9 },
    s3: {
      verdict: 'covered',
      quote: 'சிக்னல்மேன் சொல்றதை மட்டும்தான் கேப்பேன்',
      quoteTranslation: "I'll listen only to what the signalman says",
      reason: 'The worker says they will take directions only from the signalman.',
      confidence: 0.9,
    },
    s4: {
      verdict: 'contradicted',
      quote: 'கையால பிடிச்சு ஆடாம நிறுத்துவேன்',
      quoteTranslation: "I'll grab it with my hand and stop it swinging",
      reason: 'The worker says they will stop the swinging load by hand; the step says never by hand.',
      confidence: 0.88,
      judgeB: 'unclear',
    },
  },
  round1Delivery: {
    // The voice told the worker the answer was right and repeated the step: a hint, which the approved script never holds. Its
    // issues are computed from these words by the backend's rules (judge.ts replyIssues): script words, so `reply_not_neutral`.
    'q2.reply': { said: 'நன்றி. சரியான பதில், சிக்னல்மேன் சொல்வதை மட்டும் கேளுங்கள்.', issues: [] },
  },
  reexplain: (open, first) => {
    const where = ['s1', 's2'].filter((s) => open.includes(s))
    const rest = ['s3', 's4'].filter((s) => open.includes(s))
    const qs: Question[] = []
    if (where.length) qs.push({ id: '', ...LIFT_WHERE, stepIds: where })
    if (rest.length) qs.push({ id: '', ...(rest.length === 2 ? LIFT_SWING_WHO : rest[0] === 's3' ? LIFT_WHO : LIFT_SWING), stepIds: rest })
    return qs.map((q, i) => ({ ...q, id: `q${first + i}` }))
  },
  reexplainAnswer: (q) => {
    if (q.stepIds.includes('s1') || q.stepIds.includes('s2')) return scripted('sg-lead', 2) ?? LIFT_ROUND2_FALLBACK
    // The catalog's round-2 answers to q3 (tag line, s4) and q2 (signalman, s3), in the order the swing-and-signals question asks.
    const parts = [
      q.stepIds.includes('s4') ? (scripted('sg-lead', 2, 'q3') ?? LIFT_TAG_LINE_R2) : undefined,
      q.stepIds.includes('s3') ? (scripted('sg-lead', 2, 'q2') ?? LIFT_SIGNALMAN_R2) : undefined,
    ].filter((p): p is Said => p !== undefined)
    return { original: parts.map((p) => p.original).join(' '), translation: parts.map((p) => p.translation).join(' ') }
  },
  hazard: { original: 'பேரிகேடு ஒரு பக்கம் உடைஞ்சிருக்கு, ஆளுங்க உள்ள வர முடியும்.', translation: 'The barricade is broken on one side; people can walk in.' },
}

const PANEL_STEPS: Record<string, DemoStep & { question: string; questionEn: string; answer: string; answerEn: string }> = {
  s1: {
    sentence: 'பிரேக்கரை ஆஃப் செய்யுங்கள்.',
    sentenceEn: 'Switch off the breaker.',
    question: 'முதலில் பிரேக்கரில் என்ன செய்வீர்கள்?',
    questionEn: 'What will you do first at the breaker?',
    answer: 'முதல்ல பிரேக்கரை ஆஃப் பண்ணுவேன்.',
    answerEn: "First I'll switch off the breaker.",
    quote: 'பிரேக்கரை ஆஃப் பண்ணுவேன்',
    quoteEn: "I'll switch off the breaker",
  },
  s2: {
    sentence: 'அதில் உங்கள் பூட்டையும் டேக்கையும் போடுங்கள்.',
    sentenceEn: 'Put your lock and tag on it.',
    question: 'யாரும் மீண்டும் ஆன் செய்யாமல் இருக்க பிரேக்கரில் என்ன போடுவீர்கள்?',
    questionEn: 'What will you put on the breaker so nobody switches it on again?',
    answer: 'லாக் போட்டு டேக் மாட்டுவேன்.',
    answerEn: "I'll put on the lock and hang the tag.",
    quote: 'லாக் போட்டு டேக் மாட்டுவேன்',
    quoteEn: "I'll put on the lock and hang the tag",
  },
  s3: {
    sentence: 'பேனலைத் திறந்த பிறகு, எதையும் தொடும் முன், கரண்ட் இல்லை என்று டெஸ்டரில் சரிபாருங்கள்.',
    sentenceEn: 'After you open the panel, before you touch anything, check with the tester that there is no power.',
    question: 'கம்பிகளைத் தொடும் முன் கரண்ட் இல்லை என்று எப்படித் தெரிந்துகொள்வீர்கள்?',
    questionEn: 'How will you know there is no power before you touch the wires?',
    answer: 'டெஸ்டர் வச்சு கரண்ட் இல்லைன்னு செக் பண்ணிட்டுதான் தொடுவேன்.',
    answerEn: "I'll check with the tester that there's no current before I touch it.",
    quote: 'டெஸ்டர் வச்சு கரண்ட் இல்லைன்னு செக் பண்ணிட்டுதான்',
    quoteEn: "I'll check with the tester that there's no current",
  },
}

const PANEL: DemoScript = {
  taskId: 'panel-isolation',
  workerLang: 'ta',
  steps: PANEL_STEPS,
  questions: [
    { id: 'q1', text: 'பேனலைத் திறப்பதற்கு முன் என்ன செய்வீர்கள்?', backTranslation: 'What will you do before you open the panel?', stepIds: ['s1', 's2', 's3'] },
    { id: 'q2', text: 'கம்பிகளைத் தொடுவது பாதுகாப்பானது என்று எப்படித் தெரிந்துகொள்வீர்கள்?', backTranslation: 'How will you know it is safe to touch the wires?', stepIds: ['s3'] },
  ],
  answers: {
    q1: scripted('sg-panel', 1) ?? { original: 'நான் பிரேக்கரை ஆஃப் பண்ணிட்டு திறப்பேன்.', translation: "I'll switch off the breaker and open it." },
    q2: { original: 'ஆஃப் பண்ணிட்டா கரண்ட் இருக்காது.', translation: 'If I switch it off, there will be no current.' },
  },
  round1: {
    s1: { verdict: 'covered', quote: 'பிரேக்கரை ஆஃப் பண்ணிட்டு', quoteTranslation: 'switch off the breaker', reason: 'The worker says they will switch off the breaker, which covers the step.', confidence: 0.86 },
    s2: { verdict: 'missed', reason: 'The answer does not mention locking or tagging the breaker.', confidence: 0.9 },
    s3: { verdict: 'missed', reason: 'The answer does not mention testing that the circuit is dead before touching it.', confidence: 0.82, judgeB: 'unclear' },
  },
  round1Delivery: {},
  reexplain: (open, first) =>
    open.slice(0, 2).map((id, i) => ({ id: `q${first + i}`, text: PANEL_STEPS[id]?.question ?? '', backTranslation: PANEL_STEPS[id]?.questionEn ?? '', stepIds: i === 1 ? open.slice(1) : [id] })),
  reexplainAnswer: (q) => ({
    original: q.stepIds.map((id) => PANEL_STEPS[id]?.answer ?? '').join(' '),
    translation: q.stepIds.map((id) => PANEL_STEPS[id]?.answerEn ?? '').join(' '),
  }),
  hazard: { original: 'ஸ்டோர்ல லாக் இல்ல.', translation: "There's no lock in the store." },
}

type Ask = Omit<Question, 'id' | 'stepIds'>

/**
 * A demo whose task asks two questions, q1 about `early` (default s1 and s2) and q2 about `late` (default s3), saying the catalog's
 * lines in both rounds (hot work, trench entry; since 17 Oct the demo suites, the press with q1 about s1-s3 and q2 about s4).
 */
interface TwoQuestionDemo extends Pick<DemoScript, 'taskId' | 'workerLang' | 'steps' | 'round1' | 'hazard'> {
  scriptId: string
  first: Ask
  second: Ask
  early?: readonly string[]
  late?: readonly string[]
}

function twoQuestionDemo(d: TwoQuestionDemo): DemoScript {
  const early = [...(d.early ?? ['s1', 's2'])]
  const late = [...(d.late ?? ['s3'])]
  const said = (n: number, qid: string): Said => scripted(d.scriptId, n, qid) ?? UNSCRIPTED
  return {
    taskId: d.taskId,
    workerLang: d.workerLang,
    steps: d.steps,
    questions: [
      { id: 'q1', ...d.first, stepIds: early },
      { id: 'q2', ...d.second, stepIds: late },
    ],
    answers: { q1: said(1, 'q1'), q2: said(1, 'q2') },
    round1: d.round1,
    round1Delivery: {},
    reexplain: (open, first) => {
      const asks: Question[] = []
      const before = early.filter((s) => open.includes(s))
      const after = late.filter((s) => open.includes(s))
      if (before.length) asks.push({ id: '', ...d.first, stepIds: before })
      if (after.length) asks.push({ id: '', ...d.second, stepIds: after })
      return asks.map((q, i) => ({ ...q, id: `q${first + i}` }))
    },
    reexplainAnswer: (q) => {
      const parts = [q.stepIds.some((s) => early.includes(s)) ? said(2, 'q1') : undefined, q.stepIds.some((s) => late.includes(s)) ? said(2, 'q2') : undefined]
      const kept = parts.filter((p): p is Said => p !== undefined)
      return { original: kept.map((p) => p.original).join(' '), translation: kept.map((p) => p.translation).join(' ') }
    },
    hazard: d.hazard,
  }
}

// DRAFT, 16 Oct breadth: every Bengali line below is machine-written and NEEDS NATIVE-SPEAKER REVIEW (build-notes/34-breadth.md).
const HOT_WORK = twoQuestionDemo({
  scriptId: 'sg-hot-work',
  taskId: 'hot-work',
  workerLang: 'bn',
  steps: {
    s1: {
      sentence: 'কাটিং শুরুর আগে দশ মিটারের মধ্যে যা কিছু পুড়তে পারে, সব সরিয়ে ফেলুন বা ঢেকে দিন।',
      sentenceEn: 'Before you start cutting, move away or cover everything within ten metres that can burn.',
      quote: 'দশ মিটারের মধ্যে যা কিছু পুড়তে পারে, সব সরিয়ে ফেলব বা ঢেকে দেব',
      quoteEn: "I'll move away or cover everything within ten metres that can burn",
    },
    s2: {
      sentence: 'আগুন নেভানোর সিলিন্ডার পাশে রাখুন, আর আগুন পাহারা দেওয়ার লোক যেন সবসময় থাকে।',
      sentenceEn: 'Keep the fire extinguisher beside you, and make sure the person keeping watch for fire is there all the time.',
      quote: 'আগুন নেভানোর সিলিন্ডার হাতের কাছে রাখব... আগুন পাহারা দেওয়ার লোক পাশে না থাকলে কাটিং শুরু করব না',
      quoteEn: "I'll keep the fire extinguisher within reach... I won't start cutting unless the person keeping watch for fire is beside me",
    },
    s3: {
      sentence: 'কাটিং শেষ হওয়ার পরও ত্রিশ মিনিট আগুনের দিকে নজর রাখুন।',
      sentenceEn: 'After the cutting is finished, keep watching for fire for thirty minutes.',
      quote: 'ত্রিশ মিনিট ধরে আগুনের দিকে নজর রাখব',
      quoteEn: "I'll keep watching for fire for thirty minutes",
    },
  },
  first: { text: 'কাটিং শুরু করার আগে আপনি কী করবেন?', backTranslation: 'What will you do before you start cutting?' },
  second: { text: 'কাটিং শেষ করার পর আপনি কী করবেন?', backTranslation: 'What will you do after you finish cutting?' },
  round1: {
    s1: {
      verdict: 'covered',
      quote: 'দশ মিটারের মধ্যে যা কিছু পুড়তে পারে, সব সরিয়ে ফেলব',
      quoteTranslation: "I'll move away everything within ten metres that can burn",
      reason: 'The worker says they will move away, or cover, what can burn within ten metres.',
      confidence: 0.9,
    },
    s2: {
      verdict: 'covered',
      quote: 'আগুন নেভানোর সিলিন্ডার পাশে রাখব, আর আগুন পাহারা দেওয়ার একজন লোক থাকবে',
      quoteTranslation: "I'll keep the fire extinguisher beside me, and one person will be there keeping watch for fire",
      reason: 'The worker names the extinguisher beside them and a person watching for fire.',
      confidence: 0.88,
    },
    s3: {
      verdict: 'contradicted',
      quote: 'সাথে সাথে চলে যাব',
      quoteTranslation: "I'll leave straight away",
      reason: 'The worker says they will leave as soon as the cutting is finished; the step says keep watching for 30 minutes.',
      confidence: 0.92,
    },
  },
  hazard: { original: 'এখানে পাশে গ্যাসের সিলিন্ডার রাখা আছে।', translation: 'There is a gas cylinder kept right next to here.' },
})

// DRAFT, 16 Oct breadth: every Odia line below is machine-written and NEEDS NATIVE-SPEAKER REVIEW (build-notes/34-breadth.md). The pit is
// ଗାତ, the everyday word, not trench spelled out; the shoring is "the supports holding the walls".
const TRENCH = twoQuestionDemo({
  scriptId: 'chennai-trench',
  taskId: 'trench-entry',
  workerLang: 'or',
  steps: {
    s1: {
      sentence: 'ଭିତରକୁ ଯିବା ଆଗରୁ ଦେଖନ୍ତୁ, କାନ୍ଥକୁ ଧରି ରଖିଥିବା ସପୋର୍ଟ ଠିକ୍ ଲାଗିଛି।',
      sentenceEn: 'Before you go in, check that the supports holding the walls are properly in place.',
      quote: 'କାନ୍ଥକୁ ଧରି ରଖିଥିବା ସପୋର୍ଟ ଠିକ୍ ଭାବରେ ଲାଗିଛି କି ନାହିଁ',
      quoteEn: 'the supports holding up the walls are properly in place',
    },
    s2: {
      sentence: 'କେବଳ ସିଡ଼ି ଦେଇ ଭିତରକୁ ଯାଆନ୍ତୁ ଆଉ ବାହାରକୁ ଆସନ୍ତୁ।',
      sentenceEn: 'Go in and come out only by the ladder.',
      quote: 'କେବଳ ସିଡ଼ି ଦେଇ ଯିବି ଆସିବି',
      quoteEn: "I'll go in and come out only by the ladder",
    },
    s3: {
      sentence: 'କାନ୍ଥରେ ପାଣି କିମ୍ବା ଫାଟ ଦେଖିଲେ, ସଙ୍ଗେ ସଙ୍ଗେ ବାହାରକୁ ଆସନ୍ତୁ ଆଉ ମୋତେ କୁହନ୍ତୁ।',
      sentenceEn: 'If you see water or a crack in the wall, come out at once and tell me.',
      quote: 'ସଙ୍ଗେ ସଙ୍ଗେ ସିଡ଼ି ଦେଇ ବାହାରକୁ ଚାଲିଆସିବି, ଆଉ ସୁପରଭାଇଜରଙ୍କୁ କହିବି',
      quoteEn: "I'll climb out by the ladder straight away and tell the supervisor",
    },
  },
  first: { text: "ଗାତ ଭିତରକୁ ଯିବା ଆଗରୁ ତୁମେ କ'ଣ ଦେଖିବ ଆଉ କ'ଣ କରିବ?", backTranslation: 'Before you go into the trench, what will you check and what will you do?' },
  second: { text: "କାନ୍ଥରେ ପାଣି କିମ୍ବା ଫାଟ ଦେଖିଲେ ତୁମେ କ'ଣ କରିବ?", backTranslation: 'What will you do if you see water or a crack in the wall?' },
  round1: {
    s1: { verdict: 'missed', reason: 'The answer does not mention checking the shoring before going in.', confidence: 0.9 },
    s2: {
      verdict: 'covered',
      quote: 'କେବଳ ସିଡ଼ି ଦେଇ ତଳକୁ ଓହ୍ଲାଇବି, ଆଉ ସିଡ଼ି ଦେଇ ଉପରକୁ ଉଠିବି',
      quoteTranslation: "I'll go down only by the ladder, and come back up by the ladder",
      reason: 'The worker says they will go in and out only by the ladder.',
      confidence: 0.9,
    },
    s3: {
      verdict: 'covered',
      quote: 'ସଙ୍ଗେ ସଙ୍ଗେ ବାହାରକୁ ଚାଲିଆସିବି, ଆଉ ସୁପରଭାଇଜରଙ୍କୁ କହିବି',
      quoteTranslation: "I'll come out straight away and tell the supervisor",
      reason: 'The worker says they will get out at once and tell the supervisor.',
      confidence: 0.9,
    },
  },
  hazard: { original: 'କାନ୍ଥରୁ ମାଟି ଖସୁଛି।', translation: 'Soil is falling from the wall.' },
})

// DRAFT, 17 Oct demo suites: every Bengali, Tamil, Hindi and Telugu line below is machine-written and NEEDS NATIVE-SPEAKER REVIEW
// (build-notes/37-domain-suites.md). The questions are the eval's hand-written ones (spec.json questionFixes). Everyday site words:
// the water gun (পানির বন্দুক), not "jetting gun" spelled out; the press's tongs are चिमटा; a tower hook is హుక్కు.
const HYDRO_JETTING = twoQuestionDemo({
  scriptId: 'sg-hydrojet',
  taskId: 'hydro-jetting',
  workerLang: 'bn',
  steps: {
    s1: {
      sentence: 'পাম্প চলার সময় আমাদের দলের লোক ছাড়া কেউ যেন ঘেরা জায়গার ভেতরে না ঢোকে।',
      sentenceEn: 'While the pump is running, nobody but our crew may come inside the fenced-off area.',
      quote: 'ঘেরা জায়গার ভেতরে আমাদের দলের লোক ছাড়া কেউ ঢুকবে না',
      quoteEn: 'nobody but our crew will come inside the fenced-off area',
    },
    s2: {
      sentence: 'পানির বন্দুক কখনো কারও দিকে তাক করবেন না, আর ট্রিগার কখনো বাঁধবেন না।',
      sentenceEn: 'Never point the water gun at anyone, and never tie the trigger.',
      quote: 'পানির বন্দুক কখনো কারও দিকে তাক করব না... ট্রিগার কখনো বাঁধব না',
      quoteEn: "I'll never point the water gun at anyone... I'll never tie the trigger",
    },
    s3: {
      sentence: 'নজেল বদলানোর আগে পাম্প বন্ধ করে চাপ পুরো ছেড়ে দিন; মিটারের কাঁটা শূন্যে না নামা পর্যন্ত নজেলে হাত দেবেন না।',
      sentenceEn: "Before changing the nozzle, stop the pump and release all the pressure; don't touch the nozzle until the gauge needle drops to zero.",
      quote: 'পাম্প বন্ধ করে চাপ পুরো ছেড়ে দেব... মিটারের কাঁটা শূন্যে না নামা পর্যন্ত নজেলে হাত দেব না',
      quoteEn: "I'll stop the pump and release all the pressure... I won't touch the nozzle until the gauge needle drops to zero",
    },
  },
  first: { text: 'পাম্প চলার সময় আপনি কী কী খেয়াল রাখবেন?', backTranslation: 'While the pump is running, what will you make sure of?' },
  second: { text: 'নজেল বদলানোর আগে আপনি কী করবেন?', backTranslation: 'What will you do before you change the nozzle?' },
  round1: {
    s1: {
      verdict: 'covered',
      quote: 'ফিতা দিয়ে ঘেরা জায়গার ভেতরে আমাদের দলের লোক ছাড়া কাউকে ঢুকতে দেব না',
      quoteTranslation: "I won't let anyone but our crew inside the taped-off area",
      reason: 'The worker says nobody but the crew comes inside the taped-off area while the pump is running.',
      confidence: 0.9,
    },
    s2: {
      verdict: 'contradicted',
      quote: 'ট্রিগারটা দড়ি দিয়ে বেঁধে রাখব',
      quoteTranslation: "I'll tie the trigger down with a rope",
      reason: 'The worker says they will tie the trigger down when the hand tires; the step says never tie it.',
      confidence: 0.93,
    },
    s3: {
      verdict: 'covered',
      quote: 'পাম্প বন্ধ করব, তারপর চাপ পুরো ছেড়ে দেব',
      quoteTranslation: "I'll stop the pump and then release all the pressure",
      reason: 'The worker says they will stop the pump and release the pressure, and touch the nozzle only at zero.',
      confidence: 0.88,
    },
  },
  hazard: { original: 'হোস পাইপের জোড়া দিয়ে পানি ছিটকে বের হচ্ছে।', translation: 'Water is spraying out of a joint in the hose.' },
})

const STEAM_LINE = twoQuestionDemo({
  scriptId: 'sg-steam-line',
  taskId: 'steam-line-break',
  workerLang: 'ta',
  steps: {
    s1: {
      sentence: 'இரண்டு வால்விலும் உங்கள் சொந்தப் பூட்டையும் டேக்கையும் போடுங்கள்.',
      sentenceEn: 'Put your own lock and tag on both valves.',
      quote: 'ரெண்டுலயும் என் சொந்தப் பூட்டையும் டேக்கையும் போடுவேன்',
      quoteEn: "I'll put my own lock and tag on both of them",
    },
    s2: {
      sentence: 'டிரெயின் வால்வைத் திறங்கள்; கேஜில் பூஜ்ஜியம் காட்டும் வரை எந்த போல்ட்டையும் தொடாதீர்கள்.',
      sentenceEn: "Open the drain valve; don't touch any bolt until the gauge shows zero.",
      quote: 'டிரெயின் வால்வைத் திறப்பேன்... கேஜ்ல பூஜ்ஜியம் காட்டுற வரைக்கும் எந்த போல்ட்டையும் தொட மாட்டேன்',
      quoteEn: "I'll open the drain valve... until the gauge shows zero, I won't touch any bolt",
    },
    s3: {
      sentence: 'முதலில் எதிர்ப் பக்க போல்ட்டுகளைத் தளர்த்துங்கள்; முகத்தை இணைப்புக்கு நேராக வைக்காதீர்கள்.',
      sentenceEn: "Loosen the far-side bolts first; don't keep your face in line with the joint.",
      quote: 'முதல்ல எதிர்ப் பக்க போல்ட்டுகளைத்தான் லூஸ் பண்ணுவேன்... இணைப்புக்கு நேரா முகத்தை வைக்க மாட்டேன்',
      quoteEn: "First I'll loosen only the far-side bolts... I won't put my face in line with the joint",
    },
  },
  first: { text: 'முதல் போல்ட்டைத் தொடுவதற்கு முன் நீங்கள் என்ன செய்வீர்கள்?', backTranslation: 'What will you do before you touch the first bolt?' },
  second: { text: 'குழாய் இணைப்பை நீங்கள் எப்படித் திறப்பீர்கள்?', backTranslation: 'How will you open the joint?' },
  round1: {
    s1: {
      verdict: 'contradicted',
      quote: 'அதனால என் பூட்டு போட வேண்டியதில்லை',
      quoteTranslation: "so I don't need to put my lock on",
      reason: 'The worker says their own lock is not needed because the operator closed the valves; the step needs their own lock and tag on both.',
      confidence: 0.92,
    },
    s2: {
      verdict: 'covered',
      quote: 'டிரெயின் வால்வைத் திறந்து, கேஜ்ல பூஜ்ஜியம் காட்டுனதுக்கு அப்புறம்தான் போல்ட்டைத் தொடுவேன்',
      quoteTranslation: "I'll open the drain valve, and I'll touch a bolt only after the gauge shows zero",
      reason: 'The worker says they will open the drain and touch a bolt only once the gauge shows zero.',
      confidence: 0.9,
    },
    s3: {
      verdict: 'covered',
      quote: 'முதல்ல எனக்கு எதிர்ப் பக்கம் இருக்கிற போல்ட்டுகளைத்தான் லூஸ் பண்ணுவேன்... முகத்தை இணைப்புக்கு நேரா வைக்காம, ஓரமா நின்னு செய்வேன்',
      quoteTranslation: "First I'll loosen the bolts on the side away from me... I'll keep my face out of line with the joint and work standing to the side",
      reason: 'The worker says they will loosen the far-side bolts first and keep their face out of line with the joint.',
      confidence: 0.88,
    },
  },
  hazard: { original: 'டிரெயின் வால்வைத் திறந்தும் கேஜ் இன்னும் பிரஷர் காட்டுது.', translation: 'Even with the drain valve open, the gauge still shows pressure.' },
})

const PRESS = twoQuestionDemo({
  scriptId: 'chennai-press',
  taskId: 'press-lockout',
  workerLang: 'hi',
  early: ['s1', 's2', 's3'],
  late: ['s4'],
  steps: {
    s1: {
      sentence: 'मेन स्विच ऑफ़ करें और उस पर अपना ताला लगाएँ।',
      sentenceEn: 'Switch off the main switch and put your own lock on it.',
      quote: 'मेन स्विच ऑफ़ करूँगा, उस पर अपना ताला और टैग लगाऊँगा',
      quoteEn: "I'll switch off the main switch and put my own lock and tag on it",
    },
    s2: {
      sentence: 'स्टार्ट बटन दबाकर देखें कि मशीन नहीं चलती।',
      sentenceEn: 'Press the start button and check that the machine does not run.',
      quote: 'स्टार्ट बटन दबाकर पक्का करूँगा कि मशीन नहीं चलती',
      quoteEn: "I'll press the start button to make sure the machine doesn't run",
    },
    s3: {
      sentence: 'अंदर झुकने से पहले ऊपर और नीचे की डाई के बीच सेफ़्टी ब्लॉक लगाएँ।',
      sentenceEn: 'Before you lean in, put the safety block between the upper and lower dies.',
      quote: 'डाई के बीच ब्लॉक लगाऊँगा; ब्लॉक के बिना अंदर नहीं झुकूँगा',
      quoteEn: "I'll put the block between the dies; I won't lean in without the block",
    },
    s4: {
      sentence: 'फँसा हुआ पीस सिर्फ़ चिमटे से निकालें, हाथ से कभी नहीं।',
      sentenceEn: 'Take the stuck piece out only with the tongs, never by hand.',
      quote: 'फँसा हुआ पीस सिर्फ़ चिमटे से निकालूँगा... डाई के बीच कभी हाथ या उँगली नहीं डालूँगा',
      quoteEn: "I'll take the stuck piece out only with the tongs... I'll never put a hand or a finger between the dies",
    },
  },
  first: { text: 'मशीन में फँसा पीस निकालने से पहले आप क्या-क्या करेंगे?', backTranslation: 'What will you do before you clear the jam?' },
  second: { text: 'फँसा हुआ पीस आप कैसे निकालेंगे?', backTranslation: 'How will you take out the stuck piece?' },
  round1: {
    s1: {
      verdict: 'covered',
      quote: 'मेन स्विच ऑफ़ करूँगा और उस पर अपना ताला और टैग लगाऊँगा',
      quoteTranslation: "I'll switch off the main switch and put my own lock and tag on it",
      reason: 'The worker says they will switch off the main switch and put their own lock on it.',
      confidence: 0.92,
    },
    s2: {
      verdict: 'covered',
      quote: 'स्टार्ट बटन दबाकर देखूँगा कि मशीन चलती तो नहीं',
      quoteTranslation: "I'll press the start button to check the machine doesn't run",
      reason: 'The worker says they will press start to check that the press does not run.',
      confidence: 0.86,
    },
    s3: {
      verdict: 'covered',
      quote: 'ऊपर और नीचे की डाई के बीच ब्लॉक लगाऊँगा',
      quoteTranslation: "I'll put the block between the upper and lower dies",
      reason: 'The worker says they will put the block between the dies before clearing the jam.',
      confidence: 0.87,
    },
    s4: {
      verdict: 'contradicted',
      quote: 'फँसा हुआ पीस हाथ से जल्दी खींच लूँगा',
      quoteTranslation: "I'll quickly pull the stuck piece out by hand",
      reason: 'The worker says they will pull the stuck piece out by hand; the step says only with the tongs, never by hand.',
      confidence: 0.94,
    },
  },
  hazard: { original: 'चिमटा टूटा हुआ है, और यहाँ दूसरा नहीं है।', translation: "The tongs are broken, and there isn't another pair here." },
})

const TOWER = twoQuestionDemo({
  scriptId: 'chennai-tower',
  taskId: 'telecom-tower',
  workerLang: 'te',
  steps: {
    s1: {
      sentence: 'టవరు కింద ఎవరూ ఉండకూడదు; పనిముట్లను సంచిలో పెట్టి తాడుతో పైకి పంపండి.',
      sentenceEn: 'Nobody may be under the tower; send the tools up in the bag on the rope.',
      quote: 'టవరు కింద ఎవరూ లేకుండా చూసుకుంటాను, పనిముట్లు సంచిలో పెట్టి తాడుతో పైకి పంపిస్తాను',
      quoteEn: "I'll make sure nobody is under the tower, and I'll send the tools up in the bag on the rope",
    },
    s2: {
      sentence: 'ఎక్కే ముందు కంట్రోల్ రూముకి చెప్పి యాంటెన్నా ఆఫ్ చేయించండి; ఆఫ్ అయిందని వాళ్ళు చెప్పేవరకు ఎక్కకండి.',
      sentenceEn: "Before you climb, have the control room switch the antenna off; don't climb until they say it is off.",
      quote: 'కంట్రోల్ రూముకి ఫోన్ చేసి నేను పని చేసే యాంటెన్నాను ఆఫ్ చేయమంటాను... ఆఫ్ అయిందని వాళ్ళు చెప్పేవరకు ఎక్కకూడదు',
      quoteEn: "I'll phone the control room and ask them to switch off the antenna I'll work on... I must not climb until they say it is off",
    },
    s3: {
      sentence: 'ఎక్కేటప్పుడు ఎప్పుడూ ఒక హుక్కు టవరుకి తగిలించి ఉంచండి; ఒకసారికి ఒక్క హుక్కు మాత్రమే మార్చండి.',
      sentenceEn: 'While you climb, always keep one hook on the tower; move only one hook at a time.',
      quote: 'ఎప్పుడూ ఒక హుక్కు టవరుకి తగిలించే ఉంటుంది, ఒకసారికి ఒక్క హుక్కు మాత్రమే మారుస్తాను',
      quoteEn: "one hook always stays on the tower, and I'll move only one hook at a time",
    },
  },
  first: { text: 'టవరు ఎక్కడం మొదలుపెట్టే ముందు మీరు ఏం చేస్తారు?', backTranslation: 'What will you do before you start to climb?' },
  second: { text: 'టవరు పైకి మీరు ఎలా ఎక్కుతారు?', backTranslation: 'How will you go up the tower?' },
  round1: {
    s1: {
      verdict: 'covered',
      quote: 'ఎక్కే ముందు టవరు కింద ఎవరూ లేరని చూసుకుంటాను... పనిముట్లన్నీ సంచిలో పెట్టి తాడుతో పైకి లాగుతాను',
      quoteTranslation: "Before I climb, I'll make sure nobody is under the tower... I'll put all the tools in the bag and pull them up with the rope",
      reason: 'The worker says nobody will be under the tower and the tools go up in the bag on the rope.',
      confidence: 0.9,
    },
    s2: { verdict: 'missed', reason: 'The answer does not mention getting the antenna switched off before the climb.', confidence: 0.9 },
    s3: {
      verdict: 'covered',
      quote: 'ఎప్పుడూ ఒక హుక్కు టవరుకి తగిలించే ఉంటుంది... ఒకసారికి ఒక్క హుక్కు మాత్రమే తీసి పైకి మారుస్తాను',
      quoteTranslation: "one hook always stays on the tower... I'll take off only one hook at a time and move it higher",
      reason: 'The worker says one hook always stays on the tower and they move one hook at a time.',
      confidence: 0.9,
    },
  },
  hazard: { original: 'టవరు మీద ఒక మెట్టు వదులుగా ఉంది.', translation: 'A rung on the tower is loose.' },
})

const DEMOS: readonly DemoScript[] = [LIFTING, PANEL, HOT_WORK, TRENCH, HYDRO_JETTING, STEAM_LINE, PRESS, TOWER]

/** The hand-written demo for this briefing (task and worker language), if there is one. */
export const demoFor = (b: Pick<Briefing, 'taskId' | 'workerLang'>): DemoScript | undefined => DEMOS.find((d) => d.taskId === b.taskId && d.workerLang === b.workerLang)

/** The neutral thanks after an answer, or the demo's off-script reply (round 1, Live). */
export const replyFor = (demo: DemoScript | undefined, round: number, qid: string): string | undefined =>
  round === 1 ? demo?.round1Delivery[`${qid}.reply`]?.said : undefined

export const NEUTRAL_THANKS_TA = THANKS_TA

/**
 * Guard rule 1 (API.md v0.5.3): passes that agree stand, a contradiction in either pass stands, and every other split is
 * "unclear". A split is never "covered", and "missed" no longer outranks "unclear".
 */
export function rule1Verdict(a: Verdict, b: Verdict): Verdict {
  if (a === b) return a
  return a === 'contradicted' || b === 'contradicted' ? 'contradicted' : 'unclear'
}

/**
 * A rating's final verdict with judge B's disagreement folded in (guard rule 1). The reason is the pass that holds the final
 * verdict. On a split that ends "unclear" it is the pass that doubted ("unclear", else "missed", the first with a sentence):
 * a covered pass's reason would contradict "Ask again", so it is never shown there. The quote stays: it is what the worker said.
 */
export function demoRating(stepId: string, r: DemoRating): { final: Rating; a: Rating; b: Rating } {
  const base = { stepId, confidence: r.confidence, ...(r.quote ? { quote: r.quote, quoteTranslation: r.quoteTranslation } : {}) }
  const bVerdict = r.judgeB ?? r.verdict
  const a: Rating = { ...base, verdict: r.verdict, reason: r.reason, flags: [] }
  const b: Rating = { ...base, verdict: bVerdict, reason: r.judgeBReason ?? (bVerdict === r.verdict ? r.reason : ''), flags: [] }
  const verdict = rule1Verdict(a.verdict, b.verdict)
  const split = a.verdict !== b.verdict
  const doubting = (['unclear', 'missed'] as const).flatMap((v) => [a, b].filter((p) => p.verdict === v)).find((p) => p.reason)
  const reason = split && verdict === 'unclear' ? (doubting?.reason ?? '') : ([a, b].find((p) => p.verdict === verdict) ?? a).reason
  return { final: { ...base, verdict, reason, flags: split ? ['passes_disagreed'] : [] }, a, b }
}
