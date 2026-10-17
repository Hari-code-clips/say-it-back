/* Hallmark · screen: SOP library · genre: modern-minimal · macrostructure: Workbench (hairline lists) · theme: design.md
 * /library/:siteId lists the site's SOPs (title, id, newest version, its status chip). /library/:siteId/:sopId shows one SOP: its
 * version history newest first (a whole-row choice), the chosen version's critical steps (read-only once signed off; a draft's are
 * edited in StepsEditor), the SOP text behind a disclosure, and "New version" (a draft that starts from the last signed-off steps).
 * Status chips: Signed off = the blue tint (an informative label, never a verdict colour), Draft = neutral, a catalog seed = neutral.
 * states: loading (skeleton) · error (retry) · empty · default · busy (spinner) · error on a write (snackbar) · success (reload).
 */
import { useState } from 'react'
import { Link } from 'wouter'
import { langNative, useCatalog } from '../../api/catalog.tsx'
import { api } from '../../api/endpoints.ts'
import type { LibraryEntry, LibraryVersion, SiteId, Step } from '../../api/types.ts'
import { siteName } from '../../i18n/catalogText.ts'
import { useT, useUiLang, type StringKey } from '../../i18n/index.tsx'
import { apiErrorText } from '../../lib/apiError.ts'
import { formatDateTime } from '../../lib/format.ts'
import { useAsync } from '../../lib/useAsync.ts'
import { AppShell } from '../../shell/AppShell.tsx'
import { Button } from '../../ui/Button.tsx'
import { Card, RowList, Section } from '../../ui/Card.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { EmptyState, ErrorState, Skeleton } from '../../ui/Feedback.tsx'
import { useFeedback } from '../../ui/FeedbackProvider.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { PageHeading } from '../../ui/PageHeading.tsx'
import { TextArea, TextField } from '../../ui/TextField.tsx'
import { latestVersion, takesNewVersion } from './libraryModel.ts'
import { StepsEditor } from './StepsEditor.tsx'

// Pilot accounts (build-notes/34): only a VITE_AUTH_MODE=firebase build signs in. Without accounts a catalogue SOP takes no new
// version (security fixes A, H3), so "New version" is hidden on it.
const ACCOUNTS = import.meta.env.VITE_AUTH_MODE === 'firebase'

function VersionChip({ version }: { version: LibraryVersion }) {
  const t = useT()
  if (version.status === 'approved') return <StatusChip tone="primary" icon="verified">{t('library.status.approved')}</StatusChip>
  return <StatusChip icon="edit_note">{t('library.status.draft')}</StatusChip>
}

const who = (actor: string): StringKey => `library.who.${actor}` as StringKey

function SopList({ siteId, entries }: { siteId: SiteId; entries: LibraryEntry[] }) {
  const t = useT()
  if (entries.length === 0) return <EmptyState icon="description" title={t('library.empty')} />
  return (
    <Card>
      <RowList>
        {entries.map((entry) => {
          const last = latestVersion(entry)
          return (
            <li key={entry.id}>
              <Link href={`/library/${siteId}/${encodeURIComponent(entry.id)}`} className="state-layer flex items-start gap-4 px-4 py-4 focus-visible:-outline-offset-[3px] sm:px-5">
                <span className="min-w-0 flex-1 space-y-1.5">
                  <span className="block text-title-md text-on-surface">{entry.title}</span>
                  <span className="block text-body-md text-on-surface-variant">
                    {entry.id}
                    {last && ` · ${t('library.version', { n: last.number })}`}
                  </span>
                  {last && (
                    <span className="block pt-1">
                      <VersionChip version={last} />
                    </span>
                  )}
                </span>
                <Icon name="arrow_forward" className="mt-0.5 text-on-surface-variant" />
              </Link>
            </li>
          )
        })}
      </RowList>
    </Card>
  )
}

function NewVersionForm({ entry, onDone }: { entry: LibraryEntry; onDone: (n: number) => void }) {
  const t = useT()
  const feedback = useFeedback()
  const last = latestVersion(entry)
  const [text, setText] = useState(last?.text ?? '')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try {
      const saved = await api.createSopVersion(entry.siteId, entry.id, { text, changeNote: note })
      onDone(latestVersion(saved)?.number ?? 0)
    } catch (err) {
      feedback.snack({ message: apiErrorText(t, err), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="animate-fade-in space-y-4">
      <TextArea label={t('library.text')} value={text} onChange={setText} rows={8} maxLength={8000} lang={last?.lang} />
      <TextField label={t('library.changeNote')} value={note} onChange={setNote} maxLength={300} />
      <Button variant="outlined" icon="edit_note" busy={busy} disabled={!text.trim()} onClick={() => void submit()}>
        {t('library.createDraft')}
      </Button>
    </div>
  )
}

function VersionRow({ version, chosen, onChoose }: { version: LibraryVersion; chosen: boolean; onChoose: () => void }) {
  const t = useT()
  const { lang } = useUiLang()
  return (
    <li>
      <button type="button" aria-pressed={chosen} onClick={onChoose} className="state-layer flex w-full items-start gap-3 px-4 py-4 text-left focus-visible:-outline-offset-[3px] sm:px-5">
        <Icon name={chosen ? 'check_circle' : 'history'} filled={chosen} className={chosen ? 'mt-0.5 text-primary' : 'mt-0.5 text-on-surface-variant'} />
        <span className="min-w-0 flex-1 space-y-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-title-md text-on-surface">{t('library.version', { n: version.number })}</span>
            <VersionChip version={version} />
            {version.readOnly && <StatusChip>{t('library.fromCatalog')}</StatusChip>}
          </span>
          {/* A catalog seed has no real author or sign-off time: its chip says where it comes from, and nothing more. */}
          {!version.readOnly && (
            <span className="block text-body-md text-on-surface-variant">
              {version.approvedBy && version.approvedAt
                ? t('library.signedBy', { who: t(who(version.approvedBy)), when: formatDateTime(version.approvedAt, lang) })
                : t('library.createdBy', { who: t(who(version.createdBy)), when: formatDateTime(version.createdAt, lang) })}
            </span>
          )}
          {version.changeNote && !version.readOnly && <span className="block text-body-md text-on-surface-variant">{version.changeNote}</span>}
        </span>
      </button>
    </li>
  )
}

function StepList({ steps, lang }: { steps: Step[]; lang: string }) {
  return (
    <ol className="divide-y divide-outline-variant rounded-lg border border-outline-variant bg-surface-container-lowest">
      {steps.map((s, i) => (
        <li key={s.id} className="flex gap-3 px-4 py-3">
          <span className="text-title-md text-on-surface-variant tabular-nums">{i + 1}</span>
          <span className="min-w-0 space-y-0.5">
            <span lang={lang} className="block text-body-lg text-on-surface">{s.text}</span>
            {s.hazard && <span lang={lang} className="block text-body-md text-on-surface-variant">{s.hazard}</span>}
          </span>
        </li>
      ))}
    </ol>
  )
}

function SopDetail({ entry, reload }: { entry: LibraryEntry; reload: () => void }) {
  const t = useT()
  const feedback = useFeedback()
  const { data: catalog } = useCatalog()
  const [chosenN, setChosenN] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const newestFirst = [...entry.versions].reverse()
  const chosen = entry.versions.find((v) => v.number === chosenN) ?? newestFirst[0]
  const act = async (work: () => Promise<unknown>) => {
    try {
      await work()
      reload()
    } catch (err) {
      feedback.snack({ message: apiErrorText(t, err), tone: 'error' })
      throw err
    }
  }
  return (
    <div className="space-y-8">
      <Section title={t('library.versions')} id="library-versions">
        <Card>
          <RowList>
            {newestFirst.map((v) => (
              <VersionRow key={v.number} version={v} chosen={v.number === chosen?.number} onChoose={() => setChosenN(v.number)} />
            ))}
          </RowList>
        </Card>
        {takesNewVersion(entry, ACCOUNTS) && !adding && (
          <Button variant="outlined" icon="add" onClick={() => setAdding(true)}>
            {t('library.newVersion')}
          </Button>
        )}
        {adding && (
          <NewVersionForm
            entry={entry}
            onDone={(n) => {
              setAdding(false)
              setChosenN(n)
              reload()
            }}
          />
        )}
      </Section>

      {chosen && (
        <Section
          title={`${t('library.steps')} · ${t('library.version', { n: chosen.number })}`}
          hint={t('library.lang', { lang: langNative(catalog, chosen.lang) })}
          id="library-steps"
        >
          {chosen.status === 'draft' ? (
            <StepsEditor
              key={chosen.number}
              version={chosen}
              lang={chosen.lang}
              save={(steps) => act(() => api.setSopSteps(entry.siteId, entry.id, chosen.number, steps))}
              signOff={(steps) =>
                act(async () => {
                  if (steps) await api.setSopSteps(entry.siteId, entry.id, chosen.number, steps)
                  await api.approveSopVersion(entry.siteId, entry.id, chosen.number)
                })
              }
            />
          ) : (
            <StepList steps={chosen.steps} lang={chosen.lang} />
          )}
          <details className="rounded-lg border border-outline-variant bg-surface-container-lowest px-4 py-3">
            <summary className="min-h-12 cursor-pointer content-center text-title-sm text-on-surface">{t('library.text')}</summary>
            <p lang={chosen.lang} className="whitespace-pre-line pt-2 text-body-md text-on-surface-variant">{chosen.text}</p>
          </details>
        </Section>
      )}
    </div>
  )
}

export function LibraryScreen({ siteId, sopId }: { siteId: string; sopId?: string }) {
  const t = useT()
  const { lang } = useUiLang()
  const { data: catalog } = useCatalog()
  const { data, loading, error, reload } = useAsync(() => api.listSops(siteId), [siteId])
  const site = catalog?.sites.find((s) => s.id === siteId)
  const entry = sopId ? data?.items.find((e) => e.id === decodeURIComponent(sopId)) : undefined
  return (
    <AppShell>
      <div className="mx-auto max-w-3xl space-y-8">
        {sopId && (
          <Link href={`/library/${siteId}`} className="inline-flex min-h-12 items-center gap-2 text-title-sm text-primary underline-offset-4 hover:underline">
            <Icon name="arrow_back" />
            {t('library.back')}
          </Link>
        )}
        <PageHeading
          title={entry ? entry.title : t('library.title')}
          context={entry ? entry.id : site ? siteName(site, lang) : undefined}
          subtitle={entry ? undefined : t('library.subtitle')}
        />
        {loading && !data && (
          <div className="space-y-3" aria-busy="true" aria-label={t('state.loading')}>
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}
        {error && <ErrorState title={t('error.load')} message={apiErrorText(t, error)} retryLabel={t('action.retry')} onRetry={reload} />}
        {data && !sopId && <SopList siteId={siteId as SiteId} entries={data.items} />}
        {data && sopId && (entry ? <SopDetail entry={entry} reload={reload} /> : <EmptyState icon="description" title={t('library.empty')} />)}
        <p className="text-body-md text-on-surface-variant">{t('library.demoNote')}</p>
      </div>
    </AppShell>
  )
}
