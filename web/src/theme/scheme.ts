import {
  DynamicScheme,
  Hct,
  MaterialDynamicColors,
  SchemeVibrant,
  TonalPalette,
  Variant,
  argbFromHex,
  hexFromArgb,
} from '@material/material-color-utilities'

// One seed colour drives the whole palette. Google blue 600; with the Vibrant variant it
// resolves to primary #005bc0 on a #f9f9ff surface (the look of Google's own M3 apps).
// Vibrant rotates the secondary hue towards lavender, so the secondary palette is rebuilt from
// the seed hue (low chroma, like TonalSpot): tonal buttons, chips and nav pills stay blue-grey,
// and the one accent in the UI is the seed colour.
// Light scheme only for now ("light mode first"): flip `isDark` to add a dark theme later.
export const SEED_HEX = '#1A73E8'

function buildScheme(seedHex: string): DynamicScheme {
  const source = Hct.fromInt(argbFromHex(seedHex))
  const vibrant = new SchemeVibrant(source, false, 0)
  return new DynamicScheme({
    sourceColorHct: source,
    variant: Variant.VIBRANT,
    contrastLevel: 0,
    isDark: false,
    primaryPalette: vibrant.primaryPalette,
    secondaryPalette: TonalPalette.fromHueAndChroma(source.hue, 16),
    tertiaryPalette: vibrant.tertiaryPalette,
    neutralPalette: vibrant.neutralPalette,
    neutralVariantPalette: vibrant.neutralVariantPalette,
  })
}

// M3 colour roles used by the UI. Keep in sync with the `@theme inline` block in styles/index.css.
const ROLES = [
  'primary', 'onPrimary', 'primaryContainer', 'onPrimaryContainer',
  'secondary', 'onSecondary', 'secondaryContainer', 'onSecondaryContainer',
  'tertiary', 'onTertiary', 'tertiaryContainer', 'onTertiaryContainer',
  'error', 'onError', 'errorContainer', 'onErrorContainer',
  'background', 'onBackground',
  'surface', 'onSurface', 'surfaceVariant', 'onSurfaceVariant', 'surfaceTint',
  'surfaceDim', 'surfaceBright',
  'surfaceContainerLowest', 'surfaceContainerLow', 'surfaceContainer',
  'surfaceContainerHigh', 'surfaceContainerHighest',
  'outline', 'outlineVariant',
  'inverseSurface', 'inverseOnSurface', 'inversePrimary',
  'shadow', 'scrim',
] as const

// Verdict colours are not part of the core M3 roles; M3's "custom colour" recipe adds them
// (tones 40 / 100 / 90 / 10 of a hue). Calm chroma, fixed semantic hues (green, amber).
const CUSTOM = {
  success: { hue: 149, chroma: 36 },
  warning: { hue: 77, chroma: 44 },
} as const

const kebab = (s: string) => s.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)
const varName = (role: string) => `--md-sys-color-${kebab(role)}`

export function buildLightScheme(seedHex: string = SEED_HEX): Record<string, string> {
  const scheme = buildScheme(seedHex)
  const colors = new MaterialDynamicColors()
  const vars: Record<string, string> = {}
  for (const role of ROLES) {
    vars[varName(role)] = hexFromArgb(colors[role]().getArgb(scheme))
  }
  for (const [name, { hue, chroma }] of Object.entries(CUSTOM)) {
    const palette = TonalPalette.fromHueAndChroma(hue, chroma)
    vars[varName(name)] = hexFromArgb(palette.tone(40))
    vars[varName(`on-${name}`)] = hexFromArgb(palette.tone(100))
    vars[varName(`${name}-container`)] = hexFromArgb(palette.tone(90))
    vars[varName(`on-${name}-container`)] = hexFromArgb(palette.tone(10))
  }
  return vars
}

/** Writes the scheme as CSS custom properties on <html>, before React renders (no flash). */
export function applyScheme(root: HTMLElement = document.documentElement): void {
  const vars = buildLightScheme()
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value)
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', vars['--md-sys-color-surface'] ?? '#f9f9ff')
}
