import { useEffect, useState } from 'react'
import { useLocation } from 'wouter'
import { ApiError } from '../../api/client.ts'
import { bcp47, useCatalog } from '../../api/catalog.tsx'
import type { Round } from '../../api/types.ts'
import { MicError } from '../../audio/mic.ts'
import { useBriefing } from '../../flow/BriefingContext.tsx'
import { latestRound } from '../../flow/phases.ts'
import { UnexpectedState } from '../../flow/UnexpectedState.tsx'
import { WORKER_WORDS } from '../../i18n/worker.ts'
import { useLangName, useT, type Translate } from '../../i18n/index.tsx'
import { SessionError } from '../../live/session.ts'
import { apiErrorText } from '../../lib/apiError.ts'
import { MockBadge } from '../../shell/AppShell.tsx'
import { Button, IconButton, LinkButton } from '../../ui/Button.tsx'
import { Card } from '../../ui/Card.tsx'
import { SegmentedButton } from '../../ui/Choice.tsx'
import { Dialog } from '../../ui/Dialog.tsx'
import { Banner, BusyPanel } from '../../ui/Feedback.tsx'
import { usePageFocus } from '../../ui/PageHeading.tsx'
import { BriefStage } from './BriefStage.tsx'
import { failurePlan } from './failurePlan.ts'
import { Orb } from './Orb.tsx'
import { useBriefingRun, type RunMode } from './useBriefingRun.ts'

/** Keep the phone awake while the worker is being briefed. */
function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !('wakeLock' in navigator)) return
    let lock: WakeLockSentinel | null = null
    let cancelled = false
    const request = async () => {
      try {
        lock = await navigator.wakeLock.request('screen')
      } catch {
        /* not allowed right now (battery saver, hidden tab) */
      }
    }
    void request()
    const onVisible = () => {
      if (document.visibilityState === 'visible' && !cancelled) void request()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisible)
      void lock?.release()
    }
  }, [active])
}

/** The ApiError behind a failure: the error itself, or what a SessionError wraps (turn mode wraps a failed TTS call). */
const apiErrorOf = (e: unknown): ApiError | undefined => (e instanceof ApiError ? e : e instanceof SessionError && e.cause instanceof ApiError ? e.cause : undefined)

function describeError(t: Translate, e: unknown): { message: string; micProblem: boolean } {
  if (e instanceof MicError) return { message: t(`mic.${e.code}`), micProblem: true }
  const api = apiErrorOf(e)
  if (api) return { message: apiErrorText(t, api), micProblem: false }
  if (e instanceof SessionError) return { message: t(`brief.err.${e.code}`), micProblem: false }
  return { message: apiErrorText(t, e), micProblem: false }
}

/** /b/:id/brief: the worker's screen. Only meaningful while the latest round is unjudged. */
export function BriefScreen() {
  const { briefing } = useBriefing()
  const round = latestRound(briefing)
  if (!round) return <UnexpectedState />
  return <BriefRun round={round} />
}

function BriefRun({ round }: { round: Round }) {
  const t = useT()
  const [, navigate] = useLocation()
  const { briefing, refresh } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const [mode, setMode] = useState<RunMode>('live')
  const [confirmLeave, setConfirmLeave] = useState(false)
  const heading = usePageFocus(t('brief.title'))

  const run = useBriefingRun({
    briefing,
    round,
    refresh,
    onJudged: async () => {
      await refresh()
      navigate(`/b/${briefing.id}/result`, { replace: true })
    },
  })
  useWakeLock(run.state.kind === 'running' || run.state.kind === 'submitting')

  const workerTag = bcp47(catalog, briefing.workerLang, briefing.siteId)
  const workerName = langName(briefing.workerLang)
  const words = WORKER_WORDS[briefing.workerLang]
  const { state } = run
  const backToScript = () => navigate(`/b/${briefing.id}/script`)

  if (state.kind === 'running') {
    return (
      <>
        <BriefStage
          phase={state.phase}
          mode={state.mode}
          workerLang={briefing.workerLang}
          workerTag={workerTag}
          questionIds={round.script.questions.map((q) => q.id)}
          captions={run.captions}
          heard={run.heard}
          getLevel={run.getLevel}
          onDone={run.finishAnswer}
          onLeave={() => setConfirmLeave(true)}
        />
        <Dialog
          open={confirmLeave}
          onClose={() => setConfirmLeave(false)}
          title={t('brief.leaveTitle')}
          actions={
            <>
              <Button variant="text" onClick={() => setConfirmLeave(false)}>
                {t('action.cancel')}
              </Button>
              <Button
                variant="error"
                onClick={() => {
                  setConfirmLeave(false)
                  run.abort()
                }}
              >
                {t('brief.leaveConfirm')}
              </Button>
            </>
          }
        >
          {t('brief.leaveBody')}
        </Dialog>
      </>
    )
  }

  if (state.kind === 'submitting') {
    return (
      <main id="main" className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-8 px-4 py-8">
        <h1 className="sr-only">{t('brief.title')}</h1>
        <div lang={workerTag} className="space-y-4 text-center">
          <Orb tone="thinking" icon="hourglass_top" getLevel={() => 0} />
          <p className="text-worker-sm font-semibold uppercase tracking-wide text-on-surface-variant">{words.wait}</p>
        </div>
        <BusyPanel title={t('brief.checking')} hint={t('brief.checkingHint')} />
      </main>
    )
  }

  if (state.kind === 'failed' || state.kind === 'submit_failed') {
    const failure =
      state.kind === 'failed'
        ? describeError(t, state.error)
        : { message: state.error instanceof ApiError ? apiErrorText(t, state.error) : t('brief.err.submit'), micProblem: false }
    // What to offer depends on the error code: see failurePlan (daily_limit offers no turn-by-turn and no retry).
    const plan = failurePlan({
      kind: state.kind,
      mode: state.kind === 'failed' ? state.mode : undefined,
      code: apiErrorOf(state.error)?.code,
      micProblem: failure.micProblem,
    })
    return (
      <main id="main" className="mx-auto flex min-h-dvh max-w-xl flex-col justify-center gap-6 px-4 py-8">
        <h1 className="sr-only">{t('brief.title')}</h1>
        <Banner tone="error" title={state.kind === 'failed' ? t('brief.failed') : t('brief.submitFailed')} live="assertive">
          {failure.message}
        </Banner>
        {plan.hint === 'turn' && <p className="text-body-lg text-on-surface-variant">{t('brief.failedTurnHint')}</p>}
        {plan.hint === 'not_recorded' && <p className="text-body-lg text-on-surface-variant">{t('brief.notRecordedHint')}</p>}
        <div className="flex flex-col gap-3 sm:flex-row">
          {plan.offerTurn && (
            <Button size="lg" icon="volume_up" onClick={() => void run.start('turn')}>
              {t('brief.useTurn')}
            </Button>
          )}
          {plan.offerRetry && (
            <Button
              size="lg"
              variant={plan.retryQuiet ? 'tonal' : 'filled'}
              icon="refresh"
              onClick={state.kind === 'failed' ? () => void run.start(state.mode) : run.retrySubmit}
            >
              {t(state.kind === 'failed' ? 'action.tryAgain' : 'action.retry')}
            </Button>
          )}
          {state.kind === 'failed' && (
            <Button variant="text" onClick={run.reset}>
              {t('brief.backToHandover')}
            </Button>
          )}
        </div>
      </main>
    )
  }

  // Hand-over: the supervisor's strip on top, the worker's big Start below.
  return (
    <main id="main" className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col px-4 pb-8 pt-2 sm:px-6">
      <div className="flex items-center gap-2">
        <IconButton icon="arrow_back" label={t('brief.backToScript')} onClick={backToScript} />
        <span className="flex-1" />
        <MockBadge />
      </div>
      <h1 ref={heading} tabIndex={-1} className="mt-1 px-1 text-headline-sm font-semibold">
        {t('brief.title')}
      </h1>

      <Card variant="filled" className="mt-4 space-y-4 p-5">
        <p className="text-body-lg">{t('brief.handoverBody', { lang: workerName })}</p>
        <SegmentedButton<RunMode>
          label={t('brief.mode')}
          value={mode}
          onChange={setMode}
          options={[
            { value: 'live', label: t('brief.mode.live') },
            { value: 'turn', label: t('brief.mode.turn') },
          ]}
        />
        <p className="text-body-md text-on-surface-variant">{t(mode === 'live' ? 'brief.mode.liveHint' : 'brief.mode.turnHint')}</p>
      </Card>

      <div lang={workerTag} className="flex flex-1 flex-col items-center justify-center gap-8 py-8">
        <Orb tone="idle" icon="hearing" getLevel={() => 0} />
        <div className="w-full max-w-md">
          <Button size="xl" icon="play_arrow" onClick={() => void run.start(mode)}>
            {words.start}
          </Button>
        </div>
      </div>
      <LinkButton href={`/b/${briefing.id}/script`} variant="text" className="self-center">
        {t('brief.backToScript')}
      </LinkButton>
    </main>
  )
}
