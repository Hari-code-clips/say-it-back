import type { EvalBreakdown, EvalReport } from '../../api/types.ts'
import { langNative, useCatalog } from '../../api/catalog.tsx'
import type { Lang } from '../../api/types.ts'
import { useT, useUiLang } from '../../i18n/index.tsx'
import { formatDateTime } from '../../lib/format.ts'
import { Card, Section } from '../../ui/Card.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { cx } from '../../ui/cx.ts'
import { Banner } from '../../ui/Feedback.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { COMPARE_LABEL, comparisonRows, passBarKey, type CompareKey } from './compare.ts'
import { patternLabel } from './labels.ts'

/** A share as a percentage; a dash when there was nothing to measure (a null ratio). */
const pct = (v: number | null | undefined): string => (v === null || v === undefined ? '—' : `${Math.round(v * 1000) / 10}%`)

function Stat({ label, value, hint, emphasis, note }: { label: string; value: string; hint?: string; emphasis?: boolean; note?: string }) {
  return (
    <Card
      variant={emphasis ? 'filled' : 'outlined'}
      className={cx('p-4 sm:p-5', emphasis ? 'space-y-1 sm:col-span-2 lg:col-span-4 lg:flex lg:items-center lg:gap-10 lg:space-y-0' : 'space-y-1')}
    >
      <div className="space-y-1">
        <p className="text-label-lg text-on-surface-variant">{label}</p>
        <p className={cx('font-semibold tabular-nums tracking-tight text-on-surface', emphasis ? 'text-display-sm' : 'text-headline-md')}>{value}</p>
        {note && <IllustrativeNote text={note} />}
      </div>
      {hint && <p className={cx('text-body-md text-on-surface-variant', emphasis && 'lg:max-w-xl lg:text-body-lg')}>{hint}</p>}
    </Card>
  )
}

/** "Illustrative, mock only" under a number that mock mode made up, so no crop of the page passes it off as measured. */
function IllustrativeNote({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-1.5 text-label-lg text-on-surface-variant">
      <Icon name="science" className="text-[1.125rem]" />
      {text}
    </p>
  )
}

function Breakdown({ title, rows, label }: { title: string; rows: Record<string, EvalBreakdown>; label: (key: string) => string }) {
  const t = useT()
  const entries = Object.entries(rows)
  if (entries.length === 0) return null
  return (
    // No minimum width: at 320 px the table fits the card (the bar steps aside below 600 px) instead of pushing the page sideways.
    // On a phone the count moves under the row label (its own column would leave a Tamil label no room) and the two
    // share columns take the width of their header; fixed columns, the count among them, from 600 px.
    <Card className="min-w-0 p-3 sm:p-5">
      <table className="w-full table-auto text-left sm:table-fixed">
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr className="text-label-lg text-on-surface-variant">
            <th scope="col" className="py-2 pr-2 font-medium sm:w-[40%]">
              <span className="sr-only">{title}</span>
            </th>
            <th scope="col" className="hidden whitespace-nowrap py-2 pr-2 text-right font-medium sm:table-cell sm:w-[16%]">
              {t('eval.n')}
            </th>
            <th scope="col" className="whitespace-nowrap py-2 pr-2 font-medium">
              {t('eval.exactShort')}
            </th>
            <th scope="col" className="whitespace-nowrap py-2 text-right font-medium sm:w-[22%]">
              {t('eval.unsafeShort')}
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, row]) => (
            <tr key={key} className="border-t border-outline-variant">
              <th scope="row" className="py-2 pr-2 text-body-md font-normal [overflow-wrap:anywhere] sm:text-body-lg">
                {label(key)}
                <span className="block text-label-lg tabular-nums text-on-surface-variant sm:hidden">{t('eval.nSteps', { n: row.n })}</span>
              </th>
              <td className="hidden py-2 pr-2 text-right tabular-nums sm:table-cell">{row.n}</td>
              <td className="py-2 pr-2">
                <span className="flex items-center gap-2">
                  <span aria-hidden="true" className="hidden h-2 w-16 shrink-0 overflow-hidden rounded-full bg-surface-container-high sm:block">
                    <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.round((row.exactAccuracy ?? 0) * 100)}%` }} />
                  </span>
                  <span className="tabular-nums">{pct(row.exactAccuracy)}</span>
                </span>
              </td>
              <td className={cx('py-2 text-right tabular-nums', row.unsafeErrors > 0 && 'font-semibold text-error')}>{row.unsafeErrors}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

/**
 * Headline numbers of eval/reports/latest.json. The one that matters most is unsafe errors. `illustrative` (mock mode): the
 * numbers are made up, so each carries a label saying so, and there is no pass-bar verdict on them.
 */
export function MetricsPanel({ report, illustrative = false }: { report: EvalReport; illustrative?: boolean }) {
  const t = useT()
  const { lang } = useUiLang()
  const { data: catalog } = useCatalog()
  const m = report.metrics
  const passed = report.passBar.passed
  const note = illustrative ? t('eval.illustrative') : undefined
  const compare = comparisonRows(report)

  return (
    <div className="space-y-8">
      {report.complete === false && (
        <Banner tone="warning" title={t('eval.partialTitle')}>
          {t('eval.partialBody', { n: report.nItems })}
        </Banner>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {illustrative ? (
          <StatusChip tone="warning" icon="science" className="text-title-sm">
            {t('eval.illustrative')}
          </StatusChip>
        ) : (
          <StatusChip tone={passed ? 'success' : 'warning'} icon={passed ? 'check_circle' : 'warning'} className="text-title-sm">
            {passed ? t('eval.passMet') : t('eval.passNotMet')}
          </StatusChip>
        )}
        <p className="text-body-md text-on-surface-variant">
          {t(passBarKey(report), { acc: pct(report.passBar.exactAccuracyMin), unsafe: report.passBar.unsafeErrorsMax, correct: pct(report.passBar.correctPassMin) })}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          emphasis
          label={t('eval.unsafe.label')}
          value={t('eval.unsafe.value', { n: m.unsafeErrors, d: m.unsafeDenominator })}
          hint={m.unsafeErrors === 0 ? t('eval.unsafe.bound', { bound: pct(m.unsafeUpperBound95) }) : t('eval.unsafe.hint')}
          note={note}
        />
        <Stat label={t('eval.exact')} value={pct(m.exactAccuracy)} hint={t('eval.exact.hint')} note={note} />
        <Stat label={t('eval.catch')} value={pct(m.catchRate)} hint={t('eval.catch.hint')} note={note} />
        {/* v0.5: the share the pass bar now asks about. It is 1 - over-flag rate, so it takes that card's place. */}
        {m.correctPassRate === undefined ? (
          <Stat label={t('eval.overflag')} value={pct(m.overFlagRate)} hint={t('eval.overflag.hint')} note={note} />
        ) : (
          <Stat label={t('eval.correct')} value={pct(m.correctPassRate)} hint={t('eval.correct.hint')} note={note} />
        )}
        <Stat label={t('eval.unclear')} value={pct(m.unclearRate)} hint={t('eval.unclear.hint')} note={note} />
      </div>

      <p className="text-body-md text-on-surface-variant">
        {t('eval.meta', {
          items: report.nItems,
          ratings: report.nStepRatings,
          passes: report.judgePasses,
          when: formatDateTime(report.generatedAt, lang),
          prompt: report.promptVersion,
        })}
        {' · '}
        {Object.entries(report.models)
          .map(([k, v]) => `${k}: ${v}`)
          .join(' · ')}
      </p>

      {note && <IllustrativeNote text={note} />}
      {compare && (
        <Section title={t('eval.baselineTitle')} hint={t('eval.baselineHint')} id="eval-baseline">
          <Breakdown title={t('eval.baselineTitle')} rows={compare} label={(k) => t(COMPARE_LABEL[k as CompareKey])} />
        </Section>
      )}
      <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
        <Section title={t('eval.byLanguage')} id="eval-lang">
          <Breakdown title={t('eval.byLanguage')} rows={report.byLanguage} label={(k) => langNative(catalog, k as Lang)} />
        </Section>
        <Section title={t('eval.byPattern')} id="eval-pattern">
          <Breakdown title={t('eval.byPattern')} rows={report.byPattern} label={(k) => patternLabel(t, k)} />
        </Section>
      </div>
    </div>
  )
}
