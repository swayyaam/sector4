---
version: 1.0
name: sector4-design-system
description: The design system for Sector 4, an F1 race prediction site. The base canvas is pure white; a single action colour (`#6d28d9`) carries every interactive moment and nothing else. Type runs Inter for display and body at modest weights — display sits at weight 400, not 700, signalling analytical calm rather than sports-broadcast urgency — with JetBrains Mono on every number. Page rhythm rotates between bright white sections, soft grey elevation bands, and full-bleed dark editorial bands carrying data panels. Depth comes from card-on-card layering and hairlines, never decorative shadows. Team colours appear only as identification marks inside data, never as interface chrome.

colors:
  action: "#6d28d9"
  action-active: "#5b21b6"
  action-disabled: "#c4b5fd"
  action-on-dark: "#b39dfb"
  ink: "#0a0b0d"
  body: "#5b616e"
  body-strong: "#0a0b0d"
  muted: "#6f757e"
  muted-soft: "#a8acb3"
  hairline: "#dee1e6"
  hairline-soft: "#eef0f3"
  canvas: "#ffffff"
  surface-soft: "#f7f7f7"
  surface-card: "#ffffff"
  surface-strong: "#eef0f3"
  surface-dark: "#0a0b0d"
  surface-dark-elevated: "#16181c"
  on-action: "#ffffff"
  on-dark: "#ffffff"
  on-dark-soft: "#a8acb3"
  positive: "#00875a"
  positive-on-dark: "#3ddc97"
  negative: "#b3121f"
  negative-on-dark: "#ff6b78"
  caution: "#8a5a00"
  caution-surface: "#fdf6e3"

typography:
  display-mega: { fontFamily: "Inter, -apple-system, system-ui, sans-serif", fontSize: 80px, fontWeight: 400, lineHeight: 1.0, letterSpacing: -2px }
  display-xl:   { fontFamily: "Inter, sans-serif", fontSize: 64px, fontWeight: 400, lineHeight: 1.0, letterSpacing: -1.6px }
  display-lg:   { fontFamily: "Inter, sans-serif", fontSize: 52px, fontWeight: 400, lineHeight: 1.0, letterSpacing: -1.3px }
  display-md:   { fontFamily: "Inter, sans-serif", fontSize: 44px, fontWeight: 400, lineHeight: 1.09, letterSpacing: -1px }
  display-sm:   { fontFamily: "Inter, sans-serif", fontSize: 36px, fontWeight: 400, lineHeight: 1.11, letterSpacing: -0.5px }
  title-lg:     { fontFamily: "Inter, sans-serif", fontSize: 32px, fontWeight: 400, lineHeight: 1.13, letterSpacing: -0.4px }
  title-md:     { fontFamily: "Inter, sans-serif", fontSize: 18px, fontWeight: 600, lineHeight: 1.33, letterSpacing: 0 }
  title-sm:     { fontFamily: "Inter, sans-serif", fontSize: 16px, fontWeight: 600, lineHeight: 1.25, letterSpacing: 0 }
  body-md:      { fontFamily: "Inter, sans-serif", fontSize: 16px, fontWeight: 400, lineHeight: 1.5, letterSpacing: 0 }
  body-strong:  { fontFamily: "Inter, sans-serif", fontSize: 16px, fontWeight: 700, lineHeight: 1.5, letterSpacing: 0 }
  body-sm:      { fontFamily: "Inter, sans-serif", fontSize: 14px, fontWeight: 400, lineHeight: 1.5, letterSpacing: 0 }
  caption:      { fontFamily: "Inter, sans-serif", fontSize: 13px, fontWeight: 400, lineHeight: 1.5, letterSpacing: 0 }
  caption-strong: { fontFamily: "Inter, sans-serif", fontSize: 12px, fontWeight: 600, lineHeight: 1.5, letterSpacing: 0 }
  number-display: { fontFamily: "'JetBrains Mono', ui-monospace, Menlo, monospace", fontSize: 18px, fontWeight: 500, lineHeight: 1.4, letterSpacing: 0 }
  number-sm:    { fontFamily: "'JetBrains Mono', ui-monospace, Menlo, monospace", fontSize: 14px, fontWeight: 500, lineHeight: 1.4, letterSpacing: 0 }
  button:       { fontFamily: "Inter, sans-serif", fontSize: 16px, fontWeight: 600, lineHeight: 1.15, letterSpacing: 0 }
  nav-link:     { fontFamily: "Inter, sans-serif", fontSize: 14px, fontWeight: 500, lineHeight: 1.4, letterSpacing: 0 }

rounded:
  none: 0px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  pill: 100px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  base: 16px
  md: 20px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 96px

motion:
  instant: 0ms
  fast: 120ms
  base: 180ms
  slow: 260ms
  ease-out: "cubic-bezier(0.2, 0, 0, 1)"
  ease-in-out: "cubic-bezier(0.4, 0, 0.2, 1)"

components:
  top-nav-light:         { backgroundColor: "{colors.canvas}", textColor: "{colors.ink}", typography: "{typography.nav-link}", height: 64px }
  top-nav-on-dark:       { backgroundColor: "{colors.surface-dark}", textColor: "{colors.on-dark}", typography: "{typography.nav-link}", height: 64px }
  button-primary:        { backgroundColor: "{colors.action}", textColor: "{colors.on-action}", typography: "{typography.button}", rounded: "{rounded.pill}", padding: 12px 20px, height: 44px }
  button-primary-active: { backgroundColor: "{colors.action-active}", textColor: "{colors.on-action}", rounded: "{rounded.pill}" }
  button-primary-disabled: { backgroundColor: "{colors.action-disabled}", textColor: "{colors.on-action}", rounded: "{rounded.pill}" }
  button-secondary-light: { backgroundColor: "{colors.surface-strong}", textColor: "{colors.ink}", typography: "{typography.button}", rounded: "{rounded.pill}", padding: 12px 20px, height: 44px }
  button-secondary-dark: { backgroundColor: "{colors.surface-dark-elevated}", textColor: "{colors.on-dark}", typography: "{typography.button}", rounded: "{rounded.pill}", padding: 12px 20px, height: 44px }
  button-outline-on-dark: { backgroundColor: transparent, textColor: "{colors.on-dark}", typography: "{typography.button}", rounded: "{rounded.pill}", padding: 11px 19px, height: 44px }
  button-tertiary-text:  { backgroundColor: transparent, textColor: "{colors.action}", typography: "{typography.button}" }
  button-pill-cta:       { backgroundColor: "{colors.action}", textColor: "{colors.on-action}", typography: "{typography.button}", rounded: "{rounded.pill}", padding: 16px 32px, height: 56px }
  hero-band-dark:        { backgroundColor: "{colors.surface-dark}", textColor: "{colors.on-dark}", typography: "{typography.display-mega}", padding: 96px }
  hero-band-light:       { backgroundColor: "{colors.canvas}", textColor: "{colors.ink}", typography: "{typography.display-mega}", padding: 96px }
  panel-dark:            { backgroundColor: "{colors.surface-dark-elevated}", textColor: "{colors.on-dark}", rounded: "{rounded.xl}", padding: 32px }
  panel-light:           { backgroundColor: "{colors.canvas}", textColor: "{colors.ink}", rounded: "{rounded.xl}", padding: 32px }
  feature-card:          { backgroundColor: "{colors.canvas}", textColor: "{colors.ink}", typography: "{typography.title-md}", rounded: "{rounded.xl}", padding: 32px }
  data-row:              { backgroundColor: transparent, textColor: "{colors.ink}", typography: "{typography.body-md}", padding: 16px 0, height: 56px }
  delta-up:              { backgroundColor: transparent, textColor: "{colors.positive}", typography: "{typography.number-display}" }
  delta-down:            { backgroundColor: transparent, textColor: "{colors.negative}", typography: "{typography.number-display}" }
  marker-circular:       { backgroundColor: "{colors.surface-strong}", rounded: "{rounded.full}", size: 32px }
  team-marker:           { rounded: "{rounded.xs}", size: 4px 24px }
  probability-bar:       { trackColor: "{colors.surface-strong}", fillColor: "{colors.ink}", rounded: "{rounded.xs}", height: 6px }
  chart-frame:           { backgroundColor: "{colors.canvas}", gridColor: "{colors.hairline-soft}", axisColor: "{colors.hairline}", labelColor: "{colors.muted}", typography: "{typography.caption}" }
  preview-banner:        { backgroundColor: "{colors.caution-surface}", textColor: "{colors.caution}", typography: "{typography.caption-strong}", padding: 10px 24px }
  text-input:            { backgroundColor: "{colors.canvas}", textColor: "{colors.ink}", typography: "{typography.body-md}", rounded: "{rounded.md}", padding: 14px 16px, height: 48px }
  badge-pill:            { backgroundColor: "{colors.surface-strong}", textColor: "{colors.ink}", typography: "{typography.caption-strong}", rounded: "{rounded.pill}", padding: 4px 12px }
  cta-band-dark:         { backgroundColor: "{colors.surface-dark}", textColor: "{colors.on-dark}", typography: "{typography.display-lg}", padding: 96px }
  footer-light:          { backgroundColor: "{colors.canvas}", textColor: "{colors.body}", typography: "{typography.body-sm}", padding: 64px 48px }
  footer-link:           { backgroundColor: transparent, textColor: "{colors.body}", typography: "{typography.body-sm}" }
  legal-band:            { backgroundColor: "{colors.canvas}", textColor: "{colors.muted}", typography: "{typography.caption}" }
---

## Overview

Sector 4 presents probabilistic race predictions and an auditable record of how they turned out. The surface should read like a research publication rather than a sports app: quiet, white-canvas, editorially spaced and almost monochromatic, so the numbers carry the page.

The single brand voltage is the **action colour** (`{colors.action}` — #6d28d9), used scarcely: primary CTAs, inline links, active navigation, focus rings. Beyond that one colour the system is white canvas, ink, soft grey elevation bands, and a deep near-black band (`{colors.surface-dark}`) for full-bleed editorial moments carrying layered data panels.

Type pairs **Inter** for display with **Inter** for body, navigation and captions, and **JetBrains Mono** for every number. Display sits at **weight 400** — not the 700+ typical of sports products. The choice signals analytical calm rather than broadcast urgency.

**Key characteristics:**
- One accent colour, used scarcely.
- Modest display weights — display at 400, never 700+.
- Pill geometry for interactive, 24px cards for containers, full circles for glyphs. Sharp corners absent.
- Full-bleed dark bands carrying layered data panels are the strongest signature pattern.
- Outcome semantics are text colour only, never background fills.
- 96px section rhythm.
- **Team colours are data, not chrome.**

## Colours

### Action
- **Action** (`{colors.action}` — #6d28d9): The only interactive colour. 7.10:1 on white.
- **Action Active** (`{colors.action-active}` — #5b21b6): Press state. 8.98:1.
- **Action Disabled** (`{colors.action-disabled}` — #c4b5fd): Faded tint. Never carries text that must be read.
- **Action On Dark** (`{colors.action-on-dark}` — #b39dfb): Lightened for dark bands. 8.56:1 on `{colors.surface-dark}`.

> **Purple means one thing here.** In F1 timing, purple marks a fastest lap or fastest sector. In this system purple is the **action** colour and nothing else. Never use it to mark a fastest lap, a best sector, a top prediction or any superlative in data — that collision would make an interface colour look like a result. Superlatives get a text label or an icon instead. See *Data display → Marking a superlative*.

### Surface
- **Canvas** (`{colors.canvas}` — #ffffff): Default page floor.
- **Surface Soft** (`{colors.surface-soft}` — #f7f7f7): Alternating band, and table row hover.
- **Surface Strong** (`{colors.surface-strong}` — #eef0f3): Secondary buttons, badges, glyph plates, bar tracks.
- **Surface Dark** (`{colors.surface-dark}` — #0a0b0d): Full-bleed dark bands. Same hex as `{colors.ink}`.
- **Surface Dark Elevated** (`{colors.surface-dark-elevated}` — #16181c): Panels floating inside dark bands.

### Hairlines
- **Hairline** (`{colors.hairline}` — #dee1e6): Dividers, table rules, chart axes.
- **Hairline Soft** (`{colors.hairline-soft}` — #eef0f3): Chart gridlines.

### Text
- **Ink** (`{colors.ink}` — #0a0b0d): Headings, emphasis, and the default fill for data bars.
- **Body** (`{colors.body}` — #5b616e): Running text. 6.21:1 on white.
- **Muted** (`{colors.muted}` — #6f757e): Sub-titles, axis labels, breadcrumbs. 4.64:1 — meets AA for normal text.
- **Muted Soft** (`{colors.muted-soft}` — #a8acb3): Disabled text only. **Fails AA on white**; never use for content that must be read.
- **On Action / On Dark** (#ffffff), **On Dark Soft** (`{colors.on-dark-soft}` — #a8acb3, 8.64:1 on the dark band).

### Outcome semantics
For whether a prediction was borne out. Never for magnitude, never as a fill.

- **Positive** (`{colors.positive}` — #00875a, 4.55:1 on white) · **Positive On Dark** (`{colors.positive-on-dark}` — #3ddc97, 11.14:1).
- **Negative** (`{colors.negative}` — #b3121f, 6.95:1 on white) · **Negative On Dark** (`{colors.negative-on-dark}` — #ff6b78, 7.15:1).

Each is split by band deliberately: a green readable on white is not readable on near-black, and the reverse. Always paired with a word or icon, never colour alone.

### Caution
- **Caution** (`{colors.caution}` — #8a5a00) on **Caution Surface** (`{colors.caution-surface}` — #fdf6e3). Reserved for the preview banner and data-quality warnings. Never an action colour.

## Typography

**Inter** carries display, body, navigation, captions and buttons. **JetBrains Mono** carries every number. Both are SIL OFL and self-hosted.

| Token | Size | Weight | Line height | Tracking | Use |
|---|---|---|---|---|---|
| `{typography.display-mega}` | 80px | 400 | 1.0 | -2px | Home hero h1 |
| `{typography.display-xl}` | 64px | 400 | 1.0 | -1.6px | Subsidiary heroes |
| `{typography.display-lg}` | 52px | 400 | 1.0 | -1.3px | Section heads |
| `{typography.display-md}` | 44px | 400 | 1.09 | -1px | CTA-band headlines |
| `{typography.display-sm}` | 36px | 400 | 1.11 | -0.5px | Sub-section heads |
| `{typography.title-lg}` | 32px | 400 | 1.13 | -0.4px | Card group titles |
| `{typography.title-md}` | 18px | 600 | 1.33 | 0 | Component titles, driver name |
| `{typography.title-sm}` | 16px | 600 | 1.25 | 0 | List labels |
| `{typography.body-md}` | 16px | 400 | 1.5 | 0 | Default body |
| `{typography.body-strong}` | 16px | 700 | 1.5 | 0 | Emphasised body |
| `{typography.body-sm}` | 14px | 400 | 1.5 | 0 | Footer, secondary prose |
| `{typography.caption}` | 13px | 400 | 1.5 | 0 | Captions, axis labels, attribution |
| `{typography.caption-strong}` | 12px | 600 | 1.5 | 0 | Badges, table column heads |
| `{typography.number-display}` | 18px | 500 | 1.4 | 0 | Headline probabilities — mono |
| `{typography.number-sm}` | 14px | 500 | 1.4 | 0 | In-table numbers — mono |
| `{typography.button}` | 16px | 600 | 1.15 | 0 | CTA pill |
| `{typography.nav-link}` | 14px | 500 | 1.4 | 0 | Nav items |

### Principles
- **Display weight stays at 400.** The most distinctive typographic choice.
- **Negative tracking on display only.** Body stays at 0.
- **Mono on every number**, always with `font-variant-numeric: tabular-nums` so columns align and digits do not jitter as values change.
- **Percentages carry one decimal** in tables and headline figures; whole numbers in prose.

## Layout

Base unit 4px. Tokens: `{spacing.xxs}` 4 · `{spacing.xs}` 8 · `{spacing.sm}` 12 · `{spacing.base}` 16 · `{spacing.md}` 20 · `{spacing.lg}` 24 · `{spacing.xl}` 32 · `{spacing.xxl}` 48 · `{spacing.section}` 96.

Section padding is `{spacing.section}` per band; card padding `{spacing.xl}`. Max content width ~1200px centred; data tables may run full width, prose caps at 720px. Grids are 3-up desktop, 2-up tablet, 1-up mobile. 96px between bands, 24px between cards.

## Elevation and depth

| Level | Treatment | Use |
|---|---|---|
| Flat | No shadow, no border | 80% of surfaces |
| Hairline | 1px `{colors.hairline}` | Card outlines, table rules |
| Soft drop | `0 4px 12px rgba(0,0,0,0.04)` | The only shadow tier — hovered cards |
| Layered panel | Panel on dark band | Hero depth |

## Shapes

| Token | Value | Use |
|---|---|---|
| `{rounded.xs}` | 4px | Inline tags, bar fills, team markers |
| `{rounded.sm}` | 8px | Compact rows |
| `{rounded.md}` | 12px | Form inputs |
| `{rounded.lg}` | 16px | Mid-size cards |
| `{rounded.xl}` | 24px | Feature cards, panels |
| `{rounded.pill}` | 100px | All CTAs, badges |
| `{rounded.full}` | 9999px | Glyph circles, avatars |

## Components

### Navigation
**`top-nav-light`** — Default on white pages. Wordmark left, menu centre, CTA right. 64px.
**`top-nav-on-dark`** — Over a dark band; same layout, inverted palette.

### Buttons
**`button-primary`** — The action pill, 44px, `{rounded.pill}`. **`button-primary-active`** / **`button-primary-disabled`** for states. **`button-secondary-light`** / **`button-secondary-dark`** — grey or elevated-dark fill. **`button-outline-on-dark`** — transparent with 1px white border. **`button-tertiary-text`** — inline text link. **`button-pill-cta`** — 56px hero pill.

### Bands
**`hero-band-dark`** — Full-bleed near-black band carrying layered data panels. **`hero-band-light`** — white variant. **`cta-band-dark`** — pre-footer band.

### Cards and panels
**`panel-dark`** — Floating panel inside a dark band. **`panel-light`** — light variant with a hairline. **`feature-card`** — grid cards.

### Forms, badges, footer
**`text-input`** — 48px, focus thickens to 2px `{colors.action}`. **`badge-pill`** — small uppercase label. **`footer-light`**, **`footer-link`**, **`legal-band`**.

## Data display

The working heart of the product, and the part a marketing-shaped system does not cover. Everything here derives from the tokens above; nothing introduces a new colour.

### Tables

- Row height `{component.data-row}` 56px desktop, 48px mobile.
- A 1px `{colors.hairline}` rule **between** rows only. No outer border, **no zebra striping** — striping fights the team markers.
- Column heads in `{typography.caption-strong}`, uppercase, `{colors.muted}`, with a hairline beneath.
- Numbers in `{typography.number-sm}`, right-aligned, tabular. Names left-aligned in `{typography.title-md}`.
- Header row sticky below the nav on long tables.
- Sort controls are text buttons in `{colors.action}`; the active sort shows a caret and sets `aria-sort`.
- **Mobile**: the table does not scroll horizontally. Below 640px each row becomes a two-line block — name and team marker on the first line, probabilities as labelled pairs on the second.

### Team markers

Team colour identifies a team in data and never styles the interface.

- **Allowed**: a `{component.team-marker}` 4px × 24px bar or an 8px dot beside a driver name; a chart series fill; a thin left accent border on a driver row.
- **Not allowed**: backgrounds, buttons, links, headings, large surfaces, anything interactive.
- **Always paired with a text label** — team name or three-letter code — so colour is never the only channel.
- Team colours live in a per-season data file, separate from these brand tokens, tinted to meet AA wherever the colour carries text.

### Probability bars

- `{component.probability-bar}`: 6px tall, `{rounded.xs}`, track `{colors.surface-strong}`, fill `{colors.ink}`.
- **The fill is ink — not the action colour and not the team colour.** Action purple would read as interactive; team colour would make magnitude look like identity.
- Width is the probability relative to the column maximum, not to 100%, so small differences stay visible. State the scale in the column head.
- The bar is decorative; the number beside it is the accessible value. Bars carry `aria-hidden="true"`.

### Charts

- Frame per `{component.chart-frame}`: no border, gridlines `{colors.hairline-soft}`, axis `{colors.hairline}`, labels `{colors.muted}` in `{typography.caption}`.
- **One series**: `{colors.ink}`. **Two series** (model vs baseline): `{colors.ink}` and `{colors.muted}`, additionally distinguished by a dashed stroke. **Categorical by team**: team colours, each with a text label in the legend.
- A perfect-calibration reference line is 1px dashed `{colors.hairline}`.
- Line stroke 2px, round caps. Bars ≤24px thick, 4px rounded at the data end, square at the baseline.
- No dual axes. No pie charts.
- **Every chart has a text alternative**: a visually hidden table or a `<details>` disclosure with the same figures. The chart is `role="img"` with a one-sentence `aria-label` giving the takeaway.

### Marking a superlative

Because purple is the action colour, a fastest lap, best sector or top prediction is **never** marked with colour alone and never with purple.

- Use a text label (`Fastest`, `Most likely`) in `{typography.caption-strong}` on `{colors.surface-strong}`, or an icon with an accessible name.
- Rank may also be carried by position in a sorted table, which needs no colour at all.

### Predicted versus actual

- Show predicted and actual side by side, always labelled.
- A hit uses `{colors.positive}` **plus** the word "hit" or a check icon; a miss uses `{colors.negative}` plus "miss". Never colour alone.
- Misses render at the same visual weight as hits. Sorting or styling that hides misses violates this system.

### Preview banner

While the site is built from sample data, every page carries `{component.preview-banner}`.

- Full-width strip directly beneath the nav, `{colors.caution-surface}` with `{colors.caution}` text in `{typography.caption-strong}`, 1px `{colors.hairline}` bottom border.
- Text: "Preview: sample data, not real predictions."
- Not dismissible, and driven by a single flag so it cannot be omitted from one page.
- Sits in normal flow and reserves its own height, so it causes no layout shift.

### Empty and pending states

- A race with no result yet shows an em dash in the actual column and a `{component.badge-pill}` reading "Not yet run" — never a zero, which would read as a score.
- A missing photo falls back to the designed driver plate: team-coloured 4px rule, driver number in `{typography.number-display}`, initials beneath. It must look intentional, not broken.

## Interaction

### Hover and focus

| Element | Hover | Active | Focus |
|---|---|---|---|
| Primary pill | `{colors.action-active}` | `{colors.action-active}`, no transform | 2px `{colors.action}` ring, 2px offset |
| Secondary pill | `{colors.hairline}` fill | — | as above |
| Text link | Underline appears | — | as above |
| Card | Soft drop shadow tier | — | as above |
| Table row | `{colors.surface-soft}` fill | — | as above |
| Nav link | `{colors.ink}` from `{colors.body}` | — | as above |

Focus is never removed. `:focus-visible` carries the ring; a mouse click does not.

### Motion

| Token | Value | Use |
|---|---|---|
| `{motion.fast}` | 120ms | Colour and opacity changes |
| `{motion.base}` | 180ms | Panel and disclosure transitions |
| `{motion.slow}` | 260ms | Entry of a chart series |
| `{motion.ease-out}` | `cubic-bezier(0.2, 0, 0, 1)` | Anything entering |
| `{motion.ease-in-out}` | `cubic-bezier(0.4, 0, 0.2, 1)` | Anything moving in place |

Only `opacity` and `transform` animate; nothing animates layout. Under `prefers-reduced-motion: reduce` all durations collapse to `{motion.instant}` and the countdown updates without transition — it still updates, because suppressing information is not an accessibility improvement.

## Do's and don'ts

### Do
- Reserve `{colors.action}` for interaction: CTAs, links, active nav, focus rings.
- Keep display headlines at weight 400.
- Render every number in JetBrains Mono with tabular figures.
- Pair every semantic colour with a word or an icon.
- Show misses as prominently as hits.
- Give every chart a text alternative.

### Don't
- **Don't use purple to mark a fastest lap, best sector or top prediction.** It is the action colour; the collision with F1's timing convention would make an interface state look like a result.
- Don't introduce a second action colour.
- Don't use team colour for backgrounds, buttons, links, headings or anything interactive.
- Don't use colour as the only channel for meaning.
- Don't bold display copy.
- Don't add shadow tiers — the system has one.
- Don't use `{colors.muted-soft}` for content that must be read; it fails AA on white.
- Don't zebra-stripe data tables.
- Don't render a probability without stating the snapshot it came from.

## Responsive behaviour

| Name | Width | Key changes |
|---|---|---|
| Mobile | < 640px | Hero h1 80→40px; grids 1-up; table rows become two-line blocks; nav collapses to a sheet; panels collapse to one |
| Tablet | 640–1024px | Hero h1 64px; grids 2-up; tables keep columns but compress |
| Desktop | 1024–1280px | Full hero; grids 3-up; full table |
| Wide | > 1280px | Content caps at 1200px |

Touch targets: primary pill 44px, hero pill 56px, table row 56px (48px mobile), sort controls padded to 44px. All at or above WCAG AAA.

## Accessibility

Contrast is a constraint on the tokens, not a later check. Every pairing below was measured:

| Pairing | Ratio | Meets |
|---|---|---|
| `{colors.action}` on canvas | 7.10:1 | AA, AAA |
| on-action on `{colors.action}` | 7.10:1 | AA, AAA |
| `{colors.action-on-dark}` on surface-dark | 8.56:1 | AA, AAA |
| `{colors.body}` on canvas | 6.21:1 | AA, AAA |
| `{colors.muted}` on canvas | 4.64:1 | AA |
| `{colors.positive}` on canvas | 4.55:1 | AA |
| `{colors.negative}` on canvas | 6.95:1 | AA, AAA |
| `{colors.positive-on-dark}` on surface-dark | 11.14:1 | AA, AAA |
| `{colors.negative-on-dark}` on surface-dark | 7.15:1 | AA, AAA |
| `{colors.on-dark-soft}` on surface-dark | 8.64:1 | AA, AAA |

Also required: one `h1` per page with correct heading order; every interactive element keyboard-operable; `:focus-visible` rings never suppressed; charts carry a text alternative; team colour never the sole carrier of meaning; `prefers-reduced-motion` respected.

## Iteration guide

1. Work one component at a time and reference token keys directly.
2. New CTAs default to `{rounded.pill}`, glyph plates to `{rounded.full}`, containers to `{rounded.xl}`.
3. Variants live as separate entries in the `components:` block.
4. Use `{token.refs}` everywhere — never inline hex.
5. Display 400; body 400/600/700; mono 500 on numbers.
6. The action colour stays scarce — one or two moments per band.
7. Any new data surface states its accessible alternative in the same entry.

## Known gaps

- Team colours for 2026 are provisional until liveries are confirmed; they live in the per-season data file and are expected to change.
- Circuit map styling depends on the licensed source geometry and is specified only loosely here.
- Open Graph image composition is not yet specified beyond using these tokens.
- There is no dark-mode variant of the whole site; the dark band is an editorial device, not a theme.
