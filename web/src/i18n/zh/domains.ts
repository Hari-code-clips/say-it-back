import type { domains as en } from '../en/domains.ts'

// DRAFT, 17 Oct demo suites: machine-written Chinese, NEEDS NATIVE-SPEAKER REVIEW (build-notes/37-domain-suites.md).
export const domains: Record<keyof typeof en, string> = {
  'domain.construction': '建筑施工',
  'domain.utilities': '公用事业',
  'domain.marine': '船舶修造',
  'domain.process': '流程工业',
  'domain.manufacturing': '制造业',
  'domain.telecom': '通信',
  'domain.own': '自己的作业程序',
}
