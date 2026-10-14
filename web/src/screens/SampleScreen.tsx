import { useMemo } from 'react'
import { useSearch } from 'wouter'
import { api } from '../api/endpoints.ts'
import type { EvalItem } from '../api/types.ts'
import { useT } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { useAsync } from '../lib/useAsync.ts'
import { AppShell } from '../shell/AppShell.tsx'
import { LinkButton } from '../ui/Button.tsx'
import { Banner, ErrorState, Skeleton } from '../ui/Feedback.tsx'
import { PageHeading } from '../ui/PageHeading.tsx'
import { EvalItemCard } from './eval/EvalItemCard.tsx'

/** The most instructive stored clip: a demo answer where some steps are covered and some are not. */
function pickSample(items: EvalItem[]): EvalItem | undefined {
  const mixed = (i: EvalItem) => {
    const v = Object.values(i.gold)
    return v.includes('covered') && v.some((x) => x !== 'covered')
  }
  return items.find((i) => i.pattern === 'demo' && mixed(i)) ?? items.find((i) => i.pattern === 'demo') ?? items.find(mixed) ?? items[0]
}

/** "Try a sample answer": a stored worker clip goes through the real check, with gold labels beside the prediction. */
export function SampleScreen() {
  const t = useT()
  const run = new URLSearchParams(useSearch()).get('run') === '1'
  const { data, loading, error, reload } = useAsync(() => api.evalItems(), [])
  const sample = useMemo(() => (data ? pickSample(data.items) : undefined), [data])

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl space-y-8">
        <PageHeading title={t('sample.title')} subtitle={t('sample.subtitle')} />
        <Banner tone="info" title={t('sample.what')}>
          {t('sample.whatBody')}
        </Banner>
        {loading && <Skeleton className="h-64 w-full" />}
        {error && <ErrorState title={t('error.load')} message={apiErrorText(t, error)} retryLabel={t('action.retry')} onRetry={reload} />}
        {data && !sample && <Banner tone="warning" title={t('sample.none')} />}
        {sample && (
          <ul>
            <EvalItemCard item={sample} autoRun={run} />
          </ul>
        )}
        <div className="flex flex-wrap gap-3">
          <LinkButton href="/new" size="lg" icon="arrow_forward">
            {t('landing.cta.start')}
          </LinkButton>
          <LinkButton href="/eval" size="lg" variant="tonal" icon="analytics">
            {t('sample.seeEval')}
          </LinkButton>
        </div>
      </div>
    </AppShell>
  )
}
