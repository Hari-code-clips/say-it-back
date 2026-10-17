import type { ReactNode } from 'react'
import { useT } from '../../i18n/index.tsx'
import type { IconName } from '../../theme/iconNames.ts'
import { Card } from '../../ui/Card.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { VerdictChip } from '../../ui/VerdictChip.tsx'

// The product in three cards, using the Singapore lead demo: the crane lifting zone, English to Tamil. The worker's words are the
// catalog's round-1 scripted answer (demoScripts `sg-lead`): the right words for the wrong action. Illustrative only (static
// text): it is labelled as an example.

function Beat({ n, icon, title, children }: { n: number; icon: IconName; title: string; children: ReactNode }) {
  return (
    <li className="relative flex gap-4 pb-4 last:pb-0 [&:not(:last-child)]:before:absolute [&:not(:last-child)]:before:left-5 [&:not(:last-child)]:before:top-12 [&:not(:last-child)]:before:bottom-0 [&:not(:last-child)]:before:w-0.5 [&:not(:last-child)]:before:bg-outline-variant">
      <span className="relative z-10 grid size-10 shrink-0 place-items-center rounded-full bg-primary text-title-md text-on-primary" aria-hidden="true">
        {n}
      </span>
      <Card className="min-w-0 flex-1 space-y-3 p-4 sm:p-5">
        <p className="flex items-center gap-2 text-label-lg text-primary">
          <Icon name={icon} className="text-[1.25rem]" />
          {title}
        </p>
        {children}
      </Card>
    </li>
  )
}

export function Storyboard() {
  const t = useT()
  return (
    <section aria-labelledby="story-title" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="story-title" className="text-title-lg">
          {t('landing.how')}
        </h2>
        <StatusChip icon="info">{t('landing.example')}</StatusChip>
      </div>
      <ol className="space-y-0">
        <Beat n={1} icon="record_voice_over" title={t('landing.s1.label')}>
          <p className="text-title-md text-on-surface">“{t('landing.s1.text')}”</p>
        </Beat>
        <Beat n={2} icon="hearing" title={t('landing.s2.label')}>
          <p lang={t('landing.s2.lang')} className="script-text text-title-lg text-on-surface">
            “{t('landing.s2.text')}”
          </p>
          <p className="text-body-lg text-on-surface-variant">“{t('landing.s2.tr')}”</p>
        </Beat>
        <Beat n={3} icon="fact_check" title={t('landing.s3.label')}>
          <ul className="space-y-2">
            <li className="flex flex-col items-start gap-1">
              <VerdictChip verdict="contradicted" />
              <span className="min-w-0 text-body-lg">{t('landing.s3.wrong')}</span>
            </li>
            <li className="flex flex-col items-start gap-1">
              <VerdictChip verdict="missed" />
              <span className="min-w-0 text-body-lg">{t('landing.s3.miss')}</span>
            </li>
            <li className="flex flex-col items-start gap-1">
              <StatusChip tone="warning" icon="description">
                {t('steps.sopOnly')}
              </StatusChip>
              <span className="min-w-0 text-body-lg">{t('landing.s3.sop')}</span>
            </li>
          </ul>
          <p className="flex flex-wrap items-center gap-2 border-t border-outline-variant pt-3 text-body-lg">
            <Icon name="gavel" className="text-primary" />
            {t('landing.s4')}
          </p>
        </Beat>
      </ol>
    </section>
  )
}
