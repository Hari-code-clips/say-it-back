/* Hallmark · component: daily-limit notice · genre: modern-minimal · theme: design.md
 * states: hidden (limit not reached) · shown · shown with the demo video (VITE_DEMO_VIDEO_URL set). Its one control is
 * DemoVideoLink (all link states). It stands in for Retry, which cannot succeed before 00:00 UTC.
 */
import { useSyncExternalStore } from 'react'
import { DEMO_VIDEO_URL } from '../api/client.ts'
import { useT } from '../i18n/index.tsx'
import { dailyLimit } from '../lib/dailyLimit.ts'
import { Banner } from '../ui/Feedback.tsx'
import { DemoVideoLink } from './DemoVideoLink.tsx'

/**
 * Once a call answers 429 `daily_limit`, the live demo is over until the budget resets: the screen that hit it says so
 * (with no Retry), and this says when it comes back and, when the build has VITE_DEMO_VIDEO_URL, links the recorded demo.
 */
export function DailyLimitNotice({ className }: { className?: string }) {
  const t = useT()
  const reached = useSyncExternalStore(dailyLimit.subscribe, dailyLimit.reached)
  if (!reached) return null
  return (
    <Banner
      tone="info"
      title={t('demo.limitTitle')}
      live="polite"
      action={DEMO_VIDEO_URL ? <DemoVideoLink variant="tonal" className="px-4!" /> : undefined}
      className={className}
    >
      <p>{t('demo.limitBody')}</p>
      {DEMO_VIDEO_URL && <p>{t('demo.limitVideo')}</p>}
    </Banner>
  )
}
