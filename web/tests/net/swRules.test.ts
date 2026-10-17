import assert from 'node:assert/strict'
import { readdirSync } from 'node:fs'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  FONT_CACHE,
  manifestLiteral,
  precacheList,
  PUBLIC_FILES,
  ruleFor,
  shellCache,
  staleCaches,
  storable,
  versionOf,
  type Manifest,
} from '../../src/sw/rules.ts'

// 2026-10-16 signal: the offline app shell's cache rules. Stored: the page, the hashed build files, the public files and Google
// Fonts. Never stored: any API response, any audio, anything but a GET.

const ORIGIN = 'https://say-it-back.web.app'
const API = 'https://say-it-back-api-x.a.run.app'
const get = (url: string, mode = 'cors') => ({ url, method: 'GET', mode })

describe('ruleFor', () => {
  it('never handles the API: the Cloud Run origin, or /api on the page origin', () => {
    for (const url of [
      `${API}/api/briefings/b_aaaaaaaaaaaa/rounds/1/check`,
      `${API}/api/tts`,
      `${API}/api/demo-answers/lifting-zone/ta/1/q1/audio`,
      `${ORIGIN}/api/catalog`,
      `${ORIGIN}/api`,
      `${ORIGIN}/api/eval/items/x/audio`,
    ]) {
      assert.equal(ruleFor(get(url), ORIGIN), null, url)
      assert.equal(ruleFor(get(url, 'navigate'), ORIGIN), null, url)
    }
  })

  it('never handles anything but a GET', () => {
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE', 'HEAD']) {
      assert.equal(ruleFor({ url: `${ORIGIN}/assets/index-abc.js`, method, mode: 'cors' }, ORIGIN), null)
    }
  })

  it('the page on any route is a navigation (network first)', () => {
    for (const path of ['/', '/start', '/b/b_aaaaaaaaaaaa/brief', '/records']) assert.equal(ruleFor(get(`${ORIGIN}${path}`, 'navigate'), ORIGIN), 'navigate')
  })

  it('hashed build files are cache first; the public files and index.html are network first', () => {
    assert.equal(ruleFor(get(`${ORIGIN}/assets/index-cH8pDohZ.js`), ORIGIN), 'asset')
    assert.equal(ruleFor(get(`${ORIGIN}/assets/index-CRgFIa9i.css`), ORIGIN), 'asset')
    for (const path of ['/favicon.svg', '/pcm-capture.js', '/index.html', '/']) assert.equal(ruleFor(get(`${ORIGIN}${path}`), ORIGIN), 'public', path)
  })

  it('the worker script itself and unknown files are left to the browser', () => {
    assert.equal(ruleFor(get(`${ORIGIN}/sw.js`), ORIGIN), null)
    assert.equal(ruleFor(get(`${ORIGIN}/robots.txt`), ORIGIN), null)
  })

  it('Google Fonts over https only; any other origin is left alone', () => {
    assert.equal(ruleFor(get('https://fonts.googleapis.com/css2?family=Noto+Sans', 'no-cors'), ORIGIN), 'font')
    assert.equal(ruleFor(get('https://fonts.gstatic.com/s/notosans/v39/x.woff2'), ORIGIN), 'font')
    assert.equal(ruleFor(get('http://fonts.gstatic.com/s/x.woff2'), ORIGIN), null)
    assert.equal(ruleFor(get('https://fonts.gstatic.com.evil.example/x.woff2'), ORIGIN), null)
    assert.equal(ruleFor(get('https://www.youtube.com/watch?v=x', 'navigate'), ORIGIN), null)
    assert.equal(ruleFor(get('not a url'), ORIGIN), null)
  })
})

describe('storable', () => {
  const ok = { status: 200, type: 'basic', contentType: 'text/javascript' }

  it('a whole 200 of a file it handles', () => {
    assert.equal(storable(ok, 'asset'), true)
    assert.equal(storable({ ...ok, contentType: 'image/svg+xml' }, 'public'), true)
    assert.equal(storable({ status: 200, type: 'cors', contentType: 'font/woff2' }, 'font'), true)
  })

  it('never audio or video, never a partial, a redirect or an error', () => {
    for (const contentType of ['audio/wav', 'audio/mpeg', 'video/mp4', 'AUDIO/WAV']) assert.equal(storable({ ...ok, contentType }, 'public'), false, contentType)
    for (const status of [206, 301, 304, 404, 500, 503]) assert.equal(storable({ ...ok, status }, 'asset'), false, String(status))
    assert.equal(storable({ status: 0, type: 'opaqueredirect', contentType: null }, 'asset'), false)
  })

  it('an opaque reply (Google CSS fetched no-cors) only for fonts', () => {
    const opaque = { status: 0, type: 'opaque', contentType: null }
    assert.equal(storable(opaque, 'font'), true)
    assert.equal(storable(opaque, 'asset'), false)
    assert.equal(storable(opaque, 'navigate'), false)
  })

  it('a navigation only when it is the HTML page, and never for a request it does not handle', () => {
    assert.equal(storable({ ...ok, contentType: 'text/html; charset=utf-8' }, 'navigate'), true)
    assert.equal(storable({ ...ok, contentType: 'application/json' }, 'navigate'), false)
    assert.equal(storable(ok, null), false)
  })
})

describe('versions and the file list', () => {
  const bundle = ['index.html', 'assets/index-a1.js', 'assets/index-b2.css', 'assets/About-c3.js', 'assets/index-a1.js.map', 'sw.js']

  it('stores the page, the public files and every built file under assets/, sorted, without source maps', () => {
    assert.deepEqual(precacheList(bundle), ['/', ...PUBLIC_FILES, '/assets/About-c3.js', '/assets/index-a1.js', '/assets/index-b2.css'])
  })

  it('a new build is a new version, the same build the same version', () => {
    const v = versionOf(precacheList(bundle))
    assert.match(v, /^[0-9a-f]{8}$/)
    assert.equal(versionOf(precacheList([...bundle].reverse())), v)
    assert.notEqual(versionOf(precacheList(bundle.map((f) => f.replace('index-a1', 'index-a9')))), v)
  })

  it('a new version deletes the old shell caches and keeps the fonts', () => {
    const names = [shellCache('aaaa0001'), shellCache('bbbb0002'), FONT_CACHE, 'someone-else']
    assert.deepEqual(staleCaches(names, 'bbbb0002'), [shellCache('aaaa0001')])
  })

  it('the manifest written into sw.js is a JS string literal holding its JSON', () => {
    const literal = manifestLiteral(bundle)
    const manifest = JSON.parse(JSON.parse(literal) as string) as Manifest
    assert.deepEqual(manifest.files, precacheList(bundle))
    assert.equal(manifest.version, versionOf(manifest.files))
  })

  it('PUBLIC_FILES is exactly what web/public holds, so a new public file cannot miss the offline shell', () => {
    const folder = fileURLToPath(new URL('../../public/', import.meta.url))
    assert.deepEqual(readdirSync(folder).filter((f) => !f.startsWith('.')).map((f) => `/${f}`).sort(), [...PUBLIC_FILES].sort())
  })
})
