import type { EvalBreakdown, EvalReport } from '../../api/types.ts'
import { langNative, useCatalog } from '../../api/catalog.tsx'
import type { Lang } from '../../api/types.ts'
import { useT, useUiLang } from '../../i18n/index.tsx'
import { formatDateTime } from '../../lib/format.ts'
import { Card, Section } from '../../ui/Card.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { cx } from '../../ui/cx.ts'

const pct = (v: number): string => `${Math.round(v * 1000) / 10}%`

function Stat({ label, value, hint, emphasis }: { label: string; value: string; hint?: string; emphasis?: boolean }) {
  return (
    <Card
      variant={emphasis ? 'filled' : 'outlined'}
      className={cx('p-4 sm:p-5', emphasis ? 'space-y-1 sm:col-span-2 lg:col-span-4 lg:flex lg:items-center lg:gap-10 lg:space-y-0' : 'space-y-1')}
    >
      <div className="space-y-1">
        <p className="text-label-lg text-on-surface-variant">{label}</p>
        <p className={cx('font-semibold tabular-nums tracking-tight text-on-surface', emphasis ? 'text-display-sm' : 'text-headline-md')}>{value}</p>
      </div>
      {hint && <p className={cx('text-body-md text-on-surface-variant', emphasis && 'lg:max-w-xl lg:text-body-lg')}>{hint}</p>}
    </Card>
  )
}

function Breakdown({ title, rows, label }: { title: string; rows: Record<string, EvalBreakdown>; label: (key: string) => string }) {
  const t = useT()
  const entries = Object.entries(rows)
  if (entries.length === 0) return null
  return (
    <Card className="overflow-x-auto p-4 sm:p-5">
      <table className="w-full min-w-[20rem] text-left">
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr className="text-label-lg text-on-surface-variant">
            <th scope="col" className="py-2 pr-3 font-medium">
              <span className="sr-only">{title}</span>
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              {t('eval.n')}
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              {t('eval.exact')}
            </th>
            <th scope="col" className="py-2 text-right font-medium">
              {t('eval.unsafeShort')}
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, row]) => (
            <tr key={key} className="border-t border-outline-variant">
              <th scope="row" className="py-2 pr-3 text-body-lg font-normal">
                {label(key)}
              </th>
              <td className="py-2 pr-3 text-right tabular-nums">{row.n}</td>
              <td className="py-2 pr-3">
                <span className="flex items-center gap-2">
                  <span aria-hidden="true" className="h-2 w-16 overflow-hidden rounded-full bg-surface-container-high">
                    <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.round(row.exactAccuracy * 100)}%` }} />
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

/** Headline numbers of eval/reports/latest.json. The one that matters most is unsafe errors. */
export function MetricsPanel({ report }: { report: EvalReport }) {
  const t = useT()
  const { lang } = useUiLang()
  const { data: catalog } = useCatalog()
  const m = report.metrics
  const passed = report.passBar.passed

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-3">
        <StatusChip tone={passed ? 'success' : 'warning'} icon={passed ? 'check_circle' : 'warning'} className="text-title-sm">
          {passed ? t('eval.passMet') : t('eval.passNotMet')}
        </StatusChip>
        <p className="text-body-md text-on-surface-variant">
          {t('eval.passBar', { acc: pct(report.passBar.exactAccuracyMin), unsafe: report.passBar.unsafeErrorsMax })}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          emphasis
          label={t('eval.unsafe.label')}
          value={t('eval.unsafe.value', { n: m.unsafeErrors, d: m.unsafeDenominator })}
          hint={m.unsafeErrors === 0 ? t('eval.unsafe.bound', { bound: pct(m.unsafeUpperBound95) }) : t('eval.unsafe.hint')}
        />
        <Stat label={t('eval.exact')} value={pct(m.exactAccuracy)} hint={t('eval.exact.hint')} />
        <Stat label={t('eval.catch')} value={pct(m.catchRate)} hint={t('eval.catch.hint')} />
        <Stat label={t('eval.overflag')} value={pct(m.overFlagRate)} hint={t('eval.overflag.hint')} />
        <Stat label={t('eval.unclear')} value={pct(m.unclearRate)} hint={t('eval.unclear.hint')} />
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

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t('eval.byLanguage')} id="eval-lang">
          <Breakdown title={t('eval.byLanguage')} rows={report.byLanguage} label={(k) => langNative(catalog, k as Lang)} />
        </Section>
        <Section title={t('eval.byPattern')} id="eval-pattern">
          <Breakdown title={t('eval.byPattern')} rows={report.byPattern} label={(k) => k} />
        </Section>
      </div>
    </div>
  )
}
