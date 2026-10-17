// Catalog text (site names, site descriptions, task titles) in the UI languages. The API catalog
// only carries English (and Tamil task titles); these tables fill the gaps for known ids and
// fall back to whatever the API sent for anything else.
//
// DRAFT: Tamil and Chinese strings need native-speaker review.
import type { CatalogSite, CatalogTask, Lang } from '../api/types.ts'

const TASK_TITLES: Partial<Record<Lang, Record<string, string>>> = {
  zh: {
    'panel-isolation': '打开配电箱',
    'scaffold-harness': '登上脚手架（高处作业）',
    'hot-work': '切割或打磨（动火作业）',
    'lifting-zone': '吊装作业：吊装区',
    'trench-entry': '进入沟槽铺设管道',
    // v0.5: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
    'confined-space': '进入受限空间（检修井）',
    'fragile-roof': '在易碎屋面上作业',
    // 17 Oct demo suites (build-notes/37-domain-suites.md): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
    'hydro-jetting': '船体高压水射流清洗',
    'steam-line-break': '打开蒸汽管线检修（管线打开作业）',
    'press-lockout': '清除冲床卡料（上锁挂牌）',
    'telecom-tower': '攀爬通信塔维修天线',
  },
}

/** Task title in `lang` (the supervisor's language): API text, then the table, then English. */
export function taskTitle(task: Pick<CatalogTask, 'id' | 'title'>, lang: Lang): string {
  return task.title[lang] ?? TASK_TITLES[lang]?.[task.id] ?? task.title.en ?? Object.values(task.title)[0] ?? task.id
}

const SITE_NAMES: Record<string, Partial<Record<string, string>>> = {
  sg: { ta: 'சிங்கப்பூர்', zh: '新加坡' },
  chennai: { ta: 'சென்னை', zh: '金奈' },
}

export const siteName = (site: Pick<CatalogSite, 'id' | 'name'>, uiLang: string): string => SITE_NAMES[site.id]?.[uiLang] ?? site.name

const SITE_CONTEXT: Record<string, Partial<Record<string, string>>> = {
  sg: {
    ta: 'தளத்தின் மொழி ஆங்கிலம். தொழிலாளர்கள் பெரும்பாலும் வங்கதேசம், இந்தியா, சீனா, மியான்மரிலிருந்து வருகிறார்கள்.',
    zh: '工地语言为英语。工人主要来自孟加拉国、印度、中国和缅甸。',
  },
  chennai: {
    ta: 'தளத்தின் மொழி தமிழ். தொழிலாளர்கள் பலர் ஒடிசா, பீகார், ஜார்க்கண்ட், மேற்கு வங்கத்திலிருந்து வருகிறார்கள். போஜ்புரி ஆதரிக்கப்படவில்லை; பீகார் தொழிலாளர்களுக்கு இந்தியில் பிரீஃபிங் செய்யப்படும்.',
    zh: '工地语言为泰米尔语。许多工人来自奥迪沙、比哈尔、贾坎德和西孟加拉。不支持博杰普尔语，比哈尔的工人使用印地语交底。',
  },
}

export const siteContext = (site: Pick<CatalogSite, 'id' | 'context'>, uiLang: string): string => SITE_CONTEXT[site.id]?.[uiLang] ?? site.context
