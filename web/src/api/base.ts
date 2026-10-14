// Where the API lives. `VITE_API_BASE` is the Cloud Run service URL plus /api in production and unset locally, where the Vite
// proxy serves /api on the page's own origin. The CSP builder (csp.ts) reads the same value through `apiBase`, so what the page
// may call and what it calls cannot drift apart.

export const DEFAULT_API_BASE = '/api'

const ABSOLUTE = /^https?:\/\//i

// Letters, digits and the few marks a URL path or host needs. No space, quote, `;` or `,` (so a value cannot add a CSP
// directive or source), no `@`, `?` or `#` (so no credentials, query or fragment), no `%` and nothing outside ASCII.
const SAFE = /^[A-Za-z0-9:/._~[\]-]+$/

const invalid = (value: string): Error =>
  new Error(`VITE_API_BASE must be an absolute http(s) URL or a path that ends in /api, with no credentials, query or fragment (got '${value.slice(0, 80)}').`)

/**
 * The API base with no trailing slash: an absolute http(s) URL or a path, ending in /api (the contract's base path).
 * Empty means the default. Anything else throws, so a typo fails the build instead of shipping a page that calls nowhere.
 */
export function apiBase(raw: string | undefined): string {
  const value = (raw ?? '').trim()
  if (!value) return DEFAULT_API_BASE
  const absolute = ABSOLUTE.test(value)
  if (!SAFE.test(value) || !(absolute || (value.startsWith('/') && !value.startsWith('//')))) throw invalid(value)
  let url: URL
  try {
    url = new URL(value, 'http://page.invalid') // a path resolves against a stand-in origin that is dropped again below
  } catch {
    throw invalid(value)
  }
  const path = url.pathname.replace(/\/+$/, '')
  if (!path.endsWith('/api')) throw invalid(value)
  return absolute ? `${url.origin}${path}` : path
}

/** Protocol and host a relative Live `wsUrl` resolves against: the API's own for an absolute base, the page's for a path. */
export function apiLocation(base: string, page: { protocol: string; host: string }): { protocol: string; host: string } {
  if (!ABSOLUTE.test(base)) return page
  const { protocol, host } = new URL(base)
  return { protocol, host }
}
