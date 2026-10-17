/* Hallmark · component: the supervisor's handover choices (Live or Turn, stored sample answers) · genre: modern-minimal · macrostructure:
 * Workbench (hairline-divided rows in one card) · theme: design.md. Supervisor language: it is the step before the phone changes hands.
 * states: mode chips (default · hover · focus-visible · active · selected); sample checkbox (default · hover · focus-visible · checked ·
 *         disabled with its visible reason · loading (looking for a sample)). error / success: n/a (the choices cannot fail here).
 */
import { useId } from 'react'
import { useT, useUiLang } from '../../i18n/index.tsx'
import { Card, RowList } from '../../ui/Card.tsx'
import { ChoiceChips } from '../../ui/Choice.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'
import { signalHint } from '../../net/connection.ts'
import { useSignalQuality } from '../../net/useSignal.ts'
import type { SampleChoice } from './sample.ts'
import type { RunMode } from './useBriefingRun.ts'

/** 2026-10-16 signal: a weak or missing signal, as the browser reports it, said under the mode choice. Never blocks anything. */
function SignalHint({ mode }: { mode: RunMode }) {
  const t = useT()
  const hint = signalHint(useSignalQuality(), mode)
  if (!hint) return null
  return (
    <p role="status" className="flex items-start gap-2 text-body-md text-on-surface">
      <Icon name="link_off" className="mt-px text-[1.125rem]" />
      <span className="min-w-0">{t(hint)}</span>
    </p>
  )
}

interface Props {
  mode: RunMode
  onMode: (mode: RunMode) => void
  sample: SampleChoice
  sampleOn: boolean
  onSampleOn: (on: boolean) => void
  /** The worker language's name in the UI language ("Tamil"), for "Nobody needs to speak Tamil". */
  workerName: string
  /** False for a worker language Google's Live table does not list (liveLanguages.ts): the briefing starts turn by turn. */
  liveListed?: boolean
}

/**
 * The honest line under the sample choice: when every question has a stored sample, that nobody needs to speak the worker's
 * language; otherwise which questions have one and that the worker answers the rest by voice. Always: it is a synthetic voice,
 * and the result marks it.
 */
export function SampleNote({ sample, workerName }: { sample: SampleChoice; workerName: string }) {
  const t = useT()
  const { lang } = useUiLang()
  if (sample.kind === 'loading') return <>{t('brief.sample.checking')}</>
  if (sample.kind === 'none') return <>{t('brief.sample.none')}</>
  const many = sample.numbers.length > 1
  const list = new Intl.ListFormat(lang, { type: 'conjunction' }).format(sample.numbers.map(String))
  const which = sample.all ? t('brief.sample.all', { lang: workerName }) : t(many ? 'brief.sample.hasMany' : 'brief.sample.has', { list })
  const tail = sample.all ? [] : [t(sample.stepsLeft ? 'brief.sample.stepsLeft' : 'brief.sample.rest')]
  const sentences = [which, t(many ? 'brief.sample.syntheticMany' : 'brief.sample.synthetic'), ...tail]
  return <>{sentences.join(lang === 'zh' ? '' : ' ')}</> // Chinese sentences follow each other with no space
}

export function HandoverForm({ mode, onMode, sample, sampleOn, onSampleOn, workerName, liveListed }: Props) {
  const t = useT()
  const noteId = useId()
  const available = sample.kind === 'available'
  return (
    <Card as="section" aria-label={t('brief.title')}>
      <RowList as="div">
        <div className="space-y-3 p-4">
          <p className="text-title-md text-on-surface">{t('brief.mode')}</p>
          {/* Chips, not a segmented control: a longer label (Tamil "turn by turn") wraps instead of being cut off at 375 px. */}
          <ChoiceChips<RunMode>
            label={t('brief.mode')}
            value={mode}
            onChange={onMode}
            options={[
              { value: 'live', label: t('brief.mode.live') },
              { value: 'turn', label: t('brief.mode.turn') },
            ]}
          />
          <p className="text-body-md text-on-surface-variant">{t(mode === 'live' ? 'brief.mode.liveHint' : 'brief.mode.turnHint')}</p>
          {liveListed === false && <p className="text-body-md text-on-surface-variant">{t('brief.mode.liveUnlisted', { lang: workerName })}</p>}
          <SignalHint mode={mode} />
        </div>

        <div className="space-y-2 p-4">
          {/* aria-disabled, not disabled: the control stays reachable, so a screen reader hears why it is off (the note is its description). */}
          <label className={cx('state-layer -mx-3 flex min-h-12 items-center gap-3 rounded-md px-3', available ? 'cursor-pointer' : 'cursor-not-allowed')}>
            <input
              type="checkbox"
              checked={available && sampleOn}
              aria-disabled={!available || undefined}
              aria-describedby={noteId}
              onChange={(e) => available && onSampleOn(e.currentTarget.checked)}
              className="size-5 shrink-0 cursor-[inherit] accent-primary"
            />
            <span className={cx('text-title-md', available ? 'text-on-surface' : 'text-outline')}>{t('brief.sample.label')}</span>
          </label>
          <p id={noteId} className="flex items-start gap-2 text-body-md text-on-surface-variant">
            <Icon name="info" className="mt-px text-[1.125rem]" />
            <span className="min-w-0">
              <SampleNote sample={sample} workerName={workerName} />
            </span>
          </p>
        </div>

        <p className="flex items-start gap-3 p-4 text-body-md text-on-surface-variant">
          <Icon name="lock" className="mt-px text-[1.125rem]" />
          <span className="min-w-0">{t('brief.exitInfo')}</span>
        </p>

        <p className="flex items-start gap-3 p-4 text-body-md text-on-surface">
          <Icon name="record_voice_over" className="mt-px text-[1.125rem]" />
          <span className="min-w-0">{t('brief.kind')}</span>
        </p>
      </RowList>
    </Card>
  )
}
