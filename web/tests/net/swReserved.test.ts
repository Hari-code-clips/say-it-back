import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { HOSTING_RESERVED, ruleFor } from '../../src/sw/rules.ts'

// Security fixes B, L7 (build-notes/36-security-fixes-b.md): in a firebase build, Firebase Hosting serves its sign-in pages on the
// app's own origin, under /__/. The offline shell's worker never handles them, so after an offline spell the sign-in handler is
// never answered with the cached app shell.

const ORIGIN = 'https://demo-project.firebaseapp.com'
const facts = (path: string, mode: string) => ({ url: `${ORIGIN}${path}`, method: 'GET', mode })

describe('the service worker and Firebase Hosting’s reserved paths', () => {
  for (const path of ['/__/auth/handler?apiKey=k&authType=signInViaPopup', '/__/auth/iframe?apiKey=k', '/__/auth/handler', '/__/firebase/init.js', '/__/firebase/12.19.0/firebase-app.js']) {
    it(`${path} is left to the browser, as a page and as a file`, () => {
      for (const mode of ['navigate', 'cors', 'no-cors', 'same-origin']) assert.equal(ruleFor(facts(path, mode), ORIGIN), null, mode)
    })
  }

  it('is exactly /__/, so the app’s own routes are still the shell’s', () => {
    assert.equal(HOSTING_RESERVED, '/__/')
    for (const path of ['/', '/b/b_aaaaaaaaaaaa/result', '/privacy', '/__auth']) assert.equal(ruleFor(facts(path, 'navigate'), ORIGIN), 'navigate', path)
  })
})
