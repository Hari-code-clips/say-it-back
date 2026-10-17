import type { Lang } from '../api/types.ts'

// Long read-outs for the worker screen's caption layout. The default mock scripts are three short
// sentences, which never overflow a phone, so a caption that outgrew the screen was invisible in mock
// mode and was found only against the real Live model (build-notes/08-integration.md).
//
// Opt in with `localStorage.setItem('sib.mock.longScript', '6')` or `'21'` (the number of sentences in the
// instruction read-out), then run the flow. The worker's spoken answer also becomes a long one, and the mock's speech
// lasts as long as real speech does (spokenSeconds in ./audio.ts), so a caption can be compared with the voice. Tamil was
// the text the real model read out in that integration run; Chinese and English say the same thing. On 16 Oct the Tamil
// instruction lines were reworded to the word a worker on site says (the prompt's rule, PROMPT_VERSION .12, build-notes/27:
// no English term spelled letter for letter, and no English word left in Latin script). DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
// The worker's `answer` is not changed: workers do say those words, and the judge accepts them.

const FLAG = 'sib.mock.longScript'

type LongLang = 'ta' | 'zh' | 'en'

interface Text {
  /** Six distinct sentences: the usual long instruction. */
  six: string[]
  /** Seven sentences that are repeated three times for the 21-sentence stress read-out. */
  seven: string[]
  /** A 20-second answer from the worker. */
  answer: string
}

const TEXT: Record<LongLang, Text> = {
  ta: {
    six: [
      'மேலே உள்ள பிரேக்கரை ஆஃப் செய்து, கரண்ட் வராதபடி துண்டிக்கவும்.',
      'மின்சாரம் தாக்காமல் இருக்க கரண்டை ஆஃப் செய்யவும்.',
      'உங்கள் சொந்தப் பூட்டை பிரேக்கரில் மாட்டவும்.',
      'சாவி உங்களிடமே இருக்கட்டும், யாரும் ஆன் செய்யக்கூடாது.',
      'அனுமதி பெற்ற டெஸ்டரால் கரண்ட் இல்லை என்பதை உறுதி செய்யவும்.',
      'டெஸ்ட் செய்த பிறகு பேனலில் கரண்ட் இல்லை என்று தெரிந்தால் மட்டும் மூடியைத் திறக்கவும்.',
    ],
    seven: [
      'வேலை தொடங்கும் முன் மேலே உள்ள பிரேக்கரை ஆஃப் செய்து, கரண்ட் வராதபடி துண்டியுங்கள்.',
      'கரண்டைத் துண்டிக்காமல் வேலையைத் தொடங்காதீர்கள்.',
      'கரண்டைத் துண்டித்தவுடன் உங்கள் சொந்தப் பூட்டை பிரேக்கரில் மாட்டுங்கள்.',
      'பூட்டின் சாவியை எப்போதும் உங்களிடமே வைத்திருங்கள்.',
      'முன்பும் பின்பும், கரண்ட் இருப்பது தெரிந்த இடத்தில் டெஸ்டரைச் சரிபாருங்கள்.',
      'பேனல் மூடியைத் திறக்கும் முன் கரண்ட் இல்லை என்பதை டெஸ்ட் செய்யுங்கள்.',
      'டெஸ்ட் செய்யாமல் பேனல் மூடியை ஒருபோதும் திறக்காதீர்கள்.',
    ],
    answer:
      'முதல்ல நான் upstream breaker-ஐ ஆஃப் பண்ணுவேன். அப்புறம் என்னோட lock-ஐ breaker-ல மாட்டுவேன். சாவியை என் பாக்கெட்டுலயே வச்சுக்குவேன். அதுக்கப்புறம் tester வச்சு கரண்ட் இல்லன்னு செக் பண்ணுவேன். கரண்ட் இல்லன்னு தெரிஞ்சப்புறம்தான் panel கவரை திறப்பேன்.',
  },
  zh: {
    six: [
      '先断开上游断路器并隔离。',
      '切断电源，避免触电。',
      '把您的个人锁挂在断路器上。',
      '钥匙要自己保管，任何人都不能合闸。',
      '用经批准的验电器确认已经没电。',
      '测试后确认面板无电，才能打开盖板。',
    ],
    seven: [
      '开工前，先断开上游断路器并隔离。',
      '没有隔离，不要开始工作。',
      '隔离后，马上把您自己的锁挂在断路器上。',
      '锁的钥匙要一直自己保管。',
      '使用前后，都要在已知带电的电源上检查验电器。',
      '打开面板盖之前，先测试确认没有电流。',
      '没有测试，绝对不要打开面板盖。',
    ],
    answer: '我先把上游断路器关掉，然后挂上我自己的锁，钥匙放在自己口袋里。再用验电器确认没有电，确认之后才打开面板盖。',
  },
  en: {
    six: [
      'Switch off the upstream breaker and isolate it.',
      'Switch off the power so that nobody gets shocked.',
      'Put your personal lock on the breaker.',
      'Keep the key with you, and let nobody switch it on.',
      'Use an approved voltage tester to confirm there is no power.',
      'After testing, open the cover only if the panel is dead.',
    ],
    seven: [
      'Before starting work, turn off the upstream breaker and isolate it.',
      'Do not start work without isolating.',
      'As soon as you isolate, put your own lock on the breaker.',
      'Always keep the lock key with yourself.',
      'Check the tester on a known live source before and after.',
      'Before opening the panel lid, test that there is no current.',
      'Never open the panel lid without testing.',
    ],
    answer:
      'First I switch off the upstream breaker. Then I put my own lock on it and keep the key in my pocket. After that I check with the tester that there is no power. Only then do I open the panel cover.',
  },
}

const has = (lang: string): lang is LongLang => lang in TEXT

/** The sentence count the QA flag asks for, or undefined when it is not set. */
function requested(): 6 | 21 | undefined {
  try {
    const v = localStorage.getItem(FLAG)
    return v === '6' ? 6 : v === '21' ? 21 : undefined
  } catch {
    return undefined
  }
}

/** The flag is set: the mock's speech then lasts as long as real speech does (see spokenSeconds in ./audio.ts). */
export const longScriptOn = (): boolean => requested() !== undefined

/** The long instruction (one sentence per entry) for `lang`, or undefined when the flag is off or `lang` has no text. */
export function longInstruction(lang: Lang): string[] | undefined {
  const n = requested()
  if (!n || !has(lang)) return undefined
  return n === 6 ? TEXT[lang].six : [...TEXT[lang].seven, ...TEXT[lang].seven, ...TEXT[lang].seven]
}

/** What a talkative worker says, when the flag is on. */
export function longAnswer(lang: Lang): string | undefined {
  return requested() && has(lang) ? TEXT[lang].answer : undefined
}
