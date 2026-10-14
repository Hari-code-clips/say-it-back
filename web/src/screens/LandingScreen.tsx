import { useT } from '../i18n/index.tsx'
import { AppShell } from '../shell/AppShell.tsx'
import { LinkButton } from '../ui/Button.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { usePageFocus } from '../ui/PageHeading.tsx'
import { Storyboard } from './landing/Storyboard.tsx'

/** First screen. A judge should get the product in three seconds and reach either action in one tap. */
export function LandingScreen() {
  const t = useT()
  const heading = usePageFocus(t('landing.docTitle'))
  return (
    <AppShell>
      <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-20 lg:py-6">
        <div className="animate-rise space-y-8">
          <StatusChip tone="primary" icon="record_voice_over">
            {t('landing.eyebrow')}
          </StatusChip>
          <div className="space-y-5">
            <h1 ref={heading} tabIndex={-1} className="text-display-sm font-semibold tracking-tight text-on-surface sm:text-display-md lg:text-display-lg lg:leading-[1.08]">
              {t('landing.title')}
            </h1>
            <p className="max-w-xl text-body-lg text-on-surface-variant sm:text-title-lg sm:font-normal">{t('landing.body')}</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <LinkButton href="/new" size="lg" icon="record_voice_over" trailingIcon="arrow_forward">
              {t('landing.cta.start')}
            </LinkButton>
            <LinkButton href="/sample?run=1" size="lg" variant="tonal" icon="play_arrow">
              {t('landing.cta.sample')}
            </LinkButton>
          </div>
          <p className="max-w-xl text-body-md text-on-surface-variant">{t('landing.foot')}</p>
        </div>
        <div className="animate-rise [animation-delay:120ms]">
          <Storyboard />
        </div>
      </div>
    </AppShell>
  )
}
