import type { Conflict, Step } from '../../api/types.ts'
import { useT } from '../../i18n/index.tsx'
import { IconButton } from '../../ui/Button.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'
import { TextArea } from '../../ui/TextField.tsx'

interface StepCardProps {
  index: number
  step: Step
  /** Conflicts that point at this step. */
  conflicts: Conflict[]
  sopId: string
  /** BCP-47 tag of the supervisor language. */
  lang: string
  showTextError: boolean
  onChange: (patch: Partial<Step>) => void
  onBlurText: () => void
  onRemove: () => void
  canRemove: boolean
}

/** One editable critical step. Source, conflicts and voice-checkability are shown as labelled chips. */
export function StepCard({ index, step, conflicts, sopId, lang, showTextError, onChange, onBlurText, onRemove, canRemove }: StepCardProps) {
  const t = useT()
  const hasConflict = conflicts.length > 0
  return (
    <li
      id={`step-${step.id}`}
      className={cx(
        'scroll-mt-24 space-y-3 rounded-lg border p-4 sm:p-5',
        hasConflict ? 'border-error bg-error-container/30' : 'border-outline-variant bg-surface-container-lowest',
      )}
    >
      {/* Header row: number and remove. The field below gets the card's full width, which matters on a phone. */}
      <div className="flex items-center justify-between gap-3">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-full bg-primary-container text-title-md text-on-primary-container"
        >
          {index + 1}
        </span>
        <IconButton icon="delete" label={t('steps.remove', { n: index + 1 })} onClick={onRemove} disabled={!canRemove} />
      </div>

      {(step.source === 'sop' || hasConflict || !step.speakable) && (
        <div className="flex flex-wrap gap-2">
          {step.source === 'sop' && (
            <StatusChip tone="warning" icon="description">
              {t('steps.sopOnly')}
            </StatusChip>
          )}
          {hasConflict && (
            <StatusChip tone="strong-error" icon="error">
              {t('steps.conflictChip')}
            </StatusChip>
          )}
          {!step.speakable && (
            <StatusChip tone="warning" icon="touch_app">
              {t('steps.notSpeakable')}
            </StatusChip>
          )}
        </div>
      )}

      <TextArea
        label={t('steps.stepLabel', { n: index + 1 })}
        value={step.text}
        onChange={(text) => onChange({ text })}
        onBlur={onBlurText}
        rows={2}
        lang={lang}
        error={showTextError && !step.text.trim() ? t('steps.textRequired') : undefined}
      />

      {step.sopQuote && (
        <figure className="flex gap-3 rounded-md bg-surface-container px-4 py-3">
          <Icon name="format_quote" className="mt-0.5 text-on-surface-variant" />
          <div className="min-w-0 space-y-1">
            <blockquote lang={lang} className="script-text text-body-md text-on-surface">
              {step.sopQuote}
            </blockquote>
            <figcaption className="text-body-md text-on-surface-variant">
              {t('steps.sopQuote', { sop: sopId })}
              {step.source === 'sop' && ` ${t('steps.sopOnlyHint')}`}
            </figcaption>
          </div>
        </figure>
      )}

      <details className="group">
        <summary className="state-layer inline-flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-full px-3 text-label-lg text-primary">
          <Icon name="expand_more" className="transition-transform group-open:rotate-180" />
          {t('steps.details')}
        </summary>
        <div className="mt-3 space-y-4">
          <TextArea label={t('steps.hazard')} value={step.hazard} onChange={(hazard) => onChange({ hazard })} rows={2} lang={lang} />
          <TextArea
            label={t('steps.essential')}
            value={step.essential.join('\n')}
            onChange={(v) => onChange({ essential: v.split('\n') })}
            rows={2}
            lang={lang}
            helper={t('steps.essentialHint')}
          />
        </div>
      </details>
    </li>
  )
}
