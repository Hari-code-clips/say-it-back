/* Hallmark · component: the worker's live screen · genre: modern-minimal · macrostructure: Workbench (one function, one action) · theme: design.md
 * F2 (build-notes/25): worker-language text, icons, the one action (Done) and the red problem button, nothing else. No close button,
 * no mode chip, no status line in the supervisor's language, no sample button: this file does not use the supervisor's strings (no
 * useT). The supervisor's only control is the held corner button the shell draws.
 * states: orb (connecting · phone speaking · worker's turn · finishing), Done (default · hover · focus-visible · active · disabled
 *         while a stored sample plays), the problem button (ReportPanel). A visually hidden h1 (the status word) names the screen.
 */
import type { WorkerWords } from '../../i18n/worker.ts'
import type { StagePhase } from '../../live/session.ts'
import type { IconName } from '../../theme/iconNames.ts'
import { Button } from '../../ui/Button.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'
import { Caption } from './Caption.tsx'
import { Orb, type OrbTone } from './Orb.tsx'
import { ReportPanel } from './ReportPanel.tsx'
import type { HazardReport } from './useHazardReport.ts'
import { WorkerShell, type SupervisorHold } from './WorkerScreens.tsx'

interface StageProps {
  phase: StagePhase
  words: WorkerWords
  workerTag: string
  questionIds: string[]
  captions: { model: string; worker: string }
  /** The worker's voice is being picked up. */
  heard: boolean
  getLevel: () => number
  onDone: () => void
  /** The supervisor's one control: hold to end the round. */
  hold: SupervisorHold
  /** The worker's "Report a problem": shown whenever no answer window is open. */
  report: HazardReport
  /** A stored sample answer is being played into this window (the supervisor chose it): Done would cut it short. */
  samplePlaying?: boolean
}

/** Type sizes of the model's caption, large to small (see Caption). The smallest, 22 px, is the floor. */
const MODEL_SIZES = ['text-worker', 'text-worker-md', 'text-worker-min'] as const
/** The worker's own words are shown at one size. */
const WORKER_SIZES = ['text-worker-sm'] as const

/** Index of the current step among [instruction, ...questions, closing]; -1 while connecting. */
export function progressIndex(phase: StagePhase, questionIds: string[]): number {
  switch (phase.kind) {
    case 'connecting':
      return -1
    case 'speaking':
      if (phase.segment === 'instruction') return 0
      if (phase.segment === 'closing') return questionIds.length + 1
      return 1 + Math.max(0, questionIds.indexOf(phase.qid ?? ''))
    case 'listening':
      return 1 + Math.max(0, questionIds.indexOf(phase.qid))
    case 'finishing':
      return questionIds.length + 1
  }
}

/**
 * One dot per step of the round: the instruction, each question, the closing. Done = filled, now = a wide bar, still to come =
 * hollow, so the state is never a colour alone and nothing animates its width.
 */
function ProgressDots({ count, current }: { count: number; current: number }) {
  return (
    <ol aria-hidden="true" className="flex shrink-0 items-center gap-1">
      {Array.from({ length: count }, (_, i) => (
        <li
          key={i}
          className={cx('h-2.5 rounded-full', i === current ? 'w-6 bg-primary' : i < current ? 'w-2.5 bg-primary' : 'w-2.5 border-2 border-outline')}
        />
      ))}
    </ol>
  )
}

interface CaptionsProps {
  model: string
  worker: string
  listening: boolean
  /** The worker's voice is being picked up. */
  heard: boolean
}

/**
 * What the phone says, and under it what the worker said (a "..." placeholder while they speak). Not a live region, so
 * a growing caption is never re-announced; the word above says what is happening.
 */
function Captions({ model, worker, listening, heard }: CaptionsProps) {
  return (
    <div className="flex min-h-0 w-full flex-col gap-4 text-center" aria-live="off">
      <Caption text={model} sizes={MODEL_SIZES} className="min-h-[3.5em] whitespace-pre-line text-on-surface" />
      {(listening || worker) && (
        <div
          className={cx(
            'mx-auto flex min-h-0 w-full max-w-xl items-stretch justify-center gap-2 transition-opacity',
            worker ? 'text-on-surface-variant opacity-100' : 'opacity-60',
          )}
        >
          <Icon name="mic" className={cx('mt-1 self-start text-[1.5rem]', heard && 'text-success')} />
          <Caption text={worker || '…'} sizes={WORKER_SIZES} className="min-h-[2.5em] min-w-0" />
        </div>
      )}
    </div>
  )
}

export function BriefStage({ phase, words, workerTag, questionIds, captions, heard, getLevel, onDone, hold, report, samplePlaying }: StageProps) {
  const listening = phase.kind === 'listening'
  const speaking = phase.kind === 'speaking'
  const tone: OrbTone = listening ? 'listening' : speaking ? 'speaking' : 'thinking'
  const icon: IconName = listening ? 'mic' : speaking ? 'volume_up' : 'hourglass_top'
  const word = listening ? words.speak : speaking ? words.listen : words.wait
  const current = progressIndex(phase, questionIds)
  const segments = questionIds.length + 2

  return (
    // Exactly one screen tall: the caption gets whatever room is left and never pushes the page past the bottom bar.
    // (Below 31rem, a phone on its side, the page scrolls as it always did.)
    <WorkerShell
      exact
      hold={hold}
      leading={<ProgressDots count={segments} current={current} />}
      bottom={
        // The bottom bar keeps its height between the Done button and "Report a problem", so the caption above never jumps.
        <div className="sticky bottom-0 -mx-4 flex min-h-[calc(5.25rem_+_max(1rem,env(safe-area-inset-bottom)))] shrink-0 flex-col justify-end gap-2 bg-worker-ground/90 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur sm:-mx-6 sm:px-6">
          {listening ? (
            !samplePlaying && (
              <Button variant="success" size="xl" icon="check" onClick={onDone} lang={workerTag}>
                {words.done}
              </Button>
            )
          ) : (
            <ReportPanel report={report} words={words} workerTag={workerTag} />
          )}
        </div>
      }
    >
      {/* The orb gives up height on a short phone (--orb-size); the gaps tighten below 44rem. */}
      <div
        className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 py-3 [--orb-size:clamp(9rem,min(52vw,100dvh_-_32rem),16rem)] [@media(min-height:44rem)]:gap-6 [@media(min-height:44rem)]:py-6"
        lang={workerTag}
      >
        {/* The screen's h1 (build-notes/37 section 5, axe `page-has-heading-one`): the status word, in the worker's language, for a
            screen reader only. A new stage moves the focus to it (BriefScreen useStageFocus); the status line below speaks each change. */}
        <h1 tabIndex={-1} className="sr-only">
          {word}
        </h1>
        <Orb tone={tone} icon={icon} getLevel={getLevel} />
        {/* The one status line, in the worker's language; a polite live region, so a change of state is spoken in it. */}
        <p role="status" aria-live="polite" className="shrink-0 text-center text-worker-sm font-semibold text-on-surface">
          {word}
        </p>

        <Captions model={captions.model} worker={captions.worker} listening={listening} heard={heard} />
      </div>
    </WorkerShell>
  )
}
