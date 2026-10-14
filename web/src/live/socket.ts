// The WebSocket seam. The Live driver only needs this small surface, so the in-browser mock
// (VITE_API_MOCK=1) and the real WebSocket are interchangeable.

export interface LiveSocket {
  binaryType: BinaryType
  readonly readyState: number
  onopen: ((ev: Event) => void) | null
  onmessage: ((ev: MessageEvent) => void) | null
  onclose: ((ev: CloseEvent) => void) | null
  onerror: ((ev: Event) => void) | null
  send(data: string | ArrayBuffer | ArrayBufferView<ArrayBuffer>): void
  close(code?: number, reason?: string): void
}

export type SocketFactory = (url: string) => LiveSocket

export const OPEN = 1

export const browserSocketFactory: SocketFactory = (url) => {
  const ws = new WebSocket(url)
  ws.binaryType = 'arraybuffer'
  return ws
}

export async function getSocketFactory(): Promise<SocketFactory> {
  if (import.meta.env.VITE_API_MOCK === '1') {
    const { mockSocketFactory } = await import('../mock/liveSocket')
    return mockSocketFactory
  }
  return browserSocketFactory
}
