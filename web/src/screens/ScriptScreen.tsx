import { useLocation } from 'wouter'
import { bcp47, langNative, useCatalog } from '../api/catalog.tsx'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { MAX_ROUNDS, latestRound } from '../flow/phases.ts'
import { UnexpectedState } from '../flow/UnexpectedState.tsx'
import { useLangName, useT } from '../i18n/index.tsx'
import { scriptCoverage, stepsBySentence } from '../lib/coverage.ts'
import { Button } from '../ui/Button.tsx'
import { Card, Section } from '../ui/Card.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { Banner } from '../ui/Feedback.tsx'
import { Icon } from '../ui/Icon.tsx'

export function ScriptScreen() {
  const t = useT()
  const [, navigate] = useLocation()
  const { briefing } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const round = latestRound(briefing)
  if (!round) return <UnexpectedState />

  const { script } = round
  const supervisorTag = bcp47(catalog, briefing.supervisorLang, briefing.siteId)
  const workerTag = bcp47(catalog, briefing.workerLang, briefing.siteId)
  const workerName = langName(briefing.workerLang)
  const supervisorName = langName(briefing.supervisorLang)
  const { sentences, stepIds: bySentence } = stepsBySentence(script)
  const stepNumber = (id: string) => briefing.steps.findIndex((s) => s.id === id) + 1
  const coverage = scriptCoverage(round.stepIds, script)
  const complete = coverage.notDelivered.length === 0 && coverage.notAsked.length === 0
  const reexplain = round.kind === 'reexplain'

  return (
    <FlowFrame
      step="script"
      wide
      eyebrow={t('script.round', { n: round.n, max: MAX_ROUNDS })}
      title={reexplain ? t('script.titleReexplain') : t('script.title')}
      subtitle={t('script.subtitle', { worker: workerName, supervisor: supervisorName })}
      primary={
        <Button size="lg" icon="smartphone" onClick={() => navigate(`/b/${briefing.id}/brief`)}>
          {t('script.handover')}
        </Button>
      }
    >
      {complete ? (
        <Banner tone="success" title={t('script.coverageOk')} live="polite">
          {t('script.coverageOkHint', { n: round.stepIds.length })}
        </Banner>
      ) : (
        <Banner tone="warning" title={t('script.coverageGap')} live="assertive">
          {coverage.notDelivered.length > 0 && <p>{t('script.notDelivered', { steps: coverage.notDelivered.map(stepNumber).join(', ') })}</p>}
          {coverage.notAsked.length > 0 && <p>{t('script.notAsked', { steps: coverage.notAsked.map(stepNumber).join(', ') })}</p>}
        </Banner>
      )}

      {round.supervisorNote && (
        <Card variant="filled" className="space-y-2 p-4 sm:p-5">
          <p className="text-title-sm uppercase tracking-wide text-on-surface-variant">{t('script.yourWords')}</p>
          <p lang={supervisorTag} className="script-text text-body-lg">
            {round.supervisorNote}
          </p>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="space-y-4 p-5 sm:p-6" as="section" aria-labelledby="script-hears">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-full bg-primary-container text-on-primary-container">
              <Icon name="hearing" />
            </span>
            <div>
              <h2 id="script-hears" className="text-title-lg">
                {t('script.hears')}
              </h2>
              <p className="text-body-md text-on-surface-variant">
                {langNative(catalog, briefing.workerLang)} · {workerName}
              </p>
            </div>
          </div>
          <ol lang={workerTag} className="space-y-3">
            {sentences.map((sentence, i) => (
              <li key={i} className="script-text text-title-lg">
                {sentence}
                {(bySentence[i] ?? []).length > 0 && (
                  <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
                    {(bySentence[i] ?? []).map((id) => (
                      <StatusChip key={id} tone="primary" lang={briefing.supervisorLang}>
                        {t('script.deliversStep', { n: stepNumber(id) })}
                      </StatusChip>
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </Card>

        <Card variant="filled" className="space-y-4 p-5 sm:p-6" as="section" aria-labelledby="script-back">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-full bg-secondary-container text-on-secondary-container">
              <Icon name="translate" />
            </span>
            <div>
              <h2 id="script-back" className="text-title-lg">
                {t('script.back', { lang: supervisorName })}
              </h2>
              <p className="text-body-md text-on-surface-variant">{t('script.backHint')}</p>
            </div>
          </div>
          <p lang={supervisorTag} className="script-text whitespace-pre-line text-body-lg">
            {script.instructionBackTranslation}
          </p>
        </Card>
      </div>

      <Section title={t('script.questions')} hint={t('script.questionsHint')} id="script-questions">
        <ul className="grid gap-4 md:grid-cols-2">
          {script.questions.map((q) => (
            <Card as="li" key={q.id} className="space-y-3 p-5">
              <p lang={workerTag} className="script-text text-title-lg">
                {q.text}
              </p>
              <p lang={supervisorTag} className="script-text border-l-2 border-outline-variant pl-3 text-body-md text-on-surface-variant">
                {q.backTranslation}
              </p>
              <p className="flex flex-wrap items-center gap-2 text-body-md text-on-surface-variant">
                {t('script.checks')}
                {q.stepIds.map((id) => (
                  <StatusChip key={id}>{t('script.stepN', { n: stepNumber(id) })}</StatusChip>
                ))}
              </p>
            </Card>
          ))}
        </ul>
      </Section>

      <Card variant="filled" className="space-y-1 p-4">
        <p className="text-title-sm uppercase tracking-wide text-on-surface-variant">{t('script.closing')}</p>
        <p lang={workerTag} className="script-text text-body-lg">
          {script.closing}
        </p>
      </Card>
    </FlowFrame>
  )
}
