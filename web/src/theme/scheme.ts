// The colour scheme is static: every colour is an OKLCH token in the `@theme` block of styles/index.css (see web/design.md).
// Nothing is generated at startup any more, so there is no flash of unthemed content and no JavaScript on the path to first paint.
//
// The one place a token cannot reach is the browser's `<meta name="theme-color">`: a <meta> cannot read a custom property. This
// is the sRGB hex of `--color-surface` (oklch(98.3% 0.006 85)); tests/theme/palette.test.ts checks it against the token, and
// against index.html, so the three cannot drift apart.
export const THEME_COLOR_HEX = '#fbf9f5'
