/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" serves the whole REST contract and the Live socket in the browser (npm run dev:mock). */
  readonly VITE_API_MOCK?: string
  /** The API's base URL: the Cloud Run service URL plus /api in production. Unset = `/api` on the page's own origin (the Vite proxy). */
  readonly VITE_API_BASE?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
