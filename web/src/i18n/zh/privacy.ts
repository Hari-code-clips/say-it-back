// Chinese UI strings, privacy (16 Oct). DRAFT: machine-written, NEEDS NATIVE-SPEAKER REVIEW before real use.
// 17 Oct (build-notes/37-telugu-consent.md): `privacy.where.*` and `privacy.consent.body` rewritten (where it is processed). DRAFT, NEEDS
// NATIVE-SPEAKER REVIEW.
// Rule 2: never 理解, 明白, 通过 (also "by way of": use 经由), 批准, 审批 or 合格.
import type { privacy as en } from '../en/privacy.ts'

export const privacy: Record<keyof typeof en, string> = {
  'consent.event': '第 {n} 轮的录音选择',
  'consent.declinedTitle': '工人说现在不要',
  'consent.declinedBody': '什么都没有录下。这是他们的选择，不会对他们有任何不利。',
  'consent.declinedHow': '请当面讲解：面对面过一遍各个步骤和问题。如果他们改变主意，再把手机交给他们。',
  'consent.toScript': '打开说明稿',
  'consent.saveFailed': '工人的选择没有保存。请再把手机交给他们。',

  'privacy.link': '隐私',
  'privacy.aboutLine': '收集什么、保存多久，以及录音前工人的选择。',
  'privacy.docTitle': '隐私',
  'privacy.title': '隐私与工人的声音',
  'privacy.subtitle': 'Say It Back 收集什么、数据去往哪里、保存多久，以及工人的选择。本设计旨在支持新加坡的 PDPA 和印度的 DPDP 法。本页不是法律意见，也不声称符合任何法律。',
  'privacy.collect.title': '收集什么',
  'privacy.collect.body': '你给出的指示、关键步骤、说明稿、工人回答的文字记录、检查的评定、你的决定及其理由，以及工人报告的任何问题。',
  'privacy.collect.never': '从不收集工人的姓名、证件号码、国籍或分数。检查针对的是回答，不是人。',
  'privacy.collect.audio': '工人的声音在这部手机上录下，只发送一次用于检查。手机只保存到检查有结果为止，最多一天，这样断网也不会丢失回答。服务只在内存中处理，检查后丢弃：除非某个部署专门设置为保存自愿者（已同意）的录音，否则不会保存。',
  'privacy.collect.device': '默认没有账号：每个浏览器持有一个随机密钥，用它拥有自己的记录。只保存密钥的指纹；本应用自己的日志里不会出现密钥或网络地址。', // security fixes B (I2): "the app's own logs". DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'privacy.where.title': '在哪里处理',
  'privacy.where.body': 'Gemini Flash（提取步骤、编写说明稿、核对每个回答）和 Gemini TTS（逐段播放时朗读说明稿）经由 Google 的全球端点运行；实时语音 Gemini Live 在美国（us-central1）运行。记录保存在 Firestore，位于该部署自己的 Google Cloud 区域：默认孟买，也可以是新加坡。因此，工人的声音和转写文字是在新加坡和印度以外处理的。如果你的工地做了设置，每个决定也会发送到你的作业许可系统或 Google Chat 空间。',
  'privacy.where.transfer': '在新加坡或印度以外处理属于个人数据的跨境传输：录下任何内容之前会先告诉工人；使用它的工地须在自己的审查中涵盖这一点。',
  'privacy.keep.title': '保存多久',
  'privacy.keep.body': '每条记录在设定的天数后自动删除：除非部署设了其他天数或选择保留，否则为 90 天。录音不保存：检查后手机就删除（最多一天），服务在检查后删除。',
  'privacy.delete.title': '删除记录',
  'privacy.delete.body': '创建记录的浏览器可以在记录页面上立即删除它。已经发送到你的作业许可系统或 Chat 空间的副本属于那个系统，须在那里删除。',
  'privacy.consent.title': '工人的选择',
  'privacy.consent.body': '在录下第一个回答之前，工人会看到一个用他们自己语言写的页面：他们的声音会传到这个国家以外的谷歌电脑上，只用来核对这次的说明，核对后一天之内删除。他们选择"我同意"或"现在不要"。',
  'privacy.consent.decline': '"现在不要"会温和地结束这一轮。什么都不录，你会看到他们没有同意，然后你当面讲解。拒绝从来不是评定，也不会对他们不利。',
  'privacy.consent.samples': '使用存储的示例回答时不会录下任何人的声音，所以不显示这个页面。',
  'privacy.law.title': '新加坡的 PDPA 和印度的 DPDP 法',
  'privacy.law.body': '本设计旨在支持两部法律共同的义务：为说明的目的取得同意，只收集该目的所需的数据，保存不超过所需的时间，并在被要求时删除。',
  'privacy.law.limits': '这是一个原型。使用它的工地仍需要自己的隐私告知、法律要求时的数据保护负责人，以及自己的法律审查。',
  'privacy.deleteRecord': '删除这条记录',
  'privacy.deleteTitle': '现在删除这条记录吗？',
  'privacy.deleteBody': '它会立即删除，无法恢复。已经发送到你的作业许可系统的副本会留在那里。',
  'privacy.deleteConfirm': '删除记录',
  'privacy.deleted': '记录已删除。',
  'privacy.deleteFailed': '记录没有删除。请再试一次。',
}
