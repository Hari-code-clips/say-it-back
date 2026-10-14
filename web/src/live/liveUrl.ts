/**
 * Turns the `wsUrl` of endpoint 11 into something `new WebSocket()` accepts.
 * Absolute ws(s):// URLs (the Cloud Run URL in production) are used as given; http(s):// is
 * mapped to ws(s)://; a path ("/api/live/b_x/1") becomes ws(s)://host/path on `loc`: the page's own
 * host through the Vite proxy in local dev, the API's host when VITE_API_BASE is absolute (api/base.ts).
 */
export function resolveWsUrl(wsUrl: string, loc: { protocol: string; host: string }): string {
  if (/^wss?:\/\//i.test(wsUrl)) return wsUrl
  if (/^https?:\/\//i.test(wsUrl)) return wsUrl.replace(/^http/i, 'ws')
  const scheme = loc.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${loc.host}${wsUrl.startsWith('/') ? '' : '/'}${wsUrl}`
}
