/* Hallmark · components: the worker-held screens (shell, Start, failure, hand-back) · genre: modern-minimal · macrostructure: Workbench
 * (one function, one action) · theme: design.md. From the moment the worker holds the phone until it is handed back, these screens show
 * only worker-language text, icons, the single action (Start, Done) and the red problem button. The supervisor has ONE control, a
 * small held button in a corner (HoldButton), in the supervisor's language: nothing here calls useT, so no supervisor string can leak in
 * except through the `hold` props the supervisor's own screen builds (the corner button, and the hand-back's "I have the phone").
 * states: Start (default · hover · focus-visible · active · disabled while a report is open · loading n/a · error n/a · success n/a);
 *         the held button and the problem button have their own states (HoldButton, ReportPanel).
 */
import type { ReactNode } from 'react'
import type { WorkerWords } from '../../i18n/worker.ts'
import { Button } from '../../ui/Button.tsx'
import { cx } from '../../ui/cx.ts'
import { HoldButton } from '../../ui/HoldButton.tsx'
import { Icon } from '../../ui/Icon.tsx'
import type { IconName } from '../../theme/iconNames.ts'
import { ReportPanel } from './ReportPanel.tsx'
import type { HazardReport } from './useHazardReport.ts'

/** The supervisor's one control on a worker screen: a button held for 1.5 s, in the supervisor's language. */
export interface SupervisorHold {
  /** What the control is called: its text, or, for an icon-only corner lock, its accessible name and its tooltip. */
  label: string
  /** The corner lock: a 48 x 48 lock, ink-subtle, with no visible text until it is held. */
  iconOnly?: boolean
  /** Shown beside the lock only while it is being held, so the supervisor sees what the hold will do ("End round"). */
  holdingLabel?: string
  /** Said when the press was too short, and the button's description. */
  hint: string
  /** What assistive technology is asked when it activates the button without a hold. */
  confirm: { title: string; body?: string; confirmLabel: string; cancelLabel: string }
  onConfirm: () => void
}

interface ShellProps {
  /** Exactly one screen tall (the live session: the caption takes what is left). Otherwise at least one screen. */
  exact?: boolean
  hold?: SupervisorHold
  /** Left of the corner button: the round's progress dots. */
  leading?: ReactNode
  children: ReactNode
  /** Fixed to the bottom of the screen. */
  bottom?: ReactNode
}

/**
 * The supervisor's held button. The "keep holding" hint that a too-short press shows is taken out of the flow (and given a paper
 * ground), so it never makes the screen taller or pushes the worker's content: it floats beside the button for a moment.
 * `className` places the hint (right, top, max-width) and the button's own width.
 */
function HeldButton({ hold, className }: { hold: SupervisorHold; className: string }) {
  return (
    <HoldButton
      icon="lock"
      hint={hold.hint}
      confirm={hold.confirm}
      onConfirm={hold.onConfirm}
      className={cx('[&>p]:absolute [&>p]:z-10 [&>p]:mt-1 [&>p]:w-max [&>p]:rounded-md [&>p]:bg-surface [&>p]:px-3 [&>p]:py-2 [&>p]:shadow-elev-2', className)}
    >
      {hold.label}
    </HoldButton>
  )
}

/**
 * The corner lock of a worker's Start and live screens: icon-only, 48 x 48, in the quiet ink-2 (no border, no text), top right.
 * Its label is its accessible name (screen-reader text) and a tooltip (`title`). While it is held the button shows its border, a
 * paper ground and the short `holdingLabel`, beside the 8 px fill that counts the 1.5 s. It sits in a fixed 48 px box and grows
 * over it, so holding never moves the screen. The tweaks reach HoldButton's own button through its `data-phase` attribute
 * (idle, holding, confirmed), because HoldButton has no icon-only mode of its own.
 */
function CornerLock({ hold }: { hold: SupervisorHold }) {
  return (
    <div title={hold.label} className="relative size-12 shrink-0">
      <HoldButton
        icon="lock"
        hint={hold.hint}
        confirm={hold.confirm}
        onConfirm={hold.onConfirm}
        className={cx(
          'absolute right-0 top-0 z-10 w-max',
          '[&>button]:size-12 [&>button]:gap-0 [&>button]:border-transparent [&>button]:p-0 [&>button]:text-on-surface-variant',
          // Written out in full: Tailwind finds a class only where it is spelled whole in the source.
          '[&>button:not([data-phase=idle])]:w-auto [&>button:not([data-phase=idle])]:gap-2 [&>button:not([data-phase=idle])]:border-outline [&>button:not([data-phase=idle])]:bg-surface [&>button:not([data-phase=idle])]:px-4 [&>button:not([data-phase=idle])]:text-on-surface [&>button:not([data-phase=idle])_.held-label]:inline',
          '[&>p]:absolute [&>p]:right-0 [&>p]:top-full [&>p]:z-10 [&>p]:mt-1 [&>p]:w-max [&>p]:max-w-[min(20rem,calc(100vw-2rem))] [&>p]:rounded-md [&>p]:bg-surface [&>p]:px-3 [&>p]:py-2 [&>p]:shadow-elev-2',
        )}
      >
        <span className="sr-only">{hold.label}</span>
        <span aria-hidden="true" className="held-label hidden whitespace-nowrap">
          {hold.holdingLabel}
        </span>
      </HoldButton>
    </div>
  )
}

/**
 * The frame of every worker screen: a top row that holds the supervisor's corner button, the screen, and a bottom area. The
 * whole screen sits on the calm blue `worker` ground (design.md), so anyone can see at a glance that the worker holds the phone.
 */
export function WorkerShell({ exact, hold, leading, children, bottom }: ShellProps) {
  return (
    <div className="bg-worker-ground">
      <main
        id="main"
        tabIndex={-1}
        className={cx('mx-auto flex w-full max-w-3xl flex-col px-4 pt-2 sm:px-6', exact ? 'h-dvh min-h-[31rem]' : 'min-h-dvh')}
      >
        <div className="flex min-h-12 shrink-0 flex-wrap items-center justify-between gap-x-2 gap-y-1">
          <div className="flex min-h-12 items-center">{leading}</div>
          {hold &&
            (hold.iconOnly ? (
              <CornerLock hold={hold} />
            ) : (
              <HeldButton hold={hold} className="relative [&>p]:right-0 [&>p]:top-full [&>p]:max-w-[min(20rem,calc(100vw-2rem))]" />
            ))}
        </div>
        {children}
        {bottom}
      </main>
    </div>
  )
}

export function Disc({ icon, className }: { icon: IconName; className?: string }) {
  return (
    <span aria-hidden="true" className={cx('grid size-20 shrink-0 place-items-center rounded-full bg-surface-container-lowest text-primary', className)}>
      <Icon name={icon} className="text-[2.5rem]" />
    </span>
  )
}

/** A phone, an arrow, a person: "give the phone to the supervisor", with no word in it. Not a warning: there is nothing for the worker to fix. */
export function GivePhone() {
  return (
    <div aria-hidden="true" className="flex items-center justify-center gap-3 text-on-surface">
      <Disc icon="smartphone" />
      <Icon name="arrow_forward" className="text-[2.5rem]" />
      <Disc icon="groups" />
    </div>
  )
}

interface ReadyProps {
  words: WorkerWords
  workerTag: string
  hold: SupervisorHold
  report: HazardReport
  onStart: () => void
}

/**
 * The worker has the phone: one big Start (worker language) and the problem button. Above Start, two calm lines say what happens
 * next and that this is not a test of the worker (product rule 3): an honest "it is not clear" is the answer the check needs.
 */
export function WorkerReady({ words, workerTag, hold, report, onStart }: ReadyProps) {
  return (
    <WorkerShell hold={hold}>
      <h1 lang={workerTag} tabIndex={-1} className="sr-only">
        {words.start}
      </h1>
      {/* Short screens (under 640 px tall, e.g. 320 x 568): the ear goes and the words shrink, so Start and the problem button
          stay on the first screen. Written out in full: Tailwind finds a class only where it is spelled whole in the source. */}
      <div lang={workerTag} className="flex flex-1 flex-col items-center justify-center gap-8 py-8 [@media(max-height:40rem)]:gap-4 [@media(max-height:40rem)]:py-3">
        <Disc icon="hearing" className="size-24 [@media(max-height:40rem)]:hidden" />
        <div className="max-w-md space-y-3 text-center [@media(max-height:40rem)]:space-y-2">
          <p className="script-text text-title-lg text-on-surface [@media(max-height:40rem)]:text-title-md">{words.readyHow}</p>
          <p className="script-text text-title-lg font-normal text-on-surface-variant [@media(max-height:40rem)]:text-body-lg">{words.readyKind}</p>
        </div>
        <div className="w-full max-w-md">
          <Button size="xl" icon="play_arrow" disabled={report.holds} onClick={onStart}>
            {words.start}
          </Button>
        </div>
      </div>
      <ReportPanel report={report} words={words} workerTag={workerTag} className="pb-4" />
    </WorkerShell>
  )
}

interface FailedProps {
  words: WorkerWords
  workerTag: string
  /** "I'm the supervisor": the supervisor's way to the details. */
  hold: SupervisorHold
  report: HazardReport
}

/**
 * Anything that went wrong while the worker holds the phone: the worker is told, in their language and with a picture, to give
 * the phone to the supervisor. No reason, no English, no recovery action: those are the supervisor's, behind the held button.
 */
export function WorkerFailed({ words, workerTag, hold, report }: FailedProps) {
  return (
    <WorkerShell hold={hold}>
      <div lang={workerTag} className="flex flex-1 flex-col items-center justify-center gap-8 py-8 text-center">
        <GivePhone />
        <h1 tabIndex={-1} className="script-text text-worker font-semibold text-on-surface">{words.giveSupervisor}</h1>
      </div>
      <ReportPanel report={report} words={words} workerTag={workerTag} className="pb-4" />
    </WorkerShell>
  )
}

interface HandBackProps {
  words: WorkerWords
  workerTag: string
  report: HazardReport
  /** The supervisor's one control, in the supervisor's language ("Supervisor: hold to continue"), held for 1.5 s. */
  haveThePhone: SupervisorHold
}

/**
 * After the last answer: the worker is told to give the phone back. The result does not open by itself; the supervisor holds
 * "Supervisor: hold to continue" for 1.5 s and only then sees the check, so a worker's stray tap on it opens nothing. It is the
 * quiet one on this screen: outlined, 48 px, under the worker's red problem button, which is the louder of the two. The check
 * itself started the moment the answers were in.
 */
export function WorkerHandBack({ words, workerTag, report, haveThePhone }: HandBackProps) {
  return (
    <WorkerShell>
      <div lang={workerTag} className="flex flex-1 flex-col items-center justify-center gap-8 py-8 text-center">
        <GivePhone />
        <h1 tabIndex={-1} className="space-y-3 text-on-surface">
          <span className="script-text block text-headline-lg">{words.thanks}</span>
          <span className="script-text block text-worker font-semibold">{words.handBack}</span>
        </h1>
      </div>
      <ReportPanel report={report} words={words} workerTag={workerTag} />
      <div className="pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
        <HeldButton hold={haveThePhone} className="relative w-full [&>button]:w-full [&>button]:px-3 [&>button]:pl-3 [&>p]:bottom-full [&>p]:left-0 [&>p]:max-w-full" />
      </div>
    </WorkerShell>
  )
}
