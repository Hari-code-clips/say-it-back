import { useState } from 'react'
import { Redirect, useLocation } from 'wouter'
import { bcp47, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { MAX_ROUNDS, canReexplain, openSteps } from '../flow/phases.ts'
import { recoverFromConflict } from '../flow/recover.ts'
import { useLangName, useT } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { retryFor } from '../lib/dailyLimit.ts'
import { Button } from '../ui/Button.tsx'
import { Card, RowList, Section } from '../ui/Card.tsx'
import { RadioCard } from '../ui/Choice.tsx'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { Icon } from '../ui/Icon.tsx'
import { TextArea } from '../ui/TextField.tsx'
import { StepRow } from './result/StepRow.tsx'
import { WaitInView } from './instruction/WaitInView.tsx'

type Method = 'generate' | 'own'
const NOTE_MAX = 1000

/* Hallmark · screen: re-explain · genre: modern-minimal · macrostructure: Workbench · theme: design.md
 * Both ways of re-explaining are visible above the sticky bar, then the open steps they are for. The 15-40 s wait takes the place of the
 * choices, at the top, so it is on screen at 320-414 px (it used to sit below the fold, behind the bar).
 * states: default · invalid (own words empty: the bar says so) · loading (WaitInView) · error (snackbar with Retry) · success (navigates).
 */

/** Re-explain the open steps: a generated focused re-explanation, or the supervisor's own words. */
export function ReexplainScreen() {
  const t = useT()
  const feedback = useFeedback()
  const [, navigate] = useLocation()
  const { briefing, refresh } = useBriefing()
  const { data: catalog } = useCatalog()
  const langName = useLangName()
  const [method, setMethod] = useState<Method>('generate')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  if (!canReexplain(briefing)) return <Redirect to={`/b/${briefing.id}/result`} replace />

  const open = openSteps(briefing)
  const lang = bcp47(catalog, briefing.supervisorLang, briefing.siteId)
  const workerName = langName(briefing.workerLang)
  const valid = method === 'generate' || note.trim().length >= 3

  const submit = async () => {
    setBusy(true)
    try {
      await api.createRound(briefing.id, {
        stepIds: open.map((s) => s.id),
        ...(method === 'own' ? { supervisorNote: note.trim() } : {}),
      })
      await refresh()
      navigate(`/b/${briefing.id}/script`)
    } catch (e) {
      setBusy(false)
      if (await recoverFromConflict(e, refresh, navigate)) return
      feedback.snack({ message: apiErrorText(t, e), tone: 'error', ...retryFor(e, t('action.retry'), () => void submit()) })
    }
  }

  return (
    <FlowFrame
      step="reexplain"
      round={t('script.round', { n: briefing.rounds.length + 1, max: MAX_ROUNDS })}
      title={t('reexplain.title')}
      subtitle={t('reexplain.subtitle')}
      leaveTo={`/b/${briefing.id}/result`}
      primary={
        <Button size="lg" icon="checklist" disabled={!valid} disabledReason={valid ? undefined : t('reexplain.need')} busy={busy} onClick={() => void submit()}>
          {t('reexplain.write')}
        </Button>
      }
      secondary={
        <Button variant="text" disabled={busy} onClick={() => navigate(`/b/${briefing.id}/result`)}>
          {t('action.back')}
        </Button>
      }
    >
      {busy ? (
        <WaitInView title={t('reexplain.busy', { lang: workerName })} hint={t('steps.writingHint')} />
      ) : (
        <section aria-labelledby="reexplain-how">
          {/* The heading is for assistive technology only: the subtitle above already says "choose how", and the two choices belong
              in the first screen, above the bar, at 320-414 px. */}
          <h2 id="reexplain-how" className="sr-only">
            {t('reexplain.how')}
          </h2>
          <fieldset className="space-y-4">
            <legend className="sr-only">{t('reexplain.how')}</legend>
            <div role="radiogroup" aria-labelledby="reexplain-how" className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <RadioCard
                name="method"
                value="generate"
                checked={method === 'generate'}
                onChange={() => setMethod('generate')}
                icon={<Icon name="auto_awesome" />}
                title={t('reexplain.generate')}
                subtitle={t('reexplain.generateHint', { lang: workerName })}
              />
              <RadioCard
                name="method"
                value="own"
                checked={method === 'own'}
                onChange={() => setMethod('own')}
                icon={<Icon name="edit_note" />}
                title={t('reexplain.own')}
                subtitle={t('reexplain.ownHint', { lang: workerName })}
              />
            </div>
            {method === 'own' && (
              <TextArea className="animate-fade-in" label={t('reexplain.ownLabel')} value={note} onChange={setNote} rows={4} maxLength={NOTE_MAX} lang={lang} />
            )}
          </fieldset>
        </section>
      )}

      <Section title={t('reexplain.open', { n: open.length })} hint={t('reexplain.openHint')} id="reexplain-open">
        <Card>
          <RowList>
            {open.map((s) => (
              <StepRow key={s.id} verdict={briefing.latestVerdicts[s.id] ?? 'unclear'} text={s.text} lang={lang} />
            ))}
          </RowList>
        </Card>
        {/* Compassion pass (16 Oct): teach-back's rule is to re-teach differently, never to repeat louder. Below the list, so both
            choices stay above the bar (F6). */}
        <p className="mt-4 flex items-start gap-3 text-body-md text-on-surface-variant">
          <Icon name="record_voice_over" className="mt-px text-[1.125rem]" />
          <span className="min-w-0">{t('reexplain.kind')}</span>
        </p>
      </Section>
    </FlowFrame>
  )
}
