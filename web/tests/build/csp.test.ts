import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { buildCsp } from '../../csp.ts'

/** "script-src 'self'; connect-src a b" as { 'script-src': ["'self'"], 'connect-src': ['a', 'b'] }. */
function directives(policy: string): Record<string, string[]> {
  return Object.fromEntries(policy.split(';').map((d) => d.trim().split(/\s+/)).map(([name, ...sources]) => [name!, sources]))
}

const CLOUD_RUN = 'https://say-it-back-api-x.a.run.app/api'

describe('buildCsp: connect-src', () => {
  it('names the API origin over https and over wss, exactly, for a Cloud Run base', () => {
    assert.deepEqual(directives(buildCsp(CLOUD_RUN))['connect-src'], ['https://say-it-back-api-x.a.run.app', 'wss://say-it-back-api-x.a.run.app'])
  })

  it('does not allow the page’s own origin or any other host beside it: the API and its Live socket are all the page talks to', () => {
    const connect = directives(buildCsp(CLOUD_RUN))['connect-src']!

    assert.ok(!connect.includes("'self'") && !connect.some((s) => s === '*' || s.startsWith('https://*') || s === 'https:' || s === 'wss:' || s === 'blob:' || s === 'data:'))
  })

  it('maps an http API, as in a local rehearsal, to http and ws, with its port', () => {
    assert.deepEqual(directives(buildCsp('http://127.0.0.1:8081/api'))['connect-src'], ['http://127.0.0.1:8081', 'ws://127.0.0.1:8081'])
  })

  it("is the page's own origin for the default relative base (the Vite proxy, and the mock build)", () => {
    assert.deepEqual(directives(buildCsp(undefined))['connect-src'], ["'self'"])
    assert.deepEqual(directives(buildCsp('/api'))['connect-src'], ["'self'"])
  })

  it('cannot be given another directive through VITE_API_BASE', () => {
    for (const bad of ["https://x.test/api; script-src 'unsafe-inline'", 'https://x.test/api ; img-src *', "https://x.test'/api", 'https://x.test/api,https://evil.test/api', 'https://x.test\n/api']) {
      assert.throws(() => buildCsp(bad), /VITE_API_BASE/, bad)
    }
  })

  it('refuses a base that is not an API base at all', () => {
    assert.throws(() => buildCsp('https://say-it-back-api-x.a.run.app'), /VITE_API_BASE/)
  })
})

describe('buildCsp: the policy as a whole', () => {
  const policy = buildCsp(CLOUD_RUN)
  const d = directives(policy)

  it('has no unsafe-eval, no unsafe-inline, no wildcard source and no data: script source', () => {
    assert.doesNotMatch(policy, /unsafe-eval|unsafe-inline|unsafe-hashes|wasm-unsafe-eval/)
    assert.doesNotMatch(policy, /(^|\s)\*(\s|;|$)/)
    assert.ok(!d['script-src']!.some((s) => s.endsWith(':')), 'no scheme-only script source')
  })

  it('shuts everything not named: default-src is none, and objects, forms and <base> are off', () => {
    assert.deepEqual(d['default-src'], ["'none'"])
    assert.deepEqual(d['object-src'], ["'none'"])
    assert.deepEqual(d['form-action'], ["'none'"])
    assert.deepEqual(d['base-uri'], ["'none'"])
  })

  it('allows scripts from the page’s own origin only: the bundle, its chunks and the AudioWorklet module', () => {
    assert.deepEqual(d['script-src'], ["'self'"])
  })

  it('covers the Google Fonts the app uses: their stylesheets and their font files', () => {
    assert.deepEqual(d['style-src'], ["'self'", 'https://fonts.googleapis.com'])
    assert.deepEqual(d['font-src'], ['https://fonts.gstatic.com'])
  })

  it('lets answer clips and sample audio play from object URLs, and shows the favicon', () => {
    assert.deepEqual(d['media-src'], ["'self'", 'blob:'])
    assert.deepEqual(d['img-src'], ["'self'"])
  })

  it('leaves frame-ancestors out: a <meta> policy ignores it (and the browser complains). firebase.json sends it as a header.', () => {
    assert.doesNotMatch(policy, /frame-ancestors|report-uri|sandbox/)
  })

  it('is one line a double-quoted attribute can hold', () => {
    assert.doesNotMatch(policy, /["<>&\n]/)
  })
})
