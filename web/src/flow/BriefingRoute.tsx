import { useCallback, useEffect, useMemo, useState, type ComponentType } from 'react'
import { Redirect } from 'wouter'
import { api } from '../api/endpoints.ts'
import type { Briefing } from '../api/types.ts'
import { apiErrorText } from '../lib/apiError.ts'
import { useAsync } from '../lib/useAsync.ts'
import { asUiLang, useT, useUiLang } from '../i18n/index.tsx'
import { AppShell } from '../shell/AppShell.tsx'
import { LinkButton } from '../ui/Button.tsx'
import { ErrorState, Skeleton } from '../ui/Feedback.tsx'
import { BriefingContext, type BriefingApi } from './BriefingContext.tsx'
import { allowedPhases, defaultPhase, isPhase, type Phase } from './phases.ts'
import { BriefScreen } from '../screens/brief/BriefScreen.tsx'
import { DecisionScreen } from '../screens/DecisionScreen.tsx'
import { InstructionScreen } from '../screens/InstructionScreen.tsx'
import { RecordScreen } from '../screens/RecordScreen.tsx'
import { ReexplainScreen } from '../screens/ReexplainScreen.tsx'
import { ResultScreen } from '../screens/result/ResultScreen.tsx'
import { ScriptScreen } from '../screens/ScriptScreen.tsx'
import { StepsScreen } from '../screens/StepsScreen.tsx'

const SCREENS: Record<Phase, ComponentType> = {
  instruction: InstructionScreen,
  steps: StepsScreen,
  script: ScriptScreen,
  brief: BriefScreen,
  result: ResultScreen,
  reexplain: ReexplainScreen,
  decision: DecisionScreen,
  record: RecordScreen,
}

/** /b/:id/:phase. Loads the briefing, then shows only the screen the state machine allows. */
export function BriefingRoute({ id, phase }: { id: string; phase?: string }) {
  const t = useT()
  const { setLang } = useUiLang()
  const { data, error, loading, reload } = useAsync(() => api.getBriefing(id), [id])
  const [briefing, setBriefing] = useState<Briefing | undefined>(undefined)

  useEffect(() => {
    if (data) setBriefing(data)
  }, [data])

  // The UI follows the supervisor language of this briefing.
  const supervisorLang = briefing?.supervisorLang
  useEffect(() => {
    if (supervisorLang) setLang(asUiLang(supervisorLang))
  }, [supervisorLang, setLang])

  const refresh = useCallback(async () => {
    const fresh = await api.getBriefing(id)
    setBriefing(fresh)
    return fresh
  }, [id])

  const value = useMemo<BriefingApi | null>(() => (briefing ? { briefing, setBriefing, refresh } : null), [briefing, refresh])

  if (error && !briefing) {
    return (
      <AppShell>
        <ErrorState
          title={error.status === 404 ? t('flow.notFound') : t('error.load')}
          message={error.status === 404 ? t('flow.notFoundHint') : apiErrorText(t, error)}
          retryLabel={error.status === 404 ? undefined : t('action.retry')}
          onRetry={reload}
        />
        <div className="mt-6 flex justify-center">
          <LinkButton href="/records" variant="tonal" icon="receipt_long">
            {t('nav.records')}
          </LinkButton>
        </div>
      </AppShell>
    )
  }
  if (loading || !value) {
    return (
      <AppShell>
        <div className="mx-auto max-w-3xl space-y-4" aria-busy="true" aria-label={t('state.loading')}>
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      </AppShell>
    )
  }

  const b = value.briefing
  if (!isPhase(phase) || !allowedPhases(b).includes(phase)) {
    return <Redirect to={`/b/${id}/${defaultPhase(b)}`} replace />
  }
  const Screen = SCREENS[phase]
  return (
    <BriefingContext value={value}>
      <Screen />
    </BriefingContext>
  )
}
