// What the sign-in gate shows, as a pure function of the Firebase user and /api/me (tests/auth/gate.test.ts).
import type { Me, Member, Role, RolesBySite } from './types.ts'

export type GateState =
  | { kind: 'loading' }
  | { kind: 'signedOut' }
  | { kind: 'noRole'; email: string }
  | { kind: 'ready'; me: Me }

/** `user` is undefined until Firebase has restored (or not) a session, then null or the signed-in user. */
export function gateState(user: { email: string | null } | null | undefined, me: Me | null | undefined): GateState {
  if (user === undefined) return { kind: 'loading' }
  if (user === null) return { kind: 'signedOut' }
  if (!me) return { kind: 'loading' }
  if (me.mode === 'firebase' && !me.member.orgAdmin && Object.keys(me.roles).length === 0) {
    return { kind: 'noRole', email: me.member.email || user.email || '' }
  }
  return { kind: 'ready', me }
}

/** A member's roles with one role at one site switched on or off: sorted, and a site with none dropped (as the server stores it). */
export function toggleRole(roles: RolesBySite, site: string, role: Role, on: boolean): RolesBySite {
  const held = new Set(roles[site] ?? [])
  if (on) held.add(role)
  else held.delete(role)
  const next: RolesBySite = { ...roles, [site]: [...held].sort() }
  if (next[site].length === 0) delete next[site]
  return next
}

/** The body of PUT /api/orgs/{org}/members/{id}. */
export const memberBody = (m: Pick<Member, 'roles' | 'orgAdmin'>) => ({ roles: m.roles, orgAdmin: m.orgAdmin })
