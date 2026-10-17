import type { Round } from '../../api/types.ts'
import { useT, type StringKey } from '../../i18n/index.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'

/** A model id from `round.modelIds` (contract keys are snake_case; an older record may carry camelCase). */
const modelOf = (ids: Record<string, string>, key: string): string | undefined => ids[key] ?? ids[key.replace(/_(\w)/g, (_, c: string) => c.toUpperCase())]

interface Row {
  label: StringKey
  hint: StringKey
  value: string
  /** A model id (Latin, monospace), not words. */
  model: boolean
}

/**
 * "What checked these answers": the blind transcriber, the two judges (and whether judge B ran on a different model) and the
 * guard rules, which are code. A compact disclosure under the result, read from the round's own `modelIds`.
 */
export function ModelProvenance({ round }: { round: Round }) {
  const t = useT()
  const ids = round.modelIds ?? {}
  const unknown = t('models.unknown')
  const a = modelOf(ids, 'judge_a')
  const b = modelOf(ids, 'judge_b')
  const rows: Row[] = [
    { label: 'models.transcribe', hint: 'models.transcribeHint', value: modelOf(ids, 'transcribe') ?? unknown, model: Boolean(modelOf(ids, 'transcribe')) },
    { label: 'models.judgeA', hint: 'models.judgeAHint', value: a ?? unknown, model: Boolean(a) },
    ...(b ? [{ label: 'models.judgeB' as const, hint: (a && a !== b ? 'models.judgeBHint' : 'models.judgeBSame') as StringKey, value: b, model: true }] : []),
    { label: 'models.guard', hint: 'models.guardHint', value: t('models.guardValue'), model: false },
  ]
  return (
    <details className="group rounded-lg border border-outline-variant bg-surface-container-lowest">
      <summary className="state-layer flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-lg px-4 text-label-lg text-primary">
        <Icon name="fact_check" className="text-[1.25rem]" />
        <span className="min-w-0 flex-1 truncate">{t('models.title')}</span>
        <Icon name="expand_more" className="transition-transform group-open:rotate-180" />
      </summary>
      <dl className="space-y-3 px-4 pb-4 pt-1">
        {rows.map((r) => (
          <div key={r.label} className="space-y-0.5">
            <dt className="flex flex-wrap items-baseline justify-between gap-x-3 text-title-sm text-on-surface">
              <span>{t(r.label)}</span>
              <span lang={r.model ? 'en' : undefined} className={cx('text-label-lg font-normal text-on-surface-variant', r.model && 'break-all font-mono')}>
                {r.value}
              </span>
            </dt>
            <dd className="text-body-md text-on-surface-variant">{t(r.hint)}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}
