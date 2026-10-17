// Browsers built into other apps. A judge who opens the link from LinkedIn or WhatsApp lands in one, and most cannot record:
// an Android WebView only gets the microphone if its app grants it, and few do. The page then says to open it in Chrome
// or Safari (src/shell/MicBrowserBanner.tsx) instead of failing at the worker's first answer.

const IN_APP = [
  /\bFBAN\/|\bFBAV\//, // Facebook and Messenger
  /\bInstagram\b/,
  /\bLine\//, // LINE
  /\bLinkedInApp\b/,
  /\bGSA\//, // the Google app on iOS
  /\bWhatsApp\b/, // where its user agent says so (it often hands a link to the system browser instead)
  /\bMicroMessenger\//, // WeChat, which the Chinese-speaking supervisors at the Singapore site use
  /\bTwitter\b|\bSnapchat\b|\bmusical_ly_|\bBytedanceWebview\b/, // X, Snapchat, TikTok
  /; wv\)/, // any other Android WebView: Chrome itself never sends "wv"
]

/** True for a user agent of a browser built into another app (not for Chrome, Safari, Firefox, Edge or Samsung Internet). */
export function isInAppBrowser(ua: string): boolean {
  return IN_APP.some((re) => re.test(ua))
}

/** True when this browser cannot be asked for the microphone at all: an in-app browser, or no getUserMedia. */
export function micLikelyBlocked(nav: { userAgent: string; mediaDevices?: { getUserMedia?: unknown } }): boolean {
  return isInAppBrowser(nav.userAgent) || typeof nav.mediaDevices?.getUserMedia !== 'function'
}
