// The offline app shell's service worker (2026-10-16). Built by src/sw/plugin.ts into dist/sw.js, a classic script with no
// imports, with the version and file list written in at build time. The rules are in rules.ts; this file only applies them.
// It never answers an API request, the Live socket (a WebSocket never passes through a worker) or any audio.
import {
  FONT_CACHE,
  MANIFEST_TOKEN,
  NAVIGATE_TIMEOUT_MS,
  ruleFor,
  shellCache,
  staleCaches,
  storable,
  type Manifest,
  type Rule,
} from './rules.ts'

// The worker's own event types (the app's TypeScript lib is the DOM one, which has no service-worker events).
interface LifecycleEvent extends Event {
  waitUntil(work: Promise<unknown>): void
}
interface FetchRequestEvent extends LifecycleEvent {
  readonly request: Request
  respondWith(response: Promise<Response>): void
}
interface WorkerScope {
  addEventListener(type: 'install' | 'activate', listener: (event: LifecycleEvent) => void): void
  addEventListener(type: 'fetch', listener: (event: FetchRequestEvent) => void): void
  readonly location: Location
  readonly clients: { claim(): Promise<void> }
}

const scope = self as unknown as WorkerScope
const manifest = JSON.parse(MANIFEST_TOKEN) as Manifest // the build replaces the token with the manifest's JSON
const SHELL = shellCache(manifest.version)

const keep = async (cacheName: string, request: Request | string, response: Response, rule: Rule): Promise<void> => {
  const facts = { status: response.status, type: response.type, contentType: response.headers.get('content-type') }
  if (storable(facts, rule)) await (await caches.open(cacheName)).put(request, response.clone()).catch(() => undefined)
}

async function navigate(request: Request): Promise<Response> {
  const stored = await caches.match('/', { cacheName: SHELL })
  const network = fetch(request).then(async (response) => {
    await keep(SHELL, '/', response, 'navigate')
    return response
  })
  if (!stored) return network
  const late = new Promise<Response>((resolve) => setTimeout(() => resolve(stored), NAVIGATE_TIMEOUT_MS))
  return Promise.race([network.catch(() => stored), late])
}

async function asset(request: Request): Promise<Response> {
  const stored = await caches.match(request)
  if (stored) return stored
  const response = await fetch(request)
  await keep(SHELL, request, response, 'asset')
  return response
}

async function publicFile(request: Request): Promise<Response> {
  try {
    const response = await fetch(request)
    await keep(SHELL, request, response, 'public')
    return response
  } catch (e) {
    const stored = await caches.match(request, { cacheName: SHELL })
    if (stored) return stored
    throw e
  }
}

async function font(request: Request, event: FetchRequestEvent): Promise<Response> {
  const stored = await caches.match(request, { cacheName: FONT_CACHE })
  const refresh = fetch(request).then(async (response) => {
    await keep(FONT_CACHE, request, response, 'font')
    return response
  })
  if (!stored) return refresh
  event.waitUntil(refresh.catch(() => undefined))
  return stored
}

scope.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(manifest.files)))
})

scope.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(staleCaches(names, manifest.version).map((name) => caches.delete(name))))
      .then(() => scope.clients.claim()),
  )
})

scope.addEventListener('fetch', (event) => {
  const { request } = event
  const rule = ruleFor({ url: request.url, method: request.method, mode: request.mode }, scope.location.origin)
  if (rule === 'navigate') event.respondWith(navigate(request))
  else if (rule === 'asset') event.respondWith(asset(request))
  else if (rule === 'public') event.respondWith(publicFile(request))
  else if (rule === 'font') event.respondWith(font(request, event))
  // Anything else gets no answer from the worker: the browser fetches it as if there were none.
})
