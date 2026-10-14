import { useEffect, useRef, useState } from 'react'
import { findTask, langNative, taskIcon, useCatalog } from '../../api/catalog.tsx'
import { api } from '../../api/endpoints.ts'
import type { EvalItem, EvalTryResult, Verdict } from '../../api/types.ts'
import { taskTitle } from '../../i18n/catalogText.ts'
import { useT, useUiLang } from '../../i18n/index.tsx'
import { apiErrorText } from '../../lib/apiError.ts'
import { Button } from '../../ui/Button.tsx'
import { Card } from '../../ui/Card.tsx'
import { StatusChip } from '../../ui/Chip.tsx'
import { ClipPlayer } from '../../ui/ClipPlayer.tsx'
import { Banner } from '../../ui/Feedback.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { FlagChip, VerdictChip } from '../../ui/VerdictChip.tsx'

type TryState = { status: 'idle' } | { status: 'running' } | { status: 'error'; message: string } | { status: 'done'; result: EvalTryResult }

function TryResult({ item, result }: { item: EvalItem; result: EvalTryResult }) {
  const t = useT()
  const { lang } = useUiLang()
  const stepIds = Object.keys(item.gold)
  const predicted = (id: string): Verdict | undefined => result.round.ratings.find((r) => r.stepId === id)?.verdict
  const allAgree = stepIds.every((id) => result.agreement[id])
  const transcript = result.round.transcripts[0]
  const flags = [...new Set(result.round.ratings.flatMap((r) => r.flags))]

  return (
    <div className="animate-fade-in space-y-4" aria-live="polite">
      {result.unsafe ? (
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

      <table className="w-full border-separate border-spacing-y-2 text-left">
        <caption className="sr-only">{t('eval.compare')}</caption>
        <thead>
          <tr className="text-label-lg text-on-surface-variant">
            <th scope="col" className="pb-1 pr-3 font-medium">
              {t('eval.step')}
            </th>
            <th scope="col" className="pb-1 pr-3 font-medium">
              {t('eval.gold')}
            </th>
            <th scope="col" className="pb-1 pr-3 font-medium">
              {t('eval.prediction')}
            </th>
            <th scope="col" className="pb-1 font-medium">
              <span className="sr-only">{t('eval.match')}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {stepIds.map((id) => {
            const gold = item.gold[id]
            const pred = predicted(id)
            const ok = result.agreement[id]
            return (
              <tr key={id}>
                <th scope="row" className="pr-3 text-title-sm font-medium">
                  {id}
                </th>
                <td className="pr-3">{gold && <VerdictChip verdict={gold} />}</td>
                <td className="pr-3">{pred ? <VerdictChip verdict={pred} /> : <span className="text-body-md text-on-surface-variant">-</span>}</td>
                <td>
                  <span className="inline-flex items-center gap-1 text-label-lg">
                    <Icon name={ok ? 'check_circle' : 'cancel'} filled className={ok ? 'text-success' : 'text-error'} />
                    {ok ? t('eval.same') : t('eval.differ')}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {transcript && (
        <div className="space-y-1 rounded-md bg-surface-container px-4 py-3">
          <p className="text-label-lg text-on-surface-variant">{t('eval.transcript')}</p>
          <p lang={item.workerLang} className="script-text text-title-md">
            {transcript.original || '-'}
          </p>
          {transcript.translation && <p className="script-text text-body-md text-on-surface-variant">{transcript.translation}</p>}
        </div>
      )}

      {flags.length > 0 && (
        <div className="flex flex-wrap gap-2" lang={lang}>
          {flags.map((f) => (
            <FlagChip key={f} flag={f} />
          ))}
        </div>
      )}

      {result.round.passB.length > 0 && (
        <details className="group">
          <summary className="state-layer inline-flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-full px-3 text-label-lg text-primary">
            <Icon name="expand_more" className="transition-transform group-open:rotate-180" />
            {t('eval.passes')}
          </summary>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {stepIds.map((id) => {
              const a = result.round.passA.find((r) => r.stepId === id)
              const b = result.round.passB.find((r) => r.stepId === id)
              return (
                <li key={id} className="flex flex-wrap items-center gap-2 rounded-md bg-surface-container-low px-3 py-2">
                  <span className="text-title-sm">{id}</span>
                  <span className="text-label-lg text-on-surface-variant">A</span>
                  {a && <VerdictChip verdict={a.verdict} />}
                  <span className="text-label-lg text-on-surface-variant">B</span>
                  {b && <VerdictChip verdict={b.verdict} />}
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
}

/** One labelled test clip: play it, run the real check on it, compare gold with the prediction. */
export function EvalItemCard({ item, autoRun }: Props) {
  const t = useT()
  const { lang } = useUiLang()
  const { data: catalog } = useCatalog()
  const [state, setState] = useState<TryState>({ status: 'idle' })
  const started = useRef(false)
  const task = findTask(catalog, item.taskId)

  const run = async () => {
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
    <Card as="li" className="space-y-4 p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone="primary" icon={taskIcon(task?.icon)}>
          {(task && taskTitle(task, lang)) || item.taskId}
        </StatusChip>
        <StatusChip lang={item.workerLang}>{langNative(catalog, item.workerLang)}</StatusChip>
        <StatusChip>{item.pattern}</StatusChip>
        <StatusChip>{item.noise}</StatusChip>
        <StatusChip tone={item.source === 'recorded' ? 'success' : 'neutral'}>{item.source}</StatusChip>
        <span className="text-label-lg text-on-surface-variant">{item.questionId}</span>
      </div>

      {item.answerGloss && (
        <p className="script-text text-body-lg text-on-surface">
          <span className="text-label-lg text-on-surface-variant">{t('eval.gloss')} </span>“{item.answerGloss}”
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t('eval.goldLabels')}>
        <span className="text-label-lg text-on-surface-variant">{t('eval.gold')}</span>
        {Object.entries(item.gold).map(([id, v]) => (
          <span key={id} className="inline-flex items-center gap-1.5">
            <span className="text-label-lg">{id}</span>
            <VerdictChip verdict={v} />
          </span>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <ClipPlayer load={() => api.evalAudio(item.id)} playLabel={t('eval.listen')} stopLabel={t('result.stop')} />
        <Button icon="fact_check" busy={state.status === 'running'} onClick={() => void run()}>
          {state.status === 'done' ? t('eval.again') : t('eval.try')}
        </Button>
      </div>

      {state.status === 'running' && (
        <p role="status" className="text-body-md text-on-surface-variant">
          {t('eval.running')}
        </p>
      )}
      {state.status === 'error' && (
        <Banner tone="error" title={t('eval.failed')} live="assertive">
          {state.message}
        </Banner>
      )}
      {state.status === 'done' && <TryResult item={item} result={state.result} />}
    </Card>
  )
}
