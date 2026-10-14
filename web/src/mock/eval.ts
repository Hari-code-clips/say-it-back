import type { EvalItem, EvalReport, EvalTryResult, Lang, Rating, Verdict } from '../api/types.ts'
import { HttpError } from './util.ts'

// Sample evaluation data for mock mode. The numbers are made up to show the page (the Eval page
// says so); the real report comes from eval/reports/latest.json through GET /api/eval/latest.

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
): MockItem => ({ id, taskId, questionId, workerLang, pattern, noise, source: 'synthetic_tts', answerGloss, gold, pred, original, translation: answerGloss })

export const MOCK_EVAL_ITEMS: MockItem[] = [
  item('panel-isolation.q1.ta.demo.clean', 'panel-isolation', 'q1', 'ta', 'demo', 'clean', "I'll switch off the breaker and open it.",
    { s1: 'covered', s2: 'missed', s3: 'missed' }, { s1: 'covered', s2: 'missed', s3: 'missed' }, 'நான் பிரேக்கரை ஆஃப் பண்ணிட்டு திறப்பேன்.'),
  item('panel-isolation.q1.ta.complete.clean', 'panel-isolation', 'q1', 'ta', 'complete', 'clean',
    "First I'll switch off the breaker, then put on the lock and tag, and only after testing with the tester that there's no current will I open the panel.",
    { s1: 'covered', s2: 'covered', s3: 'covered' }, { s1: 'covered', s2: 'covered', s3: 'covered' },
    'முதல்ல பிரேக்கரை ஆஃப் பண்ணுவேன், அப்புறம் லாக் போட்டு டேக் மாட்டுவேன், டெஸ்டர் வச்சு கரண்ட் இல்லைன்னு செக் பண்ணிட்டுதான் பேனலைத் திறப்பேன்.'),
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
  MOCK_EVAL_ITEMS.map(({ id, taskId, questionId, workerLang, pattern, noise, source, answerGloss, gold }) => ({ id, taskId, questionId, workerLang, pattern, noise, source, answerGloss, gold }))

export function evalReport(): EvalReport {
  return {
    generatedAt: '2026-10-13T08:00:00Z',
    promptVersion: 'mock-2026-10-13',
    models: { flash: 'gemini-3.8-flash (mock)' },
    judgePasses: 2,
    nItems: 30,
    nStepRatings: 70,
    metrics: { exactAccuracy: 0.857, unsafeErrors: 0, unsafeDenominator: 41, unsafeUpperBound95: 3 / 41, catchRate: 1, overFlagRate: 0.103, unclearRate: 0.071 },
    passBar: { exactAccuracyMin: 0.8, unsafeErrorsMax: 0, passed: true },
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
    items: MOCK_EVAL_ITEMS.map((i) => ({
      id: i.id, taskId: i.taskId, workerLang: i.workerLang, pattern: i.pattern, noise: i.noise, gold: i.gold, pred: i.pred, unsafe: false,
      flags: Object.fromEntries(Object.keys(i.gold).map((s) => [s, [] as string[]])),
    })),
  }
}

export function evalTry(id: string): EvalTryResult {
  const found = MOCK_EVAL_ITEMS.find((i) => i.id === id)
  if (!found) throw new HttpError(404, 'not_found', 'No such evaluation item.')
  const ratings: Rating[] = Object.entries(found.pred).map(([stepId, verdict]) => ({
    stepId,
    verdict,
    reason: verdict === 'covered' ? 'The answer states the step.' : verdict === 'unclear' ? 'The answer touches the step without stating it.' : 'The answer does not address the step.',
    flags: verdict === 'unclear' ? ['low_confidence'] : [],
    confidence: verdict === 'unclear' ? 0.5 : 0.88,
    ...(verdict === 'covered' ? { quote: found.original.slice(0, 18), quoteTranslation: found.translation.slice(0, 24) } : {}),
  }))
  const agreement = Object.fromEntries(Object.entries(found.gold).map(([s, g]) => [s, found.pred[s] === g]))
  const unsafe = Object.entries(found.gold).some(([s, g]) => g !== 'covered' && found.pred[s] === 'covered')
  return {
    item: evalItems().find((i) => i.id === id) as EvalItem,
    round: {
      transcripts: [{ questionId: found.questionId, original: found.original, detectedLang: found.workerLang, translation: found.translation, flags: [] }],
      passA: ratings,
      passB: ratings.map((r) => (r.verdict === 'unclear' ? { ...r, verdict: 'missed' as const } : r)),
      ratings,
    },
    agreement,
    unsafe,
  }
}
