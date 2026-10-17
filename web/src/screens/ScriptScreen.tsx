/* Hallmark · screen: script check and approval (F1, act one) · genre: modern-minimal · macrostructure: Workbench · theme: design.md
 * The supervisor reads what the worker will hear in THEIR language first (the back-translation, then the questions, then the closing
 * line), and only then approves. The worker-language text is second, behind a disclosure. Approving is its own act, and handing the
 * phone over is the next screen (/b/:id/brief). Nothing is spoken before the approval (endpoint 23).
 * states: Approve (default · hover · focus-visible · active · loading `busy` · error: a snackbar with Retry · success: the
 *         approval line and "Go to the handover"); the disclosure (closed · open · focus-visible). 2026-10-17: while the worker's
 *         "Not now" stands, "Record an in-person check" is the one blue fill (default · hover · focus-visible · active · loading n/a,
 *         it only navigates · disabled n/a · error n/a · success: the decision screen) and "Go to the handover" is outlined.
 */
import { useState } from 'react'
import { useLocation } from 'wouter'
import { bcp47, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { MAX_ROUNDS, awaitsInPersonCheck, latestRound } from '../flow/phases.ts'
import { recoverFromConflict } from '../flow/recover.ts'
import { UnexpectedState } from '../flow/UnexpectedState.tsx'
import { useLangName, useT, useUiLang } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { scriptCoverage, stepsBySentence } from '../lib/coverage.ts'
import { formatDateTime } from '../lib/format.ts'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { Button } from '../ui/Button.tsx'
import { Card, RowList } from '../ui/Card.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { Banner } from '../ui/Feedback.tsx'
import { Icon } from '../ui/Icon.tsx'

export function ScriptScreen() {
  const t = useT()
  const { lang: uiLang } = useUiLang()
  const feedback = useFeedback()
  const [, navigate] = useLocation()
  const { briefing, setBriefing, refresh } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const [busy, setBusy] = useState(false)
  const round = latestRound(briefing)
  if (!round) return <UnexpectedState />

  // v0.4 gate (endpoint 23): approving is the supervisor's act, recorded on the server first. It does not hand the phone over: that is
  // the next screen. The worker's screen, the voice ticket, TTS and the check all refuse an unapproved round. A round already
  // approved (the supervisor came back to this screen) just moves on, with no second call.
  const approve = async () => {
    if (round.approvedAt) return navigate(`/b/${briefing.id}/brief`)
    setBusy(true)
    try {
      const approved = await api.approveRound(briefing.id, round.n)
      setBriefing({ ...briefing, rounds: briefing.rounds.map((r) => (r.n === approved.n ? approved : r)) })
      navigate(`/b/${briefing.id}/brief`)
    } catch (e) {
      setBusy(false)
      if (await recoverFromConflict(e, refresh, navigate)) return
      feedback.snack({ message: apiErrorText(t, e), tone: 'error', actionLabel: t('action.retry'), onAction: () => void approve() })
    }
  }

  const { script } = round
  const supervisorTag = bcp47(catalog, briefing.supervisorLang, briefing.siteId)
  const workerTag = bcp47(catalog, briefing.workerLang, briefing.siteId)
  const workerName = langName(briefing.workerLang)
  const supervisorName = langName(briefing.supervisorLang)
  const { sentences, stepIds: bySentence } = stepsBySentence(script)
  const stepNumber = (id: string) => briefing.steps.findIndex((s) => s.id === id) + 1
  const coverage = scriptCoverage(round.stepIds, script)
  const complete = coverage.notDelivered.length === 0 && coverage.notAsked.length === 0
  const reexplain = round.kind === 'reexplain'
  const approved = Boolean(round.approvedAt)
  // 2026-10-17: the worker said "Not now" to this round's recording: brief them in person, then record it (a reload lands here).
  const inPerson = awaitsInPersonCheck(briefing)
  const handover = (
    <Button size={inPerson ? 'md' : 'lg'} variant={inPerson ? 'outlined' : 'filled'} icon={approved ? 'arrow_forward' : 'check'} busy={busy} onClick={() => void approve()}>
      {approved ? t('script.toHandover') : t('script.approve')}
    </Button>
  )

  return (
    <FlowFrame
      step="script"
      round={t('script.round', { n: round.n, max: MAX_ROUNDS })}
      title={reexplain ? t('script.titleReexplain') : t('script.title')}
      subtitle={t('script.subtitle', { supervisor: supervisorName })}
      primary={
        inPerson ? (
          <Button size="lg" icon="fact_check" onClick={() => navigate(`/b/${briefing.id}/decision`)}>
            {t('inPerson.record')}
          </Button>
        ) : (
          handover
        )
      }
      secondary={inPerson ? handover : undefined}
    >
      {approved && (
        <p role="status" className="flex items-start gap-2 text-body-md text-on-surface-variant">
          <Icon name="task_alt" className="mt-0.5 text-[1.25rem] text-on-surface" />
          <span>{t('script.approvalRecorded', { time: formatDateTime(round.approvedAt ?? '', uiLang) })}</span>
        </p>
      )}
      {inPerson && (
        <p className="flex items-start gap-2 text-body-lg text-on-surface">
          <Icon name="info" className="mt-0.5 text-[1.25rem] text-on-surface-variant" />
          <span className="min-w-0">{t('inPerson.scriptLine')}</span>
        </p>
      )}
      {!complete && (
        <Banner tone="warning" title={t('script.coverageGap')} live="assertive">
          {coverage.notDelivered.length > 0 && <p>{t('script.notDelivered', { steps: coverage.notDelivered.map(stepNumber).join(', ') })}</p>}
          {coverage.notAsked.length > 0 && <p>{t('script.notAsked', { steps: coverage.notAsked.map(stepNumber).join(', ') })}</p>}
        </Banner>
      )}

      {round.supervisorNote && (
        <section aria-labelledby="script-note" className="space-y-2">
          <h2 id="script-note" className="text-title-lg text-on-surface">
            {t('script.yourWords')}
          </h2>
          <p lang={supervisorTag} className="script-text text-body-lg text-on-surface-variant">
            {round.supervisorNote}
          </p>
        </section>
      )}

      {/* 1. What the worker will hear, in the supervisor's language: the one thing the supervisor can actually check. */}
      <section aria-labelledby="script-heard" className="space-y-3">
        <div className="space-y-1">
          <h2 id="script-heard" className="text-title-lg text-on-surface">
            {t('script.heardIn', { lang: supervisorName })}
          </h2>
          <p className="text-body-md text-on-surface-variant">{t('script.heardInHint', { worker: workerName })}</p>
        </div>
        <Card className="p-4 sm:p-5">
          <p lang={supervisorTag} className="script-text whitespace-pre-line text-body-lg text-on-surface">
            {script.instructionBackTranslation}
          </p>
        </Card>
      </section>

      {/* 2. The questions, in the supervisor's language, with the steps each one checks. */}
      <section aria-labelledby="script-questions" className="space-y-3">
        <div className="space-y-1">
          <h2 id="script-questions" className="text-title-lg text-on-surface">
            {t('script.questions')}
          </h2>
          <p className="text-body-md text-on-surface-variant">{t('script.questionsHint')}</p>
        </div>
        <Card>
          <RowList as="ol">
            {script.questions.map((q) => (
              <li key={q.id} className="space-y-2 p-4 sm:p-5">
                <p lang={supervisorTag} className="script-text text-body-lg text-on-surface">
                  {q.backTranslation}
                </p>
                <p className="flex flex-wrap items-center gap-2 text-body-md text-on-surface-variant">
                  {t('script.checks')}
                  {q.stepIds.map((id) => (
                    <StatusChip key={id}>{t('script.stepN', { n: stepNumber(id) })}</StatusChip>
                  ))}
                </p>
              </li>
            ))}
          </RowList>
        </Card>
      </section>

      {/* 3. The closing line. The data carries no back-translation for it, so the screen says so instead of leaving a gap. */}
      <section aria-labelledby="script-closing" className="space-y-3">
        <h2 id="script-closing" className="text-title-lg text-on-surface">
          {t('script.closing')}
        </h2>
        <Card className="p-4 sm:p-5">
          <p className="flex items-start gap-2 text-body-md text-on-surface-variant">
            <Icon name="info" className="mt-0.5 text-[1.25rem]" />
            <span className="min-w-0">{t('script.closingNoTranslation', { lang: supervisorName })}</span>
          </p>
        </Card>
      </section>

      {complete && (
        <p className="flex items-start gap-2 text-body-md text-on-surface-variant">
          <Icon name="task_alt" className="mt-0.5 text-[1.25rem] text-on-surface" />
          <span className="min-w-0">
            <span className="block font-semibold text-on-surface">{t('script.coverageOk')}</span>
            <span className="block">{t('script.coverageOkHint', { n: round.stepIds.length })}</span>
          </span>
        </p>
      )}

      {/* The worker-language text, second and collapsed: exactly what the voice reads. */}
      <details className="group rounded-lg border border-outline-variant bg-surface-container-lowest">
        <summary className="state-layer flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-4 py-3 text-title-md text-on-surface [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            {t('script.workerText', { worker: workerName })}
          </span>
          <Icon name="expand_more" className="shrink-0 transition-transform group-open:rotate-180" />
        </summary>
        <div className="space-y-5 border-t border-outline-variant p-4 sm:p-5">
          <p className="text-body-md text-on-surface-variant">{t('script.workerTextHint')}</p>
          <ol lang={workerTag} className="space-y-3">
            {sentences.map((sentence, i) => (
              <li key={i} className="script-text text-title-lg">
                {sentence}
                {(bySentence[i] ?? []).length > 0 && (
                  <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
                    {(bySentence[i] ?? []).map((id) => (
                      <StatusChip key={id} tone="primary" lang={briefing.supervisorLang}>
                        {t('script.deliversStep', { n: stepNumber(id) })}
                      </StatusChip>
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ol>
          <ol lang={workerTag} className="space-y-3 border-t border-outline-variant pt-4">
            {script.questions.map((q) => (
              <li key={q.id} className="script-text text-title-lg">
                {q.text}
              </li>
            ))}
          </ol>
          <p lang={workerTag} className="script-text border-t border-outline-variant pt-4 text-title-lg">
            {script.closing}
          </p>
        </div>
      </details>
    </FlowFrame>
  )
}
