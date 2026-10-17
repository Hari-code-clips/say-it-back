/* Hallmark · screen: the judge demo's start (/judge) · genre: modern-minimal · macrostructure: Workbench · theme: design.md
 * The landing link lands here. The screen creates the lead case's briefing with the sample instruction and finds its critical steps
 * (the one wait, in view), then opens the Steps screen. The supervisor's gates stay: the judge confirms the steps and the script, and
 * the handover opens with the stored sample answers chosen (BriefScreen reads judgeDemo.ts).
 * states: loading (catalogue: the wait) · running (WaitInView) · error (the reason, Retry unless the day's calls are used up, and the
 *         ordinary Start as a text link) · success (navigates). No primary of its own while it works: nothing to press.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'wouter'
import { useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import type { CreateBriefingBody } from '../api/types.ts'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { judgeDemoBody, startJudgeDemo } from '../flow/judgeDemo.ts'
import { useT } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { isDailyLimit } from '../lib/dailyLimit.ts'
import { ErrorState } from '../ui/Feedback.tsx'
import { WaitInView } from './instruction/WaitInView.tsx'

export function JudgeDemoScreen() {
  const t = useT()
  const [, navigate] = useLocation()
  const { data: catalog, error: catalogError, reload } = useCatalog()
  const body = useMemo(() => (catalog ? judgeDemoBody(catalog) : null), [catalog])
  // After a failed extract the briefing exists: Retry patches that one instead of creating a second (startBriefing.ts).
  const held = useRef<{ id: string | null }>({ id: null }).current
  const started = useRef(false)
  const [failure, setFailure] = useState<unknown>(null)

  const run = useCallback(
    async (lead: CreateBriefingBody) => {
      setFailure(null)
      try {
        const steps = await startJudgeDemo(lead, held, { create: api.createBriefing, patch: api.patchInstruction, extract: api.extractSteps })
        navigate(steps, { replace: true })
      } catch (e) {
        setFailure(e)
      }
    },
    [held, navigate],
  )

  useEffect(() => {
    if (!body || started.current) return
    started.current = true // once per visit (StrictMode runs effects twice in development)
    void run(body)
  }, [body, run])

  const context = body && { taskId: body.taskId, siteId: body.siteId, supervisorLang: body.supervisorLang, workerLang: body.workerLang }
  const problem = catalogError && !catalog ? catalogError : failure
  const noLead = catalog !== undefined && body === null
  const retry = problem && !isDailyLimit(problem) ? () => (body ? void run(body) : reload()) : undefined

  return (
    <FlowFrame step="instruction" title={t('judge.title')} subtitle={t('judge.subtitle')} context={context ?? false} leaveTo="/">
      {problem || noLead ? (
        <div className="space-y-4">
          <ErrorState
            title={t('judge.failed')}
            message={noLead ? t('judge.noLead') : apiErrorText(t, problem)}
            retryLabel={t('action.retry')}
            onRetry={noLead ? undefined : retry}
          />
          <Link href="/new" className="inline-flex min-h-12 items-center font-semibold text-primary underline underline-offset-4">
            {t('judge.byHand')}
          </Link>
        </div>
      ) : (
        <WaitInView title={t('instr.extracting')} hint={t('instr.extractingHint')} />
      )}
    </FlowFrame>
  )
}
