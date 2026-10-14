import { useRef, type MouseEvent } from 'react'
import { Link } from 'wouter'
import { findTask, langNative, pickText, taskIcon, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import type { BriefingSummary, Status } from '../api/types.ts'
import { siteName, taskTitle } from '../i18n/catalogText.ts'
import { useT, useUiLang, type StringKey } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { downloadBlob } from '../lib/download.ts'
import { formatDateTime } from '../lib/format.ts'
import { useAsync } from '../lib/useAsync.ts'
import { AppShell } from '../shell/AppShell.tsx'
import { AnchorButton, LinkButton } from '../ui/Button.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { EmptyState, ErrorState, Skeleton } from '../ui/Feedback.tsx'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { Icon } from '../ui/Icon.tsx'
import { PageHeading } from '../ui/PageHeading.tsx'
import { DecisionChip } from './RecordScreen.tsx'

const STATUS_LABEL: Record<Status, StringKey> = {
  draft: 'status.draft',
  steps_proposed: 'status.steps_proposed',
  steps_confirmed: 'status.steps_confirmed',
  briefing: 'status.briefing',
  judged: 'status.judged',
  decided: 'status.decided',
}

function RecordRow({ item }: { item: BriefingSummary }) {
  const t = useT()
  const { lang } = useUiLang()
  const { data: catalog } = useCatalog()
  const task = findTask(catalog, item.taskId)
  const title = (task && taskTitle(task, item.supervisorLang)) || pickText(item.taskTitle, item.supervisorLang) || item.taskId
  const site = catalog?.sites.find((s) => s.id === item.siteId)
  const status = item.decision ? <DecisionChip decision={item.decision} /> : <StatusChip tone="warning">{t(STATUS_LABEL[item.status])}</StatusChip>
  return (
    <li>
      <Link
        href={`/b/${item.id}`}
        className="state-layer flex items-start gap-4 rounded-lg border border-outline-variant bg-surface-container-lowest p-4 sm:items-center sm:p-5"
      >
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-secondary-container text-on-secondary-container">
          <Icon name={taskIcon(task?.icon)} />
        </span>
        <span className="min-w-0 flex-1 space-y-1.5">
          <span lang={item.supervisorLang} className="block text-title-md text-on-surface">
            {title}
          </span>
          <span className="block text-body-md text-on-surface-variant">
            {site ? siteName(site, lang) : item.siteId} · {langNative(catalog, item.supervisorLang)} → {langNative(catalog, item.workerLang)} ·{' '}
            {t('records.rounds', { n: item.rounds })} · {formatDateTime(item.createdAt, lang)}
          </span>
          <span className="block pt-1 sm:hidden">{status}</span>
        </span>
        <span className="hidden sm:inline-flex">{status}</span>
        <Icon name="arrow_forward" className="hidden text-on-surface-variant sm:inline-block" />
      </Link>
    </li>
  )
}

export function RecordsScreen() {
  const t = useT()
  const feedback = useFeedback()
  const { data, loading, error, reload } = useAsync(() => api.listBriefings(50), [])

  // The export is the caller's own briefings, so the request carries the device key, which a plain link cannot send:
  // fetch the file through the API client and hand it to the browser as a download.
  const exporting = useRef(false)
  const exportCsv = async (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault()
    if (exporting.current) return
    exporting.current = true
    try {
      downloadBlob(await api.exportCsv(), 'say-it-back-briefings.csv')
    } catch (err) {
      feedback.snack({ message: apiErrorText(t, err), tone: 'error' })
    } finally {
      exporting.current = false
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl space-y-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <PageHeading title={t('records.title')} subtitle={t('records.subtitle')} />
          <AnchorButton href="#export" variant="tonal" icon="download" onClick={(e) => void exportCsv(e)}>
            {t('records.export')}
          </AnchorButton>
        </div>

        {loading && (
          <div className="space-y-3" aria-busy="true" aria-label={t('state.loading')}>
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}
        {error && <ErrorState title={t('error.load')} message={apiErrorText(t, error)} retryLabel={t('action.retry')} onRetry={reload} />}
        {data && data.items.length === 0 && (
          <EmptyState
            icon="receipt_long"
            title={t('records.empty')}
            body={t('records.emptyHint')}
            action={
              <LinkButton href="/new" icon="record_voice_over" size="lg">
                {t('landing.cta.start')}
              </LinkButton>
            }
          />
        )}
        {data && data.items.length > 0 && (
          <ul className="space-y-3">
            {data.items.map((item) => (
              <RecordRow key={item.id} item={item} />
            ))}
          </ul>
        )}
        <p className="text-body-md text-on-surface-variant">{t('records.note')}</p>
      </div>
    </AppShell>
  )
}
