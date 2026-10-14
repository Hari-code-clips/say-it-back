import { useRef, useState } from 'react'
import { Link, useLocation } from 'wouter'
import { bcp47, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import type { Step } from '../api/types.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { recoverFromConflict } from '../flow/recover.ts'
import { useSopLabel, useT } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { Button } from '../ui/Button.tsx'
import { Card } from '../ui/Card.tsx'
import { Banner, BusyPanel } from '../ui/Feedback.tsx'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { StepCard } from './steps/StepCard.tsx'

const MAX_STEPS = 6

const nextId = (steps: Step[]): string => {
  const max = steps.reduce((m, s) => Math.max(m, Number(/^s(\d+)$/.exec(s.id)?.[1] ?? 0)), 0)
  return `s${max + 1}`
}

/** Essential elements default to the step text itself, so a hand-added step can still be judged. */
const clean = (s: Step): Step => {
  const text = s.text.trim()
  const essential = s.essential.map((e) => e.trim()).filter(Boolean)
  return { ...s, text, hazard: s.hazard.trim(), essential: essential.length ? essential : [text] }
}

export function StepsScreen() {
  const t = useT()
  const sopLabel = useSopLabel()
  const feedback = useFeedback()
  const [, navigate] = useLocation()
  const { briefing, setBriefing, refresh } = useBriefing()
  const { data: catalog } = useCatalog()
  const [steps, setSteps] = useState<Step[]>(briefing.steps)
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set())
  const [busy, setBusy] = useState<'extract' | 'confirm' | 'script' | null>(null)
  const list = useRef<HTMLOListElement>(null)

  const lang = bcp47(catalog, briefing.supervisorLang, briefing.siteId)
  const valid = steps.length >= 1 && steps.length <= MAX_STEPS && steps.every((s) => s.text.trim())
  const patch = (id: string, change: Partial<Step>) => setSteps((all) => all.map((s) => (s.id === id ? { ...s, ...change } : s)))

  const remove = (step: Step) => {
    const before = steps
    setSteps(before.filter((s) => s.id !== step.id))
    feedback.snack({ message: t('steps.removed'), actionLabel: t('action.undo'), onAction: () => setSteps(before) })
  }

  const add = () => {
    const id = nextId(steps)
    setSteps([...steps, { id, text: '', hazard: '', essential: [], source: 'instruction', speakable: true }])
    // Focus the new step's text once it is in the DOM.
    requestAnimationFrame(() => list.current?.querySelector<HTMLTextAreaElement>(`#step-${id} textarea`)?.focus())
  }

  const fail = (e: unknown, retry: () => void) =>
    feedback.snack({ message: apiErrorText(t, e), tone: 'error', actionLabel: t('action.retry'), onAction: retry })

  const extract = async () => {
    setBusy('extract')
    try {
      const b = await api.extractSteps(briefing.id)
      setBriefing(b)
      setSteps(b.steps)
    } catch (e) {
      fail(e, () => void extract())
    }
    setBusy(null)
  }

  const confirm = async () => {
    setBusy('confirm')
    try {
      setBriefing(await api.confirmSteps(briefing.id, steps.map(clean)))
      setBusy('script')
      await api.createRound(briefing.id)
      await refresh()
      navigate(`/b/${briefing.id}/script`)
    } catch (e) {
      setBusy(null)
      // e.g. the round was created but the response was lost: continue from the server's state.
      if (await recoverFromConflict(e, refresh, navigate)) return
      fail(e, () => void confirm())
    }
  }

  const noSteps = steps.length === 0
  return (
    <FlowFrame
      step="steps"
      title={t('steps.title')}
      subtitle={t('steps.subtitle')}
      primary={
        noSteps && briefing.status !== 'steps_confirmed' ? (
          <Button size="lg" icon="refresh" busy={busy === 'extract'} onClick={() => void extract()}>
            {t('steps.extract')}
          </Button>
        ) : (
          <Button size="lg" icon="check" disabled={!valid || busy !== null} busy={busy === 'confirm' || busy === 'script'} onClick={() => void confirm()}>
            {t('steps.confirm')}
          </Button>
        )
      }
    >
      <Card variant="filled" className="space-y-3 p-4 sm:p-5">
        <p className="text-title-sm uppercase tracking-wide text-on-surface-variant">{t('steps.yourInstruction')}</p>
        <p lang={lang} className="script-text text-body-lg text-on-surface">
          {briefing.instruction}
        </p>
        {briefing.status !== 'steps_confirmed' && (
          <Link
            href={`/b/${briefing.id}/instruction`}
            className="state-layer inline-flex min-h-12 items-center rounded-full px-3 text-label-lg text-primary"
          >
            {t('steps.editInstruction')}
          </Link>
        )}
      </Card>

      {briefing.conflicts.length > 0 && (
        <div className="space-y-3" aria-label={t('steps.conflicts')} role="group">
          {briefing.conflicts.map((c, i) => (
            <Banner
              key={`${c.stepId ?? 'general'}-${i}`}
              tone="error"
              title={t('steps.conflictTitle')}
              live="assertive"
              action={
                c.stepId && steps.some((s) => s.id === c.stepId) ? (
                  <a href={`#step-${c.stepId}`} className="state-layer inline-flex min-h-12 items-center rounded-full border border-current px-4 text-label-lg">
                    {t('steps.goToStep', { n: steps.findIndex((s) => s.id === c.stepId) + 1 })}
                  </a>
                ) : undefined
              }
            >
              <span lang={lang}>{c.message}</span>
            </Banner>
          ))}
        </div>
      )}

      {busy === 'script' && <BusyPanel title={t('steps.writing', { lang: catalog?.languages[briefing.workerLang]?.name ?? briefing.workerLang })} hint={t('steps.writingHint')} />}
      {busy === 'extract' && <BusyPanel title={t('instr.extracting')} hint={t('instr.extractingHint')} />}

      <fieldset disabled={busy !== null} className="space-y-4">
        <legend className="sr-only">{t('steps.title')}</legend>
        {noSteps ? (
          <Banner tone="info" title={t('steps.empty')}>
            {t('steps.emptyHint')}
          </Banner>
        ) : (
          <ol ref={list} className="space-y-4">
            {steps.map((s, i) => (
              <StepCard
                key={s.id}
                index={i}
                step={s}
                conflicts={briefing.conflicts.filter((c) => c.stepId === s.id)}
                sopId={sopLabel(briefing.sop)}
                lang={lang}
                showTextError={touched.has(s.id)}
                onChange={(change) => patch(s.id, change)}
                onBlurText={() => setTouched((set) => new Set(set).add(s.id))}
                onRemove={() => remove(s)}
                canRemove={steps.length > 1}
              />
            ))}
          </ol>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outlined" icon="add" onClick={add} disabled={steps.length >= MAX_STEPS}>
            {t('steps.add')}
          </Button>
          <p className="text-body-md text-on-surface-variant">{steps.length >= MAX_STEPS ? t('steps.max', { max: MAX_STEPS }) : t('steps.count', { n: steps.length, max: MAX_STEPS })}</p>
        </div>
      </fieldset>
    </FlowFrame>
  )
}
