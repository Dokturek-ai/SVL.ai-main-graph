# Dokturek.ai Design System

> Portable, markdown-based design system (DESIGN.md format) extracted from the live
> [dokturek.ai](https://dokturek.ai/) site. Drop into a project root so an AI coding
> agent can build UI matching the Dokturek.ai brand. Plain text, version-controllable,
> tool-agnostic.

**Brand:** Dokturek.ai — AI, která automatizuje klinickou administrativu. „Vracíme lékaře k pacientům."
**Direction:** Deep-violet medical-tech. Bold expressive display headings, calm light surfaces,
saturated purple accents, soft lilac glows on dark hero backgrounds.

---

## Colors

### Brand / Primary
- **Primary** (`#7C3BED`): Main brand purple. Filled buttons, badges, active states, numbered markers.
- **Primary Hover** (`#6D39C6`): Hover/pressed state for primary surfaces.
- **Primary Deep** (`#5914D2`): Strong accent, emphasis fills.

### Hero Gradient (dark sections)
- Diagonal gradient, top-left → bottom-right:
  - **Gradient Start** (`#20074B`) 0%
  - **Gradient Mid** (`#340B79`) 50%
  - **Gradient End** (`#5C0986`) 100%
- CSS: `linear-gradient(to bottom right, #20074B 0%, #340B79 50%, #5C0986 100%)`
- Used full-bleed behind hero and CTA sections. Text on top is white.

### Accent / Glow
- **Lilac** (`#DB9EFA`): Hero headline highlight word, decorative radial glows.
- **Orchid** (`#C058F3`): Secondary glow / accent gradients.
- Glow pattern: `radial-gradient(circle, #DB9EFA, transparent 70%)` — soft atmospheric blobs.

### Neutrals
- **Background** (`#FFFFFF`): Page background (light sections).
- **Surface** (`#F4F3FC`): Alternating section background, subtle lilac-tinted off-white.
- **Surface Card** (`rgba(244,243,252,0.6)`): Card fill, translucent over light bg.
- **Border** (`#E5DFFB`): Card borders, dividers (lilac-tinted, ~60% opacity in use).

### Text
- **Text Primary** (`#130F3E`): Headings and body on light backgrounds (deep indigo, not black).
- **Text Muted** (`rgba(19,15,62,0.8)`): Secondary text, nav links, captions.
- **Text On Dark** (`#FFFFFF`): All text on hero/gradient backgrounds.
- **Text On Dark Muted** (`rgba(255,255,255,0.7)`): Sub-copy on dark, inactive lang toggle.

### Semantic
- Use **Primary** `#7C3BED` for highlights/savings callouts (e.g. „až 50%").
- No separate success/error palette defined on site — derive from primary if needed.

---

## Typography

Two families. Display = expressive, Body = neutral.

- **Display** — `Bricolage Grotesque`, weight **800**, fallback `system-ui, sans-serif`.
  Used for all `h1`/`h2`/section titles. Tight negative tracking.
- **Body** — `DM Sans`, weights 400/500/600/700, fallback `system-ui, sans-serif`.
  Used for paragraphs, nav, buttons, labels.

### Scale
| Style | Font | Size | Weight | Line height | Letter spacing |
|-------|------|------|--------|-------------|----------------|
| H1 / Hero | Bricolage Grotesque | 72px | 800 | 75.6px (1.05) | -1.8px |
| H2 / Section | Bricolage Grotesque | 60px | 800 | 66px (1.1) | -1.5px |
| H3 | Bricolage Grotesque | ~32px | 800 | 1.2 | -0.5px |
| Lead / Intro | DM Sans | 24px | 400 | 39px (1.6) | normal |
| Body | DM Sans | 16px | 400 | 24px (1.5) | normal |
| Nav / Label | DM Sans | 16px | 500 | 1.5 | normal |
| Button | DM Sans | 14px | 600 | 1 | normal |
| Caption / Pill | DM Sans | 12px | 700 | 1 | normal |

**Rule:** Headlines are large and tightly tracked. Body stays generous (1.5–1.6 line height) for readability.

---

## Spacing

- **Base unit:** 4px. Scale: 4 / 8 / 12 / 16 / 20 / 24 / 28 / 32 / 48 / 64 / 96.
- **Card padding:** 28px.
- **Button padding:** 8px 16px (primary), 4px 12px (compact/pill toggle), 12px 16px (input/large).
- **Nav item padding:** 12px.
- **Section vertical rhythm:** large (`clamp(4rem, 5vw, 8rem)`) — sections breathe; alternate
  white ↔ `#F4F3FC` ↔ dark gradient.
- Content max-width centered container; generous gutters.

---

## Components

### Buttons
- **Primary (filled):** bg `#7C3BED`, text `#FFFFFF`, radius **full** (pill), padding `8px 16px`,
  font DM Sans 14px / 600, subtle shadow (`0 4px 6px -1px rgba(0,0,0,0.1)`).
  Hover → `#6D39C6`.
- **Secondary / outline:** transparent bg, `#130F3E` text, 1px border, pill radius. On dark: white text + `rgba(255,255,255,0.2)` border.
- **Lang toggle:** compact pill `4px 12px`, 12px/700; active `#130F3E`, inactive `rgba(255,255,255,0.7)`.

### Cards
- bg `rgba(244,243,252,0.6)`, border `1px solid #E5DFFB` (~60% opacity), radius **16px**, padding **28px**.
- No drop shadow by default — depth comes from border + tinted fill.
- Used for feature grids, team cards, FAQ items.

### Inputs
- bg `rgba(255,255,255,0.1)` (on dark) / white (on light), border `1px solid rgba(255,255,255,0.2)`,
  radius **12px**, padding `12px 16px`, font 16px.

### Badge / Pill
- Pill (full radius), `#7C3BED` bg, white text, 14px/600, padding `8px 16px`. E.g. „Beta program".

### Numbered markers
- Small circular `#7C3BED` filled badges with white numerals for ordered steps („Jak to funguje", team process).

### Glow blobs
- Decorative `radial-gradient(circle, #DB9EFA → transparent 70%)` and `#C058F3` variant,
  absolutely positioned behind hero content. Purely atmospheric, low opacity.

---

## Elevation

Site favors **flat + bordered** over heavy shadows.

- **Level 0 — Flat:** sections, light surfaces. No shadow; separation by background color.
- **Level 1 — Card:** border `1px #E5DFFB` + translucent fill. No shadow.
- **Level 2 — Button:** `0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)`.
- **Glow (atmosphere):** radial lilac/orchid gradients on dark hero — depth cue, not a real shadow.

Radius scale: `12px` (inputs), `16px` (cards), `full` / pill (buttons, badges).

---

## Guidelines

**Do**
- Pair expressive `Bricolage Grotesque 800` headings with calm `DM Sans` body.
- Alternate section backgrounds: white → `#F4F3FC` → dark violet gradient for rhythm.
- Keep deep-indigo `#130F3E` (not pure black) for text on light.
- Use the pill shape consistently for buttons and badges.
- Reserve lilac/orchid glows for dark hero/CTA sections only.
- Highlight key numbers/savings in `#7C3BED`.

**Don't**
- Don't use pure black `#000000` for text — use `#130F3E`.
- Don't drop shadows on cards — use the lilac border + tinted fill instead.
- Don't put glow blobs on light sections.
- Don't mix in a third type family.
- Don't square off buttons — they are always pills.

**Tone of voice:** Czech, empatický k lékařům, jasný, konkrétní, důvěryhodný.
Klíčové sdělení: méně administrativy, více medicíny; vracíme lékaře k pacientům.

---

*Format: DESIGN.md (Google Stitch). Source: live extraction of dokturek.ai computed styles.*
