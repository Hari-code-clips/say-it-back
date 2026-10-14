import type { Question, Rating, Step } from '../../api/types.ts'
import { useT } from '../../i18n/index.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { cx } from '../../ui/cx.ts'
import { ClipPlayer } from '../../ui/ClipPlayer.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { FlagChip } from '../../ui/VerdictChip.tsx'
import { VERDICT } from './verdict.ts'

interface Props {
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

/** One card per critical step: verdict first, then what the worker said (original + translation), then why. */
export function StepResultCard({ index, step, rating, asked, clips, supervisorTag, workerTag, workerName, supervisorName }: Props) {
  const t = useT()
  // A step with no rating was never asked about: treat it as "ask again", flagged not_asked.
  const verdict = rating?.verdict ?? 'unclear'
  const look = VERDICT[verdict]
  const flags = rating?.flags ?? ['not_asked']

  return (
    <li className="overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest">
      <div className={cx('flex items-center gap-3 px-4 py-3 sm:px-5', look.band)}>
        <Icon name={look.icon} filled className="text-[1.75rem]" />
        <span className="text-title-lg">{t(look.label)}</span>
        <span className="ml-auto text-label-lg">{t('result.stepN', { n: index + 1 })}</span>
      </div>

      <div className="space-y-4 p-4 sm:p-5">
        <div className="space-y-1">
          <h3 lang={supervisorTag} className="script-text text-title-md text-on-surface">
            {step.text}
          </h3>
          {step.hazard && (
            <p lang={supervisorTag} className="script-text text-body-md text-on-surface-variant">
              {t('result.hazard', { hazard: step.hazard })}
            </p>
          )}
        </div>

        {rating?.quote ? (
          <figure className="space-y-2 rounded-md bg-surface-container px-4 py-3">
            <figcaption className="text-label-lg text-on-surface-variant">{t('result.workerSaid', { lang: workerName })}</figcaption>
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
            <p className="rounded-md bg-surface-container px-4 py-3 text-body-lg text-on-surface-variant">
              {verdict === 'missed' ? t('result.noMention') : verdict === 'unclear' ? t('result.notClear') : t('result.noQuote')}
            </p>
          )
        )}

        {rating?.reason && (
          <p lang={supervisorTag} className={cx('script-text text-body-lg text-on-surface', !rating.quote && 'rounded-md bg-surface-container px-4 py-3')}>
            <span className="text-label-lg text-on-surface-variant">{t('result.why')} </span>
            {rating.reason}
          </p>
        )}

        {(flags.length > 0 || !step.speakable || (clips && asked.length > 0)) && (
          <div className="flex flex-wrap items-center gap-2">
            {!step.speakable && (
              <StatusChip tone="warning" icon="touch_app">
                {t('steps.notSpeakable')}
              </StatusChip>
            )}
            {flags.map((f) => (
              <FlagChip key={f} flag={f} />
            ))}
            {clips &&
              asked.map(({ question, number }) => {
                const blob = clips[question.id]
                return blob ? <ClipPlayer key={question.id} blob={blob} playLabel={t('result.play', { n: number })} stopLabel={t('result.stop')} /> : null
              })}
          </div>
        )}
      </div>
    </li>
  )
}
