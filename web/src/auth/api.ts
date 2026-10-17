// The pilot-account routes (docs/API.md Deviations 2026-10-16), over the app's transport, which adds the ID token.
import { request } from '../api/client.ts'
import type { Me, Member, RolesBySite } from './types.ts'

const enc = encodeURIComponent

export const authApi = {
  me: () => request<Me>('/me'),
  members: (orgId: string) => request<{ items: Member[] }>(`/orgs/${enc(orgId)}/members`),
  putMember: (orgId: string, memberId: string, body: { roles: RolesBySite; orgAdmin: boolean }) =>
    request<Member>(`/orgs/${enc(orgId)}/members/${enc(memberId)}`, { method: 'PUT', json: body }),
}
