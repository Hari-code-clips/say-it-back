/* Hallmark · component: demo video link · genre: modern-minimal · theme: design.md
 * states: default · hover · focus-visible · active (AnchorButton: .state-layer and the global ring) · hidden when
 * VITE_DEMO_VIDEO_URL is unset. A plain link in the same tab (Back returns; nothing in the app is lost), with one icon so the
 * label keeps to one line at 320 px, also inside a banner.
 */
import { DEMO_VIDEO_URL } from '../api/client.ts'
import { useT } from '../i18n/index.tsx'
import { AnchorButton, type ButtonVariant } from '../ui/Button.tsx'

/** "Watch the demo video", or nothing when the build has no VITE_DEMO_VIDEO_URL. */
export function DemoVideoLink({ variant = 'text', className }: { variant?: ButtonVariant; className?: string }) {
  const t = useT()
  if (!DEMO_VIDEO_URL) return null
  return (
    <AnchorButton href={DEMO_VIDEO_URL} rel="noreferrer" variant={variant} icon="play_arrow" className={className}>
      <span className="whitespace-nowrap">{t('demo.watch')}</span>
    </AnchorButton>
  )
}
