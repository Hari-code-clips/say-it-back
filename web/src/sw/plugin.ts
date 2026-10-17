// Builds the offline shell's service worker (src/sw/sw.ts) into dist/sw.js (2026-10-16): one more entry chunk with a fixed name at
// the site root, then the manifest (version and file list) written in where sw.ts holds MANIFEST_TOKEN. A service worker is a
// classic script here (the widest browser support), so the build fails if the chunk would import anything.
import type { Plugin } from 'vite'
import { MANIFEST_TOKEN, SW_FILE, manifestLiteral } from './rules.ts'

export function serviceWorkerPlugin(): Plugin {
  let entry = ''
  return {
    name: 'sib-service-worker',
    apply: 'build',
    enforce: 'post',
    configResolved(config) {
      entry = `${config.root.replace(/\/+$/, '')}/src/sw/sw.ts`
    },
    buildStart() {
      this.emitFile({ type: 'chunk', id: entry, fileName: SW_FILE })
    },
    generateBundle(_options, bundle) {
      const sw = bundle[SW_FILE]
      if (!sw || sw.type !== 'chunk') return this.error(`${SW_FILE} was not built`)
      if (sw.imports.length > 0 || sw.dynamicImports.length > 0) {
        return this.error(`${SW_FILE} must not import other chunks (it imports ${[...sw.imports, ...sw.dynamicImports].join(', ')})`)
      }
      const token = new RegExp(`(["'\`])${MANIFEST_TOKEN}\\1`, 'g')
      if (!new RegExp(token.source).test(sw.code)) return this.error(`${SW_FILE} lost its ${MANIFEST_TOKEN} placeholder`)
      sw.code = sw.code.replace(token, manifestLiteral(Object.keys(bundle).filter((name) => name !== SW_FILE)))
    },
  }
}
