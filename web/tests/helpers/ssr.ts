// Renders the app's real components to HTML inside `node --test`, with no browser: Vite's SSR loader turns the .tsx files into modules and
// react-dom/server renders them. Effects do not run (so no network, no audio), which is what a "what is on this screen" test wants.
import { createElement, type ComponentType, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { fileURLToPath } from 'node:url'
import { createServer, type ViteDevServer } from 'vite'

const DAILY_LIMIT_STUB = fileURLToPath(new URL('./stubs/DailyLimitNotice.tsx', import.meta.url))

export interface Ssr {
  /** Load a module by its path from the web root, e.g. `/src/screens/brief/WorkerScreens.tsx`. */
  load<T = Record<string, unknown>>(path: string): Promise<T>
  close(): Promise<void>
}

export async function startSsr(): Promise<Ssr> {
  const server: ViteDevServer = await createServer({
    configFile: false,
    root: process.cwd(),
    appType: 'custom',
    logLevel: 'silent',
    server: { middlewareMode: true, hmr: false, ws: false },
    // The one component that cannot be server-rendered as it is (see the stub); every other screen part is the real one.
    resolve: { alias: [{ find: /^(\.\.?\/)+shell\/DailyLimitNotice\.tsx$/, replacement: DAILY_LIMIT_STUB }] },
    optimizeDeps: { noDiscovery: true, include: [] },
  })
  return { load: <T>(path: string) => server.ssrLoadModule(path) as Promise<T>, close: () => server.close() }
}

/** The UI language the I18nProvider starts in (it reads localStorage, which node does not have). */
export function withUiLang<T>(lang: 'en' | 'ta' | 'zh', fn: () => T): T {
  const had = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => lang, setItem: () => undefined } })
  try {
    return fn()
  } finally {
    if (had) Object.defineProperty(globalThis, 'localStorage', had)
    else delete (globalThis as { localStorage?: unknown }).localStorage
  }
}

export const html = (node: ReactNode): string => renderToStaticMarkup(node)
export { createElement }
export type { ComponentType }

// ---- reading the HTML back, with no DOM ----

/** The text a person would see or hear: tags removed, icon glyph names (Material Symbols ligatures) removed, spaces collapsed. */
export function visibleText(markup: string): string {
  return markup
    .replace(/<span aria-hidden="true" class="icon[^"]*">[^<]*<\/span>/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Every <button>, as { text, attrs }. */
export function buttons(markup: string): { text: string; attrs: string }[] {
  return [...markup.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].map((m) => ({ attrs: m[1] ?? '', text: visibleText(m[2] ?? '') }))
}

/** The icon glyph names drawn on the screen, in order. */
export function icons(markup: string): string[] {
  return [...markup.matchAll(/<span aria-hidden="true" class="icon[^"]*">([^<]*)<\/span>/g)].map((m) => m[1] ?? '')
}
