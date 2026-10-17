import { useRef, useState } from 'react'
import { Redirect, useLocation } from 'wouter'
import { CUSTOM_TASK_ID, bcp47, findTask, langNative, sampleInstructionFor, useCatalog } from '../api/catalog.tsx'
import { api } from '../api/endpoints.ts'
import type { CreateBriefingBody, Lang } from '../api/types.ts'
import { MicError } from '../audio/mic.ts'
import { useBriefing } from '../flow/BriefingContext.tsx'
import { INSTRUCTION_MAX, customSopValid, permitDraftValid, setDraft, useDraft, patchDraft } from '../flow/draft.ts'
import { FlowFrame, type ContextInfo } from '../flow/FlowFrame.tsx'
import { saveStartBriefing } from '../flow/startBriefing.ts'
import { useT, type Translate } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { retryFor } from '../lib/dailyLimit.ts'
import { permitLink } from '../lib/permit.ts'
import { Button } from '../ui/Button.tsx'
import { AssistChip } from '../ui/Chip.tsx'
import { useFeedback } from '../ui/FeedbackProvider.tsx'
import { TextArea } from '../ui/TextField.tsx'
import { HoldToSpeak } from './instruction/HoldToSpeak.tsx'
import { useDictation } from './instruction/useDictation.ts'
import { WaitInView } from './instruction/WaitInView.tsx'

const MIN_LENGTH = 3

function errorMessage(t: Translate, e: unknown): string {
  if (e === 'too_short') return t('instr.tooShort')
  if (e instanceof MicError) return t(`mic.${e.code}`)
  return apiErrorText(t, e)
}

interface ViewProps {
  context: ContextInfo
  supervisorLang: Lang
  sample: string
  initial: string
  onChange?: (text: string) => void
  /** Create/patch the briefing and extract the steps. Throws on failure. */
  submit: (instruction: string, report: (phase: 'save' | 'extract') => void) => Promise<void>
  leaveTo: string
}

function InstructionView({ context, supervisorLang, sample, initial, onChange, submit, leaveTo }: ViewProps) {
  const t = useT()
  const feedback = useFeedback()
  const { data: catalog } = useCatalog()
  const [text, setTextState] = useState(initial)
  const [busy, setBusy] = useState<'save' | 'extract' | null>(null)

  const setText = (next: string) => {
    setTextState(next)
    onChange?.(next)
  }

  const dictation = useDictation({
    lang: supervisorLang,
    onText: (spoken) => {
      if (spoken) setText(`${text ? `${text.trimEnd()} ` : ''}${spoken}`.slice(0, INSTRUCTION_MAX))
      feedback.announce(t('instr.transcribed'))
    },
    onError: (e) => feedback.snack({ message: errorMessage(t, e), tone: 'error' }),
  })

  const valid = text.trim().length >= MIN_LENGTH && text.length <= INSTRUCTION_MAX
  const send = async () => {
    setBusy('save')
    try {
      await submit(text.trim(), (phase) => setBusy(phase))
    } catch (e) {
      setBusy(null)
      feedback.snack({ message: errorMessage(t, e), tone: 'error', ...retryFor(e, t('action.retry'), () => void send()) })
    }
  }

  const lang = bcp47(catalog, supervisorLang, context.siteId)
  return (
    <FlowFrame
      step="instruction"
      title={t('instr.title')}
      subtitle={t('instr.subtitle', { lang: langNative(catalog, supervisorLang) })}
      context={context}
      leaveTo={leaveTo}
      primary={
        <Button size="lg" icon="checklist" disabled={!valid} disabledReason={valid ? undefined : t('instr.need')} busy={busy !== null} onClick={() => void send()}>
          {t('instr.find')}
        </Button>
      }
    >
      {/* The 15-40 s wait comes first, so it is on screen at 320-414 px, not behind the bar (note 25, "Also"). */}
      {busy && <WaitInView title={busy === 'save' ? t('instr.saving') : t('instr.extracting')} hint={t('instr.extractingHint')} />}
      <fieldset disabled={busy !== null} className="space-y-6">
        <legend className="sr-only">{t('instr.title')}</legend>
        <TextArea
          label={t('instr.label', { lang: langNative(catalog, supervisorLang) })}
          value={text}
          onChange={setText}
          rows={5}
          maxLength={INSTRUCTION_MAX}
          lang={lang}
          helper={t('instr.helper')}
        />
        <div className="flex flex-wrap items-center gap-3">
          <HoldToSpeak {...dictation} />
          {sample && text.trim() !== sample && (
            <AssistChip icon="auto_awesome" onClick={() => setText(sample)}>
              {t('instr.useSample')}
            </AssistChip>
          )}
        </div>
        <p className="max-w-xl text-body-md text-on-surface-variant">{t('instr.holdHint')}</p>
      </fieldset>
    </FlowFrame>
  )
}

/** /new/instruction: the briefing does not exist yet; the draft holds the choices from Start. */
export function NewInstructionScreen() {
  const [, navigate] = useLocation()
  const { data: catalog } = useCatalog()
  const draft = useDraft()
  // After a failed extract the briefing already exists: retry on it instead of creating a second one. A ref, not state:
  // the Retry action of the error message keeps the `submit` of the render it was made in.
  const created = useRef<{ id: string | null }>({ id: null }).current

  if (!draft || !customSopValid(draft) || !permitDraftValid(draft)) return <Redirect to="/new" replace />
  // v0.5.2: the permit-to-work this briefing is for, as the contract takes it (permitDraftValid has checked it).
  const permit = draft.permit ? permitLink(draft.permit) : null

  const task = findTask(catalog, draft.taskId)
  const context: ContextInfo = {
    taskId: draft.taskId,
    siteId: draft.siteId,
    customTitle: draft.customTitle,
    supervisorLang: draft.supervisorLang,
    workerLang: draft.workerLang,
    permit,
  }

  const submit: ViewProps['submit'] = async (instruction, report) => {
    const id = await saveStartBriefing(created, instruction, {
      create: () => {
        const body: CreateBriefingBody = {
          siteId: draft.siteId,
          taskId: draft.taskId,
          supervisorLang: draft.supervisorLang,
          workerLang: draft.workerLang,
          instruction,
          ...(draft.taskId === CUSTOM_TASK_ID ? { sop: { title: draft.customTitle.trim(), text: draft.customSop.trim() } } : {}),
          ...(permit ? { permit } : {}),
          ...(draft.sopRef && draft.taskId !== CUSTOM_TASK_ID ? { sopRef: draft.sopRef } : {}), // library: no extraction call
        }
        return api.createBriefing(body)
      },
      patch: api.patchInstruction,
    })
    report('extract')
    await api.extractSteps(id)
    setDraft(null)
    navigate(`/b/${id}/steps`, { replace: true })
  }

  return (
    <InstructionView
      context={context}
      supervisorLang={draft.supervisorLang}
      sample={sampleInstructionFor(task, draft.supervisorLang)}
      initial={draft.instruction}
      onChange={(instruction) => patchDraft({ instruction })}
      submit={submit}
      leaveTo="/new"
    />
  )
}

/** /b/:id/instruction: edit the instruction of an existing briefing and extract again. */
export function InstructionScreen() {
  const [, navigate] = useLocation()
  const { briefing, setBriefing } = useBriefing()
  const { data: catalog } = useCatalog()
  const task = findTask(catalog, briefing.taskId)

  const submit: ViewProps['submit'] = async (instruction, report) => {
    if (instruction !== briefing.instruction) await api.patchInstruction(briefing.id, instruction)
    report('extract')
    setBriefing(await api.extractSteps(briefing.id))
    navigate(`/b/${briefing.id}/steps`, { replace: true })
  }

  return (
    <InstructionView
      context={{
        taskId: briefing.taskId,
        siteId: briefing.siteId,
        customTitle: briefing.sop.title,
        sop: briefing.sop,
        supervisorLang: briefing.supervisorLang,
        workerLang: briefing.workerLang,
      }}
      supervisorLang={briefing.supervisorLang}
      sample={sampleInstructionFor(task, briefing.supervisorLang)}
      initial={briefing.instruction}
      submit={submit}
      leaveTo={`/b/${briefing.id}/steps`}
    />
  )
}
