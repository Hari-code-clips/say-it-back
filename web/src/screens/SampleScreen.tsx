/* Hallmark · component: curated sample picker · genre: utilitarian (existing M3 system) · theme: project tokens
 * states: default · hover · focus · active (RadioCard) · loading (skeleton) · error (load failed, Retry) · empty (fresh deploy) ·
 * success (the check's result, in EvalItemCard)
 */
import { useMemo, useRef, useState } from 'react'
import { useSearch } from 'wouter'
import { langNative, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import { useT } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { useAsync } from '../lib/useAsync.ts'
import { AppShell } from '../shell/AppShell.tsx'
import { LinkButton } from '../ui/Button.tsx'
import { RadioCard } from '../ui/Choice.tsx'
import { Banner, EmptyState, ErrorState, Skeleton } from '../ui/Feedback.tsx'
import { Icon } from '../ui/Icon.tsx'
import { PageHeading } from '../ui/PageHeading.tsx'
import { EvalItemCard } from './eval/EvalItemCard.tsx'
import { patternLabel, testsLine } from './eval/labels.ts'
import { pickSamples } from './eval/pickSamples.ts'
import { storedResult } from './eval/storedResult.ts'

/** "Try a sample answer": up to three stored worker clips go through the real check, with the person's labels beside it. */
export function SampleScreen() {
  const t = useT()
  const { data: catalog } = useCatalog()
  const run = new URLSearchParams(useSearch()).get('run') === '1'
  const { data, loading, error, reload } = useAsync(() => api.evalItems(), [])
  const report = useAsync(() => api.evalLatest(), [])
  const samples = useMemo(() => (data ? pickSamples(data.items) : []), [data])
  const [chosen, setChosen] = useState<string | null>(null)
  // `?run=1` (the landing page's button) runs the first clip once; picking another never re-runs it by itself.
  const autoRun = useRef(run)
  const selected = samples.find((s) => s.id === chosen) ?? samples[0]

  // A fresh deployment has no test set (404 here) and no report: say so plainly instead of showing an error.
  const noItems = error?.status === 404 || (data !== undefined && samples.length === 0)
  const hasReport = report.data !== undefined
  const stored = selected ? storedResult(report.data, selected) : null

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl space-y-8">
        <PageHeading title={t('sample.title')} subtitle={t('sample.subtitle')} />
        <Banner tone="info" title={t('sample.what')}>
          {t('sample.whatBody')}
        </Banner>
        {loading && <Skeleton className="h-64 w-full" />}
        {error && !noItems && <ErrorState title={t('error.load')} message={apiErrorText(t, error)} retryLabel={t('action.retry')} onRetry={reload} />}
        {noItems && !loading && (
          <EmptyState
            icon="graphic_eq"
            title={t('sample.none')}
            body={hasReport ? t('sample.noneReport') : t('sample.noneFresh')}
            action={
              <LinkButton href={hasReport ? '/eval' : '/new'} size="lg" icon={hasReport ? 'analytics' : 'record_voice_over'}>
                {hasReport ? t('sample.seeEval') : t('landing.cta.start')}
              </LinkButton>
            }
          />
        )}

        {samples.length > 1 && (
          <section aria-labelledby="sample-pick" className="space-y-3">
            <h2 id="sample-pick" className="text-title-lg text-on-surface">
              {t('sample.pick')}
            </h2>
            <div role="radiogroup" aria-labelledby="sample-pick" className="grid gap-3 md:grid-cols-3">
              {samples.map((item) => (
                <RadioCard
                  key={item.id}
                  name="sample"
                  value={item.id}
                  checked={selected?.id === item.id}
                  onChange={() => {
                    autoRun.current = false
                    setChosen(item.id)
                  }}
                  icon={<Icon name={item.pattern === 'demo' ? 'record_voice_over' : item.pattern === 'silence' || item.pattern === 'wrong_language' ? 'replay' : 'cancel'} />}
                  title={`${patternLabel(t, item.pattern)} · ${langNative(catalog, item.workerLang)}`}
                  subtitle={testsLine(t, item.pattern)}
                />
              ))}
            </div>
          </section>
        )}

        {selected && (
          <div key={selected.id}>
            {/* v0.5.1: with a stored result from the evaluation run the card shows it at once, and the live check (16-105 s
                on real Gemini) is the second action. `?run=1` runs it live only when there is none, once the report has
                answered: deciding before that would start a live run the stored result makes unnecessary. */}
            <EvalItemCard
              item={selected}
              as="div"
              stored={stored}
              autoRun={autoRun.current && selected.id === samples[0]?.id && !report.loading && !stored}
            />
          </div>
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
