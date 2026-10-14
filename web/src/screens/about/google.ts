import type { IconName } from '../../theme/iconNames.ts'

// "Built on Google": the Google products behind Say It Back and what each one does.
// Source: docs/ARCHITECTURE.md, "Built on Google". Kept in English: product names are proper
// nouns and the roles are technical notes for reviewers.

export interface GoogleProduct {
  name: string
  role: string
  icon: IconName
  /** Switched on by configuration only (env-gated in the backend). */
  optional?: boolean
}

export const GOOGLE_PRODUCTS: readonly GoogleProduct[] = [
  {
    name: 'Gemini 3.8 Flash',
    role: 'Extracts the critical steps, writes the worker-language script, back-translates it, transcribes answers blind, runs two judges and writes re-explanations.',
    icon: 'auto_awesome',
  },
  { name: 'Gemini 3.8 Live', role: "Speaks the confirmed script in the worker's language and listens to the answer.", icon: 'auto_awesome' },
  { name: 'Gemini 3.8 Flash TTS', role: 'Voice for turn mode and for the synthetic evaluation set.', icon: 'auto_awesome' },
  {
    name: 'ADK 2.11 (Agent Development Kit)',
    role: 'Every agent: the check workflow, the live briefer through run_live, App plugins, and the adk web developer UI over the same agents.',
    icon: 'construction',
  },
  { name: 'Gemini Enterprise Agent Platform', role: 'The cloud Gemini backend, on the Cloud Run service account.', icon: 'cloud' },
  { name: 'Cloud Run', role: 'Hosts the ADK service, REST and the Live WebSocket.', icon: 'cloud' },
  { name: 'Firebase Hosting', role: 'Serves this web app and holds the deny-all Firestore client rules. The app calls Cloud Run directly.', icon: 'cloud' },
  { name: 'Firestore', role: 'Briefing records and the state machine.', icon: 'cloud' },
  { name: 'Cloud Trace', role: "Per-agent spans and latency through ADK's OpenTelemetry.", icon: 'cloud', optional: true },
  { name: 'BigQuery', role: "Agent event analytics through ADK's plugin, with transcripts and audio redacted.", icon: 'cloud', optional: true },
  { name: 'Google Chat', role: "Go / No-go decisions posted to the site's space by incoming webhook.", icon: 'cloud', optional: true },
  { name: 'Secret Manager', role: 'Only if a Developer API key is still needed in the cloud (for example TTS).', icon: 'cloud', optional: true },
  { name: 'Cloud Build, Artifact Registry', role: 'Used by gcloud run deploy --source.', icon: 'cloud' },
  { name: 'Google Fonts, Material Design 3', role: 'Noto for every script, Material Symbols icons, M3 colour roles.', icon: 'translate' },
]
