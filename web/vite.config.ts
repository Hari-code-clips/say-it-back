import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type HtmlTagDescriptor, type Plugin } from 'vite'
import { buildCsp } from './csp.ts'
import { noMockPlugin } from './noMock.ts'
import { ICON_NAMES } from './src/theme/iconNames.ts'
import { serviceWorkerPlugin } from './src/sw/plugin.ts' // 2026-10-16: the offline app shell (dist/sw.js)

// Dev/preview proxy: with VITE_API_BASE unset the browser only talks to its own origin (in production it calls Cloud Run
// directly, see docs/ARCHITECTURE.md). `ws: true` makes `/api/live/...` (endpoint 20) work same-origin through the dev server too.
// Override with SIB_API_TARGET when the backend runs elsewhere.
const API_TARGET = process.env.SIB_API_TARGET || 'http://localhost:8080'

// Google Fonts. Noto Sans for Latin; the other Noto families carry every script the app shows.
// The big non-Latin stylesheet is loaded without blocking first paint (font-display: swap): it starts as media="print" and
// src/main.tsx switches it on once it has loaded. (Not an inline `onload`: the page's CSP allows no inline script.)
// Material Symbols is subset to the icons in src/theme/iconNames.ts (a few KB instead of ~460 KB).
const WEIGHTS = ':wght@400;600;700'
const GF = 'https://fonts.googleapis.com/css2'
const NOTO_SCRIPTS = ['Tamil', 'Bengali', 'Devanagari', 'Oriya', 'Myanmar', 'SC', 'Telugu']

const notoLatinHref = `${GF}?family=Noto+Sans${WEIGHTS}&display=swap`
const notoScriptsHref = `${GF}?${NOTO_SCRIPTS.map((s) => `family=Noto+Sans+${s}${WEIGHTS}`).join('&')}&display=swap`
const symbolsHref =
  `${GF}?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0..1,0` +
  `&icon_names=${[...ICON_NAMES].sort().join(',')}&display=block`

function googleFonts(): Plugin {
  return {
    name: 'sib-google-fonts',
    transformIndexHtml(): HtmlTagDescriptor[] {
      const link = (attrs: Record<string, string | boolean>): HtmlTagDescriptor => ({
        tag: 'link',
        attrs,
        injectTo: 'head',
      })
      return [
        link({ rel: 'preconnect', href: 'https://fonts.googleapis.com' }),
        link({ rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: true }),
        link({ rel: 'stylesheet', href: notoLatinHref }),
        link({ rel: 'stylesheet', href: symbolsHref }),
        link({ rel: 'stylesheet', href: notoScriptsHref, media: 'print', 'data-sib-lazy': true }),
        { tag: 'noscript', children: `<link rel="stylesheet" href="${notoScriptsHref}">`, injectTo: 'head' },
      ]
    },
  }
}

/** Where index.html marks the spot for the page's Content-Security-Policy <meta> tag (written at build time, see csp.ts). */
const CSP_MARKER = '<!-- sib-csp -->'

/**
 * Writes the Content-Security-Policy into index.html from VITE_API_BASE, so `connect-src` names the exact API origin.
 * Build only: the dev server needs inline script for hot reload, and the production build is what the policy is tested on.
 */
function contentSecurityPolicy(): Plugin {
  let policy = ''
  return {
    name: 'sib-csp',
    apply: 'build',
    configResolved(config) {
      const authDomain = config.env.VITE_AUTH_MODE === 'firebase' ? String(config.env.VITE_FIREBASE_AUTH_DOMAIN ?? '') : undefined // build-notes/34
      policy = buildCsp(config.env.VITE_API_BASE as string | undefined, authDomain) // throws on a bad value: no build rather than a page that cannot reach its API
    },
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        if (!html.includes(CSP_MARKER)) throw new Error(`index.html lost its ${CSP_MARKER} marker`)
        return html.replace(CSP_MARKER, `<meta http-equiv="Content-Security-Policy" content="${policy}" />`)
      },
    },
  }
}

const proxy = {
  '/api': { target: API_TARGET, changeOrigin: true, ws: true },
}

export default defineConfig({
  plugins: [react(), tailwindcss(), googleFonts(), contentSecurityPolicy(), noMockPlugin(), serviceWorkerPlugin()],
  server: { port: 5173, strictPort: true, proxy },
  // preview.proxy inherits server.proxy; the port differs so both can run together.
  preview: { port: 4173 },
  build: { target: 'es2023', sourcemap: false },
})
