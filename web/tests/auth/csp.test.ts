import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { buildCsp, firebaseAuthSources } from '../../csp.ts'

// Pilot accounts (build-notes/34): only a firebase build's policy names Firebase Auth's origins; the default build's policy is
// byte for byte what it was (tests/build/csp.test.ts pins its directives).

const FIREBASE = ['https://apis.google.com', 'identitytoolkit.googleapis.com', 'securetoken.googleapis.com', 'frame-src']
const BASE = 'https://api.example.test/api'

describe('the CSP of a firebase build', () => {
  it('the default build names none of the Firebase origins', () => {
    for (const base of [undefined, BASE]) {
      const policy = buildCsp(base)
      assert.equal(policy, buildCsp(base, undefined))
      for (const source of FIREBASE) assert.ok(!policy.includes(source), source)
    }
  })

  it('adds the gapi loader, the sign-in and refresh APIs and the auth domain frame, and nothing else', () => {
    const policy = buildCsp(BASE, 'sib-pilot.firebaseapp.com')
    const directives = Object.fromEntries(policy.split('; ').map((d) => [d.split(' ')[0], d]))
    assert.equal(directives['script-src'], "script-src 'self' https://apis.google.com")
    assert.equal(
      directives['connect-src'],
      'connect-src https://api.example.test wss://api.example.test https://identitytoolkit.googleapis.com https://securetoken.googleapis.com',
    )
    assert.equal(directives['frame-src'], 'frame-src https://sib-pilot.firebaseapp.com')
    const rest = buildCsp(BASE).split('; ').filter((d) => !d.startsWith('script-src') && !d.startsWith('connect-src'))
    for (const d of rest) assert.ok(policy.includes(d), d)
  })

  it('refuses an auth domain that could add a source or a directive', () => {
    for (const bad of ['', 'evil.com; script-src *', 'https://x.firebaseapp.com', '*.example.com', 'localhost']) {
      assert.throws(() => firebaseAuthSources(bad), /VITE_FIREBASE_AUTH_DOMAIN/, bad)
    }
  })
})
