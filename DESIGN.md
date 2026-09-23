---
version: alpha
name: Sector 4 design system
description: The Sector 4 design system — a gallery-white, monochrome interface built to disappear behind the content it presents. Near-black ink on white canvas, a ladder of barely-there neutral tints instead of shadows, stadium-pill controls, 24px card geometry, iOS-style 30% squircle tiles, and the Saans typeface at unusual variable weights (652 display, 456 text, 300 light). One electric blue accent is reserved for commercial signals; every other color on screen belongs to the content being shown.

colors:
  primary: "#141414"
  on-primary: "#ffffff"
  on-primary-soft: "#adadad"
  ink: "#141414"
  ink-soft: "#262626"
  text-muted: "#5c5c5c"
  text-faint: "#6b6b6b"
  canvas: "#ffffff"
  canvas-soft: "#f3f3f3"
  field: "#f0f0f0"
  hairline-soft: "#f0f0f0"
  hairline: "#e0e0e0"
  accent: "#0060f0"

typography:
  display:
    fontFamily: Saans
    fontSize: 80px
    fontWeight: 652
    lineHeight: 1
    letterSpacing: 0
  heading-1:
    fontFamily: Saans
    fontSize: 56px
    fontWeight: 652
    lineHeight: 1
    letterSpacing: 0
  heading-2:
    fontFamily: Saans
    fontSize: 44px
    fontWeight: 652
    lineHeight: 1.13
    letterSpacing: 0
  heading-3:
    fontFamily: Saans
    fontSize: 32px
    fontWeight: 652
    lineHeight: 1.13
    letterSpacing: 0
  heading-4:
    fontFamily: Saans
    fontSize: 24px
    fontWeight: 652
    lineHeight: 1.25
    letterSpacing: 0
  title:
    fontFamily: Saans
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: 0
  body-lg:
    fontFamily: Saans
    fontSize: 20px
    fontWeight: 300
    lineHeight: 1.38
    letterSpacing: 0
  body:
    fontFamily: Saans
    fontSize: 16px
    fontWeight: 456
    lineHeight: 1.38
    letterSpacing: 0
  body-sm:
    fontFamily: Saans
    fontSize: 14px
    fontWeight: 456
    lineHeight: 1.43
    letterSpacing: 0
  link:
    fontFamily: Saans
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.38
    letterSpacing: 0
  label:
    fontFamily: Saans
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.33
    letterSpacing: 0
  caption:
    fontFamily: Saans
    fontSize: 12px
    fontWeight: 456
    lineHeight: 1.33
    letterSpacing: 0

rounded:
  none: 0px
  sm: 16px
  md: 24px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 80px
  section-lg: 120px

motion:
  quick: 120ms
  base: 200ms
  enter: 360ms
  fill: 700ms
  stagger: 30ms
  stagger-steps: 12
  rise: 6px
  ease-out: "cubic-bezier(0.2, 0, 0, 1)"
  ease-standard: "cubic-bezier(0.4, 0, 0.2, 1)"

components:
  nav-pill:
    backgroundColor: "{colors.canvas-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"

  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.link}"
    rounded: "{rounded.full}"
    padding: "0px {spacing.md}"

  button-outline:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    rounded: "{rounded.full}"

  button-pill-soft:
    backgroundColor: "{colors.canvas-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"

  text-input:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm} {spacing.md}"

  text-input-focused:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    borderColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm} {spacing.md}"

  badge-popular:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-primary}"

  badge-overlay:
    backgroundColor: "rgba(115, 115, 115, 0.56)"
    textColor: "{colors.on-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"

  pricing-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline-soft}"
    rounded: "{rounded.md}"

  pricing-card-featured:
    backgroundColor: "{colors.canvas-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"

  segmented-control:
    backgroundColor: "{colors.canvas-soft}"
    rounded: "{rounded.full}"

  segmented-control-active:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"

  testimonial-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline-soft}"
    rounded: "{rounded.sm}"

  faq-row:
    backgroundColor: "{colors.canvas-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"

  app-icon-squircle:
    cornerRadius: "30%"

  brand-chip:
    textColor: "{colors.ink}"
    typography: "{typography.heading-3}"

  portrait-tile:
    rounded: "{rounded.md}"
    textColor: "{colors.on-primary}"

  award-lockup:
    textColor: "{colors.ink}"
    typography: "{typography.heading-3}"

  compare-table:
    rowBorder: "{colors.canvas-soft}"
    highlightBackground: "{colors.canvas-soft}"
    textColor: "{colors.ink}"

  footer:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"

  # ─── Examples (illustrative) — kit-mirror surfaces referencing brand primitives ───
  ex-pricing-tier:
    description: "Default Pricing tier card. Re-uses feature-card chrome with brand canvas-soft surface."
    backgroundColor: "{colors.canvas-soft}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  ex-pricing-tier-featured:
    description: "Featured/highlighted tier — polarity-flipped surface (dark fill + light text in light mode, light fill + dark text in dark mode)."
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  ex-product-selector:
    description: "What's Included summary card — re-purposed for SaaS / B2B verticals (NOT a literal product gallery)."
    backgroundColor: "{colors.canvas-soft}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  ex-cart-drawer:
    description: "Subscription summary — re-purposed for SaaS / B2B (line items per add-on, not literal cart)."
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
    item-divider: "{colors.hairline}"
  ex-app-shell-row:
    description: "Sidebar nav row inside the App Shell example. Active state uses brand primary as the indicator."
    backgroundColor: "{colors.canvas}"
    activeIndicator: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xs} {spacing.md}"
  ex-data-table-cell:
    description: "Default data-table th + td chrome. Header uses mono-caps eyebrow typography; body uses body-sm."
    headerBackground: "{colors.canvas-soft}"
    headerTypography: "{typography.caption}"
    bodyTypography: "{typography.body-sm}"
    cellPadding: "{spacing.sm} {spacing.md}"
    rowBorder: "{colors.hairline}"
  ex-auth-form-card:
    description: "Sign-in / sign-up card. Re-uses feature-card chrome with text-input primitives inside."
    backgroundColor: "{colors.canvas-soft}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  ex-modal-card:
    description: "Modal dialog surface — same chrome as feature-card with elevated shadow."
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  ex-empty-state-card:
    description: "Empty-state illustration frame."
    backgroundColor: "{colors.canvas-soft}"
    rounded: "{rounded.md}"
    padding: "{spacing.xxl}"
    captionTypography: "{typography.body}"
  ex-toast:
    description: "Toast notification surface — feature-card shape + medium shadow."
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
    typography: "{typography.body-sm}"

---


## Overview

This is an interface engineered to get out of the way of the content it presents. The system is strictly monochrome: near-black ink (`{colors.ink}` — #141414) on a pure white canvas (`{colors.canvas}`), with structure carried by a ladder of barely-perceptible neutral tints rather than by shadows or color. That content is the only saturated element on any page — the chrome frames it the way a gallery wall frames paintings.

The geometry does the brand work that color refuses to do. Every interactive element is a stadium pill (`{rounded.full}`): the floating navigation bar, every button, the segmented billing toggle, the overlay badges. Containers sit at a calm `{rounded.md}` (24px), media tiles at `{rounded.sm}` (16px), and app icons render as iOS-style squircles at 30% corner radius. Type is set in Saans at deliberately non-standard variable weights — a chunky 652 for every heading, a bookish 456 for text, an airy 300 for hero subtitles — which gives the monochrome pages a strong typographic voice without a single decorative flourish.

One color is allowed to interrupt: an electric blue accent (`{colors.accent}` — #0060f0), used exclusively for commercial signals — a featured-tier badge, a savings callout. Its scarcity is the point; when blue appears, it is asking for a decision.

**Key Characteristics:**
- Gallery-white monochrome palette — `{colors.ink}` on `{colors.canvas}`, zero brand chroma outside the single `{colors.accent}` blue
- Stadium-pill interaction language: nav bar, buttons, toggles, and badges all at `{rounded.full}`
- Shadow-free elevation — hierarchy built from a neutral tint ladder (`{colors.canvas-soft}`, `{colors.field}`, `{colors.hairline}`) and 1px hairlines
- Saans at signature variable weights: 652 headings with tight 1.0–1.13 line-height, 456 body, 300 light subtitles
- iOS-style squircle tiles (30% radius) as a recurring visual motif across counters and marquees
- Content supplies the color: whatever the page presents carries all visual richness, and portraits stay grayscale
- Full-bleed near-black `{colors.ink}` footer with rounded top corners closes every page in polarity inversion

## Colors

### Brand & Accent
- **Ink Black** (`{colors.primary}` — #141414): The brand color. Fills every primary CTA pill, the footer band, and all display typography. The identity is this near-black, softened just off pure black to sit comfortably next to photography.
- **Electric Blue** (`{colors.accent}` — #0060f0): The only chromatic accent in the system. Darkened from #0066ff, which fell to 4.24:1 on `{colors.field}`; the hue is unchanged. Reserved for commercial emphasis — featured badges and savings callouts. Never used decoratively, never used for CTAs.

### Surface
- **Canvas** (`{colors.canvas}` — #ffffff): Default page and card background across all pages.
- **Soft Canvas** (`{colors.canvas-soft}` — #f3f3f3): The workhorse tint — a 6% ink wash over white. Fills the floating nav pill, the featured pricing card, FAQ accordion rows, soft utility pills, segmented-control tracks, and the highlighted comparison-table column.
- **Field** (`{colors.field}` — #f0f0f0): An 8% ink wash used as the fill for form inputs, giving fields presence without borders.
- **Soft Hairline** (`{colors.hairline-soft}` — #f0f0f0): 1px card outlines — the faintest possible edge, used on white-on-white cards (pricing, testimonials).
- **Hairline** (`{colors.hairline}` — #e0e0e0): The stronger 16% control border, used on outlined pill buttons and interactive chrome.

### Text
- **Ink** (`{colors.ink}` — #141414): Headings, body copy, and nav links.
- **Soft Ink** (`{colors.ink-soft}` — #262626): Slightly lifted dark used for secondary lockups and wordmarks.
- **Muted** (`{colors.text-muted}` — #5c5c5c): Darkened from #707070, which failed AA on both tints (4.46:1 on `{colors.canvas-soft}`, 4.35:1 on `{colors.field}`). Secondary copy — supporting paragraphs, plan descriptions, counts, underlined inline links.
- **Faint** (`{colors.text-faint}` — #6b6b6b): Darkened from #adadad, which failed AA on every light surface (2.24:1 on `{colors.canvas}`). Tertiary text — placeholders and fine print on light surfaces. Still lighter than `{colors.text-muted}`, so the ladder keeps its order.
- **Faint on ink** (`{colors.on-primary-soft}` — #adadad): The original faint value, kept for the one place it passed: de-emphasized text on the `{colors.ink}` footer (8.21:1). Darkening `{colors.text-faint}` for light surfaces would have broken it there, so the footer has its own token.

### Semantic
- The system ships no dedicated success/warning/error palette on its marketing surfaces; state communication stays within the monochrome ladder, with `{colors.accent}` as the sole positive-emphasis signal.

## Typography

### Font Family

**Saans** — a contemporary neo-grotesque used exclusively, across every page and every role. It is loaded as a variable font, and the brand's voice comes from where it sits on the weight axis: headings render at an unusual 652 (heavier than semibold, lighter than bold), running text at 456 (a hair over regular), and hero subtitles at a genuinely light 300. Fallback stack: system sans (`-apple-system, "Helvetica Neue", Arial, sans-serif`).

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.display}` | 80px | 652 | 1.0 | 0 | Homepage hero statements and large counters |
| `{typography.heading-1}` | 56px | 652 | 1.0 | 0 | Page heroes ("Race predictions, scored in public.") |
| `{typography.heading-2}` | 44px | 652 | 1.13 | 0 | Section headings on content pages |
| `{typography.heading-3}` | 32px | 652 | 1.13 | 0 | Card-level headlines, featured names, auth headings |
| `{typography.heading-4}` | 24px | 652 | 1.25 | 0 | Sub-section headings, plan names |
| `{typography.title}` | 20px | 600 | 1.3 | 0 | Feature titles, emphasized rows |
| `{typography.body-lg}` | 20px | 300 | 1.38 | 0 | Hero subtitles and lead paragraphs — the light counterpoint to 652 headings |
| `{typography.body}` | 16px | 456 | 1.38 | 0 | Default body copy, testimonial quotes |
| `{typography.body-sm}` | 14px | 456 | 1.43 | 0 | Supporting copy, plan feature lists, legal text |
| `{typography.link}` | 16px | 600 | 1.38 | 0 | Nav links and button labels |
| `{typography.label}` | 12px | 600 | 1.33 | 0 | Badge and pill labels |
| `{typography.caption}` | 12px | 456 | 1.33 | 0 | Captions, metadata, form fine print |

### Principles

- **Weight contrast is the drama.** Pairing 652 headings against 300 light subtitles at the same scale step (e.g. 80px display over 20px light lead) creates hierarchy without color or ornament.
- **Tight leading up top.** Display and heading-1 sit at line-height 1.0; headings never breathe more than 1.25. Body text opens up to 1.38–1.43.
- **Zero letter-spacing everywhere.** The grotesque is trusted at its natural fit; no tracking adjustments at any size.
- **Sentence case with terminal periods.** Headlines read as declarative sentences: "Race predictions, scored in public." — the period is part of the voice.

### Note on Font Substitutes

Saans is a commercial typeface. The closest widely-available substitutes are **Inter** (variable, supports the 300/450/650 weight positions via its variable axis) or **Hanken Grotesk**. When substituting, map weight 652 → 650 (or 700 at static weights), 456 → 450 (or 500), and keep line-heights as specified — Saans has a compact x-height, so substitutes may need line-height reduced by ~0.05.

## Layout

### Spacing System
- **Base unit**: 8px, with 4px half-steps for fine rhythm
- **Tokens**: `{spacing.xxs}` 4px · `{spacing.xs}` 8px · `{spacing.sm}` 12px · `{spacing.md}` 16px · `{spacing.lg}` 24px · `{spacing.xl}` 32px · `{spacing.xxl}` 48px · `{spacing.section}` 80px · `{spacing.section-lg}` 120px
- Buttons are fixed-height pills padded horizontally at `{spacing.md}`; inputs pad `{spacing.sm} {spacing.md}`
- Universal rhythm constants: 28px and 80px vertical steps recur on every page; 120px separates major homepage acts

### Grid & Container
- Content rides a centered column: single-column centered lockups for heroes and featured items, a 2-up card grid for pricing plans, 3-up for portrait tiles, and a 4-column masonry for testimonials.
- The floating nav pill is detached from the viewport edge and horizontally centered, rather than a full-width bar — the page canvas visibly wraps around it.
- Marquee strips of content run full-bleed beyond the content column.

### Whitespace Philosophy

Whitespace is the primary grouping device. Sections are separated by `{spacing.section}` to `{spacing.section-lg}` of empty canvas with no divider rules; within cards, generous `{spacing.lg}` padding keeps content off the hairline edges. The homepage alternates dense collage moments with near-empty typographic interludes — compression and release.

### Responsive Strategy

#### Breakpoints

| Name | Width | Key Changes |
|---|---|---|
| 2xl | 1536px | Max content width engaged; marquees widen |
| xl | 1280px | Default desktop grid |
| lg | 1024px | Comparison table condenses; testimonial masonry drops to 3 columns |
| md | 840px / 768px | Pricing cards stack to 1-up; portrait grid drops to 2-up; nav links collapse |
| sm | 719px / 640px | Single-column layouts; display type scales down from 80px |
| xs | 600px | Minimum layout; auth split-panel drops its marquee |

#### Touch Targets
- Pill buttons and nav CTAs are fixed-height stadium shapes comfortably above the 44px minimum; form inputs pad to a similar height via `{spacing.sm} {spacing.md}`.
- The segmented billing toggle presents each option as a full pill target, not a small radio dot.

#### Collapsing Strategy
- The floating `nav-pill` persists on scroll and across breakpoints, tightening to logomark + CTA on narrow screens.
- Multi-column grids (pricing 2-up, portraits 3-up, testimonials 4-up) collapse column-by-column rather than reflowing horizontally.
- A two-panel split (form left, angled marquee right) drops the marquee panel entirely on narrow viewports, keeping the centered form column.

#### Image Behavior
- Screenshots and device mockups keep fixed aspect ratios and `{rounded.md}` corners at all sizes.
- Marquee strips overflow the viewport intentionally and animate horizontally; they crop rather than scale.
- Portraits stay square-ish tiles, lazily loaded, always grayscale.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| 0 | Flat on `{colors.canvas}` | Default — most of every page |
| 1 | `{colors.canvas-soft}` fill, no border | Nav pill, featured pricing card, FAQ rows, soft pills |
| 2 | 1px `{colors.hairline-soft}` outline on white | Pricing and testimonial cards |
| 3 | 1px inset ring | Comparison-table highlight column edge |
| Inverse | `{colors.ink}` fill, `{colors.on-primary}` text | Footer band, primary CTAs |

The system is essentially shadow-free: no drop shadows appear on any card, button, or nav element. Elevation is communicated by *fill difference* (white vs. 6–8% ink tints) and by hairlines, which keeps every surface print-flat and lets the content supply all depth cues. The one soft-shadow exception is the active segment of the segmented control, which lifts off its `{colors.canvas-soft}` track as a white pill.

### Decorative Depth
- **Glass monoliths** — a hero may render tall pillars in a white-to-gray vertical gradient, reading as frosted glass against the `{colors.canvas-soft}` band; the page's only atmospheric gradient.
- **Photography as depth** — floating squircle tiles, angled collages, and device mockups create parallax-like layering on a flat canvas.
- **Polarity inversion** — the `{colors.ink}` footer with `{rounded.md}` top corners acts as a heavy baseboard, giving each page a physical end-stop.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.none}` | 0px | Full-bleed media strips and marquee images |
| `{rounded.sm}` | 16px | Inputs, video tiles, testimonial cards, FAQ rows |
| `{rounded.md}` | 24px | Content cards, device mockups, portrait tiles, footer top corners |
| `{rounded.full}` | 9999px | Every pill: nav, buttons, badges, toggles |

### Photography Geometry
- Screenshots render inside device-shaped frames at `{rounded.md}`.
- Icons use the signature 30% squircle radius (`app-icon-squircle`) — the iOS icon silhouette — at every size from 32px chips to 96px hero tiles.
- Portraits are near-square tiles at `{rounded.md}`, always black-and-white, with name captions overlaid in `{colors.on-primary}` on a `badge-overlay` scrim near the lower edge.
- Avatars in testimonial cards are small circles (`{rounded.full}`) with a tiny company logo badge overlapping the bottom-right corner.

## Components

### Buttons

**`button-primary`** — "Next race", "See the race"
- Fill `{colors.primary}`, label `{colors.on-primary}` in `{typography.link}`, shape `{rounded.full}`, padding `0px {spacing.md}` on a fixed-height pill
- The single CTA style everywhere: nav, cards, forms, heroes

**`button-outline`** — "Full field and factors", "Open the track record"
- Fill `{colors.canvas}`, label `{colors.ink}`, 1px `{colors.hairline}` border, shape `{rounded.full}`
- The de-emphasized twin of the primary pill; used when two actions sit side by side or for third-party auth

**`button-pill-soft`** — "How it works", "Read more"
- Fill `{colors.canvas-soft}`, label `{colors.ink}`, shape `{rounded.full}`
- Tertiary utility pill for outbound and in-page links; no border, relies on its tint fill

### Cards & Containers

**`pricing-card`** — default plan tier
- `{colors.canvas}` fill, 1px `{colors.hairline-soft}` outline, `{rounded.md}` corners
- Plan name in `{typography.heading-4}`, price figure large with stacked `{typography.caption}` qualifiers, feature list rows in `{typography.body-sm}` with `{colors.text-muted}` icons

**`pricing-card-featured`** — highlighted plan tier
- `{colors.canvas-soft}` fill, borderless, `{rounded.md}` corners — emphasis by tint, not by outline or polarity flip
- Carries the `badge-popular` chip beside the plan name and a full-width `button-primary` CTA, while the default tier gets `button-outline`

**`testimonial-card`** — user quote tile
- `{colors.canvas}` fill, 1px `{colors.hairline-soft}` outline, `{rounded.sm}` corners
- Circular avatar with overlapping company mini-badge, name in `{typography.link}`, company in `{colors.text-muted}` `{typography.body-sm}`, quote in `{typography.body}`
- Laid out as a 4-column masonry of varying heights

**`faq-row`** — accordion item
- Full-width `{colors.canvas-soft}` bar, `{rounded.sm}` corners, question in `{typography.body}` with a trailing chevron; rows stack with `{spacing.sm}` gaps

**`portrait-tile`** — people grid cell
- Grayscale photograph at `{rounded.md}`, name + role caption overlaid at bottom center in `{colors.on-primary}`
- The strict black-and-white treatment keeps the people grid inside the monochrome system

### Inputs & Forms

**`text-input`**
- `{colors.field}` fill, no border, `{colors.ink}` text with `{colors.text-faint}` placeholder, `{rounded.sm}` corners, padding `{spacing.sm} {spacing.md}`

**`text-input-focused`**
- Same chrome plus a 2px `{colors.ink}` ring — focus is signaled in ink, consistent with the monochrome system

### Navigation

**`nav-pill`** — Top Nav (Desktop)
- A floating, horizontally-centered stadium bar in `{colors.canvas-soft}`: logomark + wordmark left, text links in `{typography.link}` right, capped by a `button-primary` CTA
- Detaches from the page edge with visible canvas above it; persists as a sticky element on scroll

**Top Nav (Mobile)**
- The pill tightens to logomark + CTA; links collapse behind the pill

**Sub-nav (section pages)**
- Minimal corner marks instead of a bar: logomark + section name top-left, a `button-pill-soft` return link to the main site top-right

### Signature Components

**`app-icon-squircle`** — the recurring 30%-radius icon tile; floats in loose clouds around counters, lines up in rows, and anchors `brand-chip` entries

**`brand-chip`** — marquee lockup of squircle icon + brand name in `{typography.heading-3}` ink; scrolls horizontally in full-bleed strips of recognizable products

**`badge-popular`** — compact `{colors.accent}` chip with `{colors.on-primary}` label marking the featured pricing tier; the only blue element on the page

**`badge-overlay`** — translucent gray pill (rgba(115, 115, 115, 0.56)) with `{colors.on-primary}` `{typography.label}` text, laid over photography and screenshots (category tags, portrait captions)

**`segmented-control`** + **`segmented-control-active`** — billing-period toggle: a `{colors.canvas-soft}` stadium track holding two pill options; the active option is a `{colors.canvas}` white pill, the inactive label sits in `{colors.text-muted}`

**`award-lockup`** — centered featured-item presentation: category eyebrow in `{colors.text-muted}`, name in `{typography.heading-3}`, description in `{colors.text-muted}` `{typography.body}`, a supporting figure in `{typography.body-sm}`, closed by a `button-pill-soft`

**`compare-table`** — the pricing comparison grid: feature rows divided by 1px `{colors.canvas-soft}` rules, the recommended plan's column washed in `{colors.canvas-soft}` with an inset ring edge

**`footer`** — full-width `{colors.ink}` band with `{rounded.md}` top corners: white wordmark at display scale, tagline in `{colors.on-primary-soft}`, two columns of `{colors.on-primary-soft}` links that read in `{colors.on-primary}` for emphasis rows

### Examples (illustrative)

> Kit-mirror demonstration surfaces. Each `ex-*` entry references brand-native primitives via token syntax so downstream consumers re-skin the same 10 surfaces consistently; none carries invented literal values.

**`ex-pricing-tier`** — Default Pricing tier card. Re-uses feature-card chrome with brand canvas-soft surface.
- Properties: `backgroundColor`, `textColor`, `borderColor`, `rounded`, `padding`

**`ex-pricing-tier-featured`** — Featured/highlighted tier — polarity-flipped surface (dark fill + light text in light mode, light fill + dark text in dark mode).
- Properties: `backgroundColor`, `textColor`, `rounded`, `padding`

**`ex-product-selector`** — What's Included summary card — re-purposed for SaaS / B2B verticals (NOT a literal product gallery).
- Properties: `backgroundColor`, `rounded`, `padding`

**`ex-cart-drawer`** — Subscription summary — re-purposed for SaaS / B2B (line items per add-on, not literal cart).
- Properties: `backgroundColor`, `rounded`, `padding`, `item-divider`

**`ex-app-shell-row`** — Sidebar nav row inside the App Shell example. Active state uses brand primary as the indicator.
- Properties: `backgroundColor`, `activeIndicator`, `rounded`, `padding`

**`ex-data-table-cell`** — Default data-table th + td chrome. Header uses mono-caps eyebrow typography; body uses body-sm.
- Properties: `headerBackground`, `headerTypography`, `bodyTypography`, `cellPadding`, `rowBorder`

**`ex-auth-form-card`** — Sign-in / sign-up card. Re-uses feature-card chrome with text-input primitives inside.
- Properties: `backgroundColor`, `rounded`, `padding`

**`ex-modal-card`** — Modal dialog surface — same chrome as feature-card with elevated shadow.
- Properties: `backgroundColor`, `rounded`, `padding`

**`ex-empty-state-card`** — Empty-state illustration frame.
- Properties: `backgroundColor`, `rounded`, `padding`, `captionTypography`

**`ex-toast`** — Toast notification surface — feature-card shape + medium shadow.
- Properties: `backgroundColor`, `rounded`, `padding`, `typography`


## Do's and Don'ts

### Do
- Keep the canvas `{colors.canvas}` white and let imported content (screenshots, icons, logos) supply all saturation.
- Use `{rounded.full}` for every interactive element — a rectangular button does not exist in this system.
- Build emphasis with the tint ladder: `{colors.canvas-soft}` fill for featured surfaces, `{colors.hairline-soft}` outlines for resting cards.
- Reserve `{colors.accent}` for commercial signals (featured badges, savings callouts) — one or two blue elements per page at most.
- Set every heading in Saans 652 with line-height 1.0–1.13 and end headline sentences with a period.
- Pair heavy 652 headings with 300-weight `{typography.body-lg}` subtitles for hierarchy without color.
- Render app icons as 30% squircles and portraits in grayscale to keep third-party imagery inside the system.
- Close pages with the inverse `{colors.ink}` footer, rounded at the top.

### Don't
- Don't add drop shadows — elevation is fills and hairlines only.
- Don't use `{colors.accent}` for CTAs; primary actions are always `{colors.primary}` ink pills.
- Don't introduce additional accent hues, gradients on UI chrome, or colored section bands.
- Don't outline the featured pricing tier — feature it with the `{colors.canvas-soft}` fill and `badge-popular` instead.
- Don't apply letter-spacing or all-caps styling; the type system runs at natural tracking in sentence case.
- Don't put borders on form fields at rest — inputs are `{colors.field}` tint fills; the border appears only as the 2px ink focus ring.
- Don't let full-color photography of people into people grids; portraits are strictly black-and-white.
- Don't square off pill geometry at small sizes — badges, chips, and toggles stay stadium-shaped.

## Motion

The system above is silent on motion beyond marquees, and Sector 4 has no marquees. These tokens are proposed for this site and follow the system's temperament: quiet, quick and flat. Motion confirms that something responded or arrived. It never decorates.

| Token | Value | Use |
|---|---|---|
| `{motion.quick}` | 120ms | Colour, fill and underline changes on hover and focus |
| `{motion.base}` | 200ms | Moving between two states: the segmented-control pill, a disclosure opening |
| `{motion.enter}` | 360ms | Rows, list items and panels arriving |
| `{motion.fill}` | 700ms | Probability bars filling to their value |
| `{motion.stagger}` | 30ms | Delay between successive rows in a list or table |
| `{motion.stagger-steps}` | 12 | Rows after the twelfth arrive together, so no list takes longer than 360ms to settle |
| `{motion.rise}` | 6px | Distance an arriving element travels upward |
| `{motion.ease-out}` | cubic-bezier(0.2, 0, 0, 1) | Anything arriving or responding |
| `{motion.ease-standard}` | cubic-bezier(0.4, 0, 0.2, 1) | Anything moving between two resting states |

### Rules
- **CSS only.** The single script on the site is the countdown, which already has to run; it adds a class when a value changes so CSS can animate the change. No animation library.
- **Composited properties only.** Opacity, transform, colour, background colour and border colour. Never width, height, margin, padding, top or left, so no animation can move layout or register as layout shift. A bar fills by sliding a fixed-width fill in with `transform`, not by growing its width.
- **Never on the largest element.** Page headings and hero leads do not animate in, so the largest contentful paint is never waiting on an animation.
- **Once.** Entrance animations run on arrival and do not repeat on scroll.
- **Reduced motion.** Under `prefers-reduced-motion: reduce` every duration and stagger becomes 0 and the rise distance becomes 0. Content arrives in its final state.
- **Performance is the gate.** A piece of motion that costs Lighthouse score or script budget does not ship.

### Where it is used
- **Rows and cards:** hover and focus-within wash to the next step of the tint ladder in `{motion.quick}`. Link cards lift 2px as well, which is the only depth the system allows besides fills and hairlines. There are no shadows.
- **Links:** the underline darkens from `{colors.text-muted}` to `{colors.ink}` and thickens from 1px to 2px.
- **Tables and lists:** rows rise `{motion.rise}` and fade in, `{motion.stagger}` apart.
- **Probability bars:** fill from the left over `{motion.fill}`, after their row has arrived.
- **Snapshot toggle:** the active pill slides between options in `{motion.base}`; the incoming panel's rows and numbers rise into place.
- **Countdown:** the value that changed rises into place each minute.

## Accessibility

Every text colour is measured on every surface it can appear on, and every pairing clears WCAG AA for normal text (4.5:1), including 12px labels. No pairing relies on the large-text allowance. `tests/contrast.test.ts` in `web/` recomputes each row from the shipped tokens and fails the build if a ratio is wrong or drops below AA, if a text colour is missing a surface it is declared to appear on, or if CSS sets text in a colour that has no text role here.

### Roles

| Token | Role | Appears on |
|---|---|---|
| `{colors.primary}` | surface | — |
| `{colors.on-primary}` | text | primary, ink, ink-soft, accent |
| `{colors.on-primary-soft}` | text | primary, ink, ink-soft |
| `{colors.ink}` | text, surface | canvas, canvas-soft, field |
| `{colors.ink-soft}` | text, surface | canvas, canvas-soft, field |
| `{colors.text-muted}` | text | canvas, canvas-soft, field |
| `{colors.text-faint}` | text | canvas, canvas-soft, field |
| `{colors.canvas}` | surface | — |
| `{colors.canvas-soft}` | surface | — |
| `{colors.field}` | surface | — |
| `{colors.hairline-soft}` | line | — |
| `{colors.hairline}` | line | — |
| `{colors.accent}` | text, surface | canvas, canvas-soft, field |

`{colors.ink-soft}` is a surface only as the hover state of a `button-primary`. `{colors.field}` is a surface as the hover state of anything resting on `{colors.canvas-soft}`, which is why every light text colour is measured on it.

### Contrast

| Pairing | Ratio | Meets |
|---|---|---|
| `{colors.ink}` on `{colors.canvas}` | 18.42:1 | AA, AAA |
| `{colors.ink}` on `{colors.canvas-soft}` | 16.60:1 | AA, AAA |
| `{colors.ink}` on `{colors.field}` | 16.17:1 | AA, AAA |
| `{colors.ink-soft}` on `{colors.canvas}` | 15.13:1 | AA, AAA |
| `{colors.ink-soft}` on `{colors.canvas-soft}` | 13.64:1 | AA, AAA |
| `{colors.ink-soft}` on `{colors.field}` | 13.28:1 | AA, AAA |
| `{colors.text-muted}` on `{colors.canvas}` | 6.69:1 | AA |
| `{colors.text-muted}` on `{colors.canvas-soft}` | 6.03:1 | AA |
| `{colors.text-muted}` on `{colors.field}` | 5.87:1 | AA |
| `{colors.text-faint}` on `{colors.canvas}` | 5.33:1 | AA |
| `{colors.text-faint}` on `{colors.canvas-soft}` | 4.80:1 | AA |
| `{colors.text-faint}` on `{colors.field}` | 4.68:1 | AA |
| `{colors.accent}` on `{colors.canvas}` | 5.34:1 | AA |
| `{colors.accent}` on `{colors.canvas-soft}` | 4.81:1 | AA |
| `{colors.accent}` on `{colors.field}` | 4.69:1 | AA |
| `{colors.on-primary}` on `{colors.primary}` | 18.42:1 | AA, AAA |
| `{colors.on-primary}` on `{colors.ink}` | 18.42:1 | AA, AAA |
| `{colors.on-primary}` on `{colors.ink-soft}` | 15.13:1 | AA, AAA |
| `{colors.on-primary}` on `{colors.accent}` | 5.34:1 | AA |
| `{colors.on-primary-soft}` on `{colors.primary}` | 8.21:1 | AA, AAA |
| `{colors.on-primary-soft}` on `{colors.ink}` | 8.21:1 | AA, AAA |
| `{colors.on-primary-soft}` on `{colors.ink-soft}` | 6.74:1 | AA |

### Other rules
- **Focus** is a 2px `{colors.ink}` ring offset 2px on light surfaces and a 2px `{colors.on-primary}` ring on the footer, on every interactive element. Both exceed the 3:1 non-text minimum on every surface they sit on.
- **Links inside text** are the same colour as the text around them, so they are always underlined. Colour never carries meaning alone.
- **Hairlines** are non-text. They only need to be visible, and `{colors.hairline}` is used wherever a line separates content rather than decorating it.
- **Touch targets** are at least 44px tall: every pill button, nav link and segmented option.

## Applied to Sector 4

Where the sections above describe patterns Sector 4 does not use, this is how each rule lands on a site of race predictions. Where they are silent, the choice made is recorded here.

- **Typeface.** Inter, per the note on font substitutes above: 652 → 650, 456 → 450, 300 and 600 unchanged, line-heights as specified. Self-hosted, latin subset only. Numbers use Inter with tabular figures; there is no second family, because the reference sets one typeface in every role.
- **No imagery.** The system lets content and photography carry colour. Sector 4 carries no photography, logos or series imagery at all. Colour comes from data only: a team's colour appears as a small squircle marker (the 30% radius of `app-icon-squircle`) beside the team's name in text. It is never chrome, never a fill behind text and never text colour.
- **The accent.** Sector 4 has no commercial signals. The accent marks the single time-sensitive thing on a page, the upcoming race, as a `badge-popular`-style chip. One per page at most. Never a button, never a link.
- **Outcomes.** The system has no success or error palette, and neither does this site. Hits and misses are written as words ("Called", "Missed", "Hit", "Miss") and deltas carry their sign. Nothing is green or red.
- **Notices.** The preview banner and the reduced-snapshot note use a `{colors.canvas-soft}` fill with an ink label: a step on the tint ladder, not a warning colour.
- **Links.** Inline links are ink and underlined. Standalone links are `button-pill-soft` pills; the one primary action on a page is a `button-primary` pill.
- **Bands.** There are no dark section bands. The `{colors.ink}` footer is the only inverse surface on any page.
- **Headlines.** Sentence case with a terminal period where the headline is a sentence ("Scored in public."). A race or circuit name used as a heading is a name, not a sentence, and takes no period.
- **Tables.** `ex-data-table-cell` as specified: `{colors.canvas-soft}` header in `{typography.caption}`, body in `{typography.body-sm}`, `{spacing.sm} {spacing.md}` cells, `{colors.hairline}` row rules. Its description mentions a mono-caps eyebrow; the Don'ts forbid all-caps and a second family, and the Don'ts win.
- **Charts.** Bars and distributions are `{colors.ink}` on a `{colors.field}` track, pill-ended. Every chart has its values in text beside it or in an accessible table; the drawing is decorative.
- **Dark mode.** The system defines none. The site is light only.
