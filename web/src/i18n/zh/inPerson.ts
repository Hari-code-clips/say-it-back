import type { inPerson as en } from '../en/inPerson.ts'

// DRAFT, 17 Oct in-person check: machine-written Chinese, NEEDS NATIVE-SPEAKER REVIEW (build-notes/38-in-person-check.md).
// Rule 2: never 理解, 明白, 通过 or 批准. "Check" is 核对, as on the decision screen.
export const inPerson: Record<keyof typeof en, string> = {
  'inPerson.record': '记录当面核对',
  'inPerson.scriptLine': '工人选择这一轮不录音。请当面讲解，然后记录你的核对。',
  'inPerson.subtitle': '这位工人的回答没有经过 AI 核对：他们选择不录音。请记录你当面核对的情况。',
  'inPerson.reasonHint': '开工必填：写明你当面和工人过了哪些内容，至少 {min} 个字符。',
  'inPerson.openHint': '没有经过 AI 核对，所以这一轮的每个步骤都仍未完成。你写的原因就是你当面核对的记录。',
  'inPerson.stepTag': '当面',
  'inPerson.confirm': '这位工人没有经过 AI 核对。记录会写明你是当面核对的。',
  'inPerson.recordLine': '已当面核对。工人选择不录音，所以没有经过 AI 核对。',
  'inPerson.notRecorded': '未录音',
  'inPerson.event': '记录决定（当面核对）',
  'flow.actions': '操作',
}
