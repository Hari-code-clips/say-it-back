// The few static words on the worker's screen, in each worker language. Everything else the
// worker reads or hears (instruction, questions, captions, closing) comes from the backend.
//
// DRAFT: these translations are machine-written and NEED NATIVE-SPEAKER REVIEW before any real
// use (Tamil, Bengali, Burmese, Hindi and Odia in particular). English and Chinese are the
// least risky; the rest are marked for review in the catalog note as well.
import type { Lang } from '../api/types.ts'

export interface WorkerWords {
  /** Big start button on the hand-over screen. */
  start: string
  /** The phone is speaking: the worker listens. */
  listen: string
  /** The worker's turn. */
  speak: string
  /** Ends the answer. */
  done: string
  /** Between steps / while the answer is being checked. */
  wait: string
}

export const WORKER_WORDS: Record<Lang, WorkerWords> = {
  en: { start: 'Start', listen: 'Listen', speak: 'Speak now', done: 'Done', wait: 'Please wait' },
  zh: { start: '开始', listen: '请听', speak: '请回答', done: '说完了', wait: '请稍等' },
  ta: { start: 'தொடங்கு', listen: 'கேளுங்கள்', speak: 'இப்போது பேசுங்கள்', done: 'முடிந்தது', wait: 'காத்திருங்கள்' },
  bn: { start: 'শুরু করুন', listen: 'শুনুন', speak: 'এখন বলুন', done: 'শেষ', wait: 'অপেক্ষা করুন' },
  my: { start: 'စတင်ပါ', listen: 'နားထောင်ပါ', speak: 'ယခု ပြောပါ', done: 'ပြီးပါပြီ', wait: 'ခဏစောင့်ပါ' },
  hi: { start: 'शुरू करें', listen: 'सुनिए', speak: 'अब बोलिए', done: 'हो गया', wait: 'कृपया रुकिए' },
  or: { start: 'ଆରମ୍ଭ କରନ୍ତୁ', listen: 'ଶୁଣନ୍ତୁ', speak: 'ଏବେ କୁହନ୍ତୁ', done: 'ହୋଇଗଲା', wait: 'ଅପେକ୍ଷା କରନ୍ତୁ' },
}
