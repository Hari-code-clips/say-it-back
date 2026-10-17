import { useRef, useState } from 'react'
import { useLocation } from 'wouter'
import { bcp47, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import type { Step } from '../api/types.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { recoverFromConflict } from '../flow/recover.ts'
import { useSopLabel, useT } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { retryFor } from '../lib/dailyLimit.ts'
import { AnchorButton, Button, LinkButton } from '../ui/Button.tsx'
import { Banner } from '../ui/Feedback.tsx'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { WaitInView } from './instruction/WaitInView.tsx'
import { StepCard } from './steps/StepCard.tsx'

/* Hallmark · screen: steps · genre: modern-minimal · macrostructure: Workbench · theme: design.md
 * The instruction is plain text under a sentence-case heading (no uppercase caption, no card), the steps are one hairline card each.
 * The 15-40 s waits come first, scrolled into view, so they are on screen at 320-414 px. A disabled primary says what to fix.
 * states: default · invalid (empty step: the bar says so) · loading (WaitInView, button busy) · error (snackbar with Retry, conflict
 *         banners) · empty (banner with the way out) · success (navigates).
 * A briefing started from a signed-off library version (`sopRef`; security fixes A, H2) shows its steps read-only, with one line
 * above the list saying where they were signed off and how they change; Confirm sends them back as they came (the server refuses
 * any other list). The header's "edit, remove or add" line is left out there.
 */

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

/** What Confirm sends: a signed-off version's steps exactly as they came (the server takes no other list), any other steps cleaned. */
export const stepsToConfirm = (steps: Step[], locked: boolean): Step[] => (locked ? steps : steps.map(clean))

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
  const locked = Boolean(briefing.sopRef)
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
    feedback.snack({ message: apiErrorText(t, e), tone: 'error', ...retryFor(e, t('action.retry'), retry) })

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
      setBriefing(await api.confirmSteps(briefing.id, stepsToConfirm(steps, locked)))
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
  // What stops Confirm, in words: no steps at all, or a step with no text.
  const need = valid ? undefined : noSteps ? t('steps.need.none') : steps.length > MAX_STEPS ? t('steps.max', { max: MAX_STEPS }) : t('steps.need.text')
  return (
    <FlowFrame
      step="steps"
      title={t('steps.title')}
      subtitle={locked ? undefined : t('steps.subtitle')}
      primary={
        noSteps && briefing.status !== 'steps_confirmed' ? (
          <Button size="lg" icon="refresh" busy={busy === 'extract'} onClick={() => void extract()}>
            {t('steps.extract')}
          </Button>
        ) : (
          <Button size="lg" icon="check" disabled={!valid || busy !== null} disabledReason={need} busy={busy === 'confirm' || busy === 'script'} onClick={() => void confirm()}>
            {t('steps.confirm')}
          </Button>
        )
      }
    >
      {busy === 'script' && <WaitInView title={t('steps.writing', { lang: catalog?.languages[briefing.workerLang]?.name ?? briefing.workerLang })} hint={t('steps.writingHint')} />}
      {busy === 'extract' && <WaitInView title={t('instr.extracting')} hint={t('instr.extractingHint')} />}

      <section aria-labelledby="steps-instruction" className="space-y-1 border-b border-outline-variant pb-4">
        <h2 id="steps-instruction" className="text-title-md text-on-surface-variant">
          {t('steps.yourInstruction')}
        </h2>
        <p lang={lang} className="script-text text-body-lg text-on-surface">
          {briefing.instruction}
        </p>
        {briefing.status !== 'steps_confirmed' && (
          <LinkButton href={`/b/${briefing.id}/instruction`} variant="text" className="-ml-3">
            {t('steps.editInstruction')}
          </LinkButton>
        )}
      </section>

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
                  <AnchorButton href={`#step-${c.stepId}`} variant="outlined" className="border-on-error-container! text-on-error-container!">
                    {t('steps.goToStep', { n: steps.findIndex((s) => s.id === c.stepId) + 1 })}
                  </AnchorButton>
                ) : undefined
              }
            >
              <span lang={lang}>{c.message}</span>
            </Banner>
          ))}
        </div>
      )}

      <fieldset disabled={busy !== null} className="space-y-4">
        <legend className="sr-only">{t('steps.title')}</legend>
        {noSteps ? (
          <Banner tone="info" title={t('steps.empty')}>
            {t('steps.emptyHint')}
          </Banner>
        ) : (
          <>
            {locked && <p className="text-body-md text-on-surface-variant">{t('steps.locked', { sop: sopLabel(briefing.sop) })}</p>}
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
                  readOnly={locked}
                />
              ))}
            </ol>
          </>
        )}
        {!locked && (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outlined" icon="add" onClick={add} disabled={steps.length >= MAX_STEPS}>
              {t('steps.add')}
            </Button>
            <p className="text-body-md text-on-surface-variant">{steps.length >= MAX_STEPS ? t('steps.max', { max: MAX_STEPS }) : t('steps.count', { n: steps.length, max: MAX_STEPS })}</p>
          </div>
        )}
      </fieldset>
    </FlowFrame>
  )
}
