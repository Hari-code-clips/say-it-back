// Types of the API contract (docs/API.md v0.4). Field names are camelCase on the wire.

export type Lang = 'en' | 'zh' | 'ta' | 'bn' | 'my' | 'hi' | 'or' | 'te'
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
/** v0.4: why a delivered segment is not `ok` (docs/API.md, "v0.4 details", Delivery check). */
export type DeliveryIssue =
  | 'not_spoken'
  | 'wrong_script'
  | 'low_similarity'
  | 'negation_changed'
  | 'number_changed'
  | 'reply_too_long'
  /** v0.4 review: the reply after an answer repeated words of the script (not only the language's thanks words). */
  | 'reply_not_neutral'
export interface DeliveryCheck {
  /** "instruction" | a question id | "closing" | "<qid>.reply" */
  segment: string
  similarity: number
  scriptOk: boolean
  /** v0.4: the server's verdict on the segment. The browser never applies a threshold of its own. */
  ok: boolean
  issues: DeliveryIssue[]
  /** v0.4: what Live said for this segment. */
  said?: string
}
/** v0.4: a worker's report of a problem. Go stays locked until the supervisor acknowledges every one. */
export interface Hazard {
  id: string
  round?: number
  kind: 'voice' | 'tap'
  original: string
  translation: string
  detectedLang: Lang | 'other' | 'none'
  raisedAt: string
  ack?: { note: string; by?: string; at: string }
}
export type ChainEventType =
  | 'created'
  | 'instruction_edited'
  | 'steps_proposed'
  | 'steps_confirmed'
  | 'round_created'
  | 'script_approved'
  | 'round_judged'
  | 'hazard_raised'
  | 'hazard_acknowledged'
  | 'decided'
  /** Privacy (16 Oct): the worker gave or declined consent for round `data.n` (`data.given`). */
  | 'consent'
/** v0.4: one link of the record's hash chain. */
export interface ChainEvent {
  seq: number
  type: ChainEventType
  at: string
  data: Record<string, unknown>
  prevHash: string
  hash: string
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
  /** v0.4: the supervisor confirmed this round's script (endpoint 23); nothing is spoken before. */
  approvedAt?: string
  approvedBy?: string
  /** v0.4: question ids answered with a stored synthetic sample answer (endpoint 24), not by a person. */
  sampleAnswers?: string[]
  judgedAt?: string
  /** Privacy (16 Oct): the worker's own choice before any answer of the round is recorded; absent until they choose. */
  consent?: { given: boolean; at: string }
}
export type Status = 'draft' | 'steps_proposed' | 'steps_confirmed' | 'briefing' | 'judged' | 'decided'
export interface Decision {
  value: 'go' | 'no_go'
  reason?: string
  by?: string
  openStepIds: string[]
  /** v0.4: reported problems still unacknowledged when the decision was recorded (a No-go only). */
  openHazardIds?: string[]
  at: string
  /** 2026-10-17: a Go after the worker declined the AI check, so the supervisor checked them in person. Absent otherwise. */
  inPerson?: boolean
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
  /** v0.4. A record written before v0.4 has none, so readers use `?? []`. */
  hazards?: Hazard[]
  /** v0.4: append-only; the server writes them. */
  events?: ChainEvent[]
  /** v0.4: the last event's hash ("" before the first event). */
  recordHash?: string
  /**
   * v0.4 review, derived and read-only: steps whose latest covering rating came only from questions answered with a stored
   * sample. They keep their verdict, are tagged, and count as open for the decision (Go needs a reason).
   */
  sampleCoveredStepIds?: string[]
  /** v0.5.2: the permit-to-work this briefing checks one worker for; null (or absent) when it belongs to none. */
  permit?: PermitLink | null
  /** SIB_OUTBOX (docs/EPERMIT_ADAPTER.md): where the decision was sent; null before it, absent when the outbox is off. */
  delivery?: Delivery | null
  /** Library (16 Oct): the approved SOP library version this briefing started from; absent for a catalog or pasted SOP. */
  sopRef?: SopRef | null
  promptVersion: string
  createdAt: string
  updatedAt: string
}
export type DeliveryStatus = 'pending' | 'delivered' | 'failed'
/** One target of the decision: a Google Chat space or a permit system. Never its URL. */
export interface DeliveryTarget {
  kind: 'chat' | 'permit'
  status: DeliveryStatus
  attempts: number
  /** A class only: "http_503", "timeout", "duplicate" (delivered: it already had it)... */
  lastError?: string | null
  nextAttemptAt?: string | null
  deliveredAt?: string | null
}
export interface Delivery {
  status: DeliveryStatus
  targets: DeliveryTarget[]
}
/** v0.5.2 (docs/API.md, "Permit-to-work grouping"): one worker on a high-risk permit. The slot is never a name or an ID. */
export interface PermitLink {
  /** The permit number as written on the permit: 1-32 characters of [A-Za-z0-9._/-]. */
  ref: string
  /** How many workers the permit covers, 1-6. */
  crewSize: number
  /** Which worker on the permit this briefing is, 1..crewSize. */
  slot: number
}

/** Library (docs/API.md Deviations 2026-10-16): a site's SOPs, their numbered versions and each version's pre-approved steps. */
export interface SopRef {
  sopId: string
  version: number
}
export type LibraryActor = 'admin' | 'safety_officer' | 'supervisor' | 'device' | 'catalog'
export interface LibraryVersion {
  number: number
  text: string
  /** The language the steps are written in; a briefing can use the version only with this supervisor language. */
  lang: Lang
  createdAt: string
  createdBy: LibraryActor
  changeNote: string
  status: 'draft' | 'approved'
  steps: Step[]
  approvedBy?: LibraryActor
  approvedAt?: string
  /** A seed from the demo catalog: it never changes. */
  readOnly: boolean
}
export interface LibraryEntry {
  id: string
  siteId: SiteId
  title: string
  taskId?: string
  seeded: boolean
  versions: LibraryVersion[]
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
  /** v0.5.2. */
  permit?: PermitLink | null
  createdAt: string
}

// Endpoints 1-2
export interface Health {
  ok: boolean
  models: { flash: string; judgeB?: string; live: string; tts: string }
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
  /** v0.4: "word" (whole words, `en`) or "substring" (the normalised text, other languages). */
  match?: 'word' | 'substring'
  /** v0.4: the language's negation markers, for the delivery check. */
  negationMarkers?: string[]
  numberWords?: string[]
  /** v0.4 review: the words a neutral thanks may use (`reply_not_neutral`). */
  thanksWords?: string[]
}
export interface CatalogSite {
  id: SiteId
  name: string
  setting: string
  supervisorLanguages: Lang[]
  defaultSupervisorLanguage: Lang
  workerLanguages: Lang[]
  /** 16 Oct breadth: worker languages offered last, for an evaluator who plays the worker ("English (for evaluators)"). Not product languages. */
  evaluatorLanguages?: Lang[]
  defaultWorkerLanguage: Lang
  bcp47Overrides?: Partial<Record<Lang, string>>
  context: string
}
export interface CatalogTask {
  id: string
  icon: string
  /** 17 Oct: the work domain ("construction", "utilities", "marine", "process", "manufacturing", "telecom"), which the Start
   * screen's task picker groups by. Optional: a server from before then sends none. */
  domain?: string
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

// Endpoint 24: the catalog's scripted demo answers that have a stored synthetic clip, one per question of a demo round
// (2026-10-16). A server from before then lists one per round, with no questionId and no stepIds.
export interface DemoAnswer {
  taskId: string
  workerLang: Lang
  /** 1 or 2: round 2 serves every later round. */
  round: number
  gloss: string
  /** The catalog reference question the answer was written for. */
  questionId?: string
  /** That question's steps (catalog reference step ids). */
  stepIds?: string[]
}

// Endpoint 25
export interface VerifyResult {
  ok: boolean
  /** The number of events checked. */
  events: number
  recordHash: string
  brokenAt?: number
  reason?: string
}

// Endpoints 4, 10, 14 request bodies
export interface CreateBriefingBody {
  siteId: SiteId
  taskId: string
  supervisorLang: Lang
  workerLang: Lang
  instruction: string
  sop?: { title: string; text: string }
  /** v0.5.2: optional; it cannot be changed after creation. */
  permit?: PermitLink
  /** Library (16 Oct): start from an approved library version's steps (no extraction call); then no `sop`. */
  sopRef?: SopRef
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
  /** Eval v0.5 (absent from older reports): gold "covered" steps rated covered, as a share. Null with no such step. */
  correctPassRate?: number | null
  /** Eval v0.5: the 95% bound over items with a gold-miss step, and how many such items there are. */
  unsafeUpperBound95Items?: number | null
  unsafeItemDenominator?: number
}
export interface EvalBreakdown {
  n: number
  exactAccuracy: number | null
  unsafeErrors: number
}
/** Eval v0.5: every metric for a subset of the step ratings, with its size. A ratio is null when its denominator is 0. */
export interface EvalGroup extends EvalBreakdown {
  nItems: number
  unsafeDenominator: number
  unsafeUpperBound95: number | null
  catchRate: number | null
  overFlagRate: number | null
  unclearRate: number | null
  correctPassRate?: number | null
  unsafeUpperBound95Items?: number | null
  unsafeItemDenominator?: number
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
  /** Eval v0.5: one of the two held-out tasks. */
  heldOut?: boolean
  /** Eval v0.5: the blind transcriber's English translation of the answer (first run). */
  translation?: string
  /** Eval v0.5.1: the blind transcriber's text in the worker's language (first run). */
  original?: string
  /** Eval v0.5.1: the first run's final, guarded ratings, gold order; keys left out when empty, unrated steps left out. */
  ratings?: EvalReportRating[]
}
export interface EvalReportRating {
  stepId: string
  verdict: Verdict
  quote?: string
  quoteTranslation?: string
  reason?: string
  flags?: string[]
}
export interface EvalReport {
  generatedAt: string
  promptVersion: string
  models: Record<string, string>
  judgePasses: number
  nItems: number
  nStepRatings: number
  metrics: EvalMetrics
  /** v0.5: `correctPassMin` (0.75) joins the bar; older reports lack it. */
  passBar: { exactAccuracyMin: number; unsafeErrorsMax: number; correctPassMin?: number; passed: boolean }
  byLanguage: Record<string, EvalBreakdown>
  byPattern: Record<string, EvalBreakdown>
  items: EvalReportItem[]
  /** Eval v0.4: every item of the test set was run. False = a partial run, whose numbers are not the headline. */
  complete?: boolean
  // Eval v0.5, all additive (docs/API.md, Deviations 2026-10-15):
  /** The two held-out tasks (no prompt was tuned on them) against the rest. */
  byHeldOut?: { heldOut: EvalGroup; inSet: EvalGroup }
  /** Without the patterns the code guards catch (silence, wrong language): the model's own share. */
  modelOnly?: EvalGroup & { excludedPatterns: string[] }
  /** Keyword baselines on the same English translations: `keyword` and `keywordNegation`. */
  baseline?: Record<string, EvalGroup>
  testsetSha256?: string | null
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
  /** v0.4: each gold step id -> the catalog's reference step text (English). */
  steps?: Record<string, string>
  /** v0.4: the catalog's reference question (English). */
  questionText?: string
  /** v0.4: the clip is on the server. */
  hasAudio?: boolean
}
export interface EvalTryResult {
  item: EvalItem
  round: Pick<Round, 'transcripts' | 'passA' | 'passB' | 'ratings'>
  agreement: Record<string, boolean>
  unsafe: boolean
}
