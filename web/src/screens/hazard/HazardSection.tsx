/* Hallmark · component: reported-problem card + compact banner + acknowledgement · genre: modern-minimal · theme: design.md
 * One containment layer: a card is a hairline (hazard red, 2 px, while the problem is open) with hairline-divided rows, no tinted
 * box and no side stripe inside it. The banner is the short form: what happened, what is locked, and one button that jumps to the note.
 * states: default · hover · focus · active · disabled (note too short) · loading (recording the note) · error (refused) ·
 * success (acknowledged: the card shows what was done)
 */
import { useState } from 'react'
import { bcp47, useCatalog } from '../../api/catalog.tsx'
import { ApiError } from '../../api/client.ts'
import { api } from '../../api/endpoints.ts'
import type { Briefing, Hazard } from '../../api/types.ts'
import { openHazards } from '../../flow/phases.ts'
import { useLangName, useT, useUiLang } from '../../i18n/index.tsx'
import { apiErrorText } from '../../lib/apiError.ts'
import { formatDateTime } from '../../lib/format.ts'
import { Button } from '../../ui/Button.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { cx } from '../../ui/cx.ts'
import { Banner } from '../../ui/Feedback.tsx'
import { useFeedback } from '../../ui/FeedbackProvider.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { TextArea } from '../../ui/TextField.tsx'

/** The contract's minimum for a note of what was done (endpoint 22). */
export const NOTE_MIN = 5

/** The section's anchor: the banner's button jumps here. */
export const HAZARDS_ID = 'hazards'

/**
 * Scrolls the first note that still needs writing into view and puts the cursor in it. With none open it scrolls to the section.
 * The banner on the result and the decision calls it; the form itself sits further down the page, not on top of it.
 */
export function jumpToHazardNote(): void {
  const root = document.getElementById(HAZARDS_ID)
  const field = root?.querySelector<HTMLTextAreaElement>('textarea:not(:disabled)')
  const target = field ?? root
  if (!target) return
  target.scrollIntoView({ block: 'center' })
  field?.focus({ preventScroll: true })
}

interface CardProps {
  briefing: Briefing
  hazard: Hazard
  number: number
  /** Show the acknowledgement form (the result and decision screens); the record only reads. */
  editable: boolean
  onAcked: (b: Briefing) => void
}

function HazardCard({ briefing, hazard, number, editable, onAcked }: CardProps) {
  const t = useT()
  const { lang: uiLang } = useUiLang()
  const feedback = useFeedback()
  const langName = useLangName()
  const { data: catalog } = useCatalog()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const supervisorTag = bcp47(catalog, briefing.supervisorLang, briefing.siteId)
  const workerTag = bcp47(catalog, briefing.workerLang, briefing.siteId)
  const open = !hazard.ack
  const noteOk = note.trim().length >= NOTE_MIN
  const headingId = `hazard-${hazard.id}`

  const acknowledge = async () => {
    if (!noteOk) return
    setBusy(true)
    setError(null)
    try {
      const b = await api.ackHazard(briefing.id, hazard.id, { note: note.trim() })
      onAcked(b)
      feedback.announce(t('hazard.ackDone', { n: number }))
    } catch (e) {
      setBusy(false)
      if (e instanceof ApiError && e.code === 'invalid_state') {
        // Already acknowledged (a lost response, or another tab): show what the server holds.
        onAcked(await api.getBriefing(briefing.id).catch(() => briefing))
        return
      }
      setError(apiErrorText(t, e))
    }
  }

  return (
    <li
      aria-labelledby={headingId}
      className={cx('divide-y divide-outline-variant overflow-hidden rounded-lg bg-surface-container-lowest', open ? 'border-2 border-error' : 'border border-outline-variant')}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:px-5">
        <Icon name="report" filled className={cx('text-[1.75rem]', open ? 'text-error' : 'text-on-surface')} />
        <h3 id={headingId} className="min-w-0 grow text-title-lg">
          {t('hazard.card', { n: number })}
        </h3>
        {open ? (
          <StatusChip tone="strong-error" icon="warning">
            {t('hazard.open')}
          </StatusChip>
        ) : (
          <StatusChip tone="primary" icon="task_alt">
            {t('hazard.acked')}
          </StatusChip>
        )}
      </div>

      <div className="space-y-2 px-4 py-3 sm:px-5">
        <p className="text-body-md text-on-surface-variant">
          {hazard.round ? t('hazard.during', { n: hazard.round, time: formatDateTime(hazard.raisedAt, uiLang) }) : formatDateTime(hazard.raisedAt, uiLang)}
        </p>
        {hazard.kind === 'tap' ? (
          <p className="text-body-lg text-on-surface">{t('hazard.tap')}</p>
        ) : hazard.original ? (
          <figure className="space-y-2">
            {hazard.translation && (
              <p lang={supervisorTag} className="script-text text-title-lg text-on-surface">
                “{hazard.translation}”
              </p>
            )}
            <figcaption className="text-label-lg text-on-surface-variant">{t('hazard.said', { lang: langName(briefing.workerLang) })}</figcaption>
            <blockquote lang={workerTag} className="script-text text-body-lg text-on-surface-variant">
              “{hazard.original}”
            </blockquote>
          </figure>
        ) : (
          <p className="text-body-lg text-on-surface">{t('hazard.noWords')}</p>
        )}
      </div>

      {hazard.ack ? (
        <div className="space-y-1 px-4 py-3 sm:px-5">
          <p className="text-label-lg text-on-surface-variant">
            {hazard.ack.by
              ? t('hazard.ackedBy', { by: hazard.ack.by, time: formatDateTime(hazard.ack.at, uiLang) })
              : t('hazard.ackedAt', { time: formatDateTime(hazard.ack.at, uiLang) })}
          </p>
          <p lang={supervisorTag} className="script-text text-body-lg text-on-surface">
            {hazard.ack.note}
          </p>
        </div>
      ) : (
        editable && (
          <div className="space-y-3 px-4 py-4 sm:px-5">
            <TextArea
              label={t('hazard.noteLabel')}
              value={note}
              onChange={(v) => {
                setNote(v)
                setError(null)
              }}
              rows={2}
              maxLength={500}
              lang={supervisorTag}
              disabled={busy}
              helper={t('hazard.noteHint', { min: NOTE_MIN })}
              error={note.length > 0 && !noteOk ? t('hazard.noteShort', { min: NOTE_MIN }) : undefined}
            />
            {error && (
              <p role="alert" className="flex items-start gap-2 text-body-md text-error">
                <Icon name="error" filled className="mt-0.5 text-[1.125rem]" />
                {error}
              </p>
            )}
            <Button icon="task_alt" disabled={!noteOk} busy={busy} onClick={() => void acknowledge()}>
              {t('hazard.ack')}
            </Button>
          </div>
        )
      )}
    </li>
  )
}

interface SectionProps {
  briefing: Briefing
  editable: boolean
  onAcked?: (b: Briefing) => void
  className?: string
}

/** Every problem the worker reported, oldest first. Nothing renders when there are none. */
export function HazardSection({ briefing, editable, onAcked, className }: SectionProps) {
  const t = useT()
  const hazards = briefing.hazards ?? []
  if (hazards.length === 0) return null
  const open = openHazards(briefing).length
  return (
    <section id={HAZARDS_ID} aria-labelledby="hazards-title" className={cx('scroll-mt-20 space-y-3', className)}>
      <div className="space-y-1">
        <h2 id="hazards-title" className="flex items-center gap-2 text-title-lg text-on-surface">
          {t('hazard.title', { n: hazards.length })}
        </h2>
        {editable && open > 0 && <p className="text-body-md text-on-surface-variant">{t('hazard.hint')}</p>}
      </div>
      <ol className="space-y-4">
        {hazards.map((h, i) => (
          <HazardCard key={h.id} briefing={briefing} hazard={h} number={i + 1} editable={editable} onAcked={onAcked ?? (() => undefined)} />
        ))}
      </ol>
    </section>
  )
}

/**
 * The short form of an open report, for the top of the result and the decision: it says what happened and what is locked, and
 * its one button goes to the note. Nothing renders once every report has a note.
 */
export function HazardBanner({ briefing }: { briefing: Briefing }) {
  const t = useT()
  const n = openHazards(briefing).length
  if (n === 0) return null
  return (
    <Banner
      tone="error"
      icon="report"
      title={n === 1 ? t('hazard.banner') : t('hazard.bannerMany', { n })}
      action={
        <Button variant="outlined" icon="expand_more" onClick={jumpToHazardNote} className="border-on-error-container! text-on-error-container!">
          {t('hazard.bannerAction')}
        </Button>
      }
    />
  )
}
