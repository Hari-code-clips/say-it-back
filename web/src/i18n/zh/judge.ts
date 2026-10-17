import type { judge as en } from '../en/judge.ts'

// DRAFT, 17 Oct judge demo: machine-written Chinese, NEEDS NATIVE-SPEAKER REVIEW (build-notes/37-review-remainder.md).
export const judge: Record<keyof typeof en, string> = {
  'judge.link': '运行 90 秒评审演示',
  'judge.title': '90 秒评审演示',
  'judge.subtitle':
    '主演示案例已为您设好：新加坡的一次起重吊装，英语到泰米尔语，使用示例指令。步骤和话术仍由您亲自核对，和现场主管一样。工人的回答是存储的示例，所以没有人需要说泰米尔语。',
  'judge.failed': '评审演示无法开始',
  'judge.noLead': '此服务器没有主演示任务。请改为自己设置一次交底。',
  'judge.byHand': '自己设置一次交底',
  'judge.handover': '评审演示：已为您选好存储的示例回答。它们是预先录制的合成泰米尔语语音；检查会现场分析它们，就像分析工人自己的声音一样。',
}
