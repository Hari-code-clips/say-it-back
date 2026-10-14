// Language names in each UI language, for sentences like "Writing the Tamil script...".
// (Chips show the native name next to this; see catalog.languages[x].native.)
//
// DRAFT: the Tamil and Chinese names need native-speaker review.
import type { Lang } from '../api/types.ts'

export const LANG_NAMES: Record<'en' | 'ta' | 'zh', Record<Lang, string>> = {
  en: { en: 'English', zh: 'Mandarin Chinese', ta: 'Tamil', bn: 'Bengali', my: 'Burmese', hi: 'Hindi', or: 'Odia' },
  ta: { en: 'ஆங்கிலம்', zh: 'சீன மாண்டரின்', ta: 'தமிழ்', bn: 'வங்காளம்', my: 'பர்மியம்', hi: 'இந்தி', or: 'ஒடியா' },
  zh: { en: '英语', zh: '中文', ta: '泰米尔语', bn: '孟加拉语', my: '缅甸语', hi: '印地语', or: '奥里亚语' },
}
