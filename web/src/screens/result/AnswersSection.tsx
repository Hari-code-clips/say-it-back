/* Hallmark · component: what the worker said, question by question · genre: modern-minimal · theme: design.md
 * Sits inside the result's disclosure, which is the one card: rows divided by hairlines, no card per question and no tinted box.
 * states: static rows; the clip button is a Button (all its states).
 */
import type { Briefing, Round } from '../../api/types.ts'
import { useT } from '../../i18n/index.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { ClipPlayer } from '../../ui/ClipPlayer.tsx'
import { FlagChip } from '../../ui/VerdictChip.tsx'
import { transcriptNote } from './verdict.ts'

interface Props {
  briefing: Briefing
  round: Round
  clips: Record<string, Blob> | undefined
  supervisorTag: string
  workerTag: string
  workerName: string
  supervisorName: string
  /** Native name of a detected language code, for the mismatch chip. */
  detectedName: (code: string) => string
}

/** What the worker said, question by question: original script, translation, and the clip. */
export function AnswersSection({ briefing, round, clips, supervisorTag, workerTag, workerName, supervisorName, detectedName }: Props) {
  const t = useT()
  return (
    <ul className="divide-y divide-outline-variant border-t border-outline-variant">
      {round.script.questions.map((q, i) => {
        const tr = round.transcripts.find((x) => x.questionId === q.id)
        const blob = clips?.[q.id]
        const mismatch = tr && tr.detectedLang !== briefing.workerLang && tr.detectedLang !== 'none'
        const sample = round.sampleAnswers?.includes(q.id)
        return (
          <li key={q.id} className="space-y-3 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="flex flex-wrap items-center gap-2 text-label-lg text-on-surface-variant">
                  {t('result.question', { n: i + 1 })}
                  {sample && (
                    <StatusChip tone="primary" icon="graphic_eq">
                      {t('result.sample')}
                    </StatusChip>
                  )}
                </p>
                <p lang={workerTag} className="script-text text-title-md">
                  {q.text}
                </p>
                <p lang={supervisorTag} className="script-text text-body-md text-on-surface-variant">
                  {q.backTranslation}
                </p>
              </div>
              {blob && <ClipPlayer blob={blob} playLabel={t('result.play', { n: i + 1 })} stopLabel={t('result.stop')} />}
            </div>

            {tr ? (
              <div className="space-y-2">
                <p className="text-label-lg text-on-surface-variant">{t('result.workerSaid', { lang: workerName })}</p>
                {transcriptNote(tr.flags) ? (
                  // v0.5.1: the model refused the clip: there is no transcript, and "No speech" would not be true.
                  <p className="text-body-lg text-on-surface">{t(transcriptNote(tr.flags)!)}</p>
                ) : tr.original ? (
                  <p lang={workerTag} className="script-text text-title-lg">
                    {tr.original}
                  </p>
                ) : (
                  <p className="text-body-lg text-on-surface-variant">{t('result.noSpeech')}</p>
                )}
                {tr.translation && (
                  <p lang={supervisorTag} className="script-text text-body-lg text-on-surface-variant">
                    <span className="text-label-lg">{t('result.inLang', { lang: supervisorName })}: </span>
                    {tr.translation}
                  </p>
                )}
                {(tr.flags.length > 0 || mismatch) && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {mismatch && (
                      <StatusChip tone="warning" icon="warning">
                        {t('result.detected', { lang: detectedName(tr.detectedLang) })}
                      </StatusChip>
                    )}
                    {tr.flags.map((f) => (
                      <FlagChip key={f} flag={f} />
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-body-md text-on-surface-variant">{t('result.noTranscript')}</p>
            )}
          </li>
        )
      })}
    </ul>
  )
}
