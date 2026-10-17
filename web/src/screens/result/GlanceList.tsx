/* Hallmark · component: "At a glance" list · genre: modern-minimal · theme: design.md
 * One row per step in one hairline card: the verdict, the step, the worker's own words, and the worker's audio beside the verdict it
 * supports (build-notes/24 topic 5: evidence next to the AI's verdict is what keeps a supervisor from rubber-stamping it).
 * From 600 px the verdict, the words and the audio line up in three columns; on a phone the audio sits on the verdict's line.
 * states: static rows; the clip buttons are Buttons (all their states).
 */
import type { Round, Step } from '../../api/types.ts'
import { useT } from '../../i18n/index.tsx'
import { ClipPlayer } from '../../ui/ClipPlayer.tsx'
import { VerdictChip } from '../../ui/VerdictChip.tsx'
import { SampleTag } from './SampleTag.tsx'
import { askedAbout, quoteLine, verdictOf } from './verdict.ts'

interface Props {
  steps: Step[]
  round: Round
  clips: Record<string, Blob> | undefined
  /** Step ids said back only by a stored sample answer. */
  bySample: ReadonlySet<string>
  supervisorTag: string
  workerTag: string
}

export function GlanceList({ steps, round, clips, bySample, supervisorTag, workerTag }: Props) {
  const t = useT()
  return (
    <ol className="divide-y divide-outline-variant overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest sm:grid sm:grid-cols-[max-content_minmax(0,1fr)_max-content]">
      {steps.map((s) => {
        // The worker's own words beside the verdict: two lines here, the whole quote is on the step's card below.
        const quote = quoteLine(round.ratings.find((r) => r.stepId === s.id))
        const players = clips ? askedAbout(round.script.questions, s.id).flatMap(({ question, number }) => (clips[question.id] ? [{ id: question.id, blob: clips[question.id]!, number }] : [])) : []
        return (
          <li key={s.id} className="flex flex-col gap-2 px-4 py-3 sm:col-span-3 sm:grid sm:grid-cols-subgrid sm:items-start sm:gap-x-4 sm:px-5">
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 sm:contents">
              <div className="sm:pt-0.5">
                <VerdictChip verdict={verdictOf(round.ratings, s.id)} />
              </div>
              {players.length > 0 && (
                <div className="flex flex-wrap gap-2 sm:order-3">
                  {players.map((p) => (
                    <ClipPlayer key={p.id} blob={p.blob} playLabel={t('result.play', { n: p.number })} stopLabel={t('result.stop')} />
                  ))}
                </div>
              )}
            </div>
            <div className="min-w-0 space-y-1 sm:order-2 sm:pt-1">
              <p lang={supervisorTag} className="script-text text-body-lg text-on-surface">
                {s.text}
              </p>
              {quote && (
                <p lang={quote.translated ? supervisorTag : workerTag} className="script-text line-clamp-2 text-body-md text-on-surface-variant">
                  “{quote.text}”
                </p>
              )}
              {bySample.has(s.id) && <SampleTag className="pt-1" />}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
