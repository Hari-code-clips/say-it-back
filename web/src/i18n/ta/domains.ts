import type { domains as en } from '../en/domains.ts'

// DRAFT, 17 Oct demo suites: machine-written Tamil, NEEDS NATIVE-SPEAKER REVIEW (build-notes/37-domain-suites.md).
export const domains: Record<keyof typeof en, string> = {
  'domain.construction': 'கட்டுமானம்',
  'domain.utilities': 'பொதுச் சேவைகள்',
  'domain.marine': 'கப்பல் துறை',
  'domain.process': 'செயல்முறை ஆலை',
  'domain.manufacturing': 'உற்பத்தி',
  'domain.telecom': 'தொலைத்தொடர்பு',
  'domain.own': 'உங்கள் சொந்த நடைமுறை',
}
