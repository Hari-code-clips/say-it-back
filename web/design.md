# Design — Say It Back (web)

Locked design system for the supervisor's phone app. Every screen reads this file first
and defers to it. Approved by Hari on 16 Oct 2026 (`build-notes/25-ux-audit-and-plan.md`,
"Proposed design system"). Amend this file intentionally; do not override it per screen.
The tokens below are checked against `src/styles/index.css` by `tests/theme/palette.test.ts`.

## Genre
modern-minimal: a working tool for one person, outdoors, one thumb, sometimes in sun. Calm
paper, near-black ink, no decoration. Hallmark theme route: custom (the catalog has no
verdict-driven palette).

## Macrostructure family
- App screens (Start, Instruction, Steps, Script, Result, Re-explain, Decision, Record, Records, worker screens): **Workbench**. Small functional heading, content in hairline-divided rows, one sticky bottom action bar. The product itself is the content, so there is no hero.
- Content screens (About, Eval, Sample): **Long Document**. One column, measure 60–65ch, headings inline, negative space as the divider.
- Landing: a single Long Document column ending in the one primary action. No enrichment on any screen.

Nav archetype: N9 edge-aligned minimal (wordmark left, language right; the four destinations as a top row from 840 px and as the bottom bar below). Footer: none (an app has no footer).

## Colour rule: the site's own safety-sign colours (v2, 16 Oct)
Amended 16 Oct at Sam's request ("Colours are important. Don't be monochrome"). The v1 rule (ink buttons, chroma only for verdicts) read as cold and template-grey. v2 keeps every verdict rule below and gives the rest of the app the colour language a worksite already reads on its signs (ISO 7010 / ISO 3864 safety colours):

| Sign colour | Meaning on a sign | In the app | Token family |
| --- | --- | --- | --- |
| Blue | mandatory action: "do this" | primary buttons, selection, focus ring, progress, links; and the calm ground of every worker-held screen | `primary`, `primary-container`, `focus`, `worker` |
| Green | safe condition | Got it (and the worker's Done) | `success` |
| Yellow-amber | caution | Ask again | `warning` |
| Red | prohibition, danger | Wrong, hazards, the worker's problem button, failures | `error` |

**Blue is never a verdict, and no verdict is blue** (the action hue sits more than 90° from Got it green; `tests/theme/palette.test.ts`). **Accent footprint:** one solid blue fill per screen, the primary action (a full-width 64 px bar button is about 7–8 % of a phone viewport, above Hallmark's 5 % guide: a deliberate, owner-requested deviation). Everything else blue is text, a ring, a 2–4 px mark or the pale tint; the worker ground is a tint, not an accent fill. Paper, ink and the containers stay neutral. A recorded decision chip stays ink: the decision is the supervisor's act, not a colour the app gives it. **Worker-held screens sit on the `worker` ground** (a pale blue), so anyone can see at a glance that the worker holds the phone; supervisor screens stay on paper.

| Verdict | Word | Mark | Treatment | Why this and not another |
| --- | --- | --- | --- | --- |
| covered | Got it | check ✓ | green tint, dark green text | positive, the quiet one |
| unclear | Ask again | refresh ↻ | amber tint, dark amber text | "try again", not a fault |
| contradicted | Wrong | close ✕ | **solid** red fill, paper text | the only solid verdict: said the opposite |
| missed | Missed | remove_circle ⊖ (outlined) | **no fill**, 2 px ink outline, ink text | the step was not said; no alarm colour; visibly different from Wrong in fill, border and glyph without any colour |

Rules that follow:
- A verdict is always word + mark + treatment; colour is never the only carrier (WCAG 1.4.1).
- Hazard red (`error`) is used for the worker's problem button and hazard cards, for the Wrong verdict, and for validation and failure messages (tint plus icon). It never decorates.
- `warning` as a chip or banner tone is **not amber**: it is a neutral with a 1.5 px ink outline and a mark. Amber belongs to Ask again.
- The Mock chip is neutral. Selection (chips, radio cards, nav) is the action blue; a selected or informative label is its tint (`primary-container`).
- Light scheme only. High contrast suits sunlight; no dark mode, no `prefers-color-scheme` branch.
- Body text ≥ 4.5:1 everywhere, secondary text ≥ 7:1 on every paper surface, large text and UI boundaries ≥ 3:1, focus ring ≥ 3:1 against every surface and shown instantly.

## Theme
Token names are the existing Tailwind/M3 names (so `bg-primary`, `text-on-surface-variant`… keep working); the Hallmark role is the right-hand column. OKLCH, hue 85 for paper, 70 for ink, 248–258 for the action blue.

| Token | Value | Hallmark role |
| --- | --- | --- |
| `--color-background` | `oklch(98.3% 0.006 85)` | paper |
| `--color-surface` | `oklch(98.3% 0.006 85)` | paper |
| `--color-surface-bright` | `oklch(98.3% 0.006 85)` | paper |
| `--color-surface-dim` | `oklch(90.3% 0.009 85)` | paper-3 (behind overlays) |
| `--color-surface-container-lowest` | `oklch(99.4% 0.005 85)` | card face (the one containment layer) |
| `--color-surface-container-low` | `oklch(97% 0.006 85)` | paper-2 (quiet panel) |
| `--color-surface-container` | `oklch(95.2% 0.007 85)` | paper-2 |
| `--color-surface-container-high` | `oklch(92.8% 0.008 85)` | paper-3 (disabled fill, chip) |
| `--color-surface-container-highest` | `oklch(90.3% 0.009 85)` | paper-3 |
| `--color-surface-variant` | `oklch(94% 0.008 85)` | paper-2 |
| `--color-on-background` | `oklch(19% 0.01 70)` | ink |
| `--color-on-surface` | `oklch(19% 0.01 70)` | ink |
| `--color-on-surface-variant` | `oklch(41% 0.012 70)` | ink-2 (secondary text, 7:1) |
| `--color-outline` | `oklch(52% 0.012 70)` | rule-2 (control borders, 3:1+) |
| `--color-outline-variant` | `oklch(85% 0.008 80)` | rule (hairlines, decorative) |
| `--color-primary` | `oklch(44% 0.145 256)` | accent = action blue (ISO safety blue), 7.4:1 with paper text |
| `--color-on-primary` | `oklch(98.3% 0.006 85)` | accent-ink |
| `--color-primary-container` | `oklch(93% 0.032 252)` | blue tint (selected or informative label) |
| `--color-on-primary-container` | `oklch(32% 0.11 258)` | dark blue text on the tint |
| `--color-worker-ground` | `oklch(95.5% 0.02 248)` | worker-held screen ground |
| `--color-secondary` | `oklch(41% 0.012 70)` | ink-2 |
| `--color-on-secondary` | `oklch(98.3% 0.006 85)` | paper |
| `--color-secondary-container` | `oklch(94% 0.008 85)` | neutral container (selected, nav) |
| `--color-on-secondary-container` | `oklch(19% 0.01 70)` | ink |
| `--color-tertiary` | `oklch(41% 0.012 70)` | ink-2 (unused, kept for the utility names) |
| `--color-on-tertiary` | `oklch(98.3% 0.006 85)` | paper |
| `--color-tertiary-container` | `oklch(94% 0.008 85)` | neutral container |
| `--color-on-tertiary-container` | `oklch(19% 0.01 70)` | ink |
| `--color-focus` | `oklch(44% 0.145 256)` | focus ring (action blue) |
| `--color-success` | `oklch(46% 0.12 150)` | Got it, solid mark |
| `--color-on-success` | `oklch(98.3% 0.006 85)` | text on solid green |
| `--color-success-container` | `oklch(93.5% 0.05 150)` | Got it fill |
| `--color-on-success-container` | `oklch(30% 0.08 150)` | Got it text |
| `--color-warning` | `oklch(50% 0.105 70)` | Ask again, solid mark |
| `--color-on-warning` | `oklch(98.3% 0.006 85)` | text on solid amber |
| `--color-warning-container` | `oklch(94.5% 0.065 90)` | Ask again fill |
| `--color-on-warning-container` | `oklch(32% 0.07 70)` | Ask again text |
| `--color-error` | `oklch(48% 0.19 27)` | Wrong fill, hazard, validation |
| `--color-on-error` | `oklch(98.3% 0.006 85)` | text on solid red |
| `--color-error-container` | `oklch(94% 0.028 25)` | failure message fill |
| `--color-on-error-container` | `oklch(33% 0.13 27)` | failure message text |
| `--color-inverse-surface` | `oklch(19% 0.01 70)` | snackbar |
| `--color-inverse-on-surface` | `oklch(98.3% 0.006 85)` | snackbar text |
| `--color-inverse-primary` | `oklch(84% 0.07 250)` | snackbar action (light blue on ink) |
| `--color-scrim` | `oklch(19% 0.01 70)` | dialog backdrop (alpha at use) |
| `--color-shadow` | `oklch(19% 0.01 70)` | shadows (alpha at use) |

Every colour in the app is one of these tokens. No hex, `rgb()` or `oklch()` outside the `@theme` block (a test enforces it). `theme-color` in `index.html` is the only literal (a `<meta>` cannot read a custom property): the sRGB hex of `--color-surface`, `#fbf9f5`.

## Typography
- Family: **Noto Sans** (the one free family that covers Latin, Tamil, Bengali, Devanagari, Odia, Myanmar and Simplified Chinese), with the matching Noto script families as fallbacks. One family, no pairing: the screens switch script mid-sentence.
- Weights: 400 body, 600 emphasis and controls, 700 headlines. Nothing at 500 (the font request loads 400, 600, 700 only).
- Display and headline tracking: `-0.02em` in Latin only (`html:lang(en)`); `0` in every other script (negative tracking breaks Indic and CJK shaping).
- `tabular-nums` on timers, counts and the round counter.
- Scale (px / line): body 16/24, secondary 14/20 (UI text never below 14), title 16–22, headline 24–32, display 36–57. Worker text is fluid, 28–44 px, weight 600.
- Script text (the worker's language) keeps the taller line heights in `.script-text`.

## Spacing
Tailwind's 4 px scale, named by use: 8 px between controls, 12 px between a control and its helper, 16 px page gutter (24 from 600 px), 24 px between groups, 32 px between sections. Every target is at least 48 px high and wide, with 8–12 px between neighbours.

## Shape and depth
- Buttons, fields, chips' parent controls: **12 px** radius. Not pills. Chips and tags 8 px. Dialog and popover 16 px. Circles (`rounded-full`) only for icon discs, progress and the worker orb.
- **One containment layer.** A card is a hairline border on `surface-container-lowest`. A card never holds a card, a tinted box or a panel. Inside, rows are divided by hairlines (`divide-y divide-outline-variant`), not by boxes.
- No shadows on cards. Shadows only on things that float above the page (dialog, language menu, snackbar).

## Header, phases, bottom bar
- One compact context line above the H1: `Crane lift · English → தமிழ் · Round 1 of 3` (task · language pair · permit when present · round). No chips, no eyebrows, no uppercase kickers.
- The sticky top bar holds leave (✕), the **named phases** `Steps · Script · Worker · Result · Decision` (all five from 600 px; on a phone the current name plus a dash per phase), the Mock chip when mocked, and the language menu. No "Step N of 7". **Rounds are the only count.**
- The sticky bottom bar holds the screen's actions: primary 64 px full width at the bottom, secondary outlined 48 px above it. Its measured height is written to `--sib-bar-h` and reserved as padding under the content (plus the safe area), so nothing is ever behind it. A disabled primary says why in visible text next to it (`disabledReason`).

## Motion
- State changes only: opacity and transform, ≤ 200 ms, `--ease-out`. No scroll reveals, no parallax, no looping decoration. The worker's listening orb stays because it is the voice state.
- Functional motion that keeps running under `prefers-reduced-motion`: the busy spinner (slowed), and the press-and-hold fill (it is the countdown). Everything else drops to ~0 ms.
- Focus ring: 3 px ink, 2 px offset, **instant** (never transitioned).

## Microinteractions stance
- Silent success: no celebratory toasts. A snackbar is for undo and for errors.
- Irreversible acts get a short confirm sheet (Record decision), not a toast. The supervisor's exit on a worker screen is press-and-hold 1.5 s with a keyboard path.
- Hover feedback only under `@media (hover: hover)`. Press = 1 px translate and a darker state layer.
- Disabled never stands alone: a visible reason sits beside it.

## CTA voice
- Primary: ink fill, paper text, 12 px radius, 64 px tall, full width at the bottom of the screen (48 px when inline). One per screen.
- Secondary: transparent, 1.5 px ink-grey outline, ink text, 48 px.
- Text button: no border, ink text, 48 px hit area, for the quiet third action.
- Hazard button (worker's problem, discard): solid red, paper text, the only red button.
- Labels: a verb and its object, one line at 320 px in English, Tamil and Chinese.

## Components and states
Every interactive component ships all eight states: default, hover, focus-visible, active, disabled, loading, error, success. Where a state has no sense for a control (a link has no loading) the code says so.
- `Button`: `busy` (loading), `status="error" | "success"`, `disabledReason` (visible text, `aria-describedby`, stays focusable via `aria-disabled`).
- `HoldButton`: press and hold 1.5 s with a visible fill; hold Space or Enter; a plain tap says "keep holding"; an assistive-tech click opens a confirm dialog.
- `VerdictChip`: the four verdicts above. `StatusChip` tones: neutral, primary (the blue tint), ink (ink fill: a recorded decision), success, warning (neutral outline), error, strong-error (hazard solid) and the verdict tones got, ask, wrong, missed.
- `TextField` / `TextArea`: label above, constant 1.5 px border, `busy`, `valid`, error with icon and text.
- `Choice`: segmented control, choice chips, radio card; selected = ink border or fill plus a check.

## Per-page allowances
- App and content screens: no enrichment. Function carries the page.
- The landing page may show the worked example (a quote, its gloss and two verdict chips); that is content, not decoration.

## What pages MUST share
- The wordmark, the ink-on-paper palette, the verdict treatments, Noto Sans, the 12 px control radius, the CTA voice, the context line + H1 header, the named-phase bar and the sticky bottom bar on flow screens.
- Verdicts always as word + mark + treatment.

## What pages MAY differ on
- Macrostructure within the family (Workbench rows vs Long Document prose).
- Column count at 1280 px (two columns on Result and Decision).

## Exports
`src/styles/index.css` (`@theme`) is the source of truth. The other formats are translations of the table above.

### tokens.css (Hallmark names → project tokens)
```css
:root {
  --color-paper:      oklch(98.3% 0.006 85);   /* --color-surface */
  --color-paper-2:    oklch(95.2% 0.007 85);   /* --color-surface-container */
  --color-paper-3:    oklch(92.8% 0.008 85);   /* --color-surface-container-high */
  --color-ink:        oklch(19% 0.01 70);      /* --color-on-surface */
  --color-ink-2:      oklch(41% 0.012 70);     /* --color-on-surface-variant */
  --color-rule:       oklch(85% 0.008 80);     /* --color-outline-variant */
  --color-rule-2:     oklch(52% 0.012 70);     /* --color-outline */
  --color-accent:     oklch(44% 0.145 256);    /* --color-primary: the action blue of a mandatory-action sign */
  --color-accent-ink: oklch(98.3% 0.006 85);
  --color-accent-2:   oklch(93% 0.032 252);    /* --color-primary-container */
  --color-ground-worker: oklch(95.5% 0.02 248); /* --color-worker-ground */
  --color-focus:      oklch(44% 0.145 256);

  --font-display: "Noto Sans", "Noto Sans Tamil", "Noto Sans Bengali", "Noto Sans Devanagari", "Noto Sans Oriya", "Noto Sans Myanmar", "Noto Sans SC", system-ui, sans-serif;
  --font-body:    var(--font-display);

  --radius-input: 0.75rem; --radius-card: 0.75rem; --radius-pill: 0.75rem; /* buttons are not pills */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --dur-micro: 120ms; --dur-short: 200ms;
}
```

### Tailwind v4 `@theme`
Already the live implementation: see `@theme` in `src/styles/index.css`.

### DTCG `tokens.json`
```json
{
  "color": {
    "paper":  { "$value": "oklch(98.3% 0.006 85)", "$type": "color" },
    "ink":    { "$value": "oklch(19% 0.01 70)", "$type": "color" },
    "ink-2":  { "$value": "oklch(41% 0.012 70)", "$type": "color" },
    "got-it":     { "$value": "oklch(93.5% 0.05 150)", "$type": "color" },
    "ask-again":  { "$value": "oklch(94.5% 0.065 90)", "$type": "color" },
    "wrong":      { "$value": "oklch(48% 0.19 27)", "$type": "color" }
  },
  "font": { "body": { "$value": "Noto Sans", "$type": "fontFamily" } },
  "radius": { "control": { "$value": "12px", "$type": "dimension" } }
}
```

### shadcn/ui CSS variables
```css
:root {
  --background: 98.3% 0.006 85;
  --foreground: 19% 0.01 70;
  --primary: 44% 0.145 256;
  --primary-foreground: 98.3% 0.006 85;
  --muted: 95.2% 0.007 85;
  --muted-foreground: 41% 0.012 70;
  --border: 85% 0.008 80;
  --input: 52% 0.012 70;
  --ring: 44% 0.145 256;
  --destructive: 48% 0.19 27;
  --radius: 0.75rem;
}
```
