import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App.tsx'
import { uploads } from './net/queue.ts'
import { registerServiceWorker } from './sw/register.ts'
import './styles/index.css'

// Stylesheets that index.html marks `data-sib-lazy` start as media="print", so they never block first paint. Switch each
// on once it has loaded. A stylesheet that never loads stays off. This is not an inline `onload` because the CSP allows no inline script.
for (const link of document.querySelectorAll<HTMLLinkElement>('link[data-sib-lazy]')) {
  if (link.sheet) link.media = 'all'
  else link.addEventListener('load', () => (link.media = 'all'), { once: true })
}

// 2026-10-16 signal: the offline app shell in production builds (src/sw/; VITE_SW=0 removes it), and answers still owed a check
// that are older than a day are deleted from this phone (src/net/queue.ts).
if (import.meta.env.PROD) registerServiceWorker(import.meta.env.VITE_SW !== '0')
void uploads.sweep()

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing')
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
