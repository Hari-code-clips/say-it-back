// Types of the API contract (docs/API.md v0.2). Field names are camelCase on the wire.

export type Lang = 'en' | 'zh' | 'ta' | 'bn' | 'my' | 'hi' | 'or'
export type Verdict = 'covered' | 'missed' | 'contradicted' | 'unclear'
export type SiteId = 'sg' | 'chennai'

export interface Step {
  id: string
  text: string
  hazard: string
  essential: string[]
  source: 'instruction' | 'sop' | 'both'
  sopQuote?: string
  speakable: boolean
}
export interface Conflict {
  stepId?: string
  message: string
}

export interface Question {
  id: string
  text: string
  backTranslation: string
  stepIds: string[]
}
export interface Script {
  instruction: string
  instructionBackTranslation: string
  questions: Question[]
  stepMap: Record<string, number[]>
  closing: string
}
export interface Transcript {
  questionId: string
  original: string
  detectedLang: Lang | 'other' | 'none'
  translation: string
  flags: string[]
}
export interface Rating {
  stepId: string
  verdict: Verdict
  quote?: string
  quoteTranslation?: string
  reason: string
  confidence?: number
  flags: string[]
}
export interface DeliveryCheck {
  segment: string
  similarity: number
  scriptOk: boolean
}
export interface LiveRecord {
  model: string
  startedAt: string
  endedAt?: string
  delivered: Record<string, string>
  heard: Record<string, string>
}
export interface Round {
  n: number
  kind: 'initial' | 'reexplain'
  stepIds: string[]
  supervisorNote?: string
  script: Script
  mode?: 'live' | 'turn'
  transcripts: Transcript[]
  passA: Rating[]
  passB: Rating[]
  ratings: Rating[]
  delivery: DeliveryCheck[]
  live?: LiveRecord
  nextAction: 'decide' | 'reexplain'
  modelIds: Record<string, string>
  timingsMs: Record<string, number>
  createdAt: string
  judgedAt?: string
}
export type Status = 'draft' | 'steps_proposed' | 'steps_confirmed' | 'briefing' | 'judged' | 'decided'
export interface Decision {
  value: 'go' | 'no_go'
  reason?: string
  by?: string
  openStepIds: string[]
  at: string
}
export interface Briefing {
  id: string
  siteId: SiteId
  taskId: string
  sop: { id: string; version: string; title: string; text: string }
  supervisorLang: Lang
  workerLang: Lang
  instruction: string
  status: Status
  steps: Step[]
  stepsVersion: number
  conflicts: Conflict[]
  rounds: Round[]
  latestVerdicts: Record<string, Verdict>
  decision?: Decision
  promptVersion: string
  createdAt: string
  updatedAt: string
}

// Endpoint 5: the contract does not type `taskTitle`; accept a plain string or a per-language map.
export interface BriefingSummary {
  id: string
  siteId: SiteId
  taskId: string
  taskTitle: string | Partial<Record<Lang, string>>
  supervisorLang: Lang
  workerLang: Lang
  status: Status
  rounds: number
  decision?: Decision
  createdAt: string
}

// Endpoints 1-2
export interface Health {
  ok: boolean
  models: { flash: string; live: string; tts: string }
  backends: { flash: string; live: string; tts: string }
  store: string
  judgePasses: number
  promptVersion: string
}
export interface CatalogLanguage {
  name: string
  native: string
  bcp47: string
  script: string
  unicodeRanges: [string, string][]
}
export interface CatalogSite {
  id: SiteId
  name: string
  setting: string
  supervisorLanguages: Lang[]
  defaultSupervisorLanguage: Lang
  workerLanguages: Lang[]
  defaultWorkerLanguage: Lang
  bcp47Overrides?: Partial<Record<Lang, string>>
  context: string
}
export interface CatalogTask {
  id: string
  icon: string
  title: Partial<Record<Lang, string>>
  demoSite: SiteId
  demoPair: { supervisorLang: Lang; workerLang: Lang }
  sop: { id: string; version: string; title: string; text: string }
  sampleInstruction: Partial<Record<Lang, string>>
}
export interface Catalog {
  version: string
  languages: Record<Lang, CatalogLanguage>
  sites: CatalogSite[]
  tasks: CatalogTask[]
}

// Endpoint 11
export interface LiveTicket {
  wsUrl: string
  ticket: string
  model: string
  expiresAt: string
}

// Endpoints 4, 10, 14 request bodies
export interface CreateBriefingBody {
  siteId: SiteId
  taskId: string
  supervisorLang: Lang
  workerLang: Lang
  instruction: string
  sop?: { title: string; text: string }
}
export interface CreateRoundBody {
  stepIds?: string[]
  supervisorNote?: string
}
export interface DecisionBody {
  value: 'go' | 'no_go'
  reason?: string
  by?: string
}

// Endpoints 16-19 (eval)
export interface EvalMetrics {
  exactAccuracy: number
  unsafeErrors: number
  unsafeDenominator: number
  unsafeUpperBound95: number
  catchRate: number
  overFlagRate: number
  unclearRate: number
}
export interface EvalBreakdown {
  n: number
  exactAccuracy: number
  unsafeErrors: number
}
export interface EvalReportItem {
  id: string
  taskId: string
  workerLang: Lang
  pattern: string
  noise: string
  gold: Record<string, Verdict>
  pred: Record<string, Verdict>
  unsafe: boolean
  flags: Record<string, string[]>
}
export interface EvalReport {
  generatedAt: string
  promptVersion: string
  models: Record<string, string>
  judgePasses: number
  nItems: number
  nStepRatings: number
  metrics: EvalMetrics
  passBar: { exactAccuracyMin: number; unsafeErrorsMax: number; passed: boolean }
  byLanguage: Record<string, EvalBreakdown>
  byPattern: Record<string, EvalBreakdown>
  items: EvalReportItem[]
}
export interface EvalItem {
  id: string
  taskId: string
  questionId: string
  workerLang: Lang
  pattern: string
  noise: string
  source: string
  answerGloss: string
  gold: Record<string, Verdict>
}
export interface EvalTryResult {
  item: EvalItem
  round: Pick<Round, 'transcripts' | 'passA' | 'passB' | 'ratings'>
  agreement: Record<string, boolean>
  unsafe: boolean
}
