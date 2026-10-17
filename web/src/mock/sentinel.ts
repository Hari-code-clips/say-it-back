// Marks the in-browser mock in a bundle. Both mock entries (handlers.ts for REST, liveSocket.ts for the Live socket) import
// this module, so any build that holds either holds this string; web/noMock.ts and deploy/03 refuse a production build that
// does. The global write is a side effect on purpose: no bundler may drop it from a build that includes the mock, and in
// the browser console `globalThis.__SIB_MOCK_BUNDLE__` says whether the mock is loaded.

export const MOCK_BUNDLE_SENTINEL = '__SIB_MOCK_BUNDLE__'

;(globalThis as Record<string, unknown>)[MOCK_BUNDLE_SENTINEL] = true
