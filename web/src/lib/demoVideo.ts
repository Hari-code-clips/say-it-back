// VITE_DEMO_VIDEO_URL: the recorded demo, linked from the landing page and from the daily-limit notice so that a judge who
// arrives after the day's Gemini calls are used up still sees the product work. Unset, nothing is linked.
// It is a plain link (a navigation), so the page's CSP, whose connect-src names only the API, does not need to allow it.

/** The demo video's URL when `raw` is an https URL with no credentials; otherwise null, and no link is shown. */
export function demoVideoUrl(raw: string | undefined): string | null {
  const value = (raw ?? '').trim()
  if (!value) return null
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return null
  }
  if (url.protocol !== 'https:' || url.username || url.password) return null
  return url.href
}
