import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { apiBase, apiLocation, DEFAULT_API_BASE } from '../../src/api/base.ts'

describe('apiBase', () => {
  it('defaults to /api, the base the Vite proxy serves, when VITE_API_BASE is unset or blank', () => {
    assert.equal(DEFAULT_API_BASE, '/api')
    assert.equal(apiBase(undefined), '/api')
    assert.equal(apiBase(''), '/api')
    assert.equal(apiBase('   '), '/api')
  })

  it('takes the Cloud Run service URL plus /api as it is', () => {
    assert.equal(apiBase('https://say-it-back-api-x.a.run.app/api'), 'https://say-it-back-api-x.a.run.app/api')
  })

  it('drops a trailing slash and the default port, and lowercases the host', () => {
    assert.equal(apiBase('https://Say-It-Back-API.a.run.app:443/api/'), 'https://say-it-back-api.a.run.app/api')
    assert.equal(apiBase('/api/'), '/api')
  })

  it('keeps a port and plain http for a local rehearsal', () => {
    assert.equal(apiBase('http://127.0.0.1:8081/api'), 'http://127.0.0.1:8081/api')
  })

  it('accepts a path that ends in /api behind a prefix', () => {
    assert.equal(apiBase('/svc/api'), '/svc/api')
    assert.equal(apiBase('https://lb.example.test/svc/api'), 'https://lb.example.test/svc/api')
  })

  it('refuses what is not an API base, so the build fails instead of shipping a page that calls nowhere', () => {
    for (const bad of [
      'https://say-it-back-api-x.a.run.app', // no /api
      'https://say-it-back-api-x.a.run.app/apix',
      'ftp://x.example.test/api',
      'javascript:alert(1)//api',
      '//x.example.test/api', // protocol-relative
      'x.example.test/api', // no scheme
      'api',
      'https://user:pass@x.example.test/api', // credentials
      'https://x.example.test/api?debug=1',
      'https://x.example.test/api#top',
      "https://x.example.test/api; script-src 'unsafe-inline'", // would add a CSP directive
      'https://x.example.test/api,https://evil.example.test/api',
      'https://x.example.test\n/api',
      'https://',
      'https://bücher.example.test/api', // IDN: give the punycode name
    ]) {
      assert.throws(() => apiBase(bad), /VITE_API_BASE/, bad)
    }
  })
})

describe('apiLocation', () => {
  const page = { protocol: 'https:', host: 'say-it-back.web.app' }

  it('is the API’s own protocol and host for an absolute base: a Live path resolves against Cloud Run, not Hosting', () => {
    assert.deepEqual(apiLocation('https://say-it-back-api-x.a.run.app/api', page), { protocol: 'https:', host: 'say-it-back-api-x.a.run.app' })
    assert.deepEqual(apiLocation('http://127.0.0.1:8081/api', page), { protocol: 'http:', host: '127.0.0.1:8081' })
  })

  it('is the page for a relative base, as with the dev proxy', () => {
    assert.deepEqual(apiLocation('/api', page), page)
  })
})
