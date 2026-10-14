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
import { Button } from '../ui/Button.tsx'
import { Card, Section } from '../ui/Card.tsx'
import { RadioCard } from '../ui/Choice.tsx'
import { BusyPanel } from '../ui/Feedback.tsx'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { Icon } from '../ui/Icon.tsx'
import { TextArea } from '../ui/TextField.tsx'
import { VerdictChip } from '../ui/VerdictChip.tsx'

type Method = 'generate' | 'own'
const NOTE_MAX = 1000

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
      feedback.snack({
        message: apiErrorText(t, e),
        tone: 'error',
        actionLabel: t('action.retry'),
        onAction: () => void submit(),
      })
    }
  }

  return (
    <FlowFrame
      step="reexplain"
      eyebrow={t('script.round', { n: briefing.rounds.length + 1, max: MAX_ROUNDS })}
      title={t('reexplain.title')}
      subtitle={t('reexplain.subtitle')}
      leaveTo={`/b/${briefing.id}/result`}
      primary={
        <Button size="lg" icon="checklist" disabled={!valid} busy={busy} onClick={() => void submit()}>
          {t('reexplain.write')}
        </Button>
      }
      secondary={
        <Button size="lg" variant="text" disabled={busy} onClick={() => navigate(`/b/${briefing.id}/result`)}>
          {t('action.back')}
        </Button>
      }
    >
      <Section title={t('reexplain.open', { n: open.length })} id="reexplain-open">
        <ul className="space-y-2">
          {open.map((s) => (
            <Card as="li" key={s.id} className="flex flex-wrap items-center gap-3 p-4">
              <VerdictChip verdict={briefing.latestVerdicts[s.id] ?? 'unclear'} />
              <span lang={lang} className="script-text min-w-0 flex-1 text-body-lg">
                {s.text}
              </span>
            </Card>
          ))}
        </ul>
      </Section>

      <Section title={t('reexplain.how')} id="reexplain-how">
        <fieldset disabled={busy} className="space-y-4">
          <legend className="sr-only">{t('reexplain.how')}</legend>
          <div role="radiogroup" aria-labelledby="reexplain-how" className="grid gap-3 sm:grid-cols-2">
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
            <TextArea
              className="animate-fade-in"
              label={t('reexplain.ownLabel')}
              value={note}
              onChange={setNote}
              rows={4}
              maxLength={NOTE_MAX}
              lang={lang}
            />
          )}
        </fieldset>
      </Section>

      {busy && <BusyPanel title={t('reexplain.busy', { lang: workerName })} hint={t('steps.writingHint')} />}
    </FlowFrame>
  )
}
