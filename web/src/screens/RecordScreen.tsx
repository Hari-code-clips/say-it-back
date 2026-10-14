import { bcp47, useCatalog } from '../api/catalog.tsx'
import type { Briefing } from '../api/types.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { siteName } from '../i18n/catalogText.ts'
import { useLangName, useSopLabel, useT, useUiLang } from '../i18n/index.tsx'
import { formatDateTime } from '../lib/format.ts'
import { LinkButton } from '../ui/Button.tsx'
import { Card, Section } from '../ui/Card.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { Banner } from '../ui/Feedback.tsx'
import { VerdictChip } from '../ui/VerdictChip.tsx'
import { VERDICT, VERDICT_ORDER } from './result/verdict.ts'

export function DecisionChip({ decision }: { decision: NonNullable<Briefing['decision']> }) {
  const t = useT()
  return decision.value === 'go' ? (
    <StatusChip tone="primary" icon="task_alt" className="text-title-md">
      {t('decision.go')}
    </StatusChip>
  ) : (
    <StatusChip tone="error" icon="block" className="text-title-md">
      {t('decision.noGo')}
    </StatusChip>
  )
}

/** What was checked and what was decided. No score, no worker identity. */
export function RecordScreen() {
  const t = useT()
  const { lang: uiLang } = useUiLang()
  const { briefing: b } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const sopLabel = useSopLabel()
  const decision = b.decision
  const tag = bcp47(catalog, b.supervisorLang, b.siteId)
  const site = catalog?.sites.find((s) => s.id === b.siteId)
  const siteLabel = site ? siteName(site, uiLang) : b.siteId

  return (
    <FlowFrame
      step="record"
      title={t('record.title')}
      subtitle={t('record.subtitle')}
      leaveTo="/records"
      primary={
        <LinkButton href="/new" size="lg" icon="add">
          {t('record.new')}
        </LinkButton>
      }
      secondary={
        <LinkButton href="/records" size="lg" variant="text">
          {t('record.all')}
        </LinkButton>
      }
    >
      {decision && (
        <Card variant="filled" className="space-y-4 p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-3">
            <DecisionChip decision={decision} />
            <span className="text-body-lg text-on-surface-variant">{formatDateTime(decision.at, uiLang)}</span>
            {decision.by && <StatusChip>{t('record.by', { by: decision.by })}</StatusChip>}
          </div>
          {decision.reason && (
            <div className="space-y-1">
              <p className="text-label-lg text-on-surface-variant">{t('record.reason')}</p>
              <p lang={tag} className="script-text text-body-lg">
                {decision.reason}
              </p>
            </div>
          )}
          {decision.openStepIds.length > 0 && (
            <Banner tone="warning" title={t('record.openAtDecision', { n: decision.openStepIds.length })} />
          )}
        </Card>
      )}

      <Section title={t('record.checked')} id="record-checked">
        <ul className="space-y-2">
          {b.steps.map((s) => (
            <Card as="li" key={s.id} className="flex flex-wrap items-center gap-3 p-4">
              <VerdictChip verdict={b.latestVerdicts[s.id] ?? 'unclear'} />
              <span lang={tag} className="script-text min-w-0 flex-1 text-body-lg">
                {s.text}
              </span>
              {decision?.openStepIds.includes(s.id) && <StatusChip tone="warning">{t('record.open')}</StatusChip>}
            </Card>
          ))}
        </ul>
      </Section>

      <Section title={t('record.rounds')} id="record-rounds">
        <ol className="space-y-2">
          {b.rounds.map((r) => (
            <Card as="li" key={r.n} className="flex flex-wrap items-center gap-3 p-4">
              <span className="text-title-md">{t('record.roundN', { n: r.n })}</span>
              <span className="text-body-md text-on-surface-variant">{t(r.kind === 'initial' ? 'record.initial' : 'record.reexplain')}</span>
              {r.mode && <StatusChip icon={r.mode === 'live' ? 'record_voice_over' : 'volume_up'}>{t(r.mode === 'live' ? 'brief.mode.live' : 'brief.mode.turn')}</StatusChip>}
              <span className="ml-auto flex flex-wrap gap-2">
                {VERDICT_ORDER.map((v) => {
                  const n = r.ratings.filter((x) => x.verdict === v).length
                  return n > 0 ? (
                    <StatusChip key={v} tone={VERDICT[v].tone} icon={VERDICT[v].icon}>
                      {t(VERDICT[v].label)} · {n}
                    </StatusChip>
                  ) : null
                })}
              </span>
            </Card>
          ))}
        </ol>
      </Section>

      <Card variant="filled" className="space-y-2 p-4 text-body-md text-on-surface-variant">
        <p>
          <span className="text-title-sm text-on-surface">{t('record.meta')} </span>
          {sopLabel(b.sop)} · {siteLabel} ·{langName(b.supervisorLang)} → {langName(b.workerLang)} · {formatDateTime(b.createdAt, uiLang)}
        </p>
        <p>{t('record.note')}</p>
      </Card>
    </FlowFrame>
  )
}
