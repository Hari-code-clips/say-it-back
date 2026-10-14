import { api } from '../api/endpoints.ts'
import { useT, type StringKey } from '../i18n/index.tsx'
import { useAsync } from '../lib/useAsync.ts'
import { AppShell } from '../shell/AppShell.tsx'
import type { IconName } from '../theme/iconNames.ts'
import { Card, Section } from '../ui/Card.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { Icon } from '../ui/Icon.tsx'
import { PageHeading } from '../ui/PageHeading.tsx'
import { GOOGLE_PRODUCTS } from './about/google.ts'

interface Guardrail {
  icon: IconName
  title: StringKey
  body: StringKey
}

const GUARDRAILS: readonly Guardrail[] = [
  { icon: 'gavel', title: 'about.g1.title', body: 'about.g1.body' },
  { icon: 'replay', title: 'about.g2.title', body: 'about.g2.body' },
  { icon: 'fact_check', title: 'about.g3.title', body: 'about.g3.body' },
  { icon: 'record_voice_over', title: 'about.g4.title', body: 'about.g4.body' },
  { icon: 'visibility_off', title: 'about.g5.title', body: 'about.g5.body' },
  { icon: 'security', title: 'about.g6.title', body: 'about.g6.body' },
]

function Deployment() {
  const t = useT()
  const { data, error, loading } = useAsync(() => api.health(), [])
  if (loading) return <p className="text-body-md text-on-surface-variant">{t('state.loading')}</p>
  if (error || !data) return <p className="text-body-md text-on-surface-variant">{t('about.deploy.unavailable')}</p>
  const rows: [string, string][] = [
    ['Flash', `${data.models.flash} (${data.backends.flash})`],
    ['Live', `${data.models.live} (${data.backends.live})`],
    ['TTS', `${data.models.tts} (${data.backends.tts})`],
    [t('about.deploy.store'), data.store],
    [t('about.deploy.passes'), String(data.judgePasses)],
    [t('about.deploy.prompt'), data.promptVersion],
  ]
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k} className="space-y-0.5">
          <dt className="text-label-lg text-on-surface-variant">{k}</dt>
          <dd className="break-words text-body-lg tabular-nums">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function AboutScreen() {
  const t = useT()
  return (
    <AppShell>
      <div className="mx-auto max-w-5xl space-y-12">
        <PageHeading title={t('about.title')} subtitle={t('about.subtitle')} />

        <Section title={t('about.guardrails')} hint={t('about.guardrailsHint')} id="about-guardrails">
          <ul className="grid gap-4 md:grid-cols-2">
            {GUARDRAILS.map((g) => (
              <Card as="li" key={g.title} className="flex gap-4 p-5">
                <span className="grid size-12 shrink-0 place-items-center rounded-full bg-primary-container text-on-primary-container">
                  <Icon name={g.icon} />
                </span>
                <div className="min-w-0 space-y-1">
                  <h3 className="text-title-md">{t(g.title)}</h3>
                  <p className="text-body-lg text-on-surface-variant">{t(g.body)}</p>
                </div>
              </Card>
            ))}
          </ul>
        </Section>

        <Section title={t('about.google')} hint={t('about.googleHint')} id="about-google">
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {GOOGLE_PRODUCTS.map((p) => (
              <Card as="li" key={p.name} variant="filled" className="space-y-2 p-4">
                <div className="flex items-start gap-3">
                  <Icon name={p.icon} className="mt-0.5 text-primary" />
                  <h3 lang="en" className="min-w-0 flex-1 text-title-md">
                    {p.name}
                  </h3>
                  {p.optional && <StatusChip>{t('about.optional')}</StatusChip>}
                </div>
                <p lang="en" className="text-body-md text-on-surface-variant">
                  {p.role}
                </p>
              </Card>
            ))}
          </ul>
        </Section>

        <Section title={t('about.deploy')} hint={t('about.deployHint')} id="about-deploy">
          <Card className="p-5 sm:p-6">
            <Deployment />
          </Card>
        </Section>
      </div>
    </AppShell>
  )
}
