import { useEffect } from 'react'
import { useLocation } from 'wouter'
import { CUSTOM_TASK_ID, langNative, taskIcon, useCatalog } from '../api/catalog.tsx'
import type { SiteId } from '../api/types.ts'
import { CUSTOM_SOP_MAX, CUSTOM_SOP_MIN, CUSTOM_TITLE_MIN, customSopValid, defaultDraft, patchDraft, setDraft, useDraft } from '../flow/draft.ts'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { siteContext, siteName, taskTitle } from '../i18n/catalogText.ts'
import { asUiLang, useLangName, useSopLabel, useT, useUiLang } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { Button } from '../ui/Button.tsx'
import { Card, Section } from '../ui/Card.tsx'
import { ChoiceChips, RadioCard, SegmentedButton } from '../ui/Choice.tsx'
import { ErrorState, Skeleton } from '../ui/Feedback.tsx'
import { Icon } from '../ui/Icon.tsx'
import { TextArea, TextField } from '../ui/TextField.tsx'

function StartSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true">
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  )
}

export function StartScreen() {
  const t = useT()
  const [, navigate] = useLocation()
  const { lang: uiLang, setLang } = useUiLang()
  const langName = useLangName()
  const sopLabel = useSopLabel()
  const { data: catalog, error, loading, reload } = useCatalog()
  const draft = useDraft()

  useEffect(() => {
    if (catalog && !draft) setDraft(defaultDraft(catalog))
  }, [catalog, draft])

  const frame = { step: 'start', title: t('start.title'), subtitle: t('start.subtitle'), context: false, leaveTo: '/' } as const

  if (error && !catalog) {
    return (
      <FlowFrame {...frame}>
        <ErrorState title={t('error.load')} message={apiErrorText(t, error)} retryLabel={t('action.retry')} onRetry={reload} />
      </FlowFrame>
    )
  }
  if (loading || !catalog || !draft) {
    return (
      <FlowFrame {...frame}>
        <StartSkeleton />
      </FlowFrame>
    )
  }

  const site = catalog.sites.find((s) => s.id === draft.siteId) ?? catalog.sites[0]
  const isCustom = draft.taskId === CUSTOM_TASK_ID

  const chooseSite = (id: SiteId) => {
    const next = catalog.sites.find((s) => s.id === id)
    if (!next) return
    patchDraft({ siteId: id, supervisorLang: next.defaultSupervisorLanguage, workerLang: next.defaultWorkerLanguage })
    setLang(asUiLang(next.defaultSupervisorLanguage))
  }

  return (
    <FlowFrame
      {...frame}
      wide
      primary={
        <Button size="lg" trailingIcon="arrow_forward" disabled={!customSopValid(draft)} onClick={() => navigate('/new/instruction')}>
          {t('action.continue')}
        </Button>
      }
    >
      <div className="grid gap-10 lg:grid-cols-[22rem_1fr] lg:gap-12">
        <div className="space-y-8">
          <Section title={t('start.site')} id="start-site">
            <SegmentedButton<SiteId>
              label={t('start.site')}
              value={draft.siteId}
              onChange={chooseSite}
              options={catalog.sites.map((s) => ({ value: s.id, label: siteName(s, uiLang) }))}
            />
            {site && <p className="text-body-md text-on-surface-variant">{siteContext(site, uiLang)}</p>}
          </Section>

          {site && (
            <Section title={t('start.languages')} id="start-langs">
              <div className="space-y-5">
                <div className="space-y-2">
                  <p className="text-title-sm text-on-surface-variant">{t('start.youSpeak')}</p>
                  <ChoiceChips
                    label={t('start.youSpeak')}
                    value={draft.supervisorLang}
                    onChange={(supervisorLang) => {
                      patchDraft({ supervisorLang })
                      setLang(asUiLang(supervisorLang))
                    }}
                    options={site.supervisorLanguages.map((l) => ({ value: l, label: langNative(catalog, l), lang: l }))}
                  />
                </div>
                <div className="space-y-2">
                  <p className="text-title-sm text-on-surface-variant">{t('start.workerHears')}</p>
                  <ChoiceChips
                    label={t('start.workerHears')}
                    value={draft.workerLang}
                    onChange={(workerLang) => patchDraft({ workerLang })}
                    options={site.workerLanguages.map((l) => ({
                      value: l,
                      label: langNative(catalog, l),
                      // The native name already says it when both are the same word (தமிழ், 中文).
                      sublabel: langName(l) === langNative(catalog, l) ? undefined : langName(l),
                      lang: l,
                    }))}
                  />
                </div>
              </div>
            </Section>
          )}
        </div>

        <Section title={t('start.task')} hint={t('start.taskHint')} id="start-task">
          <div role="radiogroup" aria-labelledby="start-task" className="grid gap-3 sm:grid-cols-2">
            {catalog.tasks.map((task) => (
              <RadioCard
                key={task.id}
                name="task"
                value={task.id}
                checked={draft.taskId === task.id}
                onChange={() => patchDraft({ taskId: task.id })}
                icon={<Icon name={taskIcon(task.icon)} />}
                title={taskTitle(task, draft.supervisorLang)}
                subtitle={sopLabel(task.sop)}
                lang={draft.supervisorLang}
              />
            ))}
            <RadioCard
              name="task"
              value={CUSTOM_TASK_ID}
              checked={isCustom}
              onChange={() => patchDraft({ taskId: CUSTOM_TASK_ID })}
              icon={<Icon name="content_paste" />}
              title={t('start.custom.title')}
              subtitle={t('start.custom.sub')}
            />
          </div>

          {isCustom && (
            <Card variant="filled" className="animate-fade-in space-y-4 p-4 sm:p-5">
              <TextField
                label={t('start.custom.name')}
                value={draft.customTitle}
                onChange={(customTitle) => patchDraft({ customTitle })}
                maxLength={120}
                lang={draft.supervisorLang}
                error={draft.customTitle && draft.customTitle.trim().length < CUSTOM_TITLE_MIN ? t('start.custom.nameShort') : undefined}
              />
              <TextArea
                label={t('start.custom.sop')}
                value={draft.customSop}
                onChange={(customSop) => patchDraft({ customSop })}
                rows={6}
                maxLength={CUSTOM_SOP_MAX}
                lang={draft.supervisorLang}
                helper={t('start.custom.sopHint', { min: CUSTOM_SOP_MIN })}
              />
            </Card>
          )}
        </Section>
      </div>
    </FlowFrame>
  )
}
