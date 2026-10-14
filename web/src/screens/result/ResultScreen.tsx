import { useEffect } from 'react'
import { useLocation } from 'wouter'
import { bcp47, langNative, useCatalog } from '../../api/catalog.tsx'
import type { Lang } from '../../api/types.ts'
import { clipKey, getClips } from '../../audio/clips.ts'
import { useBriefing } from '../../flow/BriefingContext.tsx'
import { FlowFrame } from '../../flow/FlowFrame.tsx'
import { MAX_ROUNDS, canReexplain, latestRound, openSteps } from '../../flow/phases.ts'
import { UnexpectedState } from '../../flow/UnexpectedState.tsx'
import { useLangName, useT } from '../../i18n/index.tsx'
import { deliveryIssues } from '../../lib/coverage.ts'
import { Button } from '../../ui/Button.tsx'
import { Section } from '../../ui/Card.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { Banner } from '../../ui/Feedback.tsx'
import { useFeedback } from '../../ui/FeedbackProvider.tsx'
import { VerdictChip } from '../../ui/VerdictChip.tsx'
import { AnswersSection } from './AnswersSection.tsx'
import { StepResultCard } from './StepResultCard.tsx'
import { VERDICT, VERDICT_ORDER } from './verdict.ts'

export function ResultScreen() {
  const t = useT()
  const feedback = useFeedback()
  const [, navigate] = useLocation()
  const { briefing } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const round = latestRound(briefing)
  const open = openSteps(briefing)

  // Announce the outcome once per round, in words (not just colour).
  const roundN = round?.n
  useEffect(() => {
    if (roundN) feedback.announce(t('result.announce', { n: roundN, open: open.length }))
  }, [roundN]) // once per round, not on every re-render

  if (!round) return <UnexpectedState />

  const supervisorTag = bcp47(catalog, briefing.supervisorLang, briefing.siteId)
  const workerTag = bcp47(catalog, briefing.workerLang, briefing.siteId)
  const workerName = langName(briefing.workerLang)
  const supervisorName = langName(briefing.supervisorLang)
  const clips = getClips(clipKey(briefing.id, round.n))
  const inScope = briefing.steps.filter((s) => round.stepIds.includes(s.id))
  const earlier = briefing.steps.filter((s) => !round.stepIds.includes(s.id))
  const stepIndex = (id: string) => briefing.steps.findIndex((s) => s.id === id)
  const counts = VERDICT_ORDER.map((v) => ({ v, n: round.ratings.filter((r) => r.verdict === v && round.stepIds.includes(r.stepId)).length }))
  const delivery = deliveryIssues(round.delivery)
  const reexplain = canReexplain(briefing)
  const exhausted = open.length > 0 && briefing.rounds.length >= MAX_ROUNDS

  const decide = () => navigate(`/b/${briefing.id}/decision`)

  return (
    <FlowFrame
      step="result"
      wide
      eyebrow={t('script.round', { n: round.n, max: MAX_ROUNDS })}
      title={t('result.title', { n: round.n })}
      subtitle={t('result.subtitle')}
      primary={
        reexplain ? (
          <Button size="lg" icon="replay" onClick={() => navigate(`/b/${briefing.id}/reexplain`)}>
            {t('result.reexplain', { n: open.length })}
          </Button>
        ) : (
          <Button size="lg" icon="gavel" onClick={decide}>
            {t('result.decide')}
          </Button>
        )
      }
      secondary={
        reexplain ? (
          <Button size="lg" variant="outlined" icon="gavel" onClick={decide}>
            {t('result.decideNow')}
          </Button>
        ) : undefined
      }
    >
      <div role="group" aria-label={t('result.counts')} className="flex flex-wrap gap-2">
        {counts.map(({ v, n }) =>
          n > 0 ? (
            <StatusChip key={v} tone={VERDICT[v].tone} icon={VERDICT[v].icon} className="text-title-sm">
              {t(VERDICT[v].label)} · {n}
            </StatusChip>
          ) : null,
        )}
        {round.mode && <StatusChip icon={round.mode === 'live' ? 'record_voice_over' : 'volume_up'}>{t(round.mode === 'live' ? 'brief.mode.live' : 'brief.mode.turn')}</StatusChip>}
      </div>

      {exhausted && (
        <Banner tone="warning" title={t('result.exhausted')} live="polite">
          {t('result.exhaustedHint', { max: MAX_ROUNDS })}
        </Banner>
      )}

      {delivery.length > 0 && (
        <Banner tone="warning" title={t('result.deliveryTitle')} live="polite">
          <p>{t('result.deliveryHint')}</p>
          <p className="mt-1 flex flex-wrap gap-2">
            {delivery.map((d) => (
              <StatusChip key={d.segment} tone="warning">
                {d.segment} · {Math.round(d.similarity * 100)}%
              </StatusChip>
            ))}
          </p>
        </Banner>
      )}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_23rem] lg:gap-10">
        <Section title={t('result.steps')} id="result-steps" className="order-1">
          <ol className="space-y-4">
            {inScope.map((s) => (
              <StepResultCard
                key={s.id}
                index={stepIndex(s.id)}
                step={s}
                rating={round.ratings.find((r) => r.stepId === s.id)}
                asked={round.script.questions.flatMap((q, i) => (q.stepIds.includes(s.id) ? [{ question: q, number: i + 1 }] : []))}
                clips={clips}
                supervisorTag={supervisorTag}
                workerTag={workerTag}
                workerName={workerName}
                supervisorName={supervisorName}
              />
            ))}
          </ol>
          {earlier.length > 0 && (
            <div className="space-y-2 pt-2">
              <h3 className="text-title-md text-on-surface-variant">{t('result.earlier')}</h3>
              <ul className="space-y-2">
                {earlier.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 rounded-md bg-surface-container-low px-4 py-3">
                    <VerdictChip verdict={briefing.latestVerdicts[s.id] ?? 'unclear'} />
                    <span lang={supervisorTag} className="script-text min-w-0 text-body-lg">
                      {s.text}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Section>

        <Section title={t('result.answers')} hint={t('result.answersHint', { lang: langNative(catalog, briefing.workerLang) })} id="result-answers" className="order-2">
          <AnswersSection
            briefing={briefing}
            round={round}
            clips={clips}
            supervisorTag={supervisorTag}
            workerTag={workerTag}
            workerName={workerName}
            supervisorName={supervisorName}
            detectedName={(code) => (code === 'other' ? t('result.otherLang') : langName(code as Lang))}
          />
        </Section>
      </div>
    </FlowFrame>
  )
}
