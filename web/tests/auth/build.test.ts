import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, before, describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import { buildCsp } from '../../csp.ts'
import { noMockInBundle } from '../../noMock.ts'

// Pilot accounts (build-notes/34): the default build ships no Firebase code and today's CSP; a VITE_AUTH_MODE=firebase build
// carries the SDK and the widened CSP. The firebase build is the control: it shows the markers are found when the code is there.

const WEB = fileURLToPath(new URL('../../', import.meta.url))
const VITE = join(WEB, 'node_modules', 'vite', 'bin', 'vite.js')
const MARKERS = ['identitytoolkit.googleapis.com', 'securetoken.googleapis.com']
const AUTH_DOMAIN = 'sib-pilot.firebaseapp.com'

function viteBuild(outDir: string, firebase: boolean): void {
  const env: NodeJS.ProcessEnv = { ...process.env }
  for (const name of Object.keys(env)) if (name.startsWith('VITE_')) delete env[name]
  if (firebase) {
    Object.assign(env, {
      VITE_AUTH_MODE: 'firebase',
      VITE_FIREBASE_AUTH_DOMAIN: AUTH_DOMAIN,
      VITE_FIREBASE_PROJECT_ID: 'sib-pilot',
      VITE_FIREBASE_API_KEY: 'public-web-config-for-tests',
    })
  }
  const run = spawnSync(process.execPath, [VITE, 'build', '--outDir', outDir, '--emptyOutDir', '--logLevel', 'error'], { cwd: WEB, env, encoding: 'utf8', timeout: 180_000 })
  assert.equal(run.status, 0, `vite build (${firebase ? 'firebase' : 'default'}) failed:\n${run.stdout}\n${run.stderr}`)
}

function filesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? filesUnder(path) : [path]
  })
}

const bundleText = (dir: string) => filesUnder(dir).map((f) => readFileSync(f, 'utf8')).join('\n')
const metaCsp = (dir: string) => /http-equiv="Content-Security-Policy" content="([^"]*)"/.exec(readFileSync(join(dir, 'index.html'), 'utf8'))?.[1]

describe('the default build carries no pilot-account code', () => {
  let tmp = ''
  let plain = ''
  let firebase = ''

  before(() => {
    tmp = mkdtempSync(join(tmpdir(), 'sib-auth-build-'))
    plain = join(tmp, 'default')
    firebase = join(tmp, 'firebase')
    viteBuild(plain, false)
    viteBuild(firebase, true)
  })
  after(() => rmSync(tmp, { recursive: true, force: true }))

  it('the default bundle has no Firebase Auth code and its CSP is exactly the default policy', () => {
    const text = bundleText(plain)
    for (const marker of MARKERS) assert.ok(!text.includes(marker), marker)
    assert.equal(metaCsp(plain), buildCsp(undefined))
  })

  it('the firebase bundle has the SDK, the widened CSP and still no mock code', () => {
    const text = bundleText(firebase)
    for (const marker of MARKERS) assert.ok(text.includes(marker), marker)
    assert.equal(metaCsp(firebase), buildCsp(undefined, AUTH_DOMAIN))
    assert.deepEqual(noMockInBundle(firebase), [])
  })
})
