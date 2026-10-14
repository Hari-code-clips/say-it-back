import { useState } from 'react'
import { useLocation } from 'wouter'
import { ApiError } from '../api/client.ts'
import { bcp47, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import { dropClips } from '../audio/clips.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { openSteps } from '../flow/phases.ts'
import { recoverFromConflict } from '../flow/recover.ts'
import { useT } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { Button } from '../ui/Button.tsx'
import { Card, Section } from '../ui/Card.tsx'
import { RadioCard } from '../ui/Choice.tsx'
import { Banner } from '../ui/Feedback.tsx'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { Icon } from '../ui/Icon.tsx'
import { TextArea, TextField } from '../ui/TextField.tsx'
import { VerdictChip } from '../ui/VerdictChip.tsx'

type Choice = 'go' | 'no_go'
const REASON_MIN = 5

/** The human gate: only this POST records a decision. The app never decides or scores; the words below are the supervisor's. */
export function DecisionScreen() {
  const t = useT()
  const feedback = useFeedback()
  const [, navigate] = useLocation()
  const { briefing, setBriefing, refresh } = useBriefing()
  const { data: catalog } = useCatalog()
  const [choice, setChoice] = useState<Choice | null>(null)
  const [reason, setReason] = useState('')
  const [by, setBy] = useState('')
  const [busy, setBusy] = useState(false)
  const [reasonError, setReasonError] = useState(false)

  const open = openSteps(briefing)
  const lang = bcp47(catalog, briefing.supervisorLang, briefing.siteId)
  const needReason = choice === 'go' && open.length > 0
  const reasonOk = !needReason || reason.trim().length >= REASON_MIN
  const valid = choice !== null && reasonOk

  const submit = async () => {
    if (!choice) return
    setBusy(true)
    try {
      const decided = await api.decide(briefing.id, {
        value: choice,
        reason: reason.trim() || undefined,
        by: by.trim() || undefined,
      })
      dropClips(briefing.id) // the worker's audio is not kept once the decision is recorded
      setBriefing(decided)
      navigate(`/b/${briefing.id}/record`, { replace: true })
    } catch (e) {
      setBusy(false)
      if (e instanceof ApiError && e.code === 'reason_required') {
        setReasonError(true)
        return
      }
      // Already decided (a lost response, or another device): show the record instead of a dead-end error.
      if (await recoverFromConflict(e, refresh, navigate)) return
      feedback.snack({ message: apiErrorText(t, e), tone: 'error', actionLabel: t('action.retry'), onAction: () => void submit() })
    }
  }

  return (
    <FlowFrame
      step="decision"
      title={t('decision.title')}
      subtitle={t('decision.subtitle')}
      leaveTo={`/b/${briefing.id}/result`}
      primary={
        <Button size="lg" icon="gavel" disabled={!valid} busy={busy} onClick={() => void submit()}>
          {t('decision.record')}
        </Button>
      }
      secondary={
        <Button size="lg" variant="text" disabled={busy} onClick={() => navigate(`/b/${briefing.id}/result`)}>
          {t('action.back')}
        </Button>
      }
    >
      <Section title={t('decision.checked')} id="decision-checked">
        <ul className="space-y-2">
          {briefing.steps.map((s) => (
            <Card as="li" key={s.id} className="flex flex-wrap items-center gap-3 p-4">
              <VerdictChip verdict={briefing.latestVerdicts[s.id] ?? 'unclear'} />
              <span lang={lang} className="script-text min-w-0 flex-1 text-body-lg">
                {s.text}
              </span>
            </Card>
          ))}
        </ul>
        <p className="text-body-md text-on-surface-variant">{t('decision.rounds', { n: briefing.rounds.length })}</p>
      </Section>

      {open.length > 0 && (
        <Banner tone="warning" title={t('decision.openTitle', { n: open.length })} live="polite">
          {t('decision.openHint')}
        </Banner>
      )}

      <Section title={t('decision.choose')} id="decision-choose">
        <fieldset disabled={busy} className="space-y-6">
          <legend className="sr-only">{t('decision.choose')}</legend>
          <div role="radiogroup" aria-labelledby="decision-choose" className="grid gap-3 sm:grid-cols-2">
            <RadioCard
              name="decision"
              value="go"
              checked={choice === 'go'}
              onChange={() => setChoice('go')}
              icon={<Icon name="task_alt" />}
              title={t('decision.go')}
              subtitle={t('decision.goHint')}
            />
            <RadioCard
              name="decision"
              value="no_go"
              checked={choice === 'no_go'}
              onChange={() => setChoice('no_go')}
              icon={<Icon name="block" />}
              title={t('decision.noGo')}
              subtitle={t('decision.noGoHint')}
            />
          </div>

          <TextArea
            label={needReason ? t('decision.reasonRequired') : t('decision.reason')}
            value={reason}
            onChange={(v) => {
              setReason(v)
              setReasonError(false)
            }}
            rows={3}
            maxLength={500}
            lang={lang}
            helper={needReason ? t('decision.reasonHint', { min: REASON_MIN }) : undefined}
            error={reasonError || (needReason && reason.length > 0 && !reasonOk) ? t('decision.reasonShort', { min: REASON_MIN }) : undefined}
          />
          <TextField label={t('decision.by')} value={by} onChange={setBy} maxLength={60} helper={t('decision.byHint')} autoComplete="name" />
        </fieldset>
      </Section>
    </FlowFrame>
  )
}
