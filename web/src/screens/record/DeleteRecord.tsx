/* Hallmark · component: delete this record · genre: modern-minimal · theme: design.md. Privacy, 16 Oct (build-notes/34-privacy.md).
 * The quiet third action at the foot of the record: a text button that opens a short confirm sheet (an irreversible act), whose
 * primary is the red discard. On success the supervisor lands on the Records list (silent success: no toast).
 * states: default · hover · focus-visible · active · disabled n/a · loading (the sheet's Delete is busy) · error (the sheet says the
 *         record was not deleted, and stays open for another try) · success (Records).
 */
import { useState } from 'react'
import { useLocation } from 'wouter'
import { api } from '../../api/endpoints.ts'
import { useT } from '../../i18n/index.tsx'
import { Button } from '../../ui/Button.tsx'
import { Dialog } from '../../ui/Dialog.tsx'

export function DeleteRecord({ briefingId }: { briefingId: string }) {
  const t = useT()
  const [, navigate] = useLocation()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const remove = async () => {
    setBusy(true)
    setFailed(false)
    try {
      await api.deleteBriefing(briefingId)
      setOpen(false)
      navigate('/records', { replace: true })
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Button variant="text" icon="delete" onClick={() => setOpen(true)}>
        {t('privacy.deleteRecord')}
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={t('privacy.deleteTitle')}
        actions={
          <>
            <Button variant="outlined" onClick={() => setOpen(false)}>
              {t('action.cancel')}
            </Button>
            <Button variant="error" icon="delete" busy={busy} status={failed ? 'error' : undefined} onClick={() => void remove()}>
              {t('privacy.deleteConfirm')}
            </Button>
          </>
        }
      >
        <p>{t('privacy.deleteBody')}</p>
        {failed && (
          <p role="alert" className="mt-3 text-body-md text-error">
            {t('privacy.deleteFailed')}
          </p>
        )}
      </Dialog>
    </>
  )
}
