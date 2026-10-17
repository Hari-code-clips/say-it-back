// Firebase Authentication for a VITE_AUTH_MODE=firebase build (build-notes/34). Only loaded through a dynamic import behind a
// literal `import.meta.env.VITE_AUTH_MODE === 'firebase'` (src/App.tsx, src/api/client.ts), so the default build carries none of it.
// Google sign-in today; a company's SAML or OIDC provider is a Firebase/Identity Platform setting plus a provider object here.
import { initializeApp } from 'firebase/app'
import { GoogleAuthProvider, getAuth, onAuthStateChanged, signInWithPopup, signOut, type User } from 'firebase/auth'

// Public web config, not secrets: it names the project; the backend decides who may do what.
const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
})
const auth = getAuth(app)

export async function signInWithGoogle(): Promise<void> {
  const provider = new GoogleAuthProvider()
  provider.setCustomParameters({ prompt: 'select_account' })
  await signInWithPopup(auth, provider)
}

export const signOutNow = (): Promise<void> => signOut(auth)

/** Called with undefined never: first with the restored session (a user or null), then on every change. */
export const onUser = (listener: (user: User | null) => void): (() => void) => onAuthStateChanged(auth, listener)

/**
 * The ID token for an API call. The SDK keeps it cached and refreshes it itself when it is within five minutes of expiry, so
 * each call gets a valid one; `force` asks for a new one (after the server answered 401 `bad_token`).
 */
export async function idToken(force: boolean): Promise<string | null> {
  const user = auth.currentUser
  return user ? user.getIdToken(force) : null
}
