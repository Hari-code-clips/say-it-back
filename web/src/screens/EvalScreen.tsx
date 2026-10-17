import { useMemo, useState } from 'react'
import { IS_MOCK } from '../api/client.ts'
import { langNative, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import type { Lang } from '../api/types.ts'
import { useT } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { useAsync } from '../lib/useAsync.ts'
import { AppShell } from '../shell/AppShell.tsx'
import { Section } from '../ui/Card.tsx'
import { ChoiceChips } from '../ui/Choice.tsx'
import { Banner, EmptyState, ErrorState, Skeleton } from '../ui/Feedback.tsx'
import { PageHeading } from '../ui/PageHeading.tsx'
import { EvalItemCard } from './eval/EvalItemCard.tsx'
import { MetricsPanel } from './eval/MetricsPanel.tsx'

const PAGE = 8

export function EvalScreen() {
  const t = useT()
  const { data: catalog } = useCatalog()
  const report = useAsync(() => api.evalLatest(), [])
  const items = useAsync(() => api.evalItems(), [])
  const [lang, setLang] = useState<'all' | Lang>('all')
  const [shown, setShown] = useState(PAGE)

  const all = items.data?.items
  const langs = useMemo(() => [...new Set((all ?? []).map((i) => i.workerLang))], [all])
  const filtered = useMemo(() => (all ?? []).filter((i) => lang === 'all' || i.workerLang === lang), [all, lang])
  const noReport = report.error?.code === 'no_report' || report.error?.status === 404
  // A deployment without the test set answers 404 here: that is "no items", not a failure to show.
  const noItems = items.error?.status === 404 || (all !== undefined && all.length === 0)

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl space-y-10">
        <PageHeading title={t('eval.title')} subtitle={t('eval.subtitle')} />
        {IS_MOCK && (
          <Banner tone="warning" title={t('eval.mockTitle')}>
            {t('eval.mockBody')}
          </Banner>
        )}

        {report.loading && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true" aria-label={t('state.loading')}>
            <Skeleton className="h-32 sm:col-span-2" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
        )}
        {report.data && <MetricsPanel report={report.data} illustrative={IS_MOCK} />}
        {noReport && <EmptyState icon="analytics" title={t('eval.noReport')} body={t('eval.noReportHint')} />}
        {report.error && !noReport && <ErrorState title={t('error.load')} message={apiErrorText(t, report.error)} retryLabel={t('action.retry')} onRetry={report.reload} />}

        <Section title={t('eval.items')} hint={t('eval.itemsHint')} id="eval-items">
          {langs.length > 1 && (
            <ChoiceChips<'all' | Lang>
              label={t('eval.filter')}
              value={lang}
              onChange={(v) => {
                setLang(v)
                setShown(PAGE)
              }}
              options={[{ value: 'all', label: t('eval.all') }, ...langs.map((l) => ({ value: l, label: langNative(catalog, l), lang: l }))]}
            />
          )}
          {items.loading && <Skeleton className="h-48 w-full" />}
          {items.error && !noItems && <ErrorState title={t('error.load')} message={apiErrorText(t, items.error)} retryLabel={t('action.retry')} onRetry={items.reload} />}
          {noItems && <EmptyState icon="analytics" title={t('eval.noItems')} body={t('eval.noItemsHint')} />}
          <ul className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
            {filtered.slice(0, shown).map((item) => (
              <EvalItemCard key={item.id} item={item} />
            ))}
          </ul>
          {filtered.length > shown && (
            <button
              type="button"
              onClick={() => setShown((n) => n + PAGE)}
              className="state-layer mx-auto flex min-h-12 items-center rounded-full border border-outline px-6 text-label-lg text-primary"
            >
              {t('eval.more', { n: filtered.length - shown })}
            </button>
          )}
        </Section>
      </div>
    </AppShell>
  )
}
