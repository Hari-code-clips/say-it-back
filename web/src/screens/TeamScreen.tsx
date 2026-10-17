// The org admin's Team screen (/team) of a VITE_AUTH_MODE=firebase build (build-notes/34): who has signed in, and their roles at
// each site. Only rendered inside the sign-in gate; the server refuses anyone but an org admin (403) whatever this screen shows.
import { useEffect, useState } from 'react'
import { authApi } from '../auth/api.ts'
import { useMe } from '../auth/AuthGate.tsx'
import { memberBody, toggleRole } from '../auth/gate.ts'
import { ROLES, type Member } from '../auth/types.ts'
import { useCatalog } from '../api/catalog.tsx'
import { useT } from '../i18n/index.tsx'
import { AppShell } from '../shell/AppShell.tsx'
import { Button } from '../ui/Button.tsx'
import { Banner, EmptyState, Skeleton } from '../ui/Feedback.tsx'
import { PageHeading } from '../ui/PageHeading.tsx'

function MemberCard({ orgId, initial, sites, self }: { orgId: string; initial: Member; sites: { id: string; name: string }[]; self: boolean }) {
  const t = useT()
  const [member, setMember] = useState(initial)
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')

  async function save() {
    setState('saving')
    try {
      setMember(await authApi.putMember(orgId, member.id, memberBody(member)))
      setState('saved')
    } catch {
      setState('failed')
    }
  }
  const change = (next: Member) => {
    setMember(next)
    setState('idle')
  }

  return (
    <li className="space-y-3 rounded-lg border border-outline-variant bg-surface-container-lowest p-4">
      <p className="break-all text-title-md text-on-surface">{member.email || member.id.slice(0, 12)}</p>
      <label className="flex min-h-12 items-center gap-3 text-body-md text-on-surface">
        <input
          type="checkbox"
          className="size-5 accent-primary"
          checked={member.orgAdmin}
          disabled={self && member.orgAdmin}
          onChange={(e) => change({ ...member, orgAdmin: e.target.checked })}
        />
        {t('auth.team.orgAdmin')}
      </label>
      {sites.map((site) => (
        <fieldset key={site.id} className="space-y-1">
          <legend className="text-label-lg text-on-surface-variant">{site.name}</legend>
          <div className="flex flex-wrap gap-x-4">
            {ROLES.map((role) => (
              <label key={role} className="flex min-h-12 items-center gap-3 text-body-md text-on-surface">
                <input
                  type="checkbox"
                  className="size-5 accent-primary"
                  checked={(member.roles[site.id] ?? []).includes(role)}
                  onChange={(e) => change({ ...member, roles: toggleRole(member.roles, site.id, role, e.target.checked) })}
                />
                {t(`auth.role.${role}`)}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <Button busy={state === 'saving'} onClick={() => void save()}>
          {t('auth.team.save')}
        </Button>
        {state === 'saved' && <span className="text-body-md text-on-surface-variant" role="status">{t('auth.team.saved')}</span>}
        {state === 'failed' && <span className="text-body-md text-error" role="alert">{t('auth.team.failed')}</span>}
      </div>
    </li>
  )
}

export function TeamScreen() {
  const t = useT()
  const me = useMe()
  const catalog = useCatalog()
  const [members, setMembers] = useState<Member[] | null>(null)
  const [failed, setFailed] = useState(false)
  const orgId = me?.mode === 'firebase' ? me.org.id : null

  useEffect(() => {
    if (!orgId) return
    authApi
      .members(orgId)
      .then((r) => setMembers(r.items))
      .catch(() => setFailed(true))
  }, [orgId])

  const sites = (catalog.data?.sites ?? []).map((s) => ({ id: s.id, name: s.name }))
  return (
    <AppShell>
      <div className="mx-auto max-w-3xl space-y-6">
        <PageHeading title={t('auth.team.title')} subtitle={t('auth.team.subtitle')} />
        {failed && <Banner tone="error" live="assertive" title={t('auth.team.loadFailed')} />}
        {!failed && members === null && <Skeleton className="h-40 w-full" />}
        {members?.length === 0 && <EmptyState icon="groups" title={t('auth.team.empty')} body="" />}
        {orgId && members && members.length > 0 && (
          <ul className="space-y-4">
            {members.map((m) => (
              <MemberCard key={m.id} orgId={orgId} initial={m} sites={sites} self={me?.mode === 'firebase' && m.id === me.member.id} />
            ))}
          </ul>
        )}
      </div>
    </AppShell>
  )
}
