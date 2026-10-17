// The app's API client: the request logic of transport.ts wired to this build's environment (the API base, mock mode,
// the demo video link) and to this browser's device key. The only module here that reads Vite's environment, so the rest runs under node:test.
import { dailyLimit } from '../lib/dailyLimit.ts'
import { demoVideoUrl } from '../lib/demoVideo.ts'
import { apiBase, apiLocation } from './base.ts'
import { deviceKey } from './deviceKey.ts'
import { createTransport } from './transport.ts'

export { ApiError } from './transport.ts'

/** `/api` locally (the Vite proxy); the Cloud Run service URL plus `/api` in production (docs/ARCHITECTURE.md). */
export const API_BASE = apiBase(import.meta.env.VITE_API_BASE)

/** Mock mode (npm run dev:mock). A literal comparison so production builds drop the mock code. */
export const IS_MOCK = import.meta.env.VITE_API_MOCK === '1'

/** Protocol and host a Live `wsUrl` given as a path resolves against: the API's own, not the page's (see base.ts). */
export const wsLocation = () => apiLocation(API_BASE, window.location)

async function send(url: string, init: RequestInit): Promise<Response> {
  if (import.meta.env.VITE_API_MOCK === '1') {
    const { mockFetch } = await import('../mock/handlers')
    return mockFetch(url, init)
  }
  return fetch(url, init)
}

// Pilot accounts (build-notes/34): a VITE_AUTH_MODE=firebase build sends the Firebase ID token too. A literal comparison, so the
// default build drops it and the Firebase SDK with it.
const authToken =
  import.meta.env.VITE_AUTH_MODE === 'firebase'
    ? async (force: boolean) => (await import('../auth/firebase.ts')).idToken(force)
    : undefined

export const { request, requestBlob } = createTransport({ base: API_BASE, send, deviceKey, onError: dailyLimit.note, authToken })

/** The recorded demo (VITE_DEMO_VIDEO_URL), or null when unset: no link is shown then. */
export const DEMO_VIDEO_URL = demoVideoUrl(import.meta.env.VITE_DEMO_VIDEO_URL)
