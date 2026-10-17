import { Link } from 'wouter'
import { useT } from '../i18n/index.tsx'
import { AppShell } from '../shell/AppShell.tsx'
import { DemoVideoLink } from '../shell/DemoVideoLink.tsx'
import { LinkButton } from '../ui/Button.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { Icon } from '../ui/Icon.tsx'
import { usePageFocus } from '../ui/PageHeading.tsx'
import { Storyboard } from './landing/Storyboard.tsx'

/**
 * The headline's question in ink, its answer in the action blue (the deck's title rhythm). Split after the first question mark
 * (Latin or full-width), so every language keeps one string; a title without one stays a single ink line.
 */
export function TitleLines({ text }: { text: string }) {
  const at = text.search(/[?？]/u)
  if (at < 0 || at === text.length - 1) return <>{text}</>
  return (
    <>
      {text.slice(0, at + 1)} <span className="text-primary">{text.slice(at + 1).trim()}</span>
    </>
  )
}

/** The landing page's content, inside the shell of LandingScreen (tests render it without the shell). */
export function LandingContent() {
  const t = useT()
  const heading = usePageFocus(t('landing.docTitle'))
  return (
    <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-20 lg:py-6">
      <div className="animate-rise space-y-8">
        <StatusChip tone="primary" icon="record_voice_over">
          {t('landing.eyebrow')}
        </StatusChip>
        <div className="space-y-5">
          <h1 ref={heading} tabIndex={-1} className="text-display-sm font-semibold tracking-tight text-on-surface sm:text-display-md lg:text-display-lg lg:leading-[1.08]">
            <TitleLines text={t('landing.title')} />
          </h1>
          <p className="max-w-xl text-body-lg text-on-surface-variant sm:text-title-lg sm:font-normal">{t('landing.body')}</p>
        </div>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-3 sm:flex-row">
            <LinkButton href="/new" size="lg" icon="record_voice_over" trailingIcon="arrow_forward">
              {t('landing.cta.start')}
            </LinkButton>
            <LinkButton href="/sample?run=1" size="lg" variant="tonal" icon="play_arrow">
              {t('landing.cta.sample')}
            </LinkButton>
          </div>
          {/* 17 Oct, review P0-17: the lead case with stored sample answers, for an evaluator with no Tamil. A blue text link with a
              48 px target, not a button: the solid blue fill stays the screen's one primary (design.md). */}
          <Link href="/judge" className="state-layer -mx-3 inline-flex min-h-12 items-center gap-2 self-start rounded-md px-3 text-title-md font-semibold text-primary underline underline-offset-4">
            <span>{t('judge.link')}</span>
            <Icon name="arrow_forward" className="text-[1.25rem]" />
          </Link>
          {/* VITE_DEMO_VIDEO_URL only. Centred under the stacked buttons on a phone; in line with them from 600 px. */}
          <DemoVideoLink className="self-center sm:-ml-6 sm:self-start" />
        </div>
        <p className="max-w-xl text-body-md text-on-surface-variant">
          {t('landing.foot')}{' '}
          {/* Privacy, 16 Oct: an inline link in the sentence (WCAG 2.5.8's inline exception), to /privacy. */}
          <Link href="/privacy" className="font-semibold text-primary underline underline-offset-4">
            {t('privacy.link')}
          </Link>
        </p>
        {/* 16 Oct breadth: an evaluator can run any procedure by playing the worker in English (Start screen, last choice). */}
        <p className="max-w-xl text-body-md text-on-surface-variant">{t('breadth.tryOwn')}</p>
      </div>
      <div className="animate-rise [animation-delay:120ms]">
        <Storyboard />
      </div>
    </div>
  )
}

/** First screen. A judge should get the product in three seconds and reach either action in one tap. */
export function LandingScreen() {
  return (
    <AppShell>
      <LandingContent />
    </AppShell>
  )
}
