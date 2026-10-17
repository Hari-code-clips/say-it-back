/* Hallmark · screen: records · genre: modern-minimal · macrostructure: Workbench (one hairline list) · theme: design.md
 * One card of hairline-divided rows, each row a whole-row link to the briefing at its current phase: task, the facts in one line, and the
 * decision as a chip (Go: ink, No-go: neutral outline) or the phase it is still in; the chip sits under the text until 840 px so the text
 * keeps its width. No icon discs, no pills.
 * states: loading (skeleton) · empty (what belongs here and the way in) · error (retry) · default · hover/focus/active (state layer, ring)
 */
import { useRef, type MouseEvent } from 'react'
import { Link } from 'wouter'
import { findTask, langNative, pickText, taskIcon, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import type { BriefingSummary, Status } from '../api/types.ts'
import { siteName, taskTitle } from '../i18n/catalogText.ts'
import { useT, useUiLang, type StringKey } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { formatDuration, secondsToDecision } from '../lib/briefingFacts.ts'
import { permitLabel } from '../lib/permit.ts'
import { downloadBlob } from '../lib/download.ts'
import { formatDateTime } from '../lib/format.ts'
import { useAsync } from '../lib/useAsync.ts'
import { AppShell } from '../shell/AppShell.tsx'
import { AnchorButton, LinkButton } from '../ui/Button.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { Card, RowList } from '../ui/Card.tsx'
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
  const status = item.decision ? <DecisionChip decision={item.decision} /> : <StatusChip>{t(STATUS_LABEL[item.status])}</StatusChip>
  // v0.5.1: instruction to decision, from the record's own two timestamps; nothing before a decision.
  const seconds = secondsToDecision(item.createdAt, item.decision?.at)
  return (
    <li>
      <Link href={`/b/${item.id}`} className="state-layer flex items-start gap-4 px-4 py-4 focus-visible:-outline-offset-[3px] sm:px-5 md:items-center">
        <Icon name={taskIcon(task?.icon)} className="mt-0.5 text-[1.5rem] text-on-surface-variant md:mt-0" />
        <span className="min-w-0 flex-1 space-y-1.5">
          <span lang={item.supervisorLang} className="block text-title-md text-on-surface">
            {title}
          </span>
          <span className="block text-body-md text-on-surface-variant">
            {site ? siteName(site, lang) : item.siteId} · {langNative(catalog, item.supervisorLang)} → {langNative(catalog, item.workerLang)} ·{' '}
            {t('records.rounds', { n: item.rounds })}
            {seconds !== null && ` · ${formatDuration(seconds, lang)}`} · {formatDateTime(item.createdAt, lang)}
            {item.permit && ` · ${permitLabel(item.permit, lang)}`}
          </span>
          <span className="block pt-1 md:hidden">{status}</span>
        </span>
        <span className="hidden md:inline-flex">{status}</span>
        <Icon name="arrow_forward" className="hidden text-on-surface-variant md:inline-block" />
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
          <AnchorButton href="#export" variant="outlined" icon="download" onClick={(e) => void exportCsv(e)}>
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
          <Card>
            <RowList>
              {data.items.map((item) => (
                <RecordRow key={item.id} item={item} />
              ))}
            </RowList>
          </Card>
        )}
        <p className="text-body-md text-on-surface-variant">{t('records.note')}</p>
      </div>
    </AppShell>
  )
}
