import { useContext, type ReactNode } from 'react'
import { useLocation } from 'wouter'
import { CUSTOM_TASK_ID, findTask, langNative, taskIcon, useCatalog } from '../api/catalog.tsx'
import type { Lang } from '../api/types.ts'
import { siteName, taskTitle } from '../i18n/catalogText.ts'
import { useSopLabel, useT, useUiLang } from '../i18n/index.tsx'
import { MockBadge, SkipLink } from '../shell/AppShell.tsx'
import { LangMenu } from '../shell/LangMenu.tsx'
import { IconButton } from '../ui/Button.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { cx } from '../ui/cx.ts'
import { PageHeading } from '../ui/PageHeading.tsx'
import { BriefingContext } from './BriefingContext.tsx'
import { PROGRESS, PROGRESS_TOTAL, type FlowStep } from './phases.ts'

export interface ContextInfo {
  taskId: string
  siteId: string
  /** Title of a pasted SOP. */
  customTitle?: string
  /** SOP id and version; taken from the catalog task when omitted. */
  sop?: { id: string; version: string }
  supervisorLang: Lang
  workerLang: Lang
}

/** Task, SOP and language pair: from explicit info (before a briefing exists) or the current briefing. */
export function TaskContext({ info }: { info?: ContextInfo }) {
  const t = useT()
  const { lang } = useUiLang()
  const sopLabel = useSopLabel()
  const ctx = useContext(BriefingContext)
  const { data: catalog } = useCatalog()
  const b = ctx?.briefing
  const c: ContextInfo | undefined =
    info ?? (b && { taskId: b.taskId, siteId: b.siteId, customTitle: b.sop.title, sop: b.sop, supervisorLang: b.supervisorLang, workerLang: b.workerLang })
  if (!c) return null
  const task = findTask(catalog, c.taskId)
  const title = c.taskId === CUSTOM_TASK_ID ? c.customTitle || t('start.custom.title') : (task && taskTitle(task, c.supervisorLang)) || c.customTitle || ''
  const sop = c.sop ?? task?.sop ?? (c.taskId === CUSTOM_TASK_ID ? { id: 'CUSTOM', version: '' } : undefined)
  const site = catalog?.sites.find((s) => s.id === c.siteId)
  const details = [sop && sopLabel(sop), site ? siteName(site, lang) : c.siteId, `${langNative(catalog, c.supervisorLang)} → ${langNative(catalog, c.workerLang)}`].filter(Boolean).join(' · ')
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label={t('flow.context')} role="group">
      <StatusChip tone="primary" icon={taskIcon(task?.icon)}>
        {title}
      </StatusChip>
      <StatusChip>{details}</StatusChip>
    </div>
  )
}

interface FlowFrameProps {
  step: FlowStep
  title: string
  subtitle?: ReactNode
  /** Small line above the title, e.g. "Round 2 of 3". */
  eyebrow?: string
  /** The one dominant action first; a quieter secondary beside it. */
  primary?: ReactNode
  secondary?: ReactNode
  /** Two-column layouts on laptops need the wider container. */
  wide?: boolean
  /** Explicit context (before a briefing exists); `false` hides it. */
  context?: ContextInfo | false
  /** Where the close button goes. */
  leaveTo?: string
  children: ReactNode
}

export function FlowFrame({ step, title, subtitle, eyebrow, primary, secondary, wide, context, leaveTo = '/records', children }: FlowFrameProps) {
  const t = useT()
  const [, navigate] = useLocation()
  const n = PROGRESS[step]
  const stepLabel = t('flow.step', { n, total: PROGRESS_TOTAL })

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 bg-surface/92 backdrop-blur">
        <SkipLink />
        <div className={cx('mx-auto flex h-16 items-center gap-1 px-2 sm:px-4', wide ? 'max-w-5xl' : 'max-w-3xl')}>
          <IconButton icon="close" label={t('flow.leave')} onClick={() => navigate(leaveTo)} />
          <div className="min-w-0 flex-1 px-2">
            <p className="truncate text-label-lg text-on-surface-variant">{stepLabel}</p>
            <p className="truncate text-title-md text-on-surface">{t(`phase.${step}`)}</p>
          </div>
          <MockBadge />
          <LangMenu />
        </div>
        <div
          role="progressbar"
          aria-label={`${stepLabel}: ${t(`phase.${step}`)}`}
          aria-valuemin={1}
          aria-valuemax={PROGRESS_TOTAL}
          aria-valuenow={n}
          className="h-1 bg-surface-container-high"
        >
          <div className="h-full rounded-r-full bg-primary transition-[width] duration-300" style={{ width: `${(n / PROGRESS_TOTAL) * 100}%` }} />
        </div>
      </header>

      <main id="main" tabIndex={-1} className={cx('mx-auto w-full flex-1 px-4 pb-44 pt-6 sm:px-6 md:pt-10', wide ? 'max-w-5xl' : 'max-w-3xl')}>
        <div className="animate-rise space-y-8">
          <div className="space-y-4">
            {context !== false && <TaskContext info={context} />}
            <PageHeading title={title} subtitle={subtitle} eyebrow={eyebrow} />
          </div>
          {children}
        </div>

        {(primary || secondary) && (
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-outline-variant bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
            <div className={cx('mx-auto flex flex-col-reverse gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-end sm:px-6', wide ? 'max-w-5xl' : 'max-w-3xl')}>
              {secondary}
              {primary}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
