/* Hallmark · component: one editable critical step · genre: modern-minimal · theme: design.md
 * One card, hairline-divided rows: tags, the step's text, the SOP's own words (plain text with a quote mark, no tinted box), then one
 * footer row with the detail disclosure and the remove button. A conflict is a 2 px red border and a chip, not a tinted card.
 * `readOnly` (security fixes A, H2: a signed-off library version's step): the same card with the text as plain text under its
 * label, no remove button, and the disclosure showing the hazard and key points as text.
 * states: default · hover/focus/active (the controls inside) · disabled (the whole fieldset while a request runs) · error (empty text
 *         after blur; a conflict) · loading/success n/a (the screen owns the requests).
 */
import { useId, useState } from 'react'
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
  /** A signed-off step: shown, never edited or removed. */
  readOnly?: boolean
}

/** One editable critical step. Source, conflicts and voice-checkability are shown as labelled chips. */
export function StepCard({ index, step, conflicts, sopId, lang, showTextError, onChange, onBlurText, onRemove, canRemove, readOnly = false }: StepCardProps) {
  const t = useT()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const panelId = useId()
  const hasConflict = conflicts.length > 0
  const tags = step.source === 'sop' || hasConflict || !step.speakable
  return (
    <li
      id={`step-${step.id}`}
      className={cx(
        'scroll-mt-24 divide-y divide-outline-variant overflow-hidden rounded-lg bg-surface-container-lowest',
        hasConflict ? 'border-2 border-error' : 'border border-outline-variant',
      )}
    >
      {tags && (
        <div className="flex flex-wrap gap-2 px-4 py-3 sm:px-5">
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

      {readOnly ? (
        <div className="space-y-2 px-4 py-4 sm:px-5">
          <p className="text-label-lg text-on-surface-variant">{t('steps.stepLabel', { n: index + 1 })}</p>
          <p lang={lang} className="script-text text-body-lg text-on-surface">
            {step.text}
          </p>
        </div>
      ) : (
        <div className="px-4 pt-4 sm:px-5">
          <TextArea
            label={t('steps.stepLabel', { n: index + 1 })}
            value={step.text}
            onChange={(text) => onChange({ text })}
            onBlur={onBlurText}
            rows={2}
            lang={lang}
            error={showTextError && !step.text.trim() ? t('steps.textRequired') : undefined}
          />
        </div>
      )}

      {step.sopQuote && (
        <figure className="flex gap-3 px-4 py-3 sm:px-5">
          <Icon name="format_quote" className="mt-0.5 text-on-surface-variant" />
          <div className="min-w-0 space-y-1">
            <blockquote lang={lang} className="script-text text-body-md text-on-surface">
              {step.sopQuote}
            </blockquote>
            <figcaption className="text-body-md text-on-surface-variant">
              {t('steps.sopQuote', { sop: sopId })}
              {step.source === 'sop' && !readOnly && ` ${t('steps.sopOnlyHint')}`}
            </figcaption>
          </div>
        </figure>
      )}

      <div className="flex items-center justify-between gap-2 px-2 py-1 sm:px-3">
        <button
          type="button"
          aria-expanded={detailsOpen}
          aria-controls={panelId}
          onClick={() => setDetailsOpen((open) => !open)}
          className="state-layer inline-flex min-h-12 items-center gap-2 rounded-md px-3 text-label-lg text-on-surface"
        >
          <Icon name="expand_more" className={cx('transition-transform', detailsOpen && 'rotate-180')} />
          {t('steps.details')}
        </button>
        {!readOnly && <IconButton icon="delete" label={t('steps.remove', { n: index + 1 })} onClick={onRemove} disabled={!canRemove} />}
      </div>

      {detailsOpen && readOnly && (
        <dl id={panelId} className="animate-fade-in space-y-4 px-4 py-4 sm:px-5">
          {step.hazard && (
            <div className="space-y-1">
              <dt className="text-label-lg text-on-surface-variant">{t('steps.hazard')}</dt>
              <dd lang={lang} className="script-text text-body-lg text-on-surface">
                {step.hazard}
              </dd>
            </div>
          )}
          {step.essential.length > 0 && (
            <div className="space-y-1">
              <dt className="text-label-lg text-on-surface-variant">{t('steps.essential')}</dt>
              {step.essential.map((e, i) => (
                <dd key={i} lang={lang} className="script-text text-body-lg text-on-surface">
                  {e}
                </dd>
              ))}
            </div>
          )}
        </dl>
      )}
      {detailsOpen && !readOnly && (
        <div id={panelId} className="animate-fade-in space-y-4 px-4 pt-4 sm:px-5">
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
      )}
    </li>
  )
}
