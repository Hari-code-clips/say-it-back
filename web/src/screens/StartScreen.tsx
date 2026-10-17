import { useEffect } from 'react'
import { useLocation } from 'wouter'
import { CUSTOM_TASK_ID, langNative, taskIcon, useCatalog } from '../api/catalog.tsx'
import type { SiteId, SopRef } from '../api/types.ts'
import { CUSTOM_SOP_MAX, CUSTOM_SOP_MIN, CUSTOM_TITLE_MIN, defaultDraft, patchDraft, setDraft, taskPatch, useDraft } from '../flow/draft.ts'
import { FlowFrame } from '../flow/FlowFrame.tsx'
import { siteContext, siteName, taskTitle } from '../i18n/catalogText.ts'
import { asUiLang, useLangName, useSopLabel, useT, useUiLang } from '../i18n/index.tsx'
import { apiErrorText } from '../lib/apiError.ts'
import { Button } from '../ui/Button.tsx'
import { Section } from '../ui/Card.tsx'
import { ChoiceChips, SegmentedButton } from '../ui/Choice.tsx'
import { ErrorState, Skeleton } from '../ui/Feedback.tsx'
import { Icon } from '../ui/Icon.tsx'
import { TextArea, TextField } from '../ui/TextField.tsx'
import { PermitBlock } from './start/PermitBlock.tsx'
import { startNeed } from './start/startGate.ts'
import { TaskPicker, type TaskOption } from './start/TaskPicker.tsx'
import { domainKey } from './start/taskPickerState.ts'
import { LibraryPick } from './start/LibraryPick.tsx'

const chooseSopRef = (sopRef: SopRef | null) => patchDraft({ sopRef }) // module level: a stable callback for LibraryPick

/* Hallmark · screen: start · genre: modern-minimal · macrostructure: Workbench · theme: design.md
 * Order: the task, the permit-to-work right under it, then the site and the two languages (every one has a default, so the lead demo
 * runs if nothing is touched). A disabled Continue says what is missing. No context line: there is no briefing yet.
 * states: loading (skeleton) · error (retry) · default · invalid (the bar names what is missing) · success (navigates).
 */

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
  const need = startNeed(draft)

  const chooseSite = (id: SiteId) => {
    const next = catalog.sites.find((s) => s.id === id)
    if (!next) return
    patchDraft({ siteId: id, supervisorLang: next.defaultSupervisorLanguage, workerLang: next.defaultWorkerLanguage, sopRef: null })
    setLang(asUiLang(next.defaultSupervisorLanguage))
  }

  // 17 Oct: one heading per work domain, in the UI language; a server that sends no domains gets the list as it was.
  const grouped = catalog.tasks.some((task) => task.domain)
  const domainHeading = (domain: string | undefined) => {
    const key = domain ? domainKey(domain) : undefined
    return key ? t(key) : domain
  }
  const tasks: TaskOption[] = [
    ...catalog.tasks.map((task) => ({
      value: task.id,
      icon: <Icon name={taskIcon(task.icon)} />,
      title: taskTitle(task, draft.supervisorLang),
      subtitle: sopLabel(task.sop),
      lang: draft.supervisorLang,
      group: domainHeading(task.domain),
    })),
    {
      value: CUSTOM_TASK_ID,
      icon: <Icon name="content_paste" />,
      title: t('start.custom.title'),
      subtitle: t('start.custom.sub'),
      group: grouped ? t('domain.own') : undefined,
    },
  ]

  return (
    <FlowFrame
      {...frame}
      wide
      primary={
        <Button
          size="lg"
          trailingIcon="arrow_forward"
          disabled={need !== null}
          disabledReason={need ? t(need.key, need.values) : undefined}
          onClick={() => navigate('/new/instruction')}
        >
          {t('action.continue')}
        </Button>
      }
    >
      {/* One column on a phone, in this order: task, permit, site, languages. From 1200 px the task list has the left column and the permit,
          site and languages stack in the right one, so the permit is on the first screen there too. */}
      <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:grid-rows-[auto_auto_1fr]">
        <div className="min-w-0 lg:col-start-1 lg:row-span-3 lg:row-start-1">
          <Section title={t('start.task')} hint={t('start.taskHint')} id="start-task">
            <TaskPicker labelledBy="start-task" value={draft.taskId} onChange={(taskId) => patchDraft(taskPatch(catalog, taskId))} options={tasks} />
            {/* Library (16 Oct): the site's SOP library, and a signed-off version of this task's SOP to start from. */}
            {!isCustom && (
              <LibraryPick siteId={draft.siteId} taskId={draft.taskId} lang={draft.supervisorLang} value={draft.sopRef ?? null} onChange={chooseSopRef} />
            )}

            {isCustom && (
              <div className="animate-fade-in space-y-4 pt-2">
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
              </div>
            )}
          </Section>
        </div>

        {/* v0.5.2: the permit-to-work this briefing is for, optional and off by default. */}
        <div className="min-w-0 lg:col-start-2 lg:row-start-1">
          <PermitBlock draft={draft} />
        </div>

        <div className="lg:col-start-2 lg:row-start-2">
          <Section title={t('start.site')} id="start-site">
            <SegmentedButton<SiteId>
              label={t('start.site')}
              value={draft.siteId}
              onChange={chooseSite}
              options={catalog.sites.map((s) => ({ value: s.id, label: siteName(s, uiLang) }))}
            />
            {site && <p className="text-body-md text-on-surface-variant">{siteContext(site, uiLang)}</p>}
          </Section>
        </div>

        <div className="lg:col-start-2 lg:row-start-3">
          {site && (
            <Section title={t('start.languages')} id="start-langs">
              <div className="space-y-5">
                <div className="space-y-2">
                  <p className="text-title-sm text-on-surface-variant">{t('start.youSpeak')}</p>
                  <ChoiceChips
                    label={t('start.youSpeak')}
                    value={draft.supervisorLang}
                    onChange={(supervisorLang) => {
                      patchDraft({ supervisorLang, sopRef: null })
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
                    options={[
                      ...site.workerLanguages.map((l) => ({
                        value: l,
                        label: langNative(catalog, l),
                        // The native name already says it when both are the same word (தமிழ், 中文).
                        sublabel: langName(l) === langNative(catalog, l) ? undefined : langName(l),
                        lang: l,
                      })),
                      // 16 Oct breadth: offered last and named for what it is, in the supervisor's language.
                      ...(site.evaluatorLanguages ?? []).map((l) => ({ value: l, label: t('breadth.evaluatorLang', { lang: langName(l) }), lang: uiLang })),
                    ]}
                  />
                  {site.evaluatorLanguages?.includes(draft.workerLang) && (
                    <p className="text-body-md text-on-surface-variant">{t('breadth.evaluatorNote', { lang: langName(draft.workerLang) })}</p>
                  )}
                </div>
              </div>
            </Section>
          )}
        </div>
      </div>
    </FlowFrame>
  )
}
