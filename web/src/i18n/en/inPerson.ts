// English UI strings, the in-person check (2026-10-17, build-notes/38-in-person-check.md): after the worker says "Not now" to the
// recording, the supervisor briefs and checks them in person and records it, so a decline never holds their permit. The words say
// what the supervisor did and that no AI check was made; never a verdict or a score about the worker.
// `flow.actions` names the flow screens' bottom action bar, a region landmark (build-notes/37, accessibility, moderate findings).
export const inPerson = {
  'inPerson.record': 'Record an in-person check',
  'inPerson.scriptLine': 'The worker chose not to be recorded for this round. Brief them in person, then record your check.',
  'inPerson.subtitle': 'No AI check was made for this worker: they chose not to be recorded. Record what you checked with them in person.',
  'inPerson.reasonHint': 'Required for Go: say what you went through with the worker in person, in at least {min} characters.',
  'inPerson.openHint': 'No AI check was made, so every step of this round stays open. Your reason is the record of what you checked.',
  'inPerson.stepTag': 'In person',
  'inPerson.confirm': 'No AI check was made for this worker. The record will say you checked them in person.',
  'inPerson.recordLine': 'Checked in person. The worker chose not to be recorded, so no AI check was made.',
  'inPerson.notRecorded': 'Not recorded',
  'inPerson.event': 'Decision recorded, checked in person',
  'flow.actions': 'Actions',
}
