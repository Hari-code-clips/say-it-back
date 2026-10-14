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

/** The policy for a build whose API lives at `rawApiBase` (VITE_API_BASE). Throws when that value is not a valid API base. */
export function buildCsp(rawApiBase: string | undefined): string {
  return [
    "default-src 'none'",
    "script-src 'self'", // the bundle, its lazy chunks and the AudioWorklet module: same-origin files. No inline script, no eval.
    "style-src 'self' https://fonts.googleapis.com", // the app's CSS and the Google Fonts stylesheets
    'font-src https://fonts.gstatic.com',
    "img-src 'self'", // the favicon
    "media-src 'self' blob:", // answer clips and sample audio play from object URLs
    `connect-src ${connectSources(apiBase(rawApiBase))}`, // the API and the Live socket, and nothing else
    "base-uri 'none'",
    "form-action 'none'",
    "object-src 'none'",
  ].join('; ')
}
