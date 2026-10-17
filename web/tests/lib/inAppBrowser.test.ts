import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { isInAppBrowser, micLikelyBlocked } from '../../src/lib/inAppBrowser.ts'

// User agents as the apps send them (versions trimmed where they are long). A judge who opens the link from one of these
// apps must be told to open it in Chrome or Safari; someone already in a real browser must not be.
const IN_APP: Record<string, string> = {
  'Facebook, iOS':
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/468.0.0.39.106;FBBV/652720741;FBDV/iPhone15,2;FBMD/iPhone;FBSN/iOS;FBSV/17.5;FBSS/3;FBLC/en_GB;FBOP/5]',
  'Facebook, Android':
    'Mozilla/5.0 (Linux; Android 14; SM-S911B Build/UP1A.231005.007) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.71 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/470.0.0.48.109;]',
  'Instagram, iOS':
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 337.0.3.23.54 (iPhone15,2; iOS 17_5; en_GB; en; scale=3.00; 1179x2556; 614004046)',
  'LINE, iOS': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Safari Line/14.10.0',
  'LinkedIn, iOS': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [LinkedInApp]/9.29.5843',
  'Google app, iOS': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/322.0.648915268 Mobile/15E148 Safari/604.1',
  'WhatsApp, where it says so': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 WhatsApp/24.13.80',
  'WeChat, iOS':
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x18003129) NetType/WIFI Language/zh_CN',
  'TikTok, Android':
    'Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A.230805.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.122 Mobile Safari/537.36 musical_ly_2023405030 BytedanceWebview/d8a21c6',
  'any Android WebView':
    'Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A.230805.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.122 Mobile Safari/537.36',
}

const REAL: Record<string, string> = {
  'Chrome, Android': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
  'Safari, iOS': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
  'Chrome, iOS': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/126.0.6478.54 Mobile/15E148 Safari/604.1',
  'Firefox, Android': 'Mozilla/5.0 (Android 14; Mobile; rv:127.0) Gecko/127.0 Firefox/127.0',
  'Samsung Internet': 'Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36',
  'Edge, Windows': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0',
  'Safari, macOS': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
  'Chrome, macOS': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
}

describe('isInAppBrowser', () => {
  for (const [name, ua] of Object.entries(IN_APP)) {
    it(`flags ${name}`, () => assert.equal(isInAppBrowser(ua), true))
  }

  for (const [name, ua] of Object.entries(REAL)) {
    it(`leaves ${name} alone`, () => assert.equal(isInAppBrowser(ua), false))
  }

  it('does not mistake a word that only ends in "Line" or holds "wv" for an app', () => {
    assert.equal(isInAppBrowser(`${REAL['Chrome, macOS']} TimeLine/1.0 kwv)`), false)
  })
})

describe('micLikelyBlocked', () => {
  const getUserMedia = () => Promise.resolve()

  it('is false in a real browser that can ask for the microphone', () => {
    assert.equal(micLikelyBlocked({ userAgent: REAL['Chrome, Android']!, mediaDevices: { getUserMedia } }), false)
  })

  it('is true in an in-app browser even when it exposes getUserMedia', () => {
    assert.equal(micLikelyBlocked({ userAgent: IN_APP['LinkedIn, iOS']!, mediaDevices: { getUserMedia } }), true)
  })

  it('is true when the browser has no mediaDevices, or no getUserMedia on it', () => {
    assert.equal(micLikelyBlocked({ userAgent: REAL['Safari, iOS']! }), true)
    assert.equal(micLikelyBlocked({ userAgent: REAL['Safari, iOS']!, mediaDevices: {} }), true)
  })
})
