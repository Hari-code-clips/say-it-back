import { useT } from '../i18n/index.tsx'
import { AppShell } from '../shell/AppShell.tsx'
import { LinkButton } from '../ui/Button.tsx'
import { ErrorState } from '../ui/Feedback.tsx'
import { useBriefing } from './BriefingContext.tsx'

/**
 * The server's briefing and the screen disagree (for example status `briefing` but no round).
 * Redirecting would bounce against the route guard forever, so say so and offer a reload.
 */
export function UnexpectedState() {
  const t = useT()
  const { refresh } = useBriefing()
  return (
    <AppShell>
      <ErrorState title={t('flow.unexpected')} message={t('flow.unexpectedHint')} retryLabel={t('action.reload')} onRetry={() => void refresh()} />
      <div className="mt-6 flex justify-center">
        <LinkButton href="/records" variant="tonal" icon="receipt_long">
          {t('nav.records')}
        </LinkButton>
      </div>
    </AppShell>
  )
}
