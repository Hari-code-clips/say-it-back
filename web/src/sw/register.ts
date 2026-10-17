// Registers the offline shell's service worker (2026-10-16), from main.tsx in production builds only. It imports nothing from
// sw.ts or rules.ts, so the worker's chunk shares no module with the app and stays a script with no imports (plugin.ts).

export interface WorkerHost {
  serviceWorker?: {
    register(url: string, options: { scope: string; updateViaCache: 'none' }): Promise<unknown>
    getRegistrations(): Promise<readonly { unregister(): Promise<boolean> }[]>
  }
}

/**
 * `enabled` false (a build with VITE_SW=0) removes a worker an earlier deploy installed, so a bad worker can be undone by the next
 * deploy. Registration waits for the page's `load`, so it never competes with the first paint; a failure changes nothing.
 */
export function registerServiceWorker(enabled: boolean, host: WorkerHost = navigator as WorkerHost, page: Pick<Window, 'addEventListener'> = window): void {
  const workers = host.serviceWorker
  if (!workers) return // an insecure origin, or a browser without workers: the app runs as before
  if (!enabled) {
    void workers
      .getRegistrations()
      .then((all) => Promise.all(all.map((r) => r.unregister())))
      .catch(() => undefined)
    return
  }
  page.addEventListener('load', () => void workers.register('/sw.js', { scope: '/', updateViaCache: 'none' }).catch(() => undefined), { once: true })
}
