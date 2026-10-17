/* Hallmark · component: start from a library version · genre: modern-minimal · theme: design.md
 * Under the task picker, compact so the permit block stays near the first screen: the "SOP library" link and, only when this task has
 * a signed-off library version in the supervisor's language, one line of choice chips (the same control as the language pickers):
 * "Gemini, from the SOP" (the default, today's path) or one chip per signed-off version. A version that stops being on offer (site,
 * task or language changed) falls back to the SOP, so a stale choice is never sent.
 * states: loading / error (no chips: the SOP path still works) · default · selected (blue chip + check) · focus (ring).
 */
import { useEffect } from 'react'
import { Link } from 'wouter'
import { api } from '../../api/endpoints.ts'
import type { Lang, SiteId, SopRef } from '../../api/types.ts'
import { useT } from '../../i18n/index.tsx'
import { useAsync } from '../../lib/useAsync.ts'
import { ChoiceChips } from '../../ui/Choice.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { offeredVersions, refOf, stillOffered } from '../library/libraryModel.ts'

interface Props {
  siteId: SiteId
  taskId: string
  lang: Lang
  value: SopRef | null
  onChange: (ref: SopRef | null) => void
}

const SOP = 'sop'
const key = (ref: SopRef): string => `${ref.sopId}#${ref.version}`

export function LibraryPick({ siteId, taskId, lang, value, onChange }: Props) {
  const t = useT()
  const { data } = useAsync(() => api.listSops(siteId), [siteId])
  const offers = data ? offeredVersions(data.items, taskId, lang) : []
  const kept = stillOffered(offers, value)

  useEffect(() => {
    if (data && value && !kept) onChange(null)
  }, [data, value, kept, onChange])

  const label = t('start.library.label')
  return (
    <div className="space-y-2 pt-1">
      <div className="flex flex-wrap items-center justify-between gap-x-4">
        {offers.length > 0 && <p className="text-title-sm text-on-surface-variant">{label}</p>}
        <Link href={`/library/${siteId}`} className="inline-flex min-h-12 items-center gap-2 text-title-sm text-primary underline-offset-4 hover:underline">
          <Icon name="description" />
          {t('library.link')}
        </Link>
      </div>
      {offers.length > 0 && (
        <>
          <ChoiceChips<string>
            label={label}
            value={kept ? key(kept) : SOP}
            onChange={(chosen) => onChange(offers.map(refOf).find((ref) => key(ref) === chosen) ?? null)}
            options={[
              { value: SOP, label: t('start.library.catalog') },
              ...offers.map((offer) => ({
                value: key(refOf(offer)),
                label: t('start.library.version', { id: offer.entry.id, n: offer.version.number }),
              })),
            ]}
          />
          <p className="text-body-md text-on-surface-variant">{t('start.library.hint')}</p>
        </>
      )}
    </div>
  )
}
