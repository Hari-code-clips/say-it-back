/* Hallmark · component: library draft steps · genre: modern-minimal · theme: design.md
 * A draft version's critical steps as label-above fields in hairline rows: text and an optional hazard, a remove icon button (48 px),
 * "Add a step" (text button), "Save steps" (outlined) and the one solid action, "Sign off steps", behind a confirm dialog: a signed-off
 * version never changes. Sign-off saves unsaved edits first. Disabled sign-off says why (no steps).
 * states: default · busy (spinner on the acting button) · error (snackbar with the server's reason) · success (the list reloads).
 */
import { useState } from 'react'
import type { Lang, LibraryVersion, Step } from '../../api/types.ts'
import { useT } from '../../i18n/index.tsx'
import { Button, IconButton } from '../../ui/Button.tsx'
import { RowList } from '../../ui/Card.tsx'
import { Dialog } from '../../ui/Dialog.tsx'
import { TextArea } from '../../ui/TextField.tsx'
import { numbered } from './libraryModel.ts'

interface Props {
  version: LibraryVersion
  lang: Lang
  /** PUT the steps; resolves when saved. */
  save: (steps: Step[]) => Promise<void>
  /** Save (when edited) and sign off. */
  signOff: (steps: Step[] | null) => Promise<void>
}

const blank = (): Step => ({ id: '', text: '', hazard: '', essential: [], source: 'sop', speakable: true })

export function StepsEditor({ version, lang, save, signOff }: Props) {
  const t = useT()
  const [steps, setSteps] = useState<Step[]>(() => (version.steps.length ? version.steps : [blank()]))
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState<'save' | 'sign' | null>(null)
  const [confirming, setConfirming] = useState(false)
  const ready = numbered(steps)

  const edit = (i: number, patch: Partial<Step>) => {
    setSteps(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)))
    setDirty(true)
  }
  const run = async (which: 'save' | 'sign', act: () => Promise<void>) => {
    setBusy(which)
    try {
      await act()
      setDirty(false)
    } catch {
      /* the screen's snackbar has said why; the edits stay for another try */
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <RowList className="rounded-lg border border-outline-variant bg-surface-container-lowest">
        {steps.map((step, i) => (
          <li key={i} className="flex items-start gap-2 p-4">
            <div className="min-w-0 flex-1 space-y-3">
              <TextArea label={t('library.stepText', { n: i + 1 })} value={step.text} onChange={(text) => edit(i, { text })} rows={2} maxLength={300} lang={lang} />
              <TextArea label={t('library.stepHazard')} value={step.hazard} onChange={(hazard) => edit(i, { hazard })} rows={2} maxLength={300} lang={lang} />
            </div>
            <IconButton
              icon="delete"
              label={t('library.removeStep', { n: i + 1 })}
              onClick={() => {
                setSteps(steps.filter((_, j) => j !== i))
                setDirty(true)
              }}
            />
          </li>
        ))}
      </RowList>
      {steps.length < 6 && (
        <Button variant="text" icon="add" onClick={() => setSteps([...steps, blank()])}>
          {t('library.addStep')}
        </Button>
      )}
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button variant="outlined" busy={busy === 'save'} disabled={!dirty || ready.length === 0} onClick={() => void run('save', () => save(ready))}>
          {t('library.saveSteps')}
        </Button>
        <Button
          icon="verified"
          busy={busy === 'sign'}
          disabled={ready.length === 0}
          disabledReason={ready.length === 0 ? t('library.noSteps') : undefined}
          onClick={() => setConfirming(true)}
        >
          {t('library.signOff')}
        </Button>
      </div>
      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title={t('library.signOffTitle', { n: version.number })}
        actions={
          <>
            <Button variant="outlined" onClick={() => setConfirming(false)}>
              {t('action.cancel')}
            </Button>
            <Button
              onClick={() => {
                setConfirming(false)
                void run('sign', () => signOff(dirty ? ready : null))
              }}
            >
              {t('library.signOffConfirm')}
            </Button>
          </>
        }
      >
        {t('library.signOffBody')}
      </Dialog>
    </div>
  )
}
