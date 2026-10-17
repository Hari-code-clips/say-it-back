// The request machinery of the API client: the base URL, the device key on every request, typed errors and timeouts.
// Everything that depends on the build or the browser is handed in (see client.ts), so the unit tests run it with a fake `send`.
import { DEVICE_HEADER } from './deviceKey.ts'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  json?: unknown
  form?: FormData
  /**
   * Gemini-backed calls get 125 s: the backend answers 503 `upstream_busy` itself at 120 s (SIB_REQUEST_TIMEOUT_S, v0.4), and
   * that, not a client timeout, is what the user should see. The browser calls Cloud Run directly, so no 60 s proxy cut applies.
   */
  timeoutMs?: number
  signal?: AbortSignal
  /** Extra request headers (2026-10-16: the check upload's `Idempotency-Key`). They never replace the device key. */
  headers?: Record<string, string>
}

const DEFAULT_TIMEOUT_MS = 20_000
export const GEMINI_TIMEOUT_MS = 125_000

export interface TransportDeps {
  /** `/api`, or the API's absolute URL plus `/api` (see base.ts). */
  base: string
  /** `fetch`, or the in-browser mock. */
  send: (url: string, init: RequestInit) => Promise<Response>
  /** This browser's device key. */
  deviceKey: () => string
  /** Told of every failed call before it is thrown (the app watches for `daily_limit`, src/lib/dailyLimit.ts). */
  onError?: (e: ApiError) => void
  /**
   * Pilot accounts (VITE_AUTH_MODE=firebase, build-notes/34): the ID token for each request, sent as `Authorization: Bearer`.
   * `force` asks for a fresh one after a 401 `bad_token`, and the request is then sent once more. Absent in the default build.
   */
  authToken?: (force: boolean) => Promise<string | null>
}

export interface Transport {
  request<T>(path: string, opts?: RequestOptions): Promise<T>
  requestBlob(path: string, opts?: RequestOptions): Promise<Blob>
}

async function toError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`
  let message = res.statusText || `Request failed (${res.status})`
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string } }
    if (body.error?.code) code = body.error.code
    if (body.error?.message) message = body.error.message
  } catch {
    /* body was not JSON; keep the HTTP defaults */
  }
  return new ApiError(res.status, code, message)
}

export function createTransport({ base, send, deviceKey, onError, authToken }: TransportDeps): Transport {
  async function fetchOk(path: string, opts: RequestOptions): Promise<Response> {
    try {
      try {
        return await fetchOnce(path, opts)
      } catch (e) {
        if (!authToken || !(e instanceof ApiError) || e.status !== 401 || e.code !== 'bad_token') throw e
        return await fetchOnce(path, opts, true) // the server refused the token: one fresh token, one more try
      }
    } catch (e) {
      if (e instanceof ApiError) onError?.(e)
      throw e
    }
  }

  async function fetchOnce(path: string, opts: RequestOptions, freshToken = false): Promise<Response> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? DEFAULT_TIMEOUT_MS)
    opts.signal?.addEventListener('abort', () => controller.abort(), { once: true })
    // The key goes on every request, whatever its kind: JSON, multipart upload or blob download. It is a header and never part of the URL.
    const headers = new Headers({ ...opts.headers, [DEVICE_HEADER]: deviceKey() })
    if (authToken) {
      const token = await authToken(freshToken)
      if (token) headers.set('Authorization', `Bearer ${token}`)
    }
    const init: RequestInit = { method: opts.method ?? 'GET', signal: controller.signal, headers }
    if (opts.json !== undefined) {
      init.body = JSON.stringify(opts.json)
      headers.set('Content-Type', 'application/json')
    } else if (opts.form) {
      init.body = opts.form // the browser sets the multipart boundary
    }
    try {
      const res = await send(`${base}${path}`, init)
      if (!res.ok) throw await toError(res)
      return res
    } catch (e) {
      if (e instanceof ApiError) throw e
      if (opts.signal?.aborted) throw e
      if (controller.signal.aborted) throw new ApiError(0, 'timeout', 'The server took too long to answer.')
      throw new ApiError(0, 'network', 'Could not reach the server.')
    } finally {
      clearTimeout(timer)
    }
  }

  return {
    async request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
      return (await (await fetchOk(path, opts)).json()) as T
    },
    async requestBlob(path: string, opts: RequestOptions = {}): Promise<Blob> {
      return (await fetchOk(path, opts)).blob()
    },
  }
}
