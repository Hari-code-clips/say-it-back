import type { inPerson as en } from '../en/inPerson.ts'

// DRAFT, 17 Oct in-person check: machine-written Tamil, NEEDS NATIVE-SPEAKER REVIEW (build-notes/38-in-person-check.md).
// Rule 2: never ஒப்புதல் (approval) or புரிந்த (understood). "Checked" is சரிபார், the word the decision screen already uses.
export const inPerson: Record<keyof typeof en, string> = {
  'inPerson.record': 'நேரில் சரிபார்த்ததைப் பதி',
  'inPerson.scriptLine': 'இந்தச் சுற்றில் பதிவு வேண்டாம் என்று தொழிலாளர் சொன்னார். நேரில் விளக்குங்கள், பிறகு நீங்கள் சரிபார்த்ததைப் பதியுங்கள்.',
  'inPerson.subtitle': 'இந்தத் தொழிலாளரின் பதிலை இந்தக் கருவி சரிபார்க்கவில்லை: அவர் பதிவு வேண்டாம் என்றார். நீங்கள் நேரில் சரிபார்த்ததைப் பதியுங்கள்.',
  'inPerson.reasonHint': 'Go-க்கு அவசியம்: தொழிலாளருடன் நேரில் என்ன பார்த்தீர்கள் என்று சொல்லுங்கள், குறைந்தது {min} எழுத்துகள்.',
  'inPerson.openHint': 'கருவி சரிபார்க்கவில்லை, அதனால் இந்தச் சுற்றின் எல்லாப் படிகளும் திறந்தே இருக்கும். நீங்கள் சரிபார்த்ததின் பதிவு உங்கள் காரணம்தான்.',
  'inPerson.stepTag': 'நேரில்',
  'inPerson.confirm': 'இந்தத் தொழிலாளரின் பதிலை இந்தக் கருவி சரிபார்க்கவில்லை. நீங்கள் நேரில் சரிபார்த்தீர்கள் என்று பதிவு சொல்லும்.',
  'inPerson.recordLine': 'நேரில் சரிபார்க்கப்பட்டது. தொழிலாளர் பதிவு வேண்டாம் என்றார், அதனால் கருவி சரிபார்க்கவில்லை.',
  'inPerson.notRecorded': 'பதிவு இல்லை',
  'inPerson.event': 'தீர்மானம் பதிவானது, நேரில் சரிபார்க்கப்பட்டது',
  'flow.actions': 'செயல்கள்',
}
