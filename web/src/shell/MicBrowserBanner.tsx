/* Hallmark · component: microphone-browser warning · genre: modern-minimal · theme: design.md
 * states: shown (in-app browser, or no getUserMedia) · hidden. Not interactive; reuses Banner's warning tone (icon + title + text).
 */
import { useState } from 'react'
import { useT } from '../i18n/index.tsx'
import { micLikelyBlocked } from '../lib/inAppBrowser.ts'
import { Banner } from '../ui/Feedback.tsx'

/**
 * "Open this page in Chrome or Safari to use the microphone", shown only where recording is unlikely to work: a browser
 * built into another app (LinkedIn, WhatsApp, WeChat...) or one with no getUserMedia. On the top-level pages and the
 * worker hand-over, so nobody finds out at the worker's first answer.
 */
export function MicBrowserBanner({ className }: { className?: string }) {
  const t = useT()
  const [blocked] = useState(() => micLikelyBlocked(navigator))
  if (!blocked) return null
  return (
    <Banner tone="warning" icon="mic_off" title={t('browser.micTitle')} className={className}>
      {t('browser.micBody')}
    </Banner>
  )
}
