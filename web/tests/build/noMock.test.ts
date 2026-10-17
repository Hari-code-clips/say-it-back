import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, before, describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import { build } from 'vite'
import { MOCK_SENTINEL, isMockModule, mockMarkers, noMockInBundle, noMockPlugin } from '../../noMock.ts'
import { MOCK_BUNDLE_SENTINEL as FROM_HANDLERS } from '../../src/mock/handlers.ts'
import { MOCK_BUNDLE_SENTINEL as FROM_LIVE_SOCKET } from '../../src/mock/liveSocket.ts'

// Review focus 5 (build-notes/22): `npm run build` without VITE_API_MOCK ships no mock code. This builds the app twice into
// a temporary directory, as production and as the mock, and runs the same check deploy/03 runs on dist/. The mock build is
// the control: it shows the check finds the mock when it is there, so a clean production result means something.

const WEB = fileURLToPath(new URL('../../', import.meta.url))
const VITE = join(WEB, 'node_modules', 'vite', 'bin', 'vite.js')

function viteBuild(outDir: string, mock: boolean): void {
  const env: NodeJS.ProcessEnv = { ...process.env }
  delete env.VITE_API_MOCK
  delete env.VITE_API_BASE
  if (mock) env.VITE_API_MOCK = '1'
  const run = spawnSync(process.execPath, [VITE, 'build', '--outDir', outDir, '--emptyOutDir', '--logLevel', 'error'], { cwd: WEB, env, encoding: 'utf8', timeout: 120_000 })
  assert.equal(run.status, 0, `vite build (${mock ? 'mock' : 'production'}) failed:\n${run.stdout}\n${run.stderr}`)
}

describe('the production bundle has no mock code', () => {
  let tmp = ''
  let prod = ''
  let mock = ''

  before(() => {
    tmp = mkdtempSync(join(tmpdir(), 'sib-nomock-'))
    prod = join(tmp, 'prod')
    mock = join(tmp, 'mock')
    viteBuild(prod, false)
    viteBuild(mock, true)
  })

  after(() => {
    if (tmp) rmSync(tmp, { recursive: true, force: true })
  })

  it('a build without VITE_API_MOCK holds no sentinel, no src/mock path, no mock catalog text and no file named after the mock', () => {
    assert.deepEqual(noMockInBundle(prod), [])
  })

  it('a build with VITE_API_MOCK=1 does hold the mock: the check sees it when it is there', () => {
    const found = noMockInBundle(mock)

    assert.ok(found.length > 0)
    assert.ok(found.every((f) => f.startsWith('assets/')), found.join(', '))
  })

  it('the sentinel is what both mock entries export', () => {
    assert.equal(FROM_HANDLERS, MOCK_SENTINEL)
    assert.equal(FROM_LIVE_SOCKET, MOCK_SENTINEL)
    assert.ok(mockMarkers().includes(MOCK_SENTINEL))
  })

  it('refuses to pass a directory that is not a build', () => {
    assert.throws(() => noMockInBundle(tmp), /not a web build/)
  })
})

describe('the build itself refuses mock modules when VITE_API_MOCK is not 1 (noMockPlugin, in vite.config.ts)', () => {
  let tmp = ''
  before(() => {
    tmp = mkdtempSync(join(tmpdir(), 'sib-nomock-plugin-'))
  })
  after(() => {
    if (tmp) rmSync(tmp, { recursive: true, force: true })
  })

  /** Builds one entry module with only this plugin, as production (no VITE_API_MOCK) unless `mock`. */
  async function buildEntry(name: string, source: string, mock = false): Promise<void> {
    const entry = join(tmp, `${name}.ts`)
    writeFileSync(entry, source)
    const saved = process.env.VITE_API_MOCK
    if (mock) process.env.VITE_API_MOCK = '1'
    else delete process.env.VITE_API_MOCK
    try {
      await build({
        root: WEB,
        configFile: false,
        logLevel: 'silent',
        plugins: [noMockPlugin()],
        build: { outDir: join(tmp, `out-${name}`), emptyOutDir: true, write: false, lib: { entry, formats: ['es'], fileName: name } },
      })
    } finally {
      if (saved === undefined) delete process.env.VITE_API_MOCK
      else process.env.VITE_API_MOCK = saved
    }
  }

  // src/mock/longScripts.ts carries neither the sentinel nor catalog text: the output check above cannot see it.
  const LONG = `import { longAnswer } from '${join(WEB, 'src', 'mock', 'longScripts.ts')}'\nexport const x = longAnswer('en')\n`

  it('fails a production build that imports a mock module statically, naming it', async () => {
    await assert.rejects(buildEntry('withMock', LONG), /mock code in a production build.*src\/mock\/longScripts\.ts/s)
  })

  it('lets the same import through in a mock build', async () => {
    await buildEntry('mockBuild', LONG, true)
  })

  it('lets a production build without mock modules through', async () => {
    await buildEntry('clean', `import { clock } from '${join(WEB, 'src', 'lib', 'waitCopy.ts')}'\nexport const x = clock(5)\n`)
  })

  it('knows a mock module by its path, on any platform', () => {
    assert.equal(isMockModule('/a/web/src/mock/handlers.ts'), true)
    assert.equal(isMockModule('C:\\a\\web\\src\\mock\\handlers.ts'), true)
    assert.equal(isMockModule('/a/web/src/lib/mockery.ts'), false)
  })
})
