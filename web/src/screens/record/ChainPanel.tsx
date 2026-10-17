/* Hallmark · component: record chain check · genre: modern-minimal · theme: design.md
 * The state of the check is the first thing in the section and always a mark plus a sentence: checking (skeleton), verified (neutral,
 * with the chain head), no chain (neutral, an old record), broken (red, names the event and why, announced at once), could not check
 * (outline, with Retry). Below it, one hairline card of facts and a disclosure with the event timeline. No tinted box inside a card.
 * states: loading (checking) · success (chain intact) · error (could not check; Retry) · broken · empty (no chain) · disabled n/a
 */
import { api } from '../../api/endpoints.ts'
import type { Briefing, ChainEventType } from '../../api/types.ts'
import { useT, useUiLang, type StringKey } from '../../i18n/index.tsx'
import { NUMBERED_EVENTS, chainReasonKey, eventNumber, hasNoChain, samplesByRound, shortHash, verifiedCount } from '../../lib/chain.ts'
import { formatTime } from '../../lib/format.ts'
import { useAsync } from '../../lib/useAsync.ts'
import { Button } from '../../ui/Button.tsx'
import { Card, RowList } from '../../ui/Card.tsx'
import { cx } from '../../ui/cx.ts'
import { Banner, Skeleton } from '../../ui/Feedback.tsx'
import { Icon } from '../../ui/Icon.tsx'

const EVENT_LABEL: Record<ChainEventType, StringKey> = {
  created: 'event.created',
  instruction_edited: 'event.instruction_edited',
  steps_proposed: 'event.steps_proposed',
  steps_confirmed: 'event.steps_confirmed',
  round_created: 'event.round_created',
  script_approved: 'event.script_approved',
  round_judged: 'event.round_judged',
  hazard_raised: 'event.hazard_raised',
  hazard_acknowledged: 'event.hazard_acknowledged',
  decided: 'event.decided',
  consent: 'consent.event',
}

/** "Record verified · 14 events · chain intact", the head hash, the event timeline, and which answers were stored samples. */
export function ChainPanel({ briefing }: { briefing: Briefing }) {
  const t = useT()
  const { lang } = useUiLang()
  const events = briefing.events ?? []
  const verify = useAsync(() => api.verify(briefing.id), [briefing.id, briefing.recordHash])
  const v = verify.data
  const label = (type: ChainEventType | string, n: string) => {
    const key = EVENT_LABEL[type as ChainEventType]
    return key ? t(key, NUMBERED_EVENTS.has(type as ChainEventType) ? { n } : undefined) : type
  }
  // 2026-10-17: a decision after an in-person check says so in the timeline too (its event holds `inPerson: true`).
  const eventLabel = (e: (typeof events)[number]) => (e.type === 'decided' && e.data.inPerson === true ? t('inPerson.event') : label(e.type, eventNumber(e)))
  const broken = v && !v.ok ? events.find((e) => e.seq === v.brokenAt) : undefined
  const samples = samplesByRound(briefing.rounds)

  return (
    <section aria-labelledby="chain-title" className="space-y-4">
      <div className="space-y-1">
        <h2 id="chain-title" className="text-title-lg text-on-surface">
          {t('chain.title')}
        </h2>
        <p className="text-body-md text-on-surface-variant">{t('chain.how')}</p>
      </div>

      <div aria-live="polite">
        {verify.loading && (
          <div role="status" className="space-y-2">
            <p className="text-body-md text-on-surface-variant">{t('chain.checking')}</p>
            <Skeleton className="h-14 w-full" />
          </div>
        )}
        {verify.error && !verify.loading && (
          <Banner
            tone="warning"
            icon="warning"
            title={t('chain.failed')}
            action={
              <Button variant="outlined" icon="refresh" onClick={verify.reload}>
                {t('action.retry')}
              </Button>
            }
          />
        )}
        {v && !verify.loading && v.ok && (
          <Banner tone="info" icon="verified" title={t('chain.ok', { n: verifiedCount(v, events.length) })}>
            {t('chain.head')}{' '}
            <span lang="en" className="font-mono" title={v.recordHash}>
              {shortHash(v.recordHash)}
            </span>
          </Banner>
        )}
        {v && !verify.loading && !v.ok && hasNoChain(v) && (
          <Banner tone="info" icon="info">
            {t('chain.none')}
          </Banner>
        )}
        {v && !verify.loading && !v.ok && !hasNoChain(v) && (
          <Banner tone="error" icon="link_off" live="assertive" title={t('chain.broken')}>
            {t('chain.brokenAt', { seq: v.brokenAt ?? '?', type: broken ? label(broken.type, eventNumber(broken)) : '?' })} {t(chainReasonKey(v.reason))}
          </Banner>
        )}
      </div>

      <Card>
        <RowList as="div">
          <p className="flex items-center gap-2 px-4 py-3 text-body-md text-on-surface sm:px-5">
            <Icon name="lock" className="text-[1.25rem] text-on-surface-variant" />
            {t('chain.refused')}
          </p>
          <div className="space-y-1 px-4 py-3 sm:px-5">
            <h3 className="text-title-sm text-on-surface-variant">{t('chain.samples')}</h3>
            {samples.length === 0 ? (
              <p className="text-body-md text-on-surface">{t('chain.noSamples')}</p>
            ) : (
              <ul className="space-y-1">
                {samples.flatMap((r) =>
                  r.numbers.map((q) => (
                    <li key={`${r.round}-${q}`} className="flex items-start gap-2 text-body-md text-on-surface">
                      <Icon name="graphic_eq" className="mt-0.5 text-[1.125rem] text-on-surface-variant" />
                      {t('chain.sampleLine', { round: r.round, q })}
                    </li>
                  )),
                )}
              </ul>
            )}
          </div>
        </RowList>
      </Card>

      {events.length > 0 && (
        <details className="group rounded-lg border border-outline-variant bg-surface-container-lowest" open>
          <summary className="state-layer flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-lg px-4 text-label-lg text-on-surface sm:px-5">
            <Icon name="expand_more" className="transition-transform group-open:rotate-180" />
            {t('chain.timeline', { n: events.length })}
          </summary>
          <ol className="divide-y divide-outline-variant border-t border-outline-variant">
            {events.map((e) => (
              <li
                key={e.seq}
                className={cx(
                  'grid grid-cols-[2rem_minmax(0,1fr)_auto] items-baseline gap-x-2 px-4 py-2 sm:px-5',
                  e.seq === v?.brokenAt && !v.ok && 'bg-error-container text-on-error-container',
                )}
              >
                <span className="text-label-lg tabular-nums text-on-surface-variant">{e.seq}</span>
                <span className="min-w-0">
                  <span className="block text-body-md text-on-surface">{eventLabel(e)}</span>
                  <span className="block text-label-lg font-normal tabular-nums text-on-surface-variant">{formatTime(e.at, lang)}</span>
                </span>
                <span lang="en" className="font-mono text-label-lg text-on-surface-variant" title={e.hash}>
                  {shortHash(e.hash, 8)}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  )
}
