import type { Lang } from '../../api/types.ts'
import { WORKER_WORDS } from '../../i18n/worker.ts'
import { useT, type Translate } from '../../i18n/index.tsx'
import type { StagePhase } from '../../live/session.ts'
import type { IconName } from '../../theme/iconNames.ts'
import { Button, IconButton } from '../../ui/Button.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'
import { Caption } from './Caption.tsx'
import { Orb, type OrbTone } from './Orb.tsx'
import type { RunMode } from './useBriefingRun.ts'

interface StageProps {
  phase: StagePhase
  mode: RunMode
  workerLang: Lang
  workerTag: string
  questionIds: string[]
  captions: { model: string; worker: string }
  /** The worker's voice is being picked up. */
  heard: boolean
  getLevel: () => number
  onDone: () => void
  onLeave: () => void
}

/** Type sizes of the model's caption, large to small (see Caption). The smallest, 22 px, is the floor. */
const MODEL_SIZES = ['text-worker', 'text-worker-md', 'text-worker-min'] as const
/** The worker's own words are shown at one size. */
const WORKER_SIZES = ['text-worker-sm'] as const

/** Index of the current step among [instruction, ...questions, closing]; -1 while connecting. */
function progressIndex(phase: StagePhase, questionIds: string[]): number {
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

/** The supervisor-language line that says what the phone is doing (read out by screen readers). */
function statusText(t: Translate, phase: StagePhase, questionIds: string[]): string {
  const n = (qid: string | undefined) => Math.max(1, questionIds.indexOf(qid ?? '') + 1)
  const total = questionIds.length
  switch (phase.kind) {
    case 'connecting':
      return t('brief.status.connecting')
    case 'finishing':
      return t('brief.status.finishing')
    case 'listening':
      return t('brief.status.listening', { n: n(phase.qid), total })
    case 'speaking':
      if (phase.segment === 'instruction') return t('brief.status.instruction')
      if (phase.segment === 'closing') return t('brief.status.closing')
      if (phase.segment === 'thanks') return t('brief.status.thanks')
      return t('brief.status.asking', { n: n(phase.qid), total })
  }
}

/** One dot per step of the round: the instruction, each question, the closing. */
function ProgressDots({ count, current }: { count: number; current: number }) {
  return (
    <ol aria-hidden="true" className="mx-auto mt-3 flex shrink-0 items-center gap-2">
      {Array.from({ length: count }, (_, i) => (
        <li
          key={i}
          className={cx(
            'h-2.5 rounded-full transition-all duration-300',
            i === current ? 'w-8 bg-primary' : i < current ? 'w-2.5 bg-primary/60' : 'w-2.5 bg-outline-variant',
          )}
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
 * a growing caption is never re-announced; the status line above says what is happening.
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

export function BriefStage({ phase, mode, workerLang, workerTag, questionIds, captions, heard, getLevel, onDone, onLeave }: StageProps) {
  const t = useT()
  const words = WORKER_WORDS[workerLang]
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
    <main id="main" className="mx-auto flex h-dvh min-h-[31rem] w-full max-w-3xl flex-col px-4 pt-2 sm:px-6">
      <h1 className="sr-only">{t('brief.title')}</h1>
      <div className="flex shrink-0 items-center gap-2">
        <IconButton icon="close" label={t('brief.leave')} onClick={onLeave} />
        <p role="status" aria-live="polite" className="min-w-0 flex-1 text-body-md text-on-surface-variant">
          {statusText(t, phase, questionIds)}
        </p>
        <StatusChip icon={mode === 'live' ? 'record_voice_over' : 'volume_up'}>{t(mode === 'live' ? 'brief.mode.live' : 'brief.mode.turn')}</StatusChip>
      </div>

      <ProgressDots count={segments} current={current} />

      {/* The orb gives up height on a short phone (--orb-size); the gaps tighten below 44rem. */}
      <div
        className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 py-3 [--orb-size:clamp(9rem,min(52vw,100dvh_-_32rem),16rem)] [@media(min-height:44rem)]:gap-6 [@media(min-height:44rem)]:py-6"
        lang={workerTag}
      >
        <Orb tone={tone} icon={icon} getLevel={getLevel} />
        <p className="shrink-0 text-worker-sm font-semibold uppercase tracking-wide text-on-surface-variant">{word}</p>

        <Captions model={captions.model} worker={captions.worker} listening={listening} heard={heard} />
      </div>

      {/* The Done button's bar keeps its height whether or not the button shows, so the caption above it never jumps. */}
      <div className="sticky bottom-0 -mx-4 min-h-[calc(5.25rem_+_max(1rem,env(safe-area-inset-bottom)))] shrink-0 bg-surface/90 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur sm:-mx-6 sm:px-6">
        {listening && (
          <Button variant="success" size="xl" icon="check" onClick={onDone} lang={workerTag}>
            {words.done}
            <span className="sr-only"> ({t('brief.doneSr')})</span>
          </Button>
        )}
      </div>
    </main>
  )
}
