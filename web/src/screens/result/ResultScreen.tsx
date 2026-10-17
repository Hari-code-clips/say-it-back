/* Hallmark · screen: result · genre: modern-minimal · macrostructure: Workbench (hairline rows, one sticky bottom bar) · theme: design.md
 * Order: a reported problem as one banner (it jumps to the note), "At a glance" with the worker's audio beside each verdict, then the
 * step details. Re-explain and Decide are the sticky bar's two actions on every round; nothing sits behind it (--sib-bar-h).
 * states: loading n/a (the briefing is loaded by the route); empty -> UnexpectedState; error n/a (no request here).
 */
import { useEffect } from 'react'
import { useLocation } from 'wouter'
import { bcp47, langNative, useCatalog } from '../../api/catalog.tsx'
import type { Lang } from '../../api/types.ts'
import { clipKey, getClips } from '../../audio/clips.ts'
import { useBriefing } from '../../flow/BriefingContext.tsx'
import { FlowFrame } from '../../flow/FlowFrame.tsx'
import { MAX_ROUNDS, latestRound, openHazards, openSteps } from '../../flow/phases.ts'
import { UnexpectedState } from '../../flow/UnexpectedState.tsx'
import { useLangName, useT } from '../../i18n/index.tsx'
import { causedEarlier, deliveryCauses } from '../../lib/delivery.ts'
import { quoteFromSample, sampleCoveredIds } from '../../lib/sampleCovered.ts'
import { Button } from '../../ui/Button.tsx'
import { Card, RowList, Section } from '../../ui/Card.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { Banner } from '../../ui/Feedback.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { useFeedback } from '../../ui/FeedbackProvider.tsx'
import { HazardBanner, HazardSection } from '../hazard/HazardSection.tsx'
import { AnswersSection } from './AnswersSection.tsx'
import { DeliverySection } from './DeliverySection.tsx'
import { issueSentences } from './deliveryText.ts'
import { resultBar } from './gates.ts'
import { GlanceList } from './GlanceList.tsx'
import { ModelProvenance } from './ModelProvenance.tsx'
import { StepRow } from './StepRow.tsx'
import { StepResultCard } from './StepResultCard.tsx'
import { askedAbout } from './verdict.ts'

export function ResultScreen() {
  const t = useT()
  const feedback = useFeedback()
  const [, navigate] = useLocation()
  const { briefing, setBriefing } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const round = latestRound(briefing)
  const open = openSteps(briefing)

  // Announce the outcome once per round, in words (not just colour).
  const roundN = round?.n
  const reported = openHazards(briefing).length
  useEffect(() => {
    if (roundN) feedback.announce(`${t('result.announce', { n: roundN, open: open.length })}${reported > 0 ? ` ${t('hazard.announce', { n: reported })}` : ''}`)
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
  const language = catalog?.languages[briefing.workerLang]
  const bySample = new Set(sampleCoveredIds(briefing))
  const causesOf = (stepId: string) =>
    deliveryCauses(stepId, round).flatMap(({ check, ref }) => [
      ...issueSentences(t, check, round, language),
      ...(causedEarlier(ref, stepId, round) ? [t('result.deliveryWhyEarlier')] : []),
    ])
  const bar = resultBar(briefing)
  const exhausted = open.length > 0 && briefing.rounds.length >= MAX_ROUNDS

  const decide = () => navigate(`/b/${briefing.id}/decision`)
  const reexplain = () => navigate(`/b/${briefing.id}/reexplain`)
  const action = (which: 'reexplain' | 'decide', primary: boolean) =>
    which === 'reexplain' ? (
      <Button size={primary ? 'lg' : 'md'} variant={primary ? 'filled' : 'outlined'} icon="replay" onClick={reexplain}>
        {t('result.reexplain')}
      </Button>
    ) : (
      <Button size={primary ? 'lg' : 'md'} variant={primary ? 'filled' : 'outlined'} icon="gavel" onClick={decide}>
        {t('result.decide')}
      </Button>
    )

  // build-notes/22 Task 8 + note 25 F4: the outcome first, one row per step with the worker's audio beside its verdict; the detail
  // (quotes, reasons) follows, and the answers, which repeat the quotes, are folded away. No overall verdict: each step has its own.
  return (
    <FlowFrame
      step="result"
      wide
      round={t('script.round', { n: round.n, max: MAX_ROUNDS })}
      title={t('result.title', { n: round.n })}
      subtitle={t('result.subtitle')}
      primary={action(bar.primary, true)}
      secondary={bar.secondary ? action(bar.secondary, false) : undefined}
    >
      <HazardBanner briefing={briefing} />

      <section aria-labelledby="result-glance" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <h2 id="result-glance" className="text-title-lg text-on-surface">
            {t('result.glance')}
          </h2>
          {round.mode && <StatusChip icon={round.mode === 'live' ? 'record_voice_over' : 'volume_up'}>{t(round.mode === 'live' ? 'brief.mode.live' : 'brief.mode.turn')}</StatusChip>}
        </div>
        <GlanceList steps={inScope} round={round} clips={clips} bySample={bySample} supervisorTag={supervisorTag} workerTag={workerTag} />
      </section>

      {exhausted && (
        <Banner tone="warning" title={t('result.exhausted')} live="polite">
          {t('result.exhaustedHint', { max: MAX_ROUNDS })}
        </Banner>
      )}

      <HazardSection briefing={briefing} editable onAcked={setBriefing} />

      <DeliverySection round={round} language={language} workerTag={workerTag} workerName={workerName} />

      {/* grid-cols-1 is minmax(0, 1fr): a long unbreakable label (Tamil) cannot widen the single column past the screen. */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_23rem] lg:gap-10">
        <Section title={t('result.steps')} id="result-steps" className="order-1">
          <ol className="space-y-4">
            {inScope.map((s) => (
              <StepResultCard
                key={s.id}
                sampleCovered={bySample.has(s.id)}
                quoteBySample={quoteFromSample(round, s.id, round.ratings.find((r) => r.stepId === s.id)?.quote)}
                deliveryCauses={causesOf(s.id)}
                index={stepIndex(s.id)}
                step={s}
                rating={round.ratings.find((r) => r.stepId === s.id)}
                asked={askedAbout(round.script.questions, s.id)}
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
              <Card>
                <RowList>
                  {earlier.map((s) => (
                    <StepRow key={s.id} verdict={briefing.latestVerdicts[s.id] ?? 'unclear'} text={s.text} lang={supervisorTag} sample={bySample.has(s.id)} />
                  ))}
                </RowList>
              </Card>
            </div>
          )}
        </Section>

        <div className="order-2 space-y-3">
          <details className="group rounded-lg border border-outline-variant bg-surface-container-lowest">
            <summary className="state-layer flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-lg px-4 text-label-lg text-on-surface">
              <Icon name="format_quote" className="text-[1.25rem]" />
              <span className="min-w-0 flex-1 truncate">{t('result.answers')}</span>
              <Icon name="expand_more" className="transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-2 px-4 pb-2 pt-1 sm:px-5">
              <p className="pb-2 text-body-md text-on-surface-variant">{t('result.answersHint', { lang: langNative(catalog, briefing.workerLang) })}</p>
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
            </div>
          </details>
          <ModelProvenance round={round} />
        </div>
      </div>
    </FlowFrame>
  )
}
