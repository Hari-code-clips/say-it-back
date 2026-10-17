/* Hallmark · component: one critical step's result · genre: modern-minimal · theme: design.md
 * One card, hairline-divided rows: the verdict (word + mark + treatment) and its evidence, then the step, then what the worker said
 * and the audio next to it, then why, then flags. No tinted box inside the card, no band, no side stripe.
 * states: static card; the clip buttons are Buttons (all their states); the rest is text.
 */
import type { Question, Rating, Step } from '../../api/types.ts'
import { useT } from '../../i18n/index.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { ClipPlayer } from '../../ui/ClipPlayer.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { FlagChip, VerdictChip } from '../../ui/VerdictChip.tsx'
import { SampleTag } from './SampleTag.tsx'
import { disagreementHint, ratingVerdict, transcriptNote } from './verdict.ts'

interface Props {
  /** v0.4 review: the step was said back only by a stored sample answer (it counts as open for the decision). */
  sampleCovered?: boolean
  /** 16 Oct: the quote is from a stored sample answer (any verdict), so it is never captioned as the worker's words. */
  quoteBySample?: boolean
  /** v0.4: why the voice turned this step into "Ask again" (guard rule 8), one plain sentence per cause. */
  deliveryCauses?: string[]
  index: number
  step: Step
  rating: Rating | undefined
  /** Questions of this round that check the step, with their number in the round. */
  asked: { question: Question; number: number }[]
  clips: Record<string, Blob> | undefined
  supervisorTag: string
  workerTag: string
  workerName: string
  supervisorName: string
}

/** One card per critical step: verdict first, then what the worker said (original + translation) with its audio, then why. */
export function StepResultCard({ sampleCovered, quoteBySample, deliveryCauses, index, step, rating, asked, clips, supervisorTag, workerTag, workerName, supervisorName }: Props) {
  const t = useT()
  // A step with no rating was never asked about: treat it as "ask again", flagged not_asked.
  const verdict = ratingVerdict(rating)
  const flags = rating?.flags ?? ['not_asked']
  const hint = disagreementHint(verdict, flags)
  const players = clips ? asked.flatMap(({ question, number }) => (clips[question.id] ? [{ id: question.id, blob: clips[question.id]!, number }] : [])) : []
  const chips = flags.length > 0 || !step.speakable

  return (
    <li className="divide-y divide-outline-variant overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-3 sm:px-5">
        <VerdictChip verdict={verdict} />
        <span className="text-label-lg tabular-nums text-on-surface-variant">{t('result.stepN', { n: index + 1 })}</span>
      </div>

      <div className="space-y-1 px-4 py-3 sm:px-5">
        <h3 lang={supervisorTag} className="script-text text-title-md text-on-surface">
          {step.text}
        </h3>
        {step.hazard && (
          <p lang={supervisorTag} className="script-text text-body-md text-on-surface-variant">
            {t('result.hazard', { hazard: step.hazard })}
          </p>
        )}
        {sampleCovered && <SampleTag className="pt-1" />}
      </div>

      <div className="space-y-3 px-4 py-3 sm:px-5">
        {rating?.quote ? (
          <figure className="space-y-2">
            <figcaption className="text-label-lg text-on-surface-variant">{t(quoteBySample ? 'result.sampleSaid' : 'result.workerSaid', { lang: workerName })}</figcaption>
            <blockquote lang={workerTag} className="script-text text-title-lg text-on-surface">
              “{rating.quote}”
            </blockquote>
            {rating.quoteTranslation && (
              <p lang={supervisorTag} className="script-text text-body-lg text-on-surface-variant">
                <span className="text-label-lg">{t('result.inLang', { lang: supervisorName })}: </span>“{rating.quoteTranslation}”
              </p>
            )}
          </figure>
        ) : (
          // Nothing quotable: say so once. The judge's own reason (below) is more specific than the generic line.
          !rating?.reason && (
            <p className="text-body-lg text-on-surface-variant">
              {transcriptNote(flags) ? t(transcriptNote(flags)!) : verdict === 'missed' ? t('result.noMention') : verdict === 'unclear' ? t('result.notClear') : t('result.noQuote')}
            </p>
          )
        )}
        {players.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {players.map((p) => (
              <ClipPlayer key={p.id} blob={p.blob} playLabel={t('result.play', { n: p.number })} stopLabel={t('result.stop')} />
            ))}
          </div>
        )}
      </div>

      {(rating?.reason || hint) && (
        <div className="space-y-2 px-4 py-3 sm:px-5">
          {rating?.reason && (
            <p lang={supervisorTag} className="script-text text-body-lg text-on-surface">
              <span className="text-label-lg text-on-surface-variant">{t('result.why')} </span>
              {rating.reason}
            </p>
          )}
          {hint && (
            <p className="flex items-start gap-2 text-body-lg text-on-surface">
              <Icon name="info" className="mt-0.5 text-[1.25rem] text-on-surface-variant" />
              <span className="min-w-0">{t(hint)}</span>
            </p>
          )}
        </div>
      )}

      {flags.includes('delivery_mismatch') && (
        <div className="flex gap-3 px-4 py-3 sm:px-5">
          <Icon name="record_voice_over" className="mt-0.5 text-[1.25rem] text-on-surface-variant" />
          <div className="min-w-0 space-y-1 text-body-lg text-on-surface">
            <p className="text-title-sm">{t('result.deliveryWhy')}</p>
            {(deliveryCauses?.length ? deliveryCauses : [t('result.deliveryWhyGeneric')]).map((line) => (
              <p key={line}>{line}</p>
            ))}
            <p className="text-body-md text-on-surface-variant">{t('result.deliveryWhyHint')}</p>
          </div>
        </div>
      )}

      {chips && (
        <div className="flex flex-wrap items-center gap-2 px-4 py-3 sm:px-5">
          {!step.speakable && (
            <StatusChip tone="warning" icon="touch_app">
              {t('steps.notSpeakable')}
            </StatusChip>
          )}
          {flags.map((f) => (
            <FlagChip key={f} flag={f} />
          ))}
        </div>
      )}
    </li>
  )
}
