/* Hallmark · component: worker problem report · genre: utilitarian (existing M3 system) · theme: project tokens
 * states: default · hover · focus · active · disabled · loading · error · success
 * (hover/focus/active from .state-layer and the global :focus-visible ring; disabled while a report is opening; loading = sending;
 *  error = failed (Send again keeps the recording; deleting it needs a confirm) / no mic; success = sent)
 */
import type { WorkerWords } from '../../i18n/worker.ts'
import { useElapsedSeconds } from '../../lib/useElapsed.ts'
import { clock } from '../../lib/waitCopy.ts'
import { Button } from '../../ui/Button.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'
import type { HazardReport } from './useHazardReport.ts'

interface Props {
  report: HazardReport
  words: WorkerWords
  /** BCP-47 tag of the worker language: every word here is in it. */
  workerTag: string
  className?: string
}

const seconds = (ms: number) => {
  const s = Math.max(0, Math.min(30, Math.floor(ms / 1000)))
  return `0:${String(s).padStart(2, '0')}`
}

/**
 * How long a report has been sending (with a recording, that is a Gemini call that can take a while). Digits only: the
 * worker's screen has words in eight languages, and "0:12" needs none. The Send button already says it is sending.
 */
function SendingClock() {
  const elapsed = useElapsedSeconds()
  return (
    <span className="shrink-0 text-label-lg tabular-nums text-on-surface-variant" aria-hidden="true">
      {clock(elapsed)}
    </span>
  )
}

/**
 * "Report a problem", in the worker's language, on every worker screen outside an answer window. It opens in place (not a
 * modal), so the briefing stays in view and keeps going: say it (up to 30 s) or send it without words. The confirmation
 * says the supervisor will see it.
 */
export function ReportPanel({ report, words, workerTag, className }: Props) {
  const { state } = report

  if (state.kind === 'closed') {
    return (
      <div lang={workerTag} className={cx('flex justify-center', className)}>
        <Button variant="error" size="lg" icon="report" onClick={report.open} className="w-full max-w-md px-4!">
          {words.report}
        </Button>
      </div>
    )
  }

  if (state.kind === 'sent') {
    return (
      <div lang={workerTag} role="status" className={cx('mx-auto flex w-full max-w-md animate-fade-in items-center gap-3 rounded-lg bg-success-container px-4 py-3 text-on-success-container', className)}>
        <Icon name="check_circle" filled className="text-[1.75rem]" />
        <p className="text-title-md">{words.reportSent}</p>
      </div>
    )
  }

  if (state.kind === 'confirm_discard') {
    return (
      <section
        lang={workerTag}
        role="alertdialog"
        aria-labelledby="report-discard-title"
        aria-describedby="report-discard-body"
        className={cx('mx-auto w-full max-w-md animate-fade-in space-y-3 rounded-lg border-2 border-error bg-surface-container-lowest p-3 sm:p-4', className)}
      >
        <h2 id="report-discard-title" className="flex items-center gap-2 text-title-md text-on-surface">
          <Icon name="delete" className="text-[1.5rem] text-error" />
          {words.reportDiscardTitle}
        </h2>
        <p id="report-discard-body" className="text-body-lg text-on-surface">
          {words.reportDiscardBody}
        </p>
        <div className="flex flex-col gap-2">
          <Button size="lg" variant="tonal" icon="arrow_back" full onClick={report.keep} className="px-4!">
            {words.reportKeep}
          </Button>
          <Button size="lg" variant="error" icon="delete" full onClick={report.confirmDiscard} className="px-4!">
            {words.reportDiscardConfirm}
          </Button>
        </div>
      </section>
    )
  }

  const recording = state.kind === 'recording'
  const failed = state.kind === 'failed'
  return (
    <section
      lang={workerTag}
      aria-label={words.reportTitle}
      className={cx('mx-auto w-full max-w-md animate-fade-in space-y-3 rounded-lg border border-outline-variant bg-surface-container-lowest p-3 sm:p-4', className)}
    >
      <div className="flex items-center gap-2">
        <Icon name={recording ? 'mic' : 'report'} filled className="text-[1.5rem] text-error" />
        <h2 className="min-w-0 flex-1 text-title-md text-on-surface">{recording ? words.reportRecording : words.reportTitle}</h2>
        {recording && (
          <span className="shrink-0 text-label-lg tabular-nums text-on-surface-variant" aria-hidden="true">
            {seconds(Date.now() - state.startedAt)} / 0:30
          </span>
        )}
        {state.kind === 'sending' && <SendingClock />}
      </div>

      {recording && (
        <div aria-hidden="true" className="h-2 overflow-hidden rounded-full bg-surface-container-highest">
          <div className="h-full origin-left bg-error" style={{ transform: `scaleX(${Math.max(0.04, report.level)})` }} />
        </div>
      )}

      {state.kind === 'failed' && (
        <p role="alert" className="flex items-start gap-2 text-body-lg text-error">
          <Icon name="error" filled className="mt-0.5 text-[1.25rem]" />
          {words.reportFailed}
        </p>
      )}
      {state.kind === 'no_mic' && (
        <p role="alert" className="flex items-start gap-2 text-body-lg text-on-surface">
          <Icon name="mic_off" className="mt-0.5 text-[1.25rem] text-error" />
          {words.reportNoMic}
        </p>
      )}

      <div className="flex flex-col gap-2">
        {(state.kind === 'choose' || state.kind === 'opening') && (
          <>
            <Button size="lg" icon="mic" full busy={state.kind === 'opening'} onClick={report.speak} className="px-4!">
              {words.reportSpeak}
            </Button>
            <p className="text-center text-body-md text-on-surface-variant">{words.reportLimit}</p>
            <Button size="lg" variant="tonal" icon="send" full disabled={state.kind === 'opening'} onClick={report.tap} className="px-4!">
              {words.reportTap}
            </Button>
          </>
        )}
        {(recording || state.kind === 'sending') && (
          <Button size="lg" icon="send" full busy={state.kind === 'sending'} onClick={report.finish} className="px-4!">
            {state.kind === 'sending' ? words.reportSending : words.reportSend}
          </Button>
        )}
        {state.kind === 'failed' && (
          <Button size="lg" icon="refresh" full onClick={report.retry} className="px-4!">
            {words.reportSend}
          </Button>
        )}
        {state.kind === 'no_mic' && (
          <Button size="lg" variant="tonal" icon="send" full onClick={report.tap} className="px-4!">
            {words.reportTap}
          </Button>
        )}
        {state.kind !== 'sending' && (
          <Button variant="text" full onClick={report.cancel}>
            {failed ? words.reportDiscard : words.reportCancel}
          </Button>
        )}
      </div>
    </section>
  )
}
