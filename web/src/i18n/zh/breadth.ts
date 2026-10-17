import type { breadth as en } from '../en/breadth.ts'

// DRAFT, 16 Oct breadth: machine-written Chinese, NEEDS NATIVE-SPEAKER REVIEW (build-notes/34-breadth.md).
export const breadth: Record<keyof typeof en, string> = {
  'breadth.evaluatorLang': '{lang}（供评审使用）',
  'breadth.evaluatorNote': '供评审使用：由您扮演工人，亲自用{lang}作答。面向真实的工人时，请选择工人自己的语言。',
  'breadth.tryOwn': '用您自己的作业程序试一试：把工人的语言选为“英语（供评审使用）”，然后亲自作答。',
}
