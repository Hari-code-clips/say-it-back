/* Hallmark · components: the worker's consent before any recording, and what a "Not now" leads to · genre: modern-minimal ·
 * macrostructure: Workbench (one calm screen, one decision) · theme: design.md. Privacy, 16 Oct (build-notes/34-privacy.md).
 *
 * WorkerConsent and WorkerDeclined are worker-held screens: worker-language text, icons, the one decision and the red problem button,
 * on the worker ground; they do not call useT, so no supervisor string reaches them except the held corner button's (`hold`), which
 * the supervisor's own screen builds. ConsentDeclined is the supervisor's screen after a "Not now", in the supervisor's language.
 * A decline is never a failure or a verdict: no error colour, no warning, nothing recorded.
 * states: I agree (default · hover · focus-visible · active · disabled while a report is open · loading while the choice is saved ·
 *         error: the worker is told to give the phone to the supervisor, WorkerFailed · success: the Start screen); Not now (default ·
 *         hover · focus-visible · active · disabled as I agree · loading n/a: it never waits · error n/a · success: WorkerDeclined).
 *         2026-10-17, ConsentDeclined's "Record an in-person check" (the one blue fill: default · hover · focus-visible · active ·
 *         disabled while a report is held, with its reason · loading while the decline is saved again · error: a red banner with
 *         the reason · success: the decision screen); "Open the script" (outlined) and "Give phone to worker" (text) as before.
 */
import type { ReactNode } from 'react'
import { FlowFrame } from '../../flow/FlowFrame.tsx'
import type { WorkerWords } from '../../i18n/worker.ts'
import { useT } from '../../i18n/index.tsx'
import { Button } from '../../ui/Button.tsx'
import { Banner } from '../../ui/Feedback.tsx'
import { ReportPanel } from './ReportPanel.tsx'
import type { HazardReport } from './useHazardReport.ts'
import { Disc, GivePhone, WorkerShell, type SupervisorHold } from './WorkerScreens.tsx'

interface ConsentProps {
  words: WorkerWords
  workerTag: string
  /** The supervisor's corner lock: take the phone back to the handover. */
  hold: SupervisorHold
  report: HazardReport
  /** The choice is being saved. */
  busy: boolean
  onAgree: () => void
  onDecline: () => void
}

/**
 * Before the first answer of the round is recorded: what is recorded, what the voice is for and that it is deleted, then "I agree"
 * (the one blue fill) or "Not now" (outlined). Screens under 704 px tall drop the disc and tighten the gaps, and under 640 px the
 * text steps down as Start's does, so both choices and the problem button stay on the first screen at 320 x 568 and 375 x 667.
 */
export function WorkerConsent({ words, workerTag, hold, report, busy, onAgree, onDecline }: ConsentProps) {
  const off = report.holds || busy
  return (
    <WorkerShell hold={hold}>
      {/* This screen holds two choices, so it gives up the disc and its gaps sooner than Start (under 704 px tall, measured: at
          375 x 667 the disc pushed the problem button 21 px below the fold); the text steps down under 640 px, as Start's does.
          Written out in full: Tailwind finds a class only where it is spelled whole in the source. */}
      <div lang={workerTag} className="flex flex-1 flex-col items-center justify-center gap-8 py-8 [@media(max-height:44rem)]:gap-4 [@media(max-height:44rem)]:py-3">
        <Disc icon="mic" className="size-24 [@media(max-height:44rem)]:hidden" />
        <div className="max-w-md space-y-3 text-center [@media(max-height:40rem)]:space-y-2">
          <h1 tabIndex={-1} className="script-text text-title-lg text-on-surface [@media(max-height:40rem)]:text-title-md">
            {words.consentWhat}
          </h1>
          <p className="script-text text-title-lg font-normal text-on-surface-variant [@media(max-height:40rem)]:text-body-lg">{words.consentUse}</p>
        </div>
        <div className="flex w-full max-w-md flex-col gap-3">
          <Button size="xl" icon="check" disabled={off} busy={busy} onClick={onAgree}>
            {words.consentAgree}
          </Button>
          <Button variant="outlined" full disabled={off} onClick={onDecline}>
            {words.consentNotNow}
          </Button>
        </div>
      </div>
      <ReportPanel report={report} words={words} workerTag={workerTag} className="pb-4" />
    </WorkerShell>
  )
}

interface DeclinedProps {
  words: WorkerWords
  workerTag: string
  /** "I'm the supervisor", labelled: the supervisor has to find it at once. */
  hold: SupervisorHold
  report: HazardReport
}

/** After "Not now": a thank-you and "Please give the phone to your supervisor", with the picture. Nothing else is asked of the worker. */
export function WorkerDeclined({ words, workerTag, hold, report }: DeclinedProps) {
  return (
    <WorkerShell hold={hold}>
      <div lang={workerTag} className="flex flex-1 flex-col items-center justify-center gap-8 py-8 text-center">
        <GivePhone />
        <h1 tabIndex={-1} className="space-y-3 text-on-surface">
          <span className="script-text block text-headline-lg">{words.thanks}</span>
          <span className="script-text block text-worker font-semibold">{words.giveSupervisor}</span>
        </h1>
      </div>
      <ReportPanel report={report} words={words} workerTag={workerTag} className="pb-4" />
    </WorkerShell>
  )
}

interface FrameProps {
  roundLabel: string
  /** 2026-10-17: the supervisor briefed the worker in person: record it on the decision screen (a decline never holds the permit). */
  onInPerson: () => void
  /** The decline is being saved again before the decision screen opens. */
  inPersonBusy?: boolean
  /** Why the decision screen could not open (the decline was not saved), in the supervisor's language. */
  inPersonError?: string
  /** The steps and the questions, for briefing in person. */
  onScript: () => void
  /** The worker changed their mind: the consent screen again. */
  onAskAgain: () => void
  /** A problem report still held (recording, sending or failed): it stays in reach. */
  heldReport?: ReactNode
  /** Nothing leaves the screen while a problem report is held: the reason shown beside the disabled primary. */
  holdsReason?: string
}

/**
 * The supervisor's screen after a "Not now": nothing was recorded, it is no mark against the worker, brief them in person. Then
 * "Record an in-person check" (the one blue fill) leads to the decision; "Open the script" has the steps and questions to brief from;
 * "Give phone to worker" sits under the sentence that offers it, for a worker who changes their mind.
 */
export function ConsentDeclined({ roundLabel, onInPerson, inPersonBusy, inPersonError, onScript, onAskAgain, heldReport, holdsReason }: FrameProps) {
  const t = useT()
  return (
    <FlowFrame
      step="brief"
      round={roundLabel}
      title={t('consent.declinedTitle')}
      primary={
        <Button size="lg" icon="fact_check" busy={inPersonBusy} disabled={Boolean(holdsReason)} disabledReason={holdsReason} onClick={onInPerson}>
          {t('inPerson.record')}
        </Button>
      }
      secondary={
        <Button variant="outlined" icon="description" onClick={onScript}>
          {t('consent.toScript')}
        </Button>
      }
    >
      {inPersonError && (
        <Banner tone="error" live="assertive">
          {inPersonError}
        </Banner>
      )}
      <p className="text-body-lg text-on-surface">{t('consent.declinedBody')}</p>
      <p className="text-body-lg text-on-surface-variant">{t('consent.declinedHow')}</p>
      <Button variant="text" icon="smartphone" onClick={onAskAgain}>
        {t('brief.give')}
      </Button>
      {heldReport}
    </FlowFrame>
  )
}
