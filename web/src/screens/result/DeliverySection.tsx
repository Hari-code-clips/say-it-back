/* Hallmark · component: "the voice did not keep to your script" · genre: modern-minimal · theme: design.md
 * One card with the neutral ink outline of a warning (amber is Ask again, and this is the cause, not a verdict), hairline-divided
 * rows: the header and what to do, then one row per part the voice got wrong. No fill, no card inside the card.
 * states: static; announced politely once when it appears.
 */
import type { CatalogLanguage, Round } from '../../api/types.ts'
import { useT } from '../../i18n/index.tsx'
import { approvedText, failedDeliveries, parseSegment, saidText } from '../../lib/delivery.ts'
import { Icon } from '../../ui/Icon.tsx'
import { issueSentences } from './deliveryText.ts'

interface Props {
  round: Round
  language?: CatalogLanguage
  workerTag: string
  workerName: string
}

/** Live mode: every part of the round the voice did not deliver as approved, in plain words, with what it said. */
export function DeliverySection({ round, language, workerTag, workerName }: Props) {
  const t = useT()
  const failed = failedDeliveries(round.delivery)
  if (failed.length === 0) return null
  const ids = round.script.questions.map((q) => q.id)
  return (
    <section aria-labelledby="delivery-title" role="status" className="divide-y divide-outline-variant overflow-hidden rounded-lg border-[1.5px] border-on-surface bg-surface-container-lowest text-on-surface">
      <div className="flex gap-3 px-4 py-3 sm:px-5">
        <Icon name="record_voice_over" filled className="mt-0.5 text-[1.5rem]" />
        <div className="min-w-0 space-y-1">
          <h2 id="delivery-title" className="text-title-md">
            {t('delivery.title')}
          </h2>
          <p className="text-body-md text-on-surface-variant">{t('delivery.hint')}</p>
        </div>
      </div>
      <ul className="divide-y divide-outline-variant">
        {failed.map((check) => {
          const ref = parseSegment(check.segment, ids)
          const said = saidText(round, check)
          const approved = approvedText(round.script, ref)
          return (
            <li key={check.segment} className="space-y-2 px-4 py-3 sm:px-5">
              {issueSentences(t, check, round, language).map((line) => (
                <p key={line} className="text-title-md">
                  {line}
                </p>
              ))}
              {said !== undefined && said !== '' && (
                <div className="space-y-0.5">
                  <p className="text-label-lg text-on-surface-variant">{t('delivery.said', { lang: workerName })}</p>
                  <p lang={workerTag} className="script-text text-body-lg">
                    “{said}”
                  </p>
                </div>
              )}
              {approved && (
                <div className="space-y-0.5">
                  <p className="text-label-lg text-on-surface-variant">{t('delivery.script')}</p>
                  <p lang={workerTag} className="script-text whitespace-pre-line text-body-md text-on-surface-variant">
                    {approved}
                  </p>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
