// The page's Content-Security-Policy, written into index.html at build time (vite.config.ts). It rides in a <meta> tag rather
// than a header because only the build knows the API's origin. `frame-ancestors` is the one directive a <meta> tag cannot carry,
// so firebase.json sends it as a header, alone. A header policy and a <meta> policy are both enforced and each only narrows what
// the other allows: any other directive in the header would apply to the page too, and `connect-src` there would block the API.
import { apiBase } from './src/api/base.ts'

/** What `connect-src` allows for an API base: the page's own origin for a path, else the API's origin over HTTP and over WebSocket. */
function connectSources(base: string): string {
  if (base.startsWith('/')) return "'self'"
  const { protocol, host } = new URL(base)
  return `${protocol}//${host} ${protocol === 'https:' ? 'wss:' : 'ws:'}//${host}`
}

/** A Firebase Auth domain as the CSP may name it: a bare host name, so a value cannot add a source or a directive. */
const AUTH_DOMAIN = /^[a-z0-9-]+(\.[a-z0-9-]+)+$/

/**
 * What Firebase Auth's Google sign-in needs, for a VITE_AUTH_MODE=firebase build only (build-notes/34): the gapi loader its
 * popup flow injects, the sign-in and token-refresh APIs, and the auth domain's handler frame. Throws on a bad domain.
 */
export function firebaseAuthSources(authDomain: string): { script: string; connect: string; frame: string } {
  if (!AUTH_DOMAIN.test(authDomain)) throw new Error(`VITE_FIREBASE_AUTH_DOMAIN must be a host name such as my-project.firebaseapp.com (got '${authDomain.slice(0, 80)}').`)
  return {
    script: 'https://apis.google.com',
    connect: 'https://identitytoolkit.googleapis.com https://securetoken.googleapis.com',
    frame: `https://${authDomain}`,
  }
}

/**
 * The policy for a build whose API lives at `rawApiBase` (VITE_API_BASE). Throws when that value is not a valid API base.
 * `firebaseAuthDomain` is given only for a VITE_AUTH_MODE=firebase build; without it the policy is exactly the default build's.
 */
export function buildCsp(rawApiBase: string | undefined, firebaseAuthDomain?: string): string {
  const fb = firebaseAuthDomain === undefined ? null : firebaseAuthSources(firebaseAuthDomain)
  return [
    "default-src 'none'",
    fb ? `script-src 'self' ${fb.script}` : "script-src 'self'", // the bundle, its lazy chunks and the AudioWorklet module: same-origin files. No inline script, no eval.
    "style-src 'self' https://fonts.googleapis.com", // the app's CSS and the Google Fonts stylesheets
    'font-src https://fonts.gstatic.com',
    "img-src 'self'", // the favicon
    "media-src 'self' blob:", // answer clips and sample audio play from object URLs
    `connect-src ${connectSources(apiBase(rawApiBase))}${fb ? ` ${fb.connect}` : ''}`, // the API and the Live socket, and nothing else
    ...(fb ? [`frame-src ${fb.frame}`] : []),
    "base-uri 'none'",
    "form-action 'none'",
    "object-src 'none'",
  ].join('; ')
}
