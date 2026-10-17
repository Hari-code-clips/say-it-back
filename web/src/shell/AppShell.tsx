import type { ReactNode } from 'react'
import { Link, useLocation } from 'wouter'
import { IS_MOCK } from '../api/client.ts'
import { useT, type StringKey } from '../i18n/index.tsx'
import type { IconName } from '../theme/iconNames.ts'
import { StatusChip } from '../ui/Chip.tsx'
import { cx } from '../ui/cx.ts'
import { Icon } from '../ui/Icon.tsx'
import { Logo } from '../ui/Logo.tsx'
import { DailyLimitNotice } from './DailyLimitNotice.tsx'
import { LangMenu } from './LangMenu.tsx'
import { MicBrowserBanner } from './MicBrowserBanner.tsx'

interface NavItem {
  href: string
  label: StringKey
  icon: IconName
}

const NAV: NavItem[] = [
  { href: '/new', label: 'nav.start', icon: 'record_voice_over' },
  { href: '/records', label: 'nav.records', icon: 'receipt_long' },
  { href: '/eval', label: 'nav.eval', icon: 'analytics' },
  { href: '/about', label: 'nav.about', icon: 'info' },
]

const isActive = (location: string, href: string) => location === href || location.startsWith(`${href}/`)

export function Brand() {
  const t = useT()
  return (
    <Link href="/" className="state-layer -ml-2 flex min-h-12 items-center gap-3 rounded-md px-2 pr-4" aria-label={t('app.home')}>
      <Logo className="size-9" />
      <span className="whitespace-nowrap text-title-lg font-bold tracking-tight text-on-surface">Say It Back</span>
    </Link>
  )
}

function TopNav() {
  const t = useT()
  const [location] = useLocation()
  return (
    <nav aria-label={t('nav.label')} className="ml-6 hidden gap-1 md:flex">
      {NAV.map((item) => {
        const active = isActive(location, item.href)
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            className={cx(
              'state-layer inline-flex min-h-12 items-center gap-2 rounded-md px-4 text-label-lg',
              active ? 'bg-secondary-container text-on-surface shadow-[inset_0_-2px_0_0_var(--color-primary)]' : 'text-on-surface-variant',
            )}
          >
            <Icon name={item.icon} filled={active} className="text-[1.25rem]" />
            {t(item.label)}
          </Link>
        )
      })}
    </nav>
  )
}

/** M3 navigation bar: phones only. */
function BottomNav() {
  const t = useT()
  const [location] = useLocation()
  return (
    <nav
      aria-label={t('nav.label')}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-outline-variant bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className="mx-auto flex max-w-md">
        {NAV.map((item) => {
          const active = isActive(location, item.href)
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className="state-layer flex min-h-[4.5rem] flex-col items-center justify-center gap-1 text-label-lg text-on-surface-variant active:translate-y-px"
              >
                <span
                  className={cx(
                    'grid h-8 w-16 place-items-center rounded-md transition-colors',
                    active && 'bg-primary text-on-primary',
                  )}
                >
                  <Icon name={item.icon} filled={active} />
                </span>
                <span className={cx(active && 'text-on-surface underline decoration-2 underline-offset-4')}>{t(item.label)}</span>
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

export function SkipLink() {
  const t = useT()
  return (
    // Parked above the viewport until it takes focus (not display:none, so screen readers still list it).
    <a
      href="#main"
      className="absolute left-4 top-2 z-50 inline-flex min-h-12 -translate-y-[200%] items-center rounded-md bg-primary px-6 text-label-lg text-on-primary shadow-elev-2 transition-transform focus:translate-y-0"
    >
      {t('a11y.skip')}
    </a>
  )
}

export function MockBadge() {
  const t = useT()
  if (!IS_MOCK) return null
  return (
    // Icon only on the narrowest phones, so the brand beside it keeps to one line; the word stays for screen readers.
    // Neutral: the mock build is not a verdict, so it takes none of the verdict colours (amber is Ask again).
    <StatusChip tone="neutral" icon="science">
      <span className="max-[22.5rem]:sr-only">{t('app.mock')}</span>
    </StatusChip>
  )
}

/** Layout for the top-level pages (Start, Records, Eval, About). The briefing flow has its own shell. */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-outline-variant bg-surface">
        <SkipLink />
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4 sm:px-6">
          <Brand />
          <TopNav />
          <div className="ml-auto flex items-center gap-2">
            <MockBadge />
            <LangMenu />
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 pb-32 pt-8 sm:px-6 md:pb-16 md:pt-12">
        <div className="mb-8 space-y-4 empty:hidden">
          <MicBrowserBanner />
          <DailyLimitNotice />
        </div>
        {children}
      </main>
      <BottomNav />
    </div>
  )
}
