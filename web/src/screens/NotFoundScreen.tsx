import { useT } from '../i18n/index.tsx'
import { AppShell } from '../shell/AppShell.tsx'
import { LinkButton } from '../ui/Button.tsx'
import { EmptyState } from '../ui/Feedback.tsx'
import { usePageFocus } from '../ui/PageHeading.tsx'

export function NotFoundScreen() {
  const t = useT()
  usePageFocus(t('notFound.title'))
  return (
    <AppShell>
      <div className="mx-auto max-w-xl py-8">
        <EmptyState
          icon="help"
          title={t('notFound.title')}
          body={t('notFound.body')}
          action={
            <LinkButton href="/" icon="home" size="lg">
              {t('app.home')}
            </LinkButton>
          }
        />
      </div>
    </AppShell>
  )
}
