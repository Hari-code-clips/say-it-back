import { useState } from 'react'
import { useLocation } from 'wouter'
import { ApiError } from '../api/client.ts'
import { bcp47, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import { dropClips, dropClipsIfDecided } from '../audio/clips.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { awaitsInPersonCheck, latestRound, openHazards } from '../flow/phases.ts'
import { recoverFromConflict } from '../flow/recover.ts'
import { useT, useUiLang } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { briefingFacts, factsLine } from '../lib/briefingFacts.ts'
import { decisionOpenSteps, inPersonOpenSteps, sampleCoveredIds } from '../lib/sampleCovered.ts'
import { Button } from '../ui/Button.tsx'
import { Card, RowList, Section } from '../ui/Card.tsx'
import { StatusChip } from '../ui/Chip.tsx'
import { Dialog } from '../ui/Dialog.tsx'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { Icon } from '../ui/Icon.tsx'
import { TextArea, TextField } from '../ui/TextField.tsx'
import { HazardBanner, HazardSection } from './hazard/HazardSection.tsx'
import { DecisionChoice } from './result/DecisionChoice.tsx'
import { REASON_MIN, decisionGate, type DecisionChoice as Choice } from './result/gates.ts'
import { StepRow } from './result/StepRow.tsx'

/* Hallmark · screen: decision · genre: modern-minimal · macrostructure: Workbench · theme: design.md
 * Go and No-go are the first thing under the heading, the reason right under them, then what was checked. Record decision says why it
 * is off, and opens a short confirm because the decision is final. A reported problem is one banner that jumps to its note.
 * states: default · invalid (the bar names what is missing) · locked (Go, while a reported problem has no note) · confirming (dialog)
 *         · loading (the dialog's button) · error (snackbar with Retry) · success (navigates to the record).
 * 2026-10-17, the in-person check (the worker said "Not now" to the latest round's recording): the subtitle says no AI check was
 * made for this worker, Go always needs the reason, the round's steps show no verdict (an "In person" tag instead) and count as open,
 * and the way back is the script. Same layout, same one blue fill.
 */

/** The human gate: only this POST records a decision. The app never decides or scores; the words below are the supervisor's. */
export function DecisionScreen() {
  const t = useT()
  const { lang: uiLang } = useUiLang()
  const feedback = useFeedback()
  const [, navigate] = useLocation()
  const { briefing, setBriefing, refresh } = useBriefing()
  const { data: catalog } = useCatalog()
  const [choice, setChoice] = useState<Choice | null>(null)
  const [reason, setReason] = useState('')
  const [by, setBy] = useState('')
  const [busy, setBusy] = useState(false)
  const [reasonError, setReasonError] = useState(false)
  const [confirming, setConfirming] = useState(false)

  // 2026-10-17: the worker declined the latest round's recording, so no model checked it: the supervisor records an in-person check.
  const inPerson = awaitsInPersonCheck(briefing)
  const inPersonScope = new Set(inPerson ? (latestRound(briefing)?.stepIds ?? []) : [])
  // v0.4 review: a step said back only by a stored sample answer is open here, exactly like a step that was not covered.
  const open = inPerson ? inPersonOpenSteps(briefing) : decisionOpenSteps(briefing)
  const bySample = new Set(sampleCoveredIds(briefing))
  // v0.4: a problem the worker reported locks Go until it has a note of what was done. No-go is always there.
  const goLocked = openHazards(briefing).length > 0
  const lang = bcp47(catalog, briefing.supervisorLang, briefing.siteId)
  const needReason = choice === 'go' && (open.length > 0 || inPerson)
  const reasonOk = !needReason || reason.trim().length >= REASON_MIN
  const gate = decisionGate({ choice, reason, openStepCount: open.length, goLocked, inPerson })
  const back = inPerson ? `/b/${briefing.id}/script` : `/b/${briefing.id}/result`
  // v0.5.1: the briefing so far, from its own record (time since it was created, rounds, re-explained steps, reports).
  const facts = briefingFacts(briefing, new Date())

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
      setConfirming(false)
      if (e instanceof ApiError && e.code === 'reason_required') {
        setReasonError(true)
        return
      }
      if (e instanceof ApiError && e.code === 'hazard_open') {
        // A report this screen had not seen yet: show it, and Go locks.
        await refresh().catch(() => undefined)
        setChoice(null)
        feedback.snack({ message: apiErrorText(t, e), tone: 'error' })
        return
      }
      // Already decided (a lost response, or another device): show the record instead of a dead-end error, and forget the
      // worker's audio as the success path does.
      const refreshed = async () => {
        const fresh = await refresh()
        dropClipsIfDecided(fresh)
        return fresh
      }
      if (await recoverFromConflict(e, refreshed, navigate)) return
      feedback.snack({ message: apiErrorText(t, e), tone: 'error', actionLabel: t('action.retry'), onAction: () => void submit() })
    }
  }

  const choiceValue = choice === 'go' ? t('decision.go') : t('decision.noGo')

  return (
    <FlowFrame
      step="decision"
      title={t('decision.title')}
      subtitle={inPerson ? t('inPerson.subtitle') : t('decision.subtitle')}
      leaveTo={back}
      primary={
        <Button
          size="lg"
          icon="gavel"
          disabled={!gate.valid}
          disabledReason={gate.reasonKey ? t(gate.reasonKey) : undefined}
          busy={busy}
          onClick={() => setConfirming(true)}
        >
          {t('decision.record')}
        </Button>
      }
      secondary={
        <Button variant="text" disabled={busy} onClick={() => navigate(back)}>
          {inPerson ? t('brief.backToScript') : t('decision.backToResult')}
        </Button>
      }
    >
      <fieldset disabled={busy} className="space-y-5">
        <legend className="sr-only">{t('decision.choose')}</legend>
        <div role="radiogroup" aria-label={t('decision.choose')} className="grid gap-2 sm:grid-cols-2 sm:gap-3">
          <DecisionChoice
            name="decision"
            value="go"
            checked={choice === 'go' && !goLocked}
            onChange={() => setChoice('go')}
            icon={goLocked ? 'lock' : 'task_alt'}
            title={t('decision.go')}
            hint={goLocked ? t('decision.goLocked') : t('decision.goHint')}
            disabled={goLocked}
          />
          <DecisionChoice
            name="decision"
            value="no_go"
            checked={choice === 'no_go'}
            onChange={() => setChoice('no_go')}
            icon="block"
            title={t('decision.noGo')}
            hint={t('decision.noGoHint')}
          />
        </div>

        {/* The short form of an open report sits under the choices, not above them: the lock reason is already on the Go card, and
            the choices must be fully above the bar at 375 x 667 and up (note 29, follow-up). Its button jumps to the note. */}
        <HazardBanner briefing={briefing} />

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
          // 16 Oct: an evaluator who used stored sample answers sees every step Got it, yet Go asks for a reason. Say why right here.
          helper={needReason ? t(inPerson ? 'inPerson.reasonHint' : bySample.size > 0 ? 'decision.reasonHintSample' : 'decision.reasonHint', { min: REASON_MIN }) : undefined}
          error={reasonError || (needReason && reason.length > 0 && !reasonOk) ? t('decision.reasonShort', { min: REASON_MIN }) : undefined}
        />
        <TextField label={t('decision.by')} value={by} onChange={setBy} maxLength={60} helper={t('decision.byHint')} autoComplete="name" />
      </fieldset>

      <HazardSection briefing={briefing} editable onAcked={setBriefing} />

      <Section title={t('decision.checked')} id="decision-checked">
        {facts ? (
          <p className="flex items-start gap-2 text-body-md text-on-surface-variant">
            <Icon name="history" className="mt-0.5 text-[1.125rem]" />
            <span className="min-w-0">{factsLine(facts, uiLang)}</span>
          </p>
        ) : (
          <p className="text-body-md text-on-surface-variant">{t('decision.rounds', { n: briefing.rounds.length })}</p>
        )}
        {open.length > 0 && (
          <p className="text-body-md text-on-surface">
            <span className="text-title-sm">{t('decision.openTitle', { n: open.length })}. </span>
            {inPerson ? t('inPerson.openHint') : t('decision.openHint')}
            {bySample.size > 0 && ` ${t('decision.sampleOpen')}`}
          </p>
        )}
        <Card>
          <RowList>
            {briefing.steps.map((s) =>
              inPersonScope.has(s.id) ? (
                <StepRow key={s.id} text={s.text} lang={lang} tag={<StatusChip icon="groups">{t('inPerson.stepTag')}</StatusChip>} />
              ) : (
                <StepRow key={s.id} verdict={briefing.latestVerdicts[s.id] ?? 'unclear'} text={s.text} lang={lang} sample={bySample.has(s.id)} />
              ),
            )}
          </RowList>
        </Card>
      </Section>

      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title={t('decision.confirm.title', { value: choiceValue })}
        actions={
          <>
            <Button variant="outlined" disabled={busy} onClick={() => setConfirming(false)}>
              {t('decision.confirm.cancel')}
            </Button>
            <Button busy={busy} onClick={() => void submit()}>
              {choice === 'go' ? t('decision.confirm.go') : t('decision.confirm.noGo')}
            </Button>
          </>
        }
      >
        <p>{t('decision.confirm.body')}</p>
        {inPerson && <p className="mt-2">{t('inPerson.confirm')}</p>}
        {choice === 'go' && open.length > 0 && <p className="mt-2">{t('decision.confirm.open', { n: open.length })}</p>}
        {choice === 'no_go' && <p className="mt-2">{t('decision.confirm.noGoKind')}</p>}
      </Dialog>
    </FlowFrame>
  )
}
