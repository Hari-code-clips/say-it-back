/* Hallmark · screen: record · genre: modern-minimal · macrostructure: Workbench read as a document (hairline rows, sections in the order a
 * reviewer asks): the decision, the permit, the problems, what was checked, the rounds, the tamper check. One card per section.
 * The bar: the next worker on the permit, or the same worker again after a No-go, or a new briefing. Go is the one ink chip; No-go is a
 * neutral outline (red is for hazards and failures, not for a supervisor's decision).
 * states: loading n/a (the briefing is loaded by the route) · default · error (the chain check's own states live in ChainPanel).
 * 2026-10-17: a decision after an in-person check says "Checked in person" under the chip, its unrated steps show no verdict, and a
 * round the worker declined to be recorded for reads "Not recorded". Nothing about the worker, no score.
 */
import { useLocation } from 'wouter'
import { bcp47, useCatalog } from '../api/catalog.tsx'
import { IS_MOCK } from '../api/client.ts'
import { api } from '../api/endpoints.ts'
import type { Briefing, PermitLink } from '../api/types.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { nextWorkerDraft, setDraft, type Draft } from '../flow/draft.ts'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { siteName } from '../i18n/catalogText.ts'
import { useLangName, useSopLabel, useT, useUiLang } from '../i18n/index.tsx'
import { briefingFacts, factsLine } from '../lib/briefingFacts.ts'
import { formatDateTime } from '../lib/format.ts'
import { permitBoard, permitDelivery } from '../lib/permit.ts'
import { useAsync } from '../lib/useAsync.ts'
import { PermitChip } from '../shell/PermitChip.tsx'
import { Button, LinkButton } from '../ui/Button.tsx'
import { Card, RowList, Section } from '../ui/Card.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { Icon } from '../ui/Icon.tsx'
import { sampleCoveredIds } from '../lib/sampleCovered.ts'
import { HazardSection } from './hazard/HazardSection.tsx'
import { StepRow } from './result/StepRow.tsx'
import { ChainPanel } from './record/ChainPanel.tsx'
import { DeleteRecord } from './record/DeleteRecord.tsx'
import { rebriefDraft, recordBar, type RecordAction } from './record/rebrief.ts'
import { VERDICT, VERDICT_ORDER } from './result/verdict.ts'

/**
 * Mock mode only: what the permit-to-work stub would show for this permit, from this browser's own briefings. The real
 * board lives in the permit system (integrations/ptw-stub); this one says it is a mock.
 */
function MockPermitBoard({ permit }: { permit: PermitLink }) {
  const t = useT()
  const { data } = useAsync(() => api.listBriefings(50), [permit.ref])
  if (!data) return null
  const board = permitBoard(data.items, permit.ref, permit.crewSize)
  return (
    <StatusChip icon="science">
      {t('record.mockBoard', { verified: board.verified, crew: board.crewSize, status: t(board.status === 'released' ? 'permit.released' : 'permit.held') })}
    </StatusChip>
  )
}

/** SIB_OUTBOX: whether the permit system has the decision (docs/EPERMIT_ADAPTER.md). Red only when it does not. */
const DELIVERY = {
  delivered: { label: 'permit.delivered', icon: 'task_alt', tone: 'text-on-surface' },
  retrying: { label: 'permit.retrying', icon: 'hourglass_top', tone: 'text-on-surface-variant' },
  notDelivered: { label: 'permit.notDelivered', icon: 'error', tone: 'text-error' },
} as const

/** Go is the one solid ink chip; No-go is a neutral outline with its own mark. Never colour alone: the word and the mark carry it. */
export function DecisionChip({ decision }: { decision: NonNullable<Briefing['decision']> }) {
  const t = useT()
  return decision.value === 'go' ? (
    <StatusChip tone="ink" icon="task_alt" className="text-title-md">
      {t('decision.go')}
    </StatusChip>
  ) : (
    <StatusChip tone="warning" icon="block" className="text-title-md">
      {t('decision.noGo')}
    </StatusChip>
  )
}

/** What was checked and what was decided. No score, no worker identity. */
export function RecordScreen() {
  const t = useT()
  const { lang: uiLang } = useUiLang()
  const [, navigate] = useLocation()
  const { briefing: b } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const sopLabel = useSopLabel()
  const decision = b.decision
  const sent = permitDelivery(b.delivery)
  const tag = bcp47(catalog, b.supervisorLang, b.siteId)
  const site = catalog?.sites.find((s) => s.id === b.siteId)
  const siteLabel = site ? siteName(site, uiLang) : b.siteId
  const bySample = new Set(sampleCoveredIds(b))
  // v0.5.1: what this briefing took, from its own timestamps, rounds and reports only.
  const facts = briefingFacts(b)
  // v0.5.2: a decided briefing on a permit with workers still to come starts the next one from here.
  const next = decision ? nextWorkerDraft(b) : null
  const bar = recordBar(b)

  const start = (draft: Draft | null) => {
    if (!draft) return
    setDraft(draft)
    navigate('/new/instruction')
  }
  const action = (a: RecordAction, primary: boolean) => {
    const look = { size: primary ? ('lg' as const) : ('md' as const), variant: primary ? ('filled' as const) : ('outlined' as const) }
    switch (a.kind) {
      case 'next':
        return (
          <Button {...look} icon="arrow_forward" onClick={() => start(next)}>
            {t('record.nextWorker', { n: a.slot, m: a.crew })}
          </Button>
        )
      case 'rebrief':
        return (
          <Button {...look} icon="replay" onClick={() => start(rebriefDraft(b))}>
            {t('record.rebrief', { n: a.slot })}
          </Button>
        )
      case 'new':
        return (
          <LinkButton href="/new" {...look} variant={primary ? 'filled' : 'text'} icon="add">
            {t('record.new')}
          </LinkButton>
        )
      case 'all':
        return (
          <LinkButton href="/records" {...look} variant={primary ? 'filled' : 'text'}>
            {t('record.all')}
          </LinkButton>
        )
    }
  }

  const permitHint = !b.permit
    ? null
    : decision?.value === 'no_go'
      ? t('record.rebriefHint', { n: b.permit.slot, m: b.permit.crewSize })
      : next?.permit
        ? t('record.nextWorkerHint', { n: next.permit.slot, m: next.permit.crewSize })
        : decision && t('record.permitLast', { m: b.permit.crewSize })

  return (
    <FlowFrame step="record" title={t('record.title')} subtitle={t('record.subtitle')} leaveTo="/records" primary={action(bar.primary, true)} secondary={action(bar.secondary, false)}>
      {decision && (
        <Section title={t('record.decisionTitle')} id="record-decision">
          <Card>
            <RowList as="div">
              <div className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
                <DecisionChip decision={decision} />
                <span className="text-body-lg text-on-surface-variant">{formatDateTime(decision.at, uiLang)}</span>
                {decision.by && <StatusChip>{t('record.by', { by: decision.by })}</StatusChip>}
              </div>
              {decision.inPerson && (
                <p className="flex items-start gap-2 px-4 py-3 text-title-sm text-on-surface sm:px-5">
                  <Icon name="groups" className="mt-0.5 text-[1.25rem] text-on-surface-variant" />
                  <span className="min-w-0">{t('inPerson.recordLine')}</span>
                </p>
              )}
              {facts && (
                <p className="flex items-start gap-2 px-4 py-3 text-body-lg text-on-surface sm:px-5">
                  <Icon name="history" className="mt-0.5 text-[1.25rem] text-on-surface-variant" />
                  <span className="min-w-0">{factsLine(facts, uiLang)}</span>
                </p>
              )}
              {decision.reason && (
                <div className="space-y-1 px-4 py-3 sm:px-5">
                  <p className="text-label-lg text-on-surface-variant">{t('record.reason')}</p>
                  <p lang={tag} className="script-text text-body-lg">
                    {decision.reason}
                  </p>
                </div>
              )}
              {decision.openStepIds.length > 0 && (
                <p className="flex items-start gap-2 px-4 py-3 text-title-sm text-on-surface sm:px-5">
                  <Icon name="warning" filled className="mt-0.5 text-[1.25rem]" />
                  <span className="min-w-0">{t('record.openAtDecision', { n: decision.openStepIds.length })}</span>
                </p>
              )}
              {(decision.openHazardIds?.length ?? 0) > 0 && (
                <p className="flex items-start gap-2 px-4 py-3 text-title-sm text-error sm:px-5">
                  <Icon name="report" filled className="mt-0.5 text-[1.25rem]" />
                  <span className="min-w-0">{t('record.hazardsAtDecision', { n: decision.openHazardIds?.length ?? 0 })}</span>
                </p>
              )}
              {sent && (
                <p role="status" className={`flex items-start gap-2 px-4 py-3 text-title-sm sm:px-5 ${DELIVERY[sent].tone}`}>
                  <Icon name={DELIVERY[sent].icon} className="mt-0.5 text-[1.25rem]" />
                  <span className="min-w-0">{t(DELIVERY[sent].label)}</span>
                </p>
              )}
            </RowList>
          </Card>
        </Section>
      )}

      {b.permit && (
        <Section title={t('record.permit')} id="record-permit">
          <Card>
            <RowList as="div">
              <div className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
                <PermitChip permit={b.permit} className="text-title-sm" />
                {IS_MOCK && <MockPermitBoard permit={b.permit} />}
              </div>
              {permitHint && <p className="px-4 py-3 text-body-lg text-on-surface sm:px-5">{permitHint}</p>}
            </RowList>
          </Card>
        </Section>
      )}

      <HazardSection briefing={b} editable={false} />

      <Section title={t('record.checked')} id="record-checked">
        <Card>
          <RowList>
            {b.steps.map((s) => (
              <StepRow
                key={s.id}
                // 2026-10-17: no model rated a step of an in-person check; it shows no verdict rather than "Ask again".
                verdict={b.latestVerdicts[s.id] ?? (decision?.inPerson ? undefined : 'unclear')}
                text={s.text}
                lang={tag}
                tag={decision?.openStepIds.includes(s.id) ? <StatusChip tone="warning">{t('record.open')}</StatusChip> : undefined}
                sample={bySample.has(s.id)}
              />
            ))}
          </RowList>
        </Card>
      </Section>

      <Section title={t('record.rounds')} id="record-rounds">
        <Card>
          <RowList as="ol">
            {b.rounds.map((r) => (
              <li key={r.n} className="space-y-2 px-4 py-3 sm:px-5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  <span className="text-title-md">{t('record.roundN', { n: r.n })}</span>
                  <span className="text-body-md text-on-surface-variant">{t(r.kind === 'initial' ? 'record.initial' : 'record.reexplain')}</span>
                  {r.mode && <StatusChip icon={r.mode === 'live' ? 'record_voice_over' : 'volume_up'}>{t(r.mode === 'live' ? 'brief.mode.live' : 'brief.mode.turn')}</StatusChip>}
                  {(r.sampleAnswers?.length ?? 0) > 0 && (
                    <StatusChip tone="primary" icon="graphic_eq">
                      {t('result.sample')}
                    </StatusChip>
                  )}
                  {r.consent?.given === false && <StatusChip icon="mic_off">{t('inPerson.notRecorded')}</StatusChip>}
                </div>
                <div className="flex flex-wrap gap-2">
                  {VERDICT_ORDER.map((v) => {
                    const n = r.ratings.filter((x) => x.verdict === v).length
                    return n > 0 ? (
                      <StatusChip key={v} tone={VERDICT[v].tone} icon={VERDICT[v].icon}>
                        {t(VERDICT[v].label)} · {n}
                      </StatusChip>
                    ) : null
                  })}
                </div>
              </li>
            ))}
          </RowList>
        </Card>
      </Section>

      <ChainPanel briefing={b} />

      <div className="space-y-1 border-t border-outline-variant pt-4 text-body-md text-on-surface-variant">
        <p>
          <span className="text-title-sm text-on-surface">{t('record.meta')} </span>
          {sopLabel(b.sop)} · {siteLabel} · {langName(b.supervisorLang)} → {langName(b.workerLang)} · {formatDateTime(b.createdAt, uiLang)}
        </p>
        <p>{t('record.note')}</p>
      </div>
      <DeleteRecord briefingId={b.id} />
    </FlowFrame>
  )
}
