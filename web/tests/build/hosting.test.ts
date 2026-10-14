import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

// What Firebase Hosting and Firestore are told to do (the repository root), and the page that Hosting serves. A header or a rule
// that quietly goes missing here is a security regression, not a style change.
const root = new URL('../../../', import.meta.url)
const read = (path: string) => readFileSync(new URL(path, root), 'utf8')

interface Header {
  key: string
  value: string
}
interface Config {
  firestore?: { rules?: string; indexes?: string }
  hosting: { public: string; rewrites: Array<{ source: string; destination?: string; run?: unknown; function?: unknown }>; headers: Array<{ source: string; headers: Header[] }> }
}
const config = JSON.parse(read('firebase.json')) as Config

const headersFor = (source: string): Record<string, string> =>
  Object.fromEntries(config.hosting.headers.filter((h) => h.source === source).flatMap((h) => h.headers).map((h) => [h.key, h.value]))

describe('firebase.json: Hosting', () => {
  it('serves the built web app', () => {
    assert.equal(config.hosting.public, 'web/dist')
  })

  it('has no /api rewrite and no rewrite to Cloud Run: the browser calls the service directly', () => {
    assert.ok(!JSON.stringify(config.hosting).includes('/api'))
    assert.ok(config.hosting.rewrites.every((r) => r.run === undefined && r.function === undefined))
  })

  it('still rewrites every other path to index.html, for the single-page app', () => {
    assert.deepEqual(config.hosting.rewrites, [{ source: '**', destination: '/index.html' }])
  })

  it('refuses to be framed, by header and by CSP', () => {
    const all = headersFor('**')

    assert.equal(all['X-Frame-Options'], 'DENY')
    assert.equal(all['Content-Security-Policy'], "frame-ancestors 'none'")
  })

  it('isolates the browsing context group', () => {
    assert.equal(headersFor('**')['Cross-Origin-Opener-Policy'], 'same-origin')
  })

  it('keeps the headers it had', () => {
    const all = headersFor('**')

    assert.equal(all['X-Content-Type-Options'], 'nosniff')
    assert.equal(all['Referrer-Policy'], 'no-referrer')
    assert.equal(all['Permissions-Policy'], 'microphone=(self)')
  })

  it('sends frame-ancestors alone in the header CSP: the full policy is the <meta> tag (web/csp.ts), and a header policy would be enforced on top of it', () => {
    // Both policies apply and a resource must satisfy each. A `connect-src` or `default-src` here would apply to the page as well.
    const policy = headersFor('**')['Content-Security-Policy']!

    assert.deepEqual(policy.split(';').map((d) => d.trim().split(/\s+/)[0]), ['frame-ancestors'])
  })

  it('caches built assets for good and revalidates index.html, which carries the CSP and so the API origin', () => {
    assert.match(headersFor('/assets/**')['Cache-Control']!, /immutable/)
    assert.equal(headersFor('/index.html')['Cache-Control'], 'no-cache')
  })
})

describe('firebase.json and firestore.rules: Firestore', () => {
  it('deploys the rules file beside the Hosting release, and not the indexes (deploy/01 creates the one index)', () => {
    assert.deepEqual(config.firestore, { rules: 'firestore.rules' })
  })

  it('denies every client read and write', () => {
    const rules = read('firestore.rules').replace(/\/\/.*$/gm, '')

    assert.deepEqual(rules.match(/\ballow\b[^;]*;/g), ['allow read, write: if false;'])
    assert.match(rules, /match \/\{document=\*\*\}/)
    assert.match(rules, /rules_version = '2';/)
  })
})

describe('index.html', () => {
  const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8')

  it('has the spot for the CSP <meta> tag once, right after the charset, so the policy covers everything that follows', () => {
    assert.equal(html.split('<!-- sib-csp -->').length, 2)
    assert.match(html, /<meta charset="UTF-8" \/>\s*<!-- sib-csp -->/)
  })

  it('has no inline script, inline style or event handler for the CSP to refuse', () => {
    assert.doesNotMatch(html, /<script(?![^>]*\ssrc=)[^>]*>/)
    assert.doesNotMatch(html, /<style[\s>]/)
    assert.doesNotMatch(html, /\son[a-z]+\s*=/i)
    assert.doesNotMatch(html, /\sstyle\s*=/i)
  })
})
