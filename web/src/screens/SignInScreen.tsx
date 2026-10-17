// Sign-in for a VITE_AUTH_MODE=firebase build (build-notes/34). Supervisor language; one blue action. With `waitingAs`, the
// person is signed in but has no role yet, and the screen says who to ask.
import { useState } from 'react'
import { signInWithGoogle, signOutNow } from '../auth/firebase.ts'
import { useT } from '../i18n/index.tsx'
import { Button } from '../ui/Button.tsx'
import { Banner } from '../ui/Feedback.tsx'
import { PageHeading } from '../ui/PageHeading.tsx'

export function SignInScreen({ waitingAs }: { waitingAs?: string }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  async function signIn() {
    setBusy(true)
    setFailed(false)
    try {
      await signInWithGoogle()
    } catch {
      setFailed(true) // closed popup, blocked popup or no network: the person can simply try again
    } finally {
      setBusy(false)
    }
  }

  return (
    <main id="main" className="mx-auto max-w-xl space-y-6 px-4 py-10">
      {waitingAs !== undefined ? (
        <>
          <PageHeading title={t('auth.noRole.title')} subtitle={t('auth.noRole.body', { email: waitingAs })} />
          <Button variant="outlined" size="lg" onClick={() => void signOutNow()}>
            {t('auth.signOut')}
          </Button>
        </>
      ) : (
        <>
          <PageHeading title={t('auth.signIn.title')} subtitle={t('auth.signIn.body')} />
          {failed && <Banner tone="error" live="assertive" title={t('auth.signIn.failed')} />}
          <Button size="lg" icon="lock" busy={busy} onClick={() => void signIn()}>
            {t('auth.signIn.cta')}
          </Button>
        </>
      )}
    </main>
  )
}
