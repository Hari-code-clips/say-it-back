/* Hallmark · page: /privacy · genre: modern-minimal · macrostructure: Long Document (one column, 60–65ch, headings inline,
 * negative space as the divider) · theme: design.md. Privacy, 16 Oct (build-notes/34-privacy.md).
 * What is collected, where it is stored and processed, how long it is kept, deletion, the worker's consent, and how the design is
 * meant to support Singapore's PDPA and India's DPDP Act. Honest wording: "designed to support", never "compliant"; no legal claim.
 * Supervisor language (the UI language). Linked from About and the landing page's footer line.
 * states: default only (static text: no loading, error, empty or disabled state; links have their own focus-visible and hover).
 */
import { useT, type StringKey } from '../i18n/index.tsx'
import { AppShell } from '../shell/AppShell.tsx'
import { PageHeading } from '../ui/PageHeading.tsx'

/** Each part of the page: its heading and its paragraphs, in reading order. */
export const PRIVACY_SECTIONS: { id: string; title: StringKey; body: StringKey[] }[] = [
  { id: 'collect', title: 'privacy.collect.title', body: ['privacy.collect.body', 'privacy.collect.never', 'privacy.collect.audio', 'privacy.collect.device'] },
  { id: 'where', title: 'privacy.where.title', body: ['privacy.where.body', 'privacy.where.transfer'] },
  { id: 'keep', title: 'privacy.keep.title', body: ['privacy.keep.body'] },
  { id: 'delete', title: 'privacy.delete.title', body: ['privacy.delete.body'] },
  { id: 'consent', title: 'privacy.consent.title', body: ['privacy.consent.body', 'privacy.consent.decline', 'privacy.consent.samples'] },
  { id: 'law', title: 'privacy.law.title', body: ['privacy.law.body', 'privacy.law.limits'] },
]

export function PrivacyScreen() {
  return (
    <AppShell>
      <PrivacyArticle />
    </AppShell>
  )
}

/** The page's one column (the shell is the app's own). */
export function PrivacyArticle() {
  const t = useT()
  return (
    <>
      <article className="mx-auto max-w-[65ch] space-y-8">
        <PageHeading title={t('privacy.title')} subtitle={t('privacy.subtitle')} documentTitle={t('privacy.docTitle')} />
        {PRIVACY_SECTIONS.map((s) => (
          <section key={s.id} aria-labelledby={`privacy-${s.id}`} className="space-y-3">
            <h2 id={`privacy-${s.id}`} className="text-title-lg text-on-surface">
              {t(s.title)}
            </h2>
            {s.body.map((key) => (
              <p key={key} className="break-words text-body-lg text-on-surface">
                {t(key)}
              </p>
            ))}
          </section>
        ))}
      </article>
    </>
  )
}
