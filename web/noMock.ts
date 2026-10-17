// The production bundle must hold no mock code (build-notes/22, Task 8; Hari, 15 Oct: nothing mock reaches what judges see).
// `npm run build` leaves the in-browser mock out because src/api/client.ts and src/live/socket.ts import it dynamically
// behind a literal `import.meta.env.VITE_API_MOCK === '1'`, which Vite folds to false. This checks the output, not that
// reasoning: tests/build/noMock.test.ts builds and runs it, and deploy/03 runs it on dist/ before an upload:
//
//   node noMock.ts dist        exit 1, one line per offending file
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'

/** What src/mock/sentinel.ts writes; any build that includes a mock entry contains it. */
export const MOCK_SENTINEL = '__SIB_MOCK_BUNDLE__'

/**
 * Text that only a bundle with the mock in it carries: the sentinel, a src/mock path, and the start of the mock catalog's
 * note and of each of its SOPs (the catalog is imported only by the mock). Each catalog marker stops at the first character
 * a bundler might escape, so it matches however the string is quoted.
 */
export function mockMarkers(): string[] {
  const catalog = JSON.parse(readFileSync(new URL('./src/mock/catalog.json', import.meta.url), 'utf8')) as {
    note?: string
    tasks?: Array<{ sop?: { text?: string } }>
  }
  const plain = (text: string | undefined) => (text ?? '').match(/^[A-Za-z0-9 .,;:()-]*/)?.[0].trim() ?? ''
  const fromCatalog = [plain(catalog.note), ...(catalog.tasks ?? []).map((task) => plain(task.sop?.text))].filter((m) => m.length >= 24)
  return [MOCK_SENTINEL, 'src/mock/', ...fromCatalog]
}

function filesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? filesUnder(path) : [path]
  })
}

/** Every file of the build in `distDir` (paths relative to it) that holds mock code or is named after the mock. */
export function noMockInBundle(distDir: string): string[] {
  const files = filesUnder(distDir)
  // An empty or wrong directory would pass trivially: insist on a build.
  if (!files.some((f) => relative(distDir, f) === 'index.html')) throw new Error(`${distDir} is not a web build (no index.html)`)
  const markers = mockMarkers()
  return files
    .filter((file) => {
      const rel = relative(distDir, file)
      if (/mock/i.test(rel)) return true
      const text = readFileSync(file, 'utf8')
      return markers.some((m) => text.includes(m))
    })
    .map((file) => relative(distDir, file))
}

/** A module of the in-browser mock, by its path. */
export const isMockModule = (id: string): boolean => /[\\/]src[\\/]mock[\\/]/.test(id)

/**
 * Fails a build that would ship any module under src/mock/ unless VITE_API_MOCK is '1' (vite.config.ts). This catches
 * what the output check above cannot: a mock module that carries neither the sentinel nor catalog text, imported
 * statically from an app module, as src/mock/longScripts.ts could be.
 */
export function noMockPlugin(): Plugin {
  let mockBuild = false
  return {
    name: 'sib-no-mock',
    apply: 'build',
    configResolved(config) {
      mockBuild = config.env.VITE_API_MOCK === '1'
    },
    generateBundle(_options, bundle) {
      if (mockBuild) return
      const found = Object.values(bundle).flatMap((out) => (out.type === 'chunk' ? Object.keys(out.modules) : [])).filter(isMockModule)
      if (found.length > 0) {
        const names = [...new Set(found.map((id) => id.replace(/^.*[\\/]src[\\/]mock[\\/]/, 'src/mock/')))]
        this.error(`mock code in a production build (VITE_API_MOCK is not '1'): ${names.join(', ')}`)
      }
    },
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const dist = process.argv[2] ?? 'dist'
  const offending = noMockInBundle(dist)
  for (const file of offending) console.error(`mock code in the production bundle: ${join(dist, file)}`)
  if (offending.length === 0) console.log(`${dist}: no mock code`)
  process.exitCode = offending.length > 0 ? 1 : 0
}
