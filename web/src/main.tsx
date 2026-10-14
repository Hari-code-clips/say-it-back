import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App.tsx'
import './styles/index.css'
import { applyScheme } from './theme/scheme.ts'

// Colour variables first, then render: no flash of unthemed content.
applyScheme()

// Stylesheets that index.html marks `data-sib-lazy` start as media="print", so they never block first paint. Switch each
// on once it has loaded. A stylesheet that never loads stays off. This is not an inline `onload` because the CSP allows no inline script.
for (const link of document.querySelectorAll<HTMLLinkElement>('link[data-sib-lazy]')) {
  if (link.sheet) link.media = 'all'
  else link.addEventListener('load', () => (link.media = 'all'), { once: true })
}

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing')
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
