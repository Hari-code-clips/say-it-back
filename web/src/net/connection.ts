// How good the phone's signal looks, from what the browser reports (2026-10-16). Only a hint: `navigator.connection` exists in
// Chrome and Edge on Android, not in Safari or Firefox, and `navigator.onLine` true does not prove the server can be reached. So
// nothing is ever blocked on it; it only suggests Turn by turn, which needs far less of the network than a Live voice session.

/** The Network Information API fields this app reads. */
export interface ConnectionInfo {
  effectiveType?: string
  addEventListener?: (type: 'change', listener: () => void) => void
  removeEventListener?: (type: 'change', listener: () => void) => void
}

export interface NavigatorLike {
  onLine?: boolean
  connection?: ConnectionInfo
}

/** `unknown`: the browser does not say (Safari, Firefox). */
export type SignalQuality = 'offline' | 'weak' | 'ok' | 'unknown'

/** Effective types too slow for a live voice session (two audio streams at once): 2G, and 3G (about 0.7 Mbit/s or a slow round trip). */
const WEAK = new Set(['slow-2g', '2g', '3g'])

export function signalQuality(nav: NavigatorLike | undefined): SignalQuality {
  if (!nav) return 'unknown'
  if (nav.onLine === false) return 'offline'
  const type = nav.connection?.effectiveType
  if (!type) return 'unknown'
  return WEAK.has(type) ? 'weak' : 'ok'
}

/**
 * The handover step's hint under the mode choice: on a weak signal with Live chosen, that Turn by turn works better; with no signal
 * at all, that the briefing needs one. Nothing otherwise, and nothing when the browser does not say.
 */
export function signalHint(quality: SignalQuality, mode: 'live' | 'turn'): 'signal.hintWeak' | 'signal.hintOffline' | null {
  if (quality === 'offline') return 'signal.hintOffline'
  return quality === 'weak' && mode === 'live' ? 'signal.hintWeak' : null
}

/** Calls `onChange` when the phone goes on or offline, or its connection type changes. Returns the unsubscribe. */
export function watchSignal(onChange: () => void, target: Pick<Window, 'addEventListener' | 'removeEventListener'> | undefined = globalThis.window, nav: NavigatorLike | undefined = globalThis.navigator as NavigatorLike | undefined): () => void {
  target?.addEventListener('online', onChange)
  target?.addEventListener('offline', onChange)
  nav?.connection?.addEventListener?.('change', onChange)
  return () => {
    target?.removeEventListener('online', onChange)
    target?.removeEventListener('offline', onChange)
    nav?.connection?.removeEventListener?.('change', onChange)
  }
}
