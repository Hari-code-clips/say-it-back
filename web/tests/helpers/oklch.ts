// OKLCH to sRGB and WCAG contrast, for tests/theme/palette.test.ts. Björn Ottosson's OKLab matrices; the WCAG 2.x ratio.

export interface Oklch {
  l: number // 0..1
  c: number
  h: number // degrees
}

export function parseOklch(value: string): Oklch {
  const m = /^oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)$/.exec(value.trim())
  if (!m) throw new Error(`not an oklch() colour: ${value}`)
  return { l: Number(m[1]) / 100, c: Number(m[2]), h: Number(m[3]) }
}

/** Linear-light sRGB, unclamped (a component outside 0..1 means the colour is outside the sRGB gamut). */
export function toLinearRgb({ l, c, h }: Oklch): [number, number, number] {
  const rad = (h * Math.PI) / 180
  const a = c * Math.cos(rad)
  const b = c * Math.sin(rad)
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3
  return [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ]
}

export const inSrgb = (rgb: readonly number[]): boolean => rgb.every((v) => v >= -0.0005 && v <= 1.0005)

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v))

export function luminance(colour: Oklch): number {
  const [r, g, b] = toLinearRgb(colour).map(clamp01) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG contrast ratio, 1..21. */
export function contrast(a: Oklch, b: Oklch): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

export function toHex(colour: Oklch): string {
  const enc = (v: number) => Math.round((v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055) * 255)
  return '#' + toLinearRgb(colour).map((v) => enc(clamp01(v)).toString(16).padStart(2, '0')).join('')
}
