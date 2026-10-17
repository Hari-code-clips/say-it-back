import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { gateState, memberBody, toggleRole } from '../../src/auth/gate.ts'
import type { Me } from '../../src/auth/types.ts'

// Pilot accounts (build-notes/34): what the sign-in gate shows, and the Team screen's role edits.

const me = (roles: Me & { mode: 'firebase' } extends { roles: infer R } ? R : never, orgAdmin = false): Me => ({
  mode: 'firebase',
  org: { id: 'acme' },
  member: { id: 'm1', email: 'sup@acme.example', orgAdmin },
  roles,
})

describe('the sign-in gate', () => {
  it('waits for Firebase to restore the session, then for /api/me', () => {
    assert.equal(gateState(undefined, null).kind, 'loading')
    assert.equal(gateState({ email: 'a@b.c' }, null).kind, 'loading')
  })

  it('shows sign-in when there is no user, whatever /api/me said before', () => {
    assert.equal(gateState(null, me({ sg: ['supervisor'] })).kind, 'signedOut')
  })

  it('a member with no role waits for access, and says as whom', () => {
    assert.deepEqual(gateState({ email: 'x@y.z' }, me({})), { kind: 'noRole', email: 'sup@acme.example' })
  })

  it('a role at any site, or org admin, opens the app', () => {
    assert.equal(gateState({ email: null }, me({ chennai: ['safety_officer'] })).kind, 'ready')
    assert.equal(gateState({ email: null }, me({}, true)).kind, 'ready')
  })

  it('a device-mode server lets the app through (no accounts there)', () => {
    assert.equal(gateState({ email: null }, { mode: 'device' }).kind, 'ready')
  })
})

describe('role edits on the Team screen', () => {
  it('adds a role sorted and once', () => {
    const one = toggleRole({}, 'sg', 'supervisor', true)
    assert.deepEqual(toggleRole(one, 'sg', 'admin', true), { sg: ['admin', 'supervisor'] })
    assert.deepEqual(toggleRole(one, 'sg', 'supervisor', true), { sg: ['supervisor'] })
  })

  it('drops a site when its last role goes, and never touches another site', () => {
    const roles = { sg: ['supervisor' as const], chennai: ['admin' as const] }
    assert.deepEqual(toggleRole(roles, 'sg', 'supervisor', false), { chennai: ['admin'] })
    assert.deepEqual(roles, { sg: ['supervisor'], chennai: ['admin'] }) // the old object is unchanged
  })

  it('sends exactly roles and orgAdmin', () => {
    assert.deepEqual(memberBody({ roles: { sg: ['admin'] }, orgAdmin: true }), { roles: { sg: ['admin'] }, orgAdmin: true })
  })
})
