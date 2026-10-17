// Pilot accounts (docs/API.md Deviations 2026-10-16, build-notes/34): what /api/me and the org routes send.
export type Role = 'admin' | 'safety_officer' | 'supervisor'

/** The order roles are shown in, least to most power. */
export const ROLES: readonly Role[] = ['supervisor', 'safety_officer', 'admin']

export type RolesBySite = Record<string, Role[]>

export type Me =
  | { mode: 'device' }
  | { mode: 'firebase'; org: { id: string }; member: { id: string; email: string; orgAdmin: boolean }; roles: RolesBySite }

export interface Member {
  id: string
  email: string
  orgAdmin: boolean
  roles: RolesBySite
  createdAt: string
  updatedAt: string
}
