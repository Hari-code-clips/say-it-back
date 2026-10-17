/* Hallmark · component: flow frame (sticky top bar, context line + H1, sticky bottom bar) · genre: modern-minimal · macrostructure: Workbench
 * theme: design.md. The top bar: leave, the named phases, Mock chip, language. The content: ONE context line, the H1, the screen.
 * The bottom bar: the screen's actions, primary 64 px full width at the bottom. Its measured height is written to --sib-bar-h and
 * reserved under the content (plus the safe area), so nothing is ever behind it, at any width, in any language. It is a labelled
 * region landmark ("Actions"), so its buttons and a disabled reason are inside a landmark (axe `region`; build-notes/37 section 5).
 */
import { useContext, useLayoutEffect, useRef, type ReactNode } from 'react'
import { useLocation } from 'wouter'
import { CUSTOM_TASK_ID, findTask, langNative, useCatalog } from '../api/catalog.tsx'
import type { Lang, PermitLink } from '../api/types.ts'
import { taskTitle } from '../i18n/catalogText.ts'
import { useT, useUiLang } from '../i18n/index.tsx'
import { permitLabel } from '../lib/permit.ts'
import { MockBadge, SkipLink } from '../shell/AppShell.tsx'
import { DailyLimitNotice } from '../shell/DailyLimitNotice.tsx'
import { LangMenu } from '../shell/LangMenu.tsx'
import { IconButton } from '../ui/Button.tsx'
import { cx } from '../ui/cx.ts'
import { PageHeading } from '../ui/PageHeading.tsx'
import { BriefingContext } from './BriefingContext.tsx'
import { contextParts, CONTEXT_SEPARATOR, languagePair } from './contextLine.ts'
import { PhaseBar } from './PhaseBar.tsx'
import type { FlowStep } from './phases.ts'

export interface ContextInfo {
  taskId: string
  siteId: string
  /** Title of a pasted SOP. */
  customTitle?: string
  /** SOP id and version; taken from the catalog task when omitted. */
  sop?: { id: string; version: string }
  supervisorLang: Lang
  workerLang: Lang
  /** v0.5.2: the permit-to-work this briefing checks one worker for. */
  permit?: PermitLink | null
}

/**
 * The one context line: task · language pair · permit (when there is one) · round (when the screen has one).
 * From explicit info (before a briefing exists) or the current briefing. The SOP id and the site are not in it: they are on the
 * Steps and Record screens, where they mean something.
 */
export function ContextLine({ info, round }: { info?: ContextInfo; round?: string }) {
  const t = useT()
  const { lang } = useUiLang()
  const ctx = useContext(BriefingContext)
  const { data: catalog } = useCatalog()
  const b = ctx?.briefing
  const c: ContextInfo | undefined =
    info ?? (b && { taskId: b.taskId, siteId: b.siteId, customTitle: b.sop.title, sop: b.sop, supervisorLang: b.supervisorLang, workerLang: b.workerLang, permit: b.permit })
  if (!c) return round ? <span>{round}</span> : null
  const task = findTask(catalog, c.taskId)
  const title = c.taskId === CUSTOM_TASK_ID ? c.customTitle || t('start.custom.title') : (task && taskTitle(task, c.supervisorLang)) || c.customTitle || ''
  const pair = languagePair(langNative(catalog, c.supervisorLang), langNative(catalog, c.workerLang))
  // Each part after the title stays on one line ("Round 1 of 3" never breaks in the middle); the line breaks between parts.
  const parts = contextParts([title, pair, c.permit && permitLabel(c.permit, lang), round])
  return (
    <p className="text-body-md text-on-surface-variant">
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 && CONTEXT_SEPARATOR}
          <span className={i > 0 ? 'whitespace-nowrap' : undefined}>{part}</span>
        </span>
      ))}
    </p>
  )
}

interface FlowFrameProps {
  step: FlowStep
  title: string
  subtitle?: ReactNode
  /** The round, e.g. "Round 2 of 3": the last part of the context line. Rounds are the only count in the header. */
  round?: string
  /** @deprecated The old name of `round`. There are no eyebrows now; a screen still passing one gets it as its round. */
  eyebrow?: string
  /** The one dominant action: 64 px, full width, at the bottom. Give it `disabledReason` when it is off. */
  primary?: ReactNode
  /** A quieter action above it (on a phone) or beside it (from 600 px). */
  secondary?: ReactNode
  /** Two-column layouts on laptops need the wider container. */
  wide?: boolean
  /** Explicit context (before a briefing exists); `false` hides it. */
  context?: ContextInfo | false
  /** Where the close button goes. */
  leaveTo?: string
  children: ReactNode
}

/**
 * Keeps `--sib-bar-h` on <html> equal to the measured height of the sticky bottom bar (safe area included), so the page, the
 * scroll-padding and the snackbar all clear it. A bar that grows (a disabled reason appears, a longer language) is followed.
 */
function useBarHeight(active: boolean) {
  const ref = useRef<HTMLElement>(null)
  useLayoutEffect(() => {
    const root = document.documentElement
    const el = ref.current
    if (!active || !el) return
    const write = () => root.style.setProperty('--sib-bar-h', `${Math.ceil(el.getBoundingClientRect().height)}px`)
    write()
    const watch = new ResizeObserver(write)
    watch.observe(el)
    return () => {
      watch.disconnect()
      root.style.removeProperty('--sib-bar-h')
    }
  }, [active])
  return ref
}

export function FlowFrame({ step, title, subtitle, round, eyebrow, primary, secondary, wide, context, leaveTo = '/records', children }: FlowFrameProps) {
  const t = useT()
  const [, navigate] = useLocation()
  const hasBar = Boolean(primary || secondary)
  const bar = useBarHeight(hasBar)
  const width = wide ? 'max-w-5xl' : 'max-w-3xl'

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-outline-variant bg-surface">
        <SkipLink />
        <div className={cx('mx-auto flex h-14 items-center gap-1 px-2 sm:px-4', width)}>
          <IconButton icon="close" label={t('flow.leave')} onClick={() => navigate(leaveTo)} />
          <PhaseBar step={step} />
          <MockBadge />
          <LangMenu />
        </div>
      </header>

      <main
        id="main"
        tabIndex={-1}
        // Room under the content for the fixed action bar: its measured height, 11rem until it has been measured.
        className={cx('mx-auto w-full flex-1 px-4 pt-6 sm:px-6 md:pt-10', hasBar ? 'pb-[calc(var(--sib-bar-h,11rem)+1.5rem)]' : 'pb-16', width)}
      >
        <div className="animate-rise space-y-8">
          <DailyLimitNotice />
          <PageHeading title={title} subtitle={subtitle} context={context === false ? (round ?? eyebrow) : <ContextLine info={context} round={round ?? eyebrow} />} />
          {children}
        </div>
      </main>

      {hasBar && (
        <section
          ref={bar}
          aria-label={t('flow.actions')}
          className="fixed inset-x-0 bottom-0 z-30 border-t border-outline-variant bg-surface pb-[env(safe-area-inset-bottom)]"
        >
          {/* Primary first in the DOM (it is first in the tab order), last on screen: at the bottom on a phone, at the right from 600 px. */}
          <div className={cx('mx-auto flex flex-col-reverse gap-2 px-4 py-3 sm:flex-row-reverse sm:items-center sm:justify-start sm:gap-3 sm:px-6', width)}>
            {primary}
            {secondary}
          </div>
        </section>
      )}
    </div>
  )
}
