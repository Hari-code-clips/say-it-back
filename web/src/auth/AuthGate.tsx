// The sign-in gate of a VITE_AUTH_MODE=firebase build (build-notes/34): nothing of the app renders, and no API call is made,
// until Firebase has a signed-in user and /api/me has answered with a role (or org admin). Lazy-loaded from src/App.tsx.
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { User } from 'firebase/auth'
import { useT } from '../i18n/index.tsx'
import { SignInScreen } from '../screens/SignInScreen.tsx'
import { Button } from '../ui/Button.tsx'
import { Banner, Skeleton } from '../ui/Feedback.tsx'
import { authApi } from './api.ts'
import { onUser, signOutNow } from './firebase.ts'
import { gateState } from './gate.ts'
import type { Me } from './types.ts'

const MeContext = createContext<Me | null>(null)

/** /api/me of the signed-in member, for the Team screen. Null outside the gate (the default build). */
export const useMe = (): Me | null => useContext(MeContext)

function AccountBar({ me }: { me: Me }) {
  const t = useT()
  if (me.mode !== 'firebase') return null
  return (
    <div className="flex flex-wrap items-center justify-end gap-2 border-b border-outline-variant px-4 text-body-md text-on-surface-variant">
      <span className="min-w-0 truncate">{me.member.email}</span>
      {me.member.orgAdmin && (
        <a className="state-layer inline-flex min-h-12 items-center rounded-md px-3 text-label-lg text-primary" href="/team">
          {t('auth.team.link')}
        </a>
      )}
      <Button variant="text" onClick={() => void signOutNow()}>
        {t('auth.signOut')}
      </Button>
    </div>
  )
}

export function AuthGate({ children }: { children: ReactNode }) {
  const t = useT()
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const [me, setMe] = useState<Me | null>(null)
  const [failed, setFailed] = useState(false)
  const uid = user?.uid

  useEffect(() => onUser(setUser), [])
  useEffect(() => {
    setMe(null)
    setFailed(false)
    if (!uid) return
    let live = true
    authApi
      .me()
      .then((m) => live && setMe(m))
      .catch(() => live && setFailed(true))
    return () => {
      live = false
    }
  }, [uid])

  if (failed) {
    return (
      <div className="mx-auto max-w-xl p-4">
        <Banner tone="error" live="assertive" title={t('auth.failed')}>
          <Button variant="text" onClick={() => void signOutNow()}>
            {t('auth.signOut')}
          </Button>
        </Banner>
      </div>
    )
  }
  const state = gateState(user === undefined ? undefined : user && { email: user.email }, me)
  if (state.kind === 'loading') return <Skeleton className="m-4 h-40" />
  if (state.kind === 'signedOut') return <SignInScreen />
  if (state.kind === 'noRole') return <SignInScreen waitingAs={state.email} />
  return (
    <MeContext.Provider value={state.me}>
      <AccountBar me={state.me} />
      {children}
    </MeContext.Provider>
  )
}
