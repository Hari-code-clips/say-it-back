import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, before, describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import { MANIFEST_TOKEN, type Manifest } from '../../src/sw/rules.ts'

// 2026-10-16 signal: a production build ships the offline shell's worker at dist/sw.js: a classic script (no import or export, so
// every browser that has workers runs it), its manifest written in, every listed file present, and the page's CSP unchanged (a
// same-origin worker is allowed by script-src 'self', which worker-src falls back to).

const WEB = fileURLToPath(new URL('../../', import.meta.url))
const VITE = join(WEB, 'node_modules', 'vite', 'bin', 'vite.js')
const API = 'https://say-it-back-api-x.a.run.app/api'

describe('the production build ships the offline shell', () => {
  let tmp = ''
  let sw = ''
  let manifest: Manifest = { version: '', files: [] }
  let html = ''

  before(() => {
    tmp = mkdtempSync(join(tmpdir(), 'sib-sw-'))
    const env: NodeJS.ProcessEnv = { ...process.env, VITE_API_BASE: API }
    delete env.VITE_API_MOCK
    const run = spawnSync(process.execPath, [VITE, 'build', '--outDir', tmp, '--emptyOutDir', '--logLevel', 'error'], { cwd: WEB, env, encoding: 'utf8', timeout: 120_000 })
    assert.equal(run.status, 0, `vite build failed:\n${run.stdout}\n${run.stderr}`)
    sw = readFileSync(join(tmp, 'sw.js'), 'utf8')
    html = readFileSync(join(tmp, 'index.html'), 'utf8')
    const literal = /JSON\.parse\(("(?:[^"\\]|\\.)*")\)|=("\{\\"version(?:[^"\\]|\\.)*")/.exec(sw)
    assert.ok(literal, 'the manifest literal is in sw.js')
    manifest = JSON.parse(JSON.parse((literal[1] ?? literal[2])!) as string) as Manifest
  })
  after(() => rmSync(tmp, { recursive: true, force: true }))

  it('sw.js is at the site root and is a classic script: no import, no export', () => {
    assert.doesNotMatch(sw, /(^|[;}\s])import\s*[\s{*("'`]/)
    assert.doesNotMatch(sw, /(^|[;}\s])export\s*[\s{*]/)
    assert.doesNotMatch(sw, new RegExp(MANIFEST_TOKEN))
  })

  it('the manifest lists the page, the public files and every built file, and each exists', () => {
    assert.match(manifest.version, /^[0-9a-f]{8}$/)
    const built = readdirSync(join(tmp, 'assets')).map((f) => `/assets/${f}`).sort()
    assert.deepEqual(manifest.files.filter((f) => f.startsWith('/assets/')), built)
    assert.ok(manifest.files.includes('/'))
    for (const f of manifest.files.filter((f) => f !== '/')) assert.ok(existsSync(join(tmp, f.slice(1))), f)
  })

  it('the worker never names the API origin, so it cannot store an API reply by mistake', () => {
    assert.doesNotMatch(sw, /run\.app/)
  })

  it('the page still carries its CSP: script-src self, and connect-src only the API', () => {
    const csp = /http-equiv="Content-Security-Policy" content="([^"]+)"/.exec(html)?.[1] ?? ''
    assert.match(csp, /script-src 'self'(;|$)/)
    assert.match(csp, /connect-src https:\/\/say-it-back-api-x\.a\.run\.app wss:\/\/say-it-back-api-x\.a\.run\.app;/)
    assert.doesNotMatch(csp, /worker-src|unsafe-inline|unsafe-eval/)
  })

  it('the app registers /sw.js', () => {
    const main = readdirSync(join(tmp, 'assets')).filter((f) => f.endsWith('.js')).map((f) => readFileSync(join(tmp, 'assets', f), 'utf8'))
    assert.ok(main.some((code) => code.includes('/sw.js') && code.includes('updateViaCache')))
  })
})
