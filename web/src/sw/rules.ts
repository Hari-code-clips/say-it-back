// The offline app shell's cache rules (2026-10-16), as pure functions: the service worker (sw.ts) applies them, the build plugin
// (plugin.ts) writes the file list, and tests/net/swRules.test.ts checks them. What is stored: the page, the built files under
// /assets/ (hashed, so immutable), the public files the app needs, and the Google Fonts it loads. What is never stored: any API
// response (the API is another origin in production, and /api on this one), any audio, any request that is not a GET, and
// Firebase Hosting's reserved paths under /__/ (security fixes B: its sign-in handler must never be answered with the app shell).

/** Where the worker is served: the site root, so its scope is the whole app. */
export const SW_FILE = 'sw.js'

/** Written into sw.js by the build in place of this token: the version and the files to store at install. */
export const MANIFEST_TOKEN = '__SIB_SW_MANIFEST__'

export const SHELL_PREFIX = 'sib-shell-'
export const FONT_CACHE = 'sib-fonts-1'

/** The files of web/public the shell needs offline (tests/net/swRules.test.ts checks this against the folder). */
export const PUBLIC_FILES: readonly string[] = ['/favicon.svg', '/pcm-capture.js']

/** Hosts of the stylesheets and font files index.html loads (vite.config.ts, csp.ts). */
export const FONT_HOSTS: readonly string[] = ['fonts.googleapis.com', 'fonts.gstatic.com']

/** How long a navigation waits for the network before it is answered from the cache, when the cache has the page. */
export const NAVIGATE_TIMEOUT_MS = 4_000

/** Firebase Hosting's own paths on the app's origin (/__/auth/handler, /__/auth/iframe, /__/firebase/init.js): never the app's. */
export const HOSTING_RESERVED = '/__/'

/**
 * - `navigate`: the page itself (any route: Hosting rewrites every path to index.html). Network first, the stored page after
 *   NAVIGATE_TIMEOUT_MS or on a failure, so a new deploy is picked up whenever the network answers.
 * - `asset`: a hashed build file. Cache first: its name changes whenever its content does.
 * - `public`: a public file or index.html fetched as a file. Network first, the stored copy on a failure.
 * - `font`: Google Fonts. The stored copy at once, refreshed in the background.
 * - `null`: not handled. The worker does not answer, so the browser goes to the network exactly as without it.
 */
export type Rule = 'navigate' | 'asset' | 'public' | 'font' | null

export interface RequestFacts {
  url: string
  method: string
  mode: string
}

export function ruleFor({ url, method, mode }: RequestFacts, origin: string): Rule {
  if (method !== 'GET') return null
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return null
  }
  if (parsed.origin !== origin) return parsed.protocol === 'https:' && FONT_HOSTS.includes(parsed.hostname) ? 'font' : null
  const path = parsed.pathname
  if (path === '/api' || path.startsWith('/api/') || path === `/${SW_FILE}` || path.startsWith(HOSTING_RESERVED)) return null
  if (mode === 'navigate') return 'navigate'
  if (path.startsWith('/assets/')) return 'asset'
  if (path === '/' || path === '/index.html' || PUBLIC_FILES.includes(path)) return 'public'
  return null
}

export interface ResponseFacts {
  status: number
  type: string
  contentType: string | null
}

/** A response that may be stored: a whole 200 (never a partial 206, a redirect or an error), never audio or video. */
export function storable({ status, type, contentType }: ResponseFacts, rule: Rule): boolean {
  if (rule === null) return false
  // A stylesheet <link> without crossorigin is fetched no-cors, so Google's CSS comes back opaque (status 0): stored for fonts only.
  if (type === 'opaque') return rule === 'font'
  if (status !== 200 || type === 'opaqueredirect') return false
  if (contentType && /^(audio|video)\//i.test(contentType)) return false
  return rule !== 'navigate' || (contentType ?? '').toLowerCase().startsWith('text/html')
}

export const shellCache = (version: string): string => `${SHELL_PREFIX}${version}`

/** The shell caches of other versions, deleted once this version's worker takes over. The font cache is kept. */
export const staleCaches = (names: readonly string[], version: string): string[] =>
  names.filter((name) => name.startsWith(SHELL_PREFIX) && name !== shellCache(version))

/** The URLs stored at install: the page, the public files and every built file under assets/ (from the bundle's file names). */
export function precacheList(bundleFiles: readonly string[]): string[] {
  const assets = bundleFiles.filter((f) => f.startsWith('assets/') && !f.endsWith('.map')).map((f) => `/${f}`)
  return ['/', ...PUBLIC_FILES, ...[...new Set(assets)].sort()]
}

/** The cache version: FNV-1a over the list. Every assets/ name carries its content hash, so any change to the build is a new version. */
export function versionOf(files: readonly string[]): string {
  let hash = 0x811c9dc5
  for (const ch of files.join('\n')) {
    hash ^= ch.codePointAt(0) ?? 0
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

export interface Manifest {
  version: string
  files: string[]
}

/** The manifest the build writes into sw.js, as a JS string literal that holds its JSON. */
export const manifestLiteral = (bundleFiles: readonly string[]): string => {
  const files = precacheList(bundleFiles)
  return JSON.stringify(JSON.stringify({ version: versionOf(files), files } satisfies Manifest))
}
