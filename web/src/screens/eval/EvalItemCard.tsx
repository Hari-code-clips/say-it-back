import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { findTask, langNative, taskIcon, useCatalog } from '../../api/catalog.tsx'
import { IS_MOCK } from '../../api/client.ts'
import { api } from '../../api/endpoints.ts'
import type { EvalItem, EvalTryResult, Verdict } from '../../api/types.ts'
import { taskTitle } from '../../i18n/catalogText.ts'
import { useT, useUiLang } from '../../i18n/index.tsx'
import { apiErrorText } from '../../lib/apiError.ts'
import { dailyLimit } from '../../lib/dailyLimit.ts'
import { formatDate } from '../../lib/format.ts'
import { Button } from '../../ui/Button.tsx'
import { Card } from '../../ui/Card.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { ClipPlayer } from '../../ui/ClipPlayer.tsx'
import { cx } from '../../ui/cx.ts'
import { ElapsedHint } from '../../ui/ElapsedHint.tsx'
import { Banner } from '../../ui/Feedback.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { FlagChip, VerdictChip } from '../../ui/VerdictChip.tsx'
import { transcriptNote } from '../result/verdict.ts'
import { noiseLabel, patternLabel, sourceLabel, stepText } from './labels.ts'
import { liveView, type ResultView, type StoredResult } from './storedResult.ts'

type TryState = { status: 'idle' } | { status: 'running' } | { status: 'error'; message: string } | { status: 'done'; result: EvalTryResult }

/** The check's result on a clip, from a live try or from the stored evaluation run (src/screens/eval/storedResult.ts). */
function TryResult({ item, view }: { item: EvalItem; view: ResultView }) {
  const t = useT()
  const { lang } = useUiLang()
  const stepIds = Object.keys(item.gold)
  const predicted = (id: string): Verdict | undefined => view.verdicts[id]
  const allAgree = stepIds.every((id) => view.agreement[id])
  const flags = view.flags

  return (
    <div className="animate-fade-in space-y-4" aria-live="polite">
      {view.unsafe ? (
        <Banner tone="error" title={t('eval.unsafe')} live="assertive">
          {t('eval.unsafeHint')}
        </Banner>
      ) : allAgree ? (
        <Banner tone="success" title={t('eval.agrees')} />
      ) : (
        <Banner tone="warning" title={t('eval.differs')}>
          {t('eval.differsHint')}
        </Banner>
      )}

      {/* One row per step: its text, then the person's label and the checker's, wrapping on a narrow phone (no table to scroll). */}
      <ul className="space-y-2" aria-label={t('eval.compare')}>
        {stepIds.map((id) => {
          const gold = item.gold[id]
          const pred = predicted(id)
          const ok = view.agreement[id]
          const ev = view.evidence[id]
          return (
            <li key={id} className="space-y-2 rounded-md bg-surface-container-low px-3 py-2">
              <p lang="en" className="text-title-sm text-on-surface">
                {stepText(t, item, id)}
              </p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-label-lg text-on-surface-variant">{t('eval.gold')}</span>
                  {gold && <VerdictChip verdict={gold} />}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-label-lg text-on-surface-variant">{t('eval.prediction')}</span>
                  {pred ? <VerdictChip verdict={pred} /> : <span className="text-body-md text-on-surface-variant">-</span>}
                </span>
                <span className="inline-flex items-center gap-1 text-label-lg">
                  <Icon name={ok ? 'check_circle' : 'cancel'} filled className={ok ? 'text-success' : 'text-error'} />
                  {ok ? t('eval.same') : t('eval.differ')}
                </span>
              </div>
              {/* The worker's own words for this step, in their language, then the English translation and the reason. */}
              {ev?.quote && (
                <p lang={item.workerLang} className="script-text text-body-lg text-on-surface">
                  “{ev.quote}”
                </p>
              )}
              {ev?.quoteTranslation && (
                <p lang="en" className="script-text text-body-md text-on-surface-variant">
                  “{ev.quoteTranslation}”
                </p>
              )}
              {ev?.reason && (
                <p lang="en" className="text-body-md text-on-surface-variant">
                  <span className="text-label-lg">{t('result.why')} </span>
                  {ev.reason}
                </p>
              )}
            </li>
          )
        })}
      </ul>

      {(view.original !== undefined || view.translation || transcriptNote(view.flags)) && (
        <div className="space-y-1 rounded-md bg-surface-container px-4 py-3">
          <p className="text-label-lg text-on-surface-variant">{t('eval.transcript')}</p>
          {transcriptNote(view.flags) ? (
            <p className="text-body-lg text-on-surface">{t(transcriptNote(view.flags)!)}</p>
          ) : (
            view.original !== undefined && (
              <p lang={item.workerLang} className="script-text text-title-md">
                {view.original || '-'}
              </p>
            )
          )}
          {view.translation && (
            <p lang="en" className={cx('script-text', view.original === undefined ? 'text-title-md text-on-surface' : 'text-body-md text-on-surface-variant')}>
              {view.translation}
            </p>
          )}
        </div>
      )}

      {flags.length > 0 && (
        <div className="flex flex-wrap gap-2" lang={lang}>
          {flags.map((f) => (
            <FlagChip key={f} flag={f} />
          ))}
        </div>
      )}

      {view.passes && (
        <details className="group">
          <summary className="state-layer inline-flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-full px-3 text-label-lg text-primary">
            <Icon name="expand_more" className="transition-transform group-open:rotate-180" />
            {t('eval.passes')}
          </summary>
          <ul className="mt-2 grid gap-2">
            {stepIds.map((id) => {
              const a = view.passes?.a[id]
              const b = view.passes?.b[id]
              return (
                <li key={id} className="flex flex-wrap items-center gap-2 rounded-md bg-surface-container-low px-3 py-2">
                  <span lang="en" className="w-full text-title-sm">
                    {stepText(t, item, id)}
                  </span>
                  <span className="text-label-lg text-on-surface-variant">A</span>
                  {a && <VerdictChip verdict={a} />}
                  <span className="text-label-lg text-on-surface-variant">B</span>
                  {b && <VerdictChip verdict={b} />}
                </li>
              )
            })}
          </ul>
        </details>
      )}
    </div>
  )
}

interface Props {
  item: EvalItem
  /** Run the check as soon as the card appears ("Try a sample answer"). */
  autoRun?: boolean
  /** A list item (the Eval grid) or a plain card (the Sample page). */
  as?: 'li' | 'div'
  /** v0.5.1: this clip's result in the stored evaluation run, shown at once; the live check becomes the second action. */
  stored?: StoredResult | null
}

/** One labelled test clip: play it, run the real check on it, compare gold with the prediction. */
export function EvalItemCard({ item, autoRun, as = 'li', stored }: Props) {
  const t = useT()
  const { lang } = useUiLang()
  const { data: catalog } = useCatalog()
  const [state, setState] = useState<TryState>({ status: 'idle' })
  const started = useRef(false)
  const task = findTask(catalog, item.taskId)

  const limitReached = useSyncExternalStore(dailyLimit.subscribe, dailyLimit.reached)
  // The stored result stands until a live run is asked for; then the live one replaces it.
  const showStored = Boolean(stored) && state.status === 'idle'
  const run = async () => {
    if (dailyLimit.reached()) return
    setState({ status: 'running' })
    try {
      setState({ status: 'done', result: await api.evalTry(item.id) })
    } catch (e) {
      setState({ status: 'error', message: apiErrorText(t, e) })
    }
  }

  useEffect(() => {
    if (autoRun && !started.current) {
      started.current = true
      void run()
    }
  }, [autoRun]) // run() is stable enough: the ref guard makes this fire once

  return (
    <Card as={as} className="min-w-0 space-y-4 p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone="primary" icon={taskIcon(task?.icon)}>
          {(task && taskTitle(task, lang)) || item.taskId}
        </StatusChip>
        <StatusChip lang={item.workerLang}>{langNative(catalog, item.workerLang)}</StatusChip>
        <StatusChip>{patternLabel(t, item.pattern)}</StatusChip>
        <StatusChip>{noiseLabel(t, item.noise)}</StatusChip>
        <StatusChip tone={item.source === 'recorded' ? 'success' : 'neutral'} icon={item.source === 'recorded' ? 'mic' : 'graphic_eq'}>
          {sourceLabel(t, item.source)}
        </StatusChip>
      </div>

      {item.questionText && (
        <p className="text-body-lg text-on-surface">
          <span className="text-label-lg text-on-surface-variant">{t('eval.question')} </span>
          <span lang="en">{item.questionText}</span>
        </p>
      )}

      {item.answerGloss && (
        <p className="script-text text-body-lg text-on-surface">
          <span className="text-label-lg text-on-surface-variant">{t('eval.gloss')} </span>“{item.answerGloss}”
        </p>
      )}

      <div className="space-y-2" role="group" aria-label={t('eval.goldLabels')}>
        <p className="text-label-lg text-on-surface-variant">{t('eval.goldLabels')}</p>
        <ul className="space-y-1.5">
          {Object.entries(item.gold).map(([id, v]) => (
            <li key={id} className="flex flex-wrap items-center gap-2">
              <VerdictChip verdict={v} />
              <span lang="en" className="min-w-0 text-body-md text-on-surface">
                {stepText(t, item, id)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {item.hasAudio !== false && <ClipPlayer load={() => api.evalAudio(item.id)} playLabel={t('eval.listen')} stopLabel={t('result.stop')} />}
        {/* After a 429 daily_limit no try can succeed before 00:00 UTC: the page shows DailyLimitNotice instead. */}
        <Button
          icon="fact_check"
          variant={showStored ? 'outlined' : 'filled'}
          busy={state.status === 'running'}
          disabled={item.hasAudio === false || limitReached}
          onClick={() => void run()}
        >
          {state.status === 'done' ? t('eval.again') : showStored ? t('sample.liveAgain') : t('eval.try')}
        </Button>
      </div>

      {state.status === 'running' && (
        <div role="status" aria-atomic="false" className="space-y-2 text-body-md text-on-surface-variant">
          <p>{t('eval.running')}</p>
          <ElapsedHint />
        </div>
      )}
      {state.status === 'error' && (
        <Banner tone="error" title={t('eval.failed')} live="assertive">
          {state.message}
        </Banner>
      )}
      {showStored && stored && (
        <section aria-labelledby={`stored-${item.id}`} className="space-y-4">
          <div className="flex items-start gap-3 rounded-md bg-secondary-container px-4 py-3 text-on-secondary-container">
            <Icon name="history" className="mt-0.5 text-[1.25rem]" />
            <div className="min-w-0 space-y-0.5">
              <p id={`stored-${item.id}`} className="text-title-sm">
                {t(IS_MOCK ? 'sample.storedMock' : 'sample.stored', { date: formatDate(stored.generatedAt, lang) })}
              </p>
              {/* The models that judged it; the mock report names none, and its label already says no model ran. */}
              {!IS_MOCK && (
                <p lang="en" className="break-words text-body-md">
                  {Object.entries(stored.models)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(' · ')}
                </p>
              )}
            </div>
          </div>
          <TryResult item={item} view={stored.view} />
        </section>
      )}
      {state.status === 'done' && <TryResult item={item} view={liveView(state.result)} />}
    </Card>
  )
}
