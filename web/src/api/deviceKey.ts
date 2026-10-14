// The device key (docs/API.md, "Callers and ownership"). There are no accounts: each browser makes one random key, keeps it in
// localStorage and sends it as `X-SIB-Device` on every request. The backend stores only its SHA-256 and shows a briefing to the
// key that made it. The key is a header value and nothing else: never put it in a URL, a log line or an error message.

export const DEVICE_HEADER = 'X-SIB-Device'

const STORAGE_NAME = 'sib.device'
const KEY_BYTES = 24 // 192 bits, 32 characters. The contract asks for at least 128 bits and 22 to 64 characters.
const FORMAT = /^[A-Za-z0-9_-]{22,64}$/

/** The part of `Storage` the key needs, so a test can hand in a broken one. */
export interface KeyStorage {
  getItem(name: string): string | null
  setItem(name: string, value: string): void
}

export const isDeviceKey = (value: unknown): value is string => typeof value === 'string' && FORMAT.test(value)

/** Fills the array it is given with random bytes. */
export type FillRandom = (bytes: Uint8Array<ArrayBuffer>) => void

/** Random bytes as unpadded base64url. */
export function newDeviceKey(fill: FillRandom = (bytes) => void crypto.getRandomValues(bytes)): string {
  const raw = new Uint8Array(KEY_BYTES)
  fill(raw)
  return btoa(String.fromCharCode(...raw)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '')
}

/**
 * The key kept in `storage`, or a new one, stored. A stored value that is not a key is replaced. Where storage cannot be read
 * or written (private mode, blocked site data) the new key lives in memory only; `deviceKey` then keeps it for the page.
 */
export function loadDeviceKey(storage: KeyStorage | undefined, fill?: FillRandom): string {
  try {
    const stored = storage?.getItem(STORAGE_NAME)
    if (isDeviceKey(stored)) return stored
  } catch {
    /* unreadable: make a key below */
  }
  const fresh = newDeviceKey(fill)
  try {
    storage?.setItem(STORAGE_NAME, fresh)
    const kept = storage?.getItem(STORAGE_NAME) // a second tab may have written its own key meanwhile: use the one that stuck
    return isDeviceKey(kept) ? kept : fresh
  } catch {
    return fresh
  }
}

function browserStorage(): KeyStorage | undefined {
  try {
    return localStorage // even reading the property throws when site data is blocked
  } catch {
    return undefined
  }
}

let current: string | undefined

/** This browser's key, read once and kept for the life of the page, so storage that cannot persist still gives one stable key. */
export function deviceKey(): string {
  current ??= loadDeviceKey(browserStorage())
  return current
}
