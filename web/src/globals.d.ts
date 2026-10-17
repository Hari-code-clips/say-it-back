/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" serves the whole REST contract and the Live socket in the browser (npm run dev:mock). */
  readonly VITE_API_MOCK?: string
  /** The API's base URL: the Cloud Run service URL plus /api in production. Unset = `/api` on the page's own origin (the Vite proxy). */
  readonly VITE_API_BASE?: string
  /** An https link to the recorded demo, shown on the landing page and once the day's Gemini calls are used up. Unset = no link. */
  readonly VITE_DEMO_VIDEO_URL?: string
  /** "firebase" builds the pilot sign-in gate, the ID token header and the Team screen (build-notes/34). Unset = today's build. */
  readonly VITE_AUTH_MODE?: string
  /** Firebase web config of a firebase build: public, not secrets. */
  readonly VITE_FIREBASE_API_KEY?: string
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string
  readonly VITE_FIREBASE_PROJECT_ID?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
