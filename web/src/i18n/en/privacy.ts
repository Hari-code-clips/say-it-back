// English UI strings, privacy (16 Oct): the supervisor's side of the worker's consent, and the /privacy page.
// The worker's own consent words are in ../worker.ts. Honest wording: "designed to support", never "compliant"; no legal claim.
// 17 Oct (build-notes/37-telugu-consent.md, outside review P0-14): `privacy.where.*` says where it is processed (global endpoint, Live in
// us-central1, records in the data region) and `privacy.consent.body` that the worker is told so.
export const privacy = {
  'consent.event': 'Recording choice for round {n}',
  'consent.declinedTitle': 'The worker said not now',
  'consent.declinedBody': 'Nothing was recorded. It is their choice, and it is no mark against them.',
  'consent.declinedHow': 'Brief them in person: go through the steps and the questions face to face. If they change their mind, give them the phone again.',
  'consent.toScript': 'Open the script',
  'consent.saveFailed': "The worker's choice was not saved. Give them the phone again.",

  'privacy.link': 'Privacy',
  'privacy.aboutLine': "What is collected, how long it is kept, and the worker's choice before any recording.",
  'privacy.docTitle': 'Privacy',
  'privacy.title': 'Privacy and the worker’s voice',
  'privacy.subtitle': "What Say It Back collects, where it goes, how long it is kept, and the worker's choice. The design is meant to support Singapore's PDPA and India's DPDP Act. This page is not legal advice, and it claims no compliance.",
  'privacy.collect.title': 'What is collected',
  'privacy.collect.body': "The instruction you give, the critical steps, the scripts, the transcripts of the worker's answers, the checker's ratings, your decision and its reason, and any problem the worker reports.",
  'privacy.collect.never': "Never a worker's name, ID number, nationality or score. The check is about the answer, not the person.",
  'privacy.collect.audio': "The worker's voice is recorded on this phone and sent once for the check. The phone keeps it only until the check answers, never more than a day, so a dropped connection loses no answer. The service processes it in memory and drops it after the check: it is not kept, unless a deployment is set up to keep recordings of consenting volunteers.",
  'privacy.collect.device': "By default there are no accounts: each browser holds a random key that owns its records. Only a fingerprint of the key is stored, and no key or internet address appears in the app's own logs.", // security fixes B (I2): the app's own logs, not Google's platform request logs
  'privacy.where.title': 'Where it is processed',
  'privacy.where.body': "Gemini Flash (the steps, the scripts and the check of each answer) and Gemini TTS (the spoken script, turn by turn) run on Google's global endpoint, and Gemini Live, the live voice, runs in the US (us-central1). Records are stored in Firestore in the deployment's own Google Cloud region: Mumbai by default, or Singapore. So the worker's voice and the transcripts are processed outside Singapore and India. If your site sets it up, each decision is also sent to your permit-to-work system or a Google Chat space.",
  'privacy.where.transfer': 'Processing outside Singapore or India is a transfer of personal data: the worker is told so before anything is recorded, and a site using this must cover it in its own review.',
  'privacy.keep.title': 'How long it is kept',
  'privacy.keep.body': 'Each record is deleted automatically after a set number of days: 90 unless the deployment sets another number, or keeps records. Audio is not kept: the phone deletes it once it is checked (a day at most), and the service after the check.',
  'privacy.delete.title': 'Deleting a record',
  'privacy.delete.body': 'The browser that made a record can delete it at once, from the record itself. A copy already sent to your permit-to-work system or Chat space belongs to that system, and is deleted there.',
  'privacy.consent.title': 'The worker’s choice',
  'privacy.consent.body': 'Before the first answer is recorded, the worker sees one screen in their own language: their voice goes to Google’s computers outside the country, only to check this briefing, and is deleted after the check, within a day. They choose "I agree" or "Not now".',
  'privacy.consent.decline': '"Not now" ends the round kindly. Nothing is recorded, you see that they declined, and you brief them in person. A decline is never a verdict or a mark against them.',
  'privacy.consent.samples': 'With stored sample answers no one’s voice is recorded, so the screen is not shown.',
  'privacy.law.title': "Singapore's PDPA and India's DPDP Act",
  'privacy.law.body': 'The design is meant to support the duties both laws share: consent for a stated purpose, collecting only what that purpose needs, keeping data no longer than needed, and deleting it on request.',
  'privacy.law.limits': 'This is a prototype. A site that uses it still needs its own privacy notice, a data protection officer where the law asks for one, and its own legal review.',
  'privacy.deleteRecord': 'Delete this record',
  'privacy.deleteTitle': 'Delete this record now?',
  'privacy.deleteBody': 'It is removed at once and cannot be brought back. A copy already sent to your permit-to-work system stays there.',
  'privacy.deleteConfirm': 'Delete record',
  'privacy.deleted': 'Record deleted.',
  'privacy.deleteFailed': 'The record was not deleted. Try again.',
}
