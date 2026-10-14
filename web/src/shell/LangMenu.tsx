import { useRef } from 'react'
import { UI_LANGS, useT, useUiLang, type UiLang } from '../i18n/index.tsx'
import { cx } from '../ui/cx.ts'
import { Icon } from '../ui/Icon.tsx'

const NATIVE: Record<UiLang, string> = { en: 'English', ta: 'தமிழ்', zh: '中文' }
const TAGS: Record<UiLang, string> = { en: 'en', ta: 'ta', zh: 'zh-CN' }

/** UI language switcher on the native Popover API: light dismiss and Esc come from the browser. */
export function LangMenu() {
  const t = useT()
  const { lang, setLang } = useUiLang()
  const menu = useRef<HTMLDivElement>(null)

  return (
    <div className="relative">
      <button
        type="button"
        popoverTarget="ui-lang-menu"
        aria-label={`${t('nav.language')}: ${NATIVE[lang]}`}
        className="state-layer inline-flex min-h-12 items-center gap-2 rounded-full px-3 text-label-lg text-on-surface-variant"
      >
        <Icon name="translate" />
        <span lang={TAGS[lang]} className="hidden sm:inline">
          {NATIVE[lang]}
        </span>
      </button>
      <div
        ref={menu}
        id="ui-lang-menu"
        popover="auto"
        role="menu"
        aria-label={t('nav.language')}
        className="fixed inset-auto right-4 top-16 m-0 w-48 rounded-md bg-surface-container p-2 text-on-surface shadow-elev-2 sm:right-6"
      >
        {UI_LANGS.map((code) => (
          <button
            key={code}
            type="button"
            role="menuitemradio"
            aria-checked={lang === code}
            lang={TAGS[code]}
            onClick={() => {
              setLang(code)
              menu.current?.hidePopover()
            }}
            className={cx(
              'state-layer flex min-h-12 w-full items-center gap-3 rounded-sm px-3 text-left text-body-lg',
              lang === code && 'bg-secondary-container text-on-secondary-container',
            )}
          >
            <Icon name="check" className={cx('text-[1.125rem]', lang !== code && 'invisible')} />
            {NATIVE[code]}
          </button>
        ))}
      </div>
    </div>
  )
}
