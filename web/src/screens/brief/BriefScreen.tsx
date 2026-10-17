/* Hallmark · screen: the briefing round on /b/:id/brief · genre: modern-minimal · macrostructure: Workbench · theme: design.md
 * One route, seven stages, two holders (see handover.ts). The supervisor's stages (handover, recovery, checking) are the flow frame in
 * the supervisor's language; the worker's stages (Start, the session, a failure) are WorkerScreens / BriefStage, worker language only;
 * the hand-back is the worker's last message with the supervisor's one quiet held button. The result never opens by itself: only
 * after "Supervisor: hold to continue" is held for 1.5 s (F3). The check request still starts the moment the last answer is in (useBriefingRun).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'wouter'
import { ApiError } from '../../api/client.ts'
import { bcp47, useCatalog } from '../../api/catalog.tsx'
import { api } from '../../api/endpoints.ts'
import type { Round } from '../../api/types.ts'
import { MicError } from '../../audio/mic.ts'
import { useBriefing } from '../../flow/BriefingContext.tsx'
import { FlowFrame } from '../../flow/FlowFrame.tsx'
import { MAX_ROUNDS, latestRound } from '../../flow/phases.ts'
import { UnexpectedState } from '../../flow/UnexpectedState.tsx'
import { WORKER_WORDS } from '../../i18n/worker.ts'
import { useLangName, useT, type Translate } from '../../i18n/index.tsx'
import { SessionError } from '../../live/session.ts'
import { apiErrorText } from '../../lib/apiError.ts'
import { useAsync } from '../../lib/useAsync.ts'
import { MicBrowserBanner } from '../../shell/MicBrowserBanner.tsx'
import { SignalBanner } from '../../shell/SignalBanner.tsx'
import { Button } from '../../ui/Button.tsx'
import { Banner } from '../../ui/Feedback.tsx'
import type { IconName } from '../../theme/iconNames.ts'
import { BriefStage } from './BriefStage.tsx'
import { CheckWait } from './CheckWait.tsx'
import { failurePlan } from './failurePlan.ts'
import { HandoverForm } from './HandoverForm.tsx'
import { defaultMode, liveListed } from './liveLanguages.ts'
import { resultMayOpen, stageOf, type Stage } from './handover.ts'
import { ReportPanel } from './ReportPanel.tsx'
import { sampleChoice, sampleLoader, sampleQids } from './sample.ts'
import { useBriefingRun, type RunMode } from './useBriefingRun.ts'
import { useHazardReport } from './useHazardReport.ts'
import { WorkerFailed, WorkerHandBack, WorkerReady, type SupervisorHold } from './WorkerScreens.tsx'
import { ConsentDeclined, WorkerConsent, WorkerDeclined } from './ConsentStep.tsx'
import { consentStep, type ConsentChoice } from './consentFlow.ts'
import { isJudgeDemo } from '../../flow/judgeDemo.ts'

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

/**
 * The stage changed inside the same route: move focus to the new screen's heading (or its main), so a screen reader announces
 * it. Not on the first render, so a fresh page load keeps the browser's normal first Tab.
 */
function useStageFocus(stage: Stage | string) {
  const first = useRef(true)
  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    const target = document.querySelector<HTMLElement>('main h1') ?? document.getElementById('main')
    target?.focus({ preventScroll: true })
  }, [stage])
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

/** /b/:id/brief. Only meaningful while the latest round is unjudged (and, v0.4, its script approved). */
export function BriefScreen() {
  const { briefing } = useBriefing()
  const round = latestRound(briefing)
  if (!round) return <UnexpectedState />
  return <BriefRun round={round} />
}

interface RecoveryAction {
  key: string
  label: string
  icon: IconName
  onClick: () => void
}

function BriefRun({ round }: { round: Round }) {
  const t = useT()
  const [, navigate] = useLocation()
  const { briefing, refresh } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const [mode, setMode] = useState<RunMode>(() => defaultMode(briefing.workerLang))
  // 17 Oct, review P0-17: a briefing the judge demo started (/judge) opens every handover with the stored sample answers chosen.
  const judgeDemo = isJudgeDemo(briefing.id)
  const [sampleOn, setSampleOn] = useState(judgeDemo)
  // Who holds the phone, as the supervisor's own acts: giving it to the worker, taking it back after a failure, taking it back
  // after the last answer. The run's state says the rest (see stageOf).
  const [handed, setHanded] = useState(false)
  const [tookOver, setTookOver] = useState(false)
  const [haveThePhone, setHaveThePhone] = useState(false)
  const [judged, setJudged] = useState(false)
  // Privacy (16 Oct): the worker's own choice before any answer is recorded (ConsentStep.tsx, consentFlow.ts). A choice made on an
  // earlier visit counts only if it was "I agree": after a "Not now" the worker is asked again the next time they get the phone.
  const [consent, setConsent] = useState<ConsentChoice>(round.consent?.given ? 'given' : 'pending')
  const [consentBusy, setConsentBusy] = useState(false)
  const [consentFailed, setConsentFailed] = useState(false)
  const [declinedSeen, setDeclinedSeen] = useState(false)
  // 2026-10-17: "Record an in-person check" after a decline (build-notes/38-in-person-check.md).
  const [inPersonBusy, setInPersonBusy] = useState(false)
  const [inPersonError, setInPersonError] = useState<string | undefined>(undefined)

  // Sample answers (endpoint 24): which questions of this round have a stored clip for this task and worker language (one per
  // question since 16 Oct, paired by shared steps in sample.ts). Every paired clip is fetched once, ahead of the choice.
  const demo = useAsync(() => api.demoAnswers(), [])
  const questionIds = useMemo(() => round.script.questions.map((q) => q.id), [round])
  const choice = useMemo(
    () => sampleChoice(demo.data?.items, !demo.loading, briefing.taskId, briefing.workerLang, round.n, round.script.questions),
    [demo.data, demo.loading, briefing.taskId, briefing.workerLang, round],
  )
  const pairs = choice.kind === 'available' ? choice.pairs : undefined
  const loadSample = useMemo(() => pairs && sampleLoader(pairs, (d) => api.demoAnswerAudio(d.taskId, d.workerLang, d.round, d.questionId)), [pairs])
  useEffect(() => {
    for (const p of pairs ?? []) void loadSample?.(p.qid)?.catch(() => undefined)
  }, [pairs, loadSample])

  const run = useBriefingRun({
    briefing,
    round,
    sample: loadSample,
    // F1: the choice made on the handover step. A question without a stored sample is the worker's voice.
    sampleQids: sampleQids(sampleOn, choice),
    // Judged is only noted: the route's briefing is not re-read here, or it would redirect to the result on its own.
    onJudged: async () => setJudged(true),
  })
  useWakeLock(run.state.kind === 'running' || run.state.kind === 'submitting')

  const report = useHazardReport({
    openSource: run.reportSource,
    send: async (audio) => {
      await api.reportHazard(briefing.id, { ...(audio ? { audio } : {}), round: round.n })
    },
  })

  // An answer window opened: a report being recorded is sent as it is (the mic's side sink gets nothing during the window).
  const listening = run.state.kind === 'running' && run.state.phase.kind === 'listening'
  const { finish: finishReport } = report
  useEffect(() => {
    if (listening) finishReport()
  }, [listening, finishReport])

  // The hand-back gate (F3): the result opens once the check is done AND the supervisor has the phone AND no report is held.
  const opened = useRef(false)
  const toResult = useCallback(async () => {
    if (opened.current) return
    opened.current = true
    await refresh().catch(() => undefined)
    navigate(`/b/${briefing.id}/result`, { replace: true })
  }, [refresh, navigate, briefing.id])
  const mayOpen = resultMayOpen({ judged, haveThePhone, reportHolds: report.holds })
  useEffect(() => {
    if (mayOpen) void toResult()
  }, [mayOpen, toResult])

  const { state } = run
  const stage = stageOf({ run: state.kind, handed, tookOver, haveThePhone })
  // The consent screens share the worker_ready stage: their own changes move the focus too.
  const consentView = consentStep({
    stage,
    questionIds,
    sampleQids: sampleQids(sampleOn, choice),
    consent,
    failed: consentFailed,
    declinedSeen,
  })
  useStageFocus(`${stage}:${consentView}`)

  const workerTag = bcp47(catalog, briefing.workerLang, briefing.siteId)
  const workerName = langName(briefing.workerLang)
  const words = WORKER_WORDS[briefing.workerLang]
  const roundLabel = t('script.round', { n: round.n, max: MAX_ROUNDS })

  // Nothing leaves the screen while a problem report is held (the report would be lost with the page).
  const backToScript = () => {
    if (!report.holds) navigate(`/b/${briefing.id}/script`)
  }
  const startRun = (m: RunMode) => {
    setTookOver(false)
    setHaveThePhone(false)
    setJudged(false)
    void run.start(m)
  }
  const backToHandover = () => {
    setHanded(false)
    setTookOver(false)
    setHaveThePhone(false)
    run.reset()
  }
  /** The supervisor gives the phone to the worker again, in this mode: a retry starts with the worker's Start, as the first run did. */
  const handBackToWorker = (m: RunMode) => {
    setMode(m)
    setHanded(true)
    setTookOver(false)
    setHaveThePhone(false)
    setJudged(false)
    run.reset()
  }
  const endRound = () => {
    setHanded(false)
    setTookOver(false)
    run.abort()
  }

  // `quiet`: the corner lock of the Start screen (icon only, its name and tooltip are the label, the label shows while held). The
  // failure screen keeps the labelled button: there the supervisor has to find it at once.
  const supervisorHold = (onConfirm: () => void, quiet = false): SupervisorHold => ({
    label: t('brief.supervisor'),
    ...(quiet ? { iconOnly: true, holdingLabel: t('brief.supervisor') } : {}),
    hint: t('brief.supervisorHint'),
    confirm: { title: t('brief.supervisorTitle'), body: t('brief.supervisorBody'), confirmLabel: t('brief.supervisorConfirm'), cancelLabel: t('action.cancel') },
    onConfirm,
  })
  // F3: taking the phone back after the last answer is held too, so a worker's stray tap cannot open the supervisor's wait.
  const haveThePhoneHold: SupervisorHold = {
    label: t('brief.holdToContinue'),
    hint: t('brief.supervisorHint'),
    confirm: { title: t('brief.haveThePhoneTitle'), body: t('brief.haveThePhoneBody'), confirmLabel: t('brief.haveThePhoneConfirm'), cancelLabel: t('action.cancel') },
    onConfirm: () => setHaveThePhone(true),
  }
  const exitHold: SupervisorHold = {
    label: t('brief.exit'),
    iconOnly: true,
    holdingLabel: t('brief.leaveConfirm'),
    hint: t('brief.exitHint'),
    confirm: { title: t('brief.leaveTitle'), body: t('brief.leaveBody'), confirmLabel: t('brief.leaveConfirm'), cancelLabel: t('action.cancel') },
    onConfirm: endRound,
  }

  // ---- the worker holds the phone ----

  // Privacy (16 Oct): before Start, the worker chooses whether their voice is recorded; skipped when every answer is a stored sample.
  const agree = async () => {
    setConsentBusy(true)
    try {
      await api.consent(briefing.id, round.n, true)
      setConsent('given')
    } catch {
      setConsentFailed(true)
    } finally {
      setConsentBusy(false)
    }
  }
  const decline = () => {
    setConsent('declined')
    setDeclinedSeen(false)
    // Nothing is recorded either way; the server is told so that a check can never follow (409 consent_declined).
    void api.consent(briefing.id, round.n, false).catch(() => undefined)
  }
  if (consentView === 'failed') {
    return <WorkerFailed words={words} workerTag={workerTag} hold={supervisorHold(backToHandover)} report={report} />
  }
  if (consentView === 'ask') {
    return (
      <WorkerConsent
        words={words}
        workerTag={workerTag}
        hold={supervisorHold(backToHandover, true)}
        report={report}
        busy={consentBusy}
        onAgree={() => void agree()}
        onDecline={decline}
      />
    )
  }
  if (consentView === 'declined') {
    return <WorkerDeclined words={words} workerTag={workerTag} hold={supervisorHold(() => setDeclinedSeen(true))} report={report} />
  }
  if (consentView === 'declined_supervisor') {
    const askAgain = () => {
      setConsent('pending')
      setDeclinedSeen(false)
      setInPersonError(undefined)
    }
    // 2026-10-17: a decline never holds the permit. The decline is saved again first (the same choice is a no-op on the server, and
    // the first save may have failed) and the briefing re-read, so the decision screen, which the route allows only while the
    // decline is on record (phases.ts awaitsInPersonCheck), opens. No model is called and no audio is sent.
    const recordInPerson = async () => {
      if (report.holds) return
      setInPersonBusy(true)
      setInPersonError(undefined)
      try {
        await api.consent(briefing.id, round.n, false)
        await refresh()
        navigate(`/b/${briefing.id}/decision`)
      } catch (e) {
        setInPersonBusy(false)
        setInPersonError(apiErrorText(t, e))
      }
    }
    // The script is read with the decline on record too, so the Script screen offers the in-person check (a reload lands there).
    const scriptForInPerson = async () => {
      if (report.holds) return
      await api.consent(briefing.id, round.n, false).catch(() => undefined)
      await refresh().catch(() => undefined)
      backToScript()
    }
    return (
      <ConsentDeclined
        roundLabel={roundLabel}
        onInPerson={() => void recordInPerson()}
        inPersonBusy={inPersonBusy}
        inPersonError={inPersonError}
        onScript={() => void scriptForInPerson()}
        onAskAgain={askAgain}
        heldReport={report.holds && <ReportPanel report={report} words={words} workerTag={workerTag} />}
        holdsReason={report.holds ? t('brief.reportHoldsPage') : undefined}
      />
    )
  }
  if (stage === 'worker_ready') {
    return <WorkerReady words={words} workerTag={workerTag} hold={supervisorHold(backToHandover, true)} report={report} onStart={() => startRun(mode)} />
  }
  if (stage === 'worker_running' && state.kind === 'running') {
    return (
      <BriefStage
        phase={state.phase}
        words={words}
        workerTag={workerTag}
        questionIds={questionIds}
        captions={run.captions}
        heard={run.heard}
        getLevel={run.getLevel}
        onDone={run.finishAnswer}
        hold={exitHold}
        report={report}
        samplePlaying={run.sampleState === 'loading' || run.sampleState === 'playing'}
      />
    )
  }
  if (stage === 'worker_failed') {
    return <WorkerFailed words={words} workerTag={workerTag} hold={supervisorHold(() => setTookOver(true))} report={report} />
  }
  if (stage === 'handback') {
    return <WorkerHandBack words={words} workerTag={workerTag} report={report} haveThePhone={haveThePhoneHold} />
  }

  // ---- the supervisor holds the phone ----

  // A report still recording, sending, or failed and not deliberately deleted stays in reach on every supervisor screen: it is sent
  // again or deleted on purpose, never lost (v0.4 review).
  const heldReport = report.holds && <ReportPanel report={report} words={words} workerTag={workerTag} />

  if (stage === 'checking') {
    // The check began when the last answer was in; the sample note is said once, after the fact, for whichever window it was.
    const sampleNote = run.sampleIssue === 'failed' ? t('brief.sample.failed') : run.sampleIssue === 'dropped' ? t('brief.sample.dropped') : undefined
    return (
      <FlowFrame step="brief" round={roundLabel} title={t('brief.checking')}>
        {sampleNote && (
          <Banner tone="info" live="polite">
            {sampleNote}
          </Banner>
        )}
        {judged && report.holds && (
          <Banner tone="warning" title={t('brief.reportHeld')} live="polite">
            {t('brief.reportHeldHint')}
          </Banner>
        )}
        {heldReport}
        {!judged && <SignalBanner waiting={run.waiting} />}
        {!judged && <CheckWait startedAt={run.submittedAt ?? Date.now()} />}
      </FlowFrame>
    )
  }

  if (stage === 'recovery' && (state.kind === 'failed' || state.kind === 'submit_failed')) {
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
    // v0.4: 409 script_not_approved: nothing may be spoken before the supervisor approves the script. Go back to it.
    const toScript = async () => {
      await refresh().catch(() => undefined)
      backToScript()
    }
    const actions: RecoveryAction[] = []
    if (plan.backToScript) actions.push({ key: 'script', label: t('brief.backToScript'), icon: 'arrow_back', onClick: () => void toScript() })
    if (plan.offerTurn) actions.push({ key: 'turn', label: t('brief.useTurn'), icon: 'volume_up', onClick: () => handBackToWorker('turn') })
    if (plan.offerRetry) {
      actions.push({
        key: 'retry',
        label: t(state.kind === 'failed' ? 'action.tryAgain' : 'action.retry'),
        icon: 'refresh',
        // A failed session starts again with the worker's Start; a failed check is asked again straight away (the answers are here).
        onClick: state.kind === 'failed' ? () => handBackToWorker(state.mode) : run.retrySubmit,
      })
    }
    const [lead, second] = actions
    return (
      <FlowFrame
        step="brief"
        round={roundLabel}
        title={state.kind === 'failed' ? t('brief.failed') : t('brief.submitFailed')}
        primary={
          lead && (
            <Button size="lg" icon={lead.icon} onClick={lead.onClick}>
              {lead.label}
            </Button>
          )
        }
        secondary={
          second && (
            <Button variant="outlined" icon={second.icon} onClick={second.onClick}>
              {second.label}
            </Button>
          )
        }
      >
        <Banner tone="error" live="assertive">
          {failure.message}
        </Banner>
        {plan.hint === 'turn' && <p className="text-body-lg text-on-surface-variant">{t('brief.failedTurnHint')}</p>}
        {plan.hint === 'not_recorded' && <p className="text-body-lg text-on-surface-variant">{t('brief.notRecordedHint')}</p>}
        {state.kind === 'failed' && (
          <Button variant="text" icon="arrow_back" onClick={backToHandover}>
            {t('brief.backToHandover')}
          </Button>
        )}
        {heldReport}
      </FlowFrame>
    )
  }

  // The handover: the supervisor sets the round up, then gives the phone to the worker.
  const give: ReactNode = (
    <Button
      size="lg"
      icon="smartphone"
      disabled={report.holds}
      disabledReason={report.holds ? t('brief.reportHoldsPage') : undefined}
      onClick={() => {
        setConsentFailed(false)
        setHanded(true)
      }}
    >
      {t('brief.give')}
    </Button>
  )
  return (
    <FlowFrame
      step="brief"
      round={roundLabel}
      title={t('brief.title')}
      subtitle={t('brief.handoverBody', { lang: workerName })}
      primary={give}
      secondary={
        report.holds ? undefined : (
          <Button variant="text" icon="arrow_back" onClick={backToScript}>
            {t('brief.backToScript')}
          </Button>
        )
      }
    >
      {consentFailed && (
        <Banner tone="error" live="assertive">
          {t('consent.saveFailed')}
        </Banner>
      )}
      {judgeDemo && sampleOn && choice.kind === 'available' && <Banner tone="info">{t('judge.handover')}</Banner>}
      <HandoverForm mode={mode} onMode={setMode} sample={choice} sampleOn={sampleOn} onSampleOn={setSampleOn} workerName={workerName} liveListed={liveListed(briefing.workerLang)} />
      <MicBrowserBanner />
      {heldReport}
    </FlowFrame>
  )
}
