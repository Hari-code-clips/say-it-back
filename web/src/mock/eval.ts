import type { EvalGroup, EvalItem, EvalReport, EvalReportRating, EvalTryResult, Lang, Rating, Verdict } from '../api/types.ts'
import { rawDemoScript, rawTask } from './catalog.ts'
import { HttpError } from './util.ts'

// Sample evaluation data for mock mode. The numbers are made up to show the page: the Eval page says so in a banner and
// labels each metric "Illustrative, mock only" (v0.5), and the report names no model, because none ran. The real report
// comes from eval/reports/latest.json through GET /api/eval/latest.
// v0.4: each item carries its steps' reference text and the reference question (from the catalog), and `hasAudio`.

interface MockItem extends EvalItem {
  pred: Record<string, Verdict>
  original: string
  translation: string
}

const item = (
  id: string,
  taskId: string,
  questionId: string,
  workerLang: Lang,
  pattern: string,
  noise: string,
  answerGloss: string,
  gold: Record<string, Verdict>,
  pred: Record<string, Verdict>,
  original: string,
): MockItem => {
  const task = rawTask(taskId)
  return {
    id,
    taskId,
    questionId,
    workerLang,
    pattern,
    noise,
    source: 'synthetic_tts',
    answerGloss,
    gold,
    steps: Object.fromEntries(Object.keys(gold).map((s) => [s, task?.referenceSteps.find((r) => r.id === s)?.text ?? ''])),
    questionText: task?.referenceQuestions.find((q) => q.id === questionId)?.text ?? '',
    hasAudio: true,
    pred,
    original,
    translation: answerGloss,
  }
}

const lead = (n: number) => rawDemoScript('sg-lead')?.rounds[n - 1]?.answer
const panel = (n: number) => rawDemoScript('sg-panel')?.rounds[n - 1]?.answer

export const MOCK_EVAL_ITEMS: MockItem[] = [
  item('lifting-zone.q1.ta.demo.clean.r1', 'lifting-zone', 'q1', 'ta', 'demo', 'clean', lead(1)?.en ?? '',
    { s1: 'contradicted', s2: 'missed' }, { s1: 'contradicted', s2: 'missed' }, lead(1)?.ta ?? ''),
  item('lifting-zone.q1.ta.demo.clean.r2', 'lifting-zone', 'q1', 'ta', 'demo', 'clean', lead(2)?.en ?? '',
    { s1: 'covered', s2: 'covered' }, { s1: 'covered', s2: 'covered' }, lead(2)?.ta ?? ''),
  item('lifting-zone.q1.ta.negation.snr10', 'lifting-zone', 'q1', 'ta', 'negation', 'snr10', "I won't stay outside the barricade; I'll go under the load to guide it.",
    { s1: 'contradicted', s2: 'contradicted' }, { s1: 'contradicted', s2: 'contradicted' }, 'நான் பேரிகேடுக்கு வெளியே நிக்க மாட்டேன், லோடுக்கு அடியில போய் வழிகாட்டுவேன்.'),
  item('lifting-zone.q1.zh.silence.clean', 'lifting-zone', 'q1', 'zh', 'silence', 'clean', '(no answer)',
    { s1: 'unclear', s2: 'unclear' }, { s1: 'unclear', s2: 'unclear' }, ''),
  item('panel-isolation.q1.ta.demo.clean.r1', 'panel-isolation', 'q1', 'ta', 'demo', 'clean', panel(1)?.en ?? '',
    { s1: 'covered', s2: 'missed', s3: 'missed' }, { s1: 'covered', s2: 'missed', s3: 'missed' }, panel(1)?.ta ?? ''),
  // v0.5: the catalog's sg-panel round 2, in the SOP's order (open, then test dead before touching anything).
  item('panel-isolation.q1.ta.complete.clean', 'panel-isolation', 'q1', 'ta', 'complete', 'clean', panel(2)?.en ?? '',
    { s1: 'covered', s2: 'covered', s3: 'covered' }, { s1: 'covered', s2: 'covered', s3: 'covered' }, panel(2)?.ta ?? ''),
  item('panel-isolation.q1.bn.one_missing.snr10', 'panel-isolation', 'q1', 'bn', 'one_missing', 'snr10',
    "I'll switch off the breaker and lock it, then open the panel.",
    { s1: 'covered', s2: 'covered', s3: 'missed' }, { s1: 'covered', s2: 'covered', s3: 'missed' }, 'আমি ব্রেকার বন্ধ করে তালা দেব, তারপর প্যানেল খুলব।'),
  item('scaffold-harness.q1.hi.demo.clean', 'scaffold-harness', 'q1', 'hi', 'demo', 'clean', "I'll put on the harness and go up.",
    { s1: 'covered', s2: 'missed' }, { s1: 'covered', s2: 'missed' }, 'मैं हार्नेस पहनूँगा और ऊपर चढ़ जाऊँगा।'),
  item('scaffold-harness.q1.hi.vague.clean', 'scaffold-harness', 'q1', 'hi', 'vague', 'clean', "I'll be careful when I go up.",
    { s1: 'missed', s2: 'missed' }, { s1: 'unclear', s2: 'missed' }, 'मैं ऊपर जाते समय सावधान रहूँगा।'),
  item('hot-work.q1.bn.complete.clean', 'hot-work', 'q1', 'bn', 'complete', 'clean',
    'I will clear everything that can burn within ten metres and keep the extinguisher and a fire watcher next to me.',
    { s1: 'covered', s2: 'covered' }, { s1: 'covered', s2: 'covered' }, 'আমি দশ মিটারের মধ্যে সব জ্বলনযোগ্য জিনিস সরিয়ে দেব এবং অগ্নিনির্বাপক ও ফায়ার ওয়াচার পাশে রাখব।'),
  item('hot-work.q2.bn.contradicted.clean', 'hot-work', 'q2', 'bn', 'contradicted', 'clean', "I'll leave as soon as I finish cutting.",
    { s3: 'contradicted' }, { s3: 'contradicted' }, 'কাটা শেষ হলেই আমি চলে যাব।'),
  item('lifting-zone.q1.zh.negation.snr5', 'lifting-zone', 'q1', 'zh', 'negation', 'snr5', "I won't stand under the load, and I'll stay outside the barrier until it has landed.",
    { s1: 'covered', s2: 'covered' }, { s1: 'covered', s2: 'unclear' }, '我不会站在吊物下面，会一直待在围栏外面，等吊物落地。'),
  item('trench-entry.q1.ta.two_missing.clean', 'trench-entry', 'q1', 'ta', 'two_missing', 'clean', "I'll go down by the ladder.",
    { s1: 'missed', s2: 'covered' }, { s1: 'missed', s2: 'covered' }, 'நான் ஏணியில் இறங்குவேன்.'),
  item('lifting-zone.q2.zh.echo.clean', 'lifting-zone', 'q2', 'zh', 'echo', 'clean', 'During the lift, who will I take directions from?',
    { s3: 'missed' }, { s3: 'missed' }, '吊装期间我听谁的指挥？'),
]

export const evalItems = (): EvalItem[] =>
  MOCK_EVAL_ITEMS.map(({ id, taskId, questionId, workerLang, pattern, noise, source, answerGloss, gold, steps, questionText, hasAudio }) => ({
    id, taskId, questionId, workerLang, pattern, noise, source, answerGloss, gold, steps, questionText, hasAudio,
  }))

/** One subset's metrics, made up like the rest of the mock report. */
function group(nItems: number, n: number, exact: number, unsafe: number, unsafeOf: number, correct: number): EvalGroup {
  return {
    n, nItems, exactAccuracy: exact, unsafeErrors: unsafe, unsafeDenominator: unsafeOf,
    unsafeUpperBound95: unsafe === 0 ? 3 / unsafeOf : null, catchRate: (unsafeOf - unsafe) / unsafeOf,
    overFlagRate: 1 - correct, unclearRate: 0.08, correctPassRate: correct,
  }
}

export function evalReport(): EvalReport {
  return {
    generatedAt: '2026-10-13T08:00:00Z',
    promptVersion: 'mock',
    models: { mock: 'illustrative values, no model ran' },
    judgePasses: 2,
    nItems: 30,
    nStepRatings: 70,
    metrics: {
      exactAccuracy: 0.857, unsafeErrors: 0, unsafeDenominator: 41, unsafeUpperBound95: 3 / 41, catchRate: 1, overFlagRate: 0.103, unclearRate: 0.071,
      correctPassRate: 0.897, unsafeUpperBound95Items: 3 / 22, unsafeItemDenominator: 22,
    },
    passBar: { exactAccuracyMin: 0.8, unsafeErrorsMax: 0, correctPassMin: 0.75, passed: true },
    byLanguage: {
      ta: { n: 12, exactAccuracy: 0.917, unsafeErrors: 0 },
      bn: { n: 9, exactAccuracy: 0.889, unsafeErrors: 0 },
      hi: { n: 6, exactAccuracy: 0.833, unsafeErrors: 0 },
      or: { n: 4, exactAccuracy: 0.75, unsafeErrors: 0 },
      my: { n: 3, exactAccuracy: 0.667, unsafeErrors: 0 },
      zh: { n: 3, exactAccuracy: 0.833, unsafeErrors: 0 },
    },
    byPattern: {
      complete: { n: 10, exactAccuracy: 0.9, unsafeErrors: 0 },
      one_missing: { n: 8, exactAccuracy: 0.875, unsafeErrors: 0 },
      two_missing: { n: 6, exactAccuracy: 0.833, unsafeErrors: 0 },
      contradicted: { n: 3, exactAccuracy: 1, unsafeErrors: 0 },
      vague: { n: 3, exactAccuracy: 0.667, unsafeErrors: 0 },
    },
    // v0.5 fields, as illustrative as the rest: the Eval page labels them so in mock mode.
    byHeldOut: { heldOut: group(8, 16, 0.75, 0, 9, 0.857), inSet: group(22, 54, 0.889, 0, 32, 0.909) },
    modelOnly: { excludedPatterns: ['silence', 'wrong_language'], ...group(26, 62, 0.871, 0, 37, 0.897) },
    baseline: { keyword: group(30, 70, 0.514, 9, 41, 0.931), keywordNegation: group(30, 70, 0.6, 5, 41, 0.862) },
    testsetSha256: null,
    items: MOCK_EVAL_ITEMS.map((i) => ({
      id: i.id, taskId: i.taskId, workerLang: i.workerLang, pattern: i.pattern, noise: i.noise, gold: i.gold, pred: i.pred, unsafe: false,
      flags: Object.fromEntries(Object.keys(i.gold).map((s) => [s, [] as string[]])),
      // v0.5: as the real report, the English translation only (the Sample page shows it with the stored result).
      heldOut: false, translation: i.translation,
      // v0.5.1: the worker-language transcript and the final ratings, which the Sample page shows with the stored result.
      original: i.original, ratings: mockRatings(i).map(reportRating),
    })),
  }
}

/** The mock check's ratings of an item: what the live try returns, and what the mock report stores (both illustrative). */
function mockRatings(found: MockItem): Rating[] {
  const silent = found.original === ''
  return Object.entries(found.pred).map(([stepId, verdict]) => ({
    stepId,
    verdict,
    reason: silent
      ? 'No speech was heard in the answer.'
      : verdict === 'covered'
        ? 'The answer states the step.'
        : verdict === 'contradicted'
          ? 'The answer states the wrong action for this step.'
          : verdict === 'unclear'
            ? 'The answer touches the step without stating it.'
            : 'The answer does not address the step.',
    flags: silent ? ['no_speech'] : verdict === 'unclear' ? ['low_confidence'] : [],
    confidence: verdict === 'unclear' ? 0.5 : 0.88,
    ...(verdict === 'covered' || verdict === 'contradicted' ? { quote: found.original.slice(0, 18), quoteTranslation: found.translation.slice(0, 24) } : {}),
  }))
}

/** A rating as the report stores it (eval v0.5.1): no confidence, and no empty key. */
const reportRating = ({ stepId, verdict, quote, quoteTranslation, reason, flags }: Rating): EvalReportRating => ({
  stepId,
  verdict,
  ...(quote ? { quote } : {}),
  ...(quoteTranslation ? { quoteTranslation } : {}),
  ...(reason ? { reason } : {}),
  ...(flags.length > 0 ? { flags } : {}),
})

export function evalTry(id: string): EvalTryResult {
  const found = MOCK_EVAL_ITEMS.find((i) => i.id === id)
  if (!found) throw new HttpError(404, 'not_found', 'No such evaluation item.')
  const silent = found.original === ''
  const ratings = mockRatings(found)
  const agreement = Object.fromEntries(Object.entries(found.gold).map(([s, g]) => [s, found.pred[s] === g]))
  const unsafe = Object.entries(found.gold).some(([s, g]) => g !== 'covered' && found.pred[s] === 'covered')
  return {
    item: evalItems().find((i) => i.id === id) as EvalItem,
    round: {
      transcripts: [
        silent
          ? { questionId: found.questionId, original: '', detectedLang: 'none', translation: '', flags: ['no_speech'] }
          : { questionId: found.questionId, original: found.original, detectedLang: found.workerLang, translation: found.translation, flags: [] },
      ],
      passA: ratings,
      passB: ratings.map((r) => (r.verdict === 'unclear' ? { ...r, verdict: 'missed' as const } : r)),
      ratings,
    },
    agreement,
    unsafe,
  }
}
