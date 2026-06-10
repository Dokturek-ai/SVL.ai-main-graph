---
name: Doktůrek.ai
source: https://dokturek.ai/
extracted: 2026-06-10
colors:
  background: "#FFFFFF"
  foreground: "#130F3E"
  primary: "#7C3BED"
  primary-foreground: "#FFFFFF"
  accent-magenta: "#C058F3"
  accent-lilac: "#DB9EFA"
  violet-link: "#6D39C6"
  violet-deep: "#5914D2"
  surface-lavender: "#E5DFFB"
  surface-muted: "#F4F3FC"
  dark-1: "#20074B"
  dark-2: "#340B79"
  dark-3: "#5C0986"
  border: "#E7E1F4"
fonts:
  heading: "Bricolage Grotesque"
  body: "DM Sans"
---

# Design System: Doktůrek.ai
**Source:** https://dokturek.ai/ (live site) · **Language:** Czech (cs)

## 1. Visual Theme & Atmosphere

Doktůrek.ai is a confident, modern healthtech landing page built on a single
dominant brand color — a saturated electric violet — set against generous white
space. The page alternates between three moods: bright airy white sections for
content (problem, solution, features), tinted lavender sections for soft
breathing room, and dramatic deep-purple gradient sections that anchor the
hero, mid-page CTAs, and footer. This rhythm of light → tinted → dark keeps a
long scroll page feeling structured and intentional rather than flat.

The atmosphere is clean and optimistic but premium — not a generic SaaS
template. Headlines are oversized (72px hero) in an expressive grotesque
display face with tight negative letter-spacing, while body copy stays calm and
legible in a humanist sans. The dark hero pairs a multi-stop purple gradient
with soft radial lilac/magenta glows and a light-lilac headline highlight,
giving real depth and atmosphere. Spacing is generous, corners are soft (pill
buttons, 16px cards), and shadows are restrained — the visual weight comes from
color and scale contrast, not heavy elevation.

## 2. Color Palette & Roles

### Primary Foundation
- **Pure White** `#FFFFFF` — Page background, card surfaces
- **Soft Lavender Wash** `#F4F3FC` — Alternating section background (barely-tinted)
- **Light Lavender Surface** `#E5DFFB` — Pill badge / section-label background
- **Deep Royal Indigo** `#130F3E` — Dark text + footer/dark-zone foreground

### Accent & Interactive
- **Electric Violet** `#7C3BED` — Primary brand color: CTA buttons, badge text, icons, links
- **Vivid Magenta-Violet** `#C058F3` — Gradient end-stop, radial glow accent
- **Light Lilac** `#DB9EFA` — Hero headline highlight, radial glow
- **Saturated Link Violet** `#6D39C6` — Secondary violet for inline text/icons
- **Deep Violet** `#5914D2` — Strongest violet, emphasis text

### Dark Gradient (hero / CTA / footer)
- **Near-Black Indigo** `#20074B` → **Deep Purple** `#340B79` → **Royal Magenta-Purple** `#5C0986`
  diagonal `linear-gradient(to bottom right)`, overlaid with radial lilac/magenta glows.

### Typography & Text Hierarchy
- **Primary text** `#130F3E` (Deep Royal Indigo) — dominant body & heading color on light
- **On-dark text** `#FFFFFF` at 100% / 80% / 70% / 55% opacity for hierarchy
- **Accent text** `#7C3BED` — labels, links, highlighted terms
- **Hero highlight** `#DB9EFA` — the headline accent line on the dark hero

### Borders & States
- **Hairline border** `#E7E1F4` (light lilac-gray, ~0.6 alpha) — card & divider borders on light
- **Glass border (on dark)** `rgba(255,255,255,0.2–0.25)` — outlined ghost buttons over gradient

## 3. Typography Rules

### Families
- **Bricolage Grotesque** — display/headings and high-emphasis CTAs. An
  expressive, slightly quirky grotesque with character; used at heavy weights.
- **DM Sans** — body, nav, badges, UI labels. Clean, humanist, neutral, highly
  legible. Fallback stack: `system-ui, sans-serif`.

### Hierarchy & Weights
| Level | Font | Size | Weight | Line-height | Letter-spacing |
|:---|:---|:---|:---|:---|:---|
| H1 (hero) | Bricolage Grotesque | 72px | 800 | 75.6px (~1.05) | −1.8px (tight) |
| H2 (section) | Bricolage Grotesque | 60px | 800 | 66px (1.1) | −1.5px |
| Body | DM Sans | 16px | 400 | 24px (1.5) | normal |
| Nav links | DM Sans | 14px | 500 | — | normal |
| Badge / label | DM Sans | 14px | 500–600 | — | normal |
| Hero CTA label | Bricolage Grotesque | 18px | 700 | — | normal |

### Spacing Principles
- Display headings use **tight negative tracking** (−1.5 to −1.8px) for a
  dense, confident editorial feel; body stays at default tracking with relaxed
  1.5 line-height for readability.
- Big scale jump between display (60–72px) and body (16px) — hierarchy comes
  from dramatic size contrast, not many in-between steps.

## 4. Component Stylings

### Buttons
- **Shape:** fully rounded **pill** (`border-radius: 9999px`) on all buttons.
- **Primary (solid):** `#7C3BED` violet bg, white text, weight 600 (nav, 8×16px)
  — the dominant CTA color.
- **Hero primary (inverted):** white bg, `#130F3E` text, **Bricolage Grotesque
  700**, 18px, padding 16×28px — high-contrast CTA on dark gradient.
- **Hero secondary (ghost/glass):** `rgba(255,255,255,0.1)` bg, white text,
  `1px rgba(255,255,255,0.25)` border, same pill + padding — sits over the
  purple gradient.
- **Nav links:** plain text, DM Sans 14px/500, white at 80% opacity on dark hero.

### Badges / Section Labels
- Pill (`rounded-full`), **lavender `#E5DFFB` background, violet `#7C3BED`
  text**, weight 600, padding 8×16px — used as the eyebrow label above each
  section heading ("Problém", "Řešení", "Jak to funguje").
- Small tag variant: padding 2×10px, weight 500 — inline feature tags
  ("Proaktivní", "Real-time", "AI agenti").

### Cards
- **Radius:** 16px primary (also 12px for nested/smaller cards).
- **Surface:** white on light sections; hairline `#E7E1F4` lilac border.
- **Elevation:** restrained Tailwind shadow scale — `shadow-sm`
  (`0 1px 3px rgba(0,0,0,0.1)`) default, up to `shadow-2xl`
  (`0 25px 50px rgba(0,0,0,0.25)`) for featured/floating media.
- Feature cards carry a small gradient-filled icon tile
  (`linear-gradient(to bottom right, #7C3BED → #C058F3)`).

### Navigation
- **Fixed** top bar, transparent background (overlays the dark hero).
- DM Sans 14px/500 links, white at ~80% opacity; right side holds a
  CS/EN language pill toggle (glass style) and a solid violet "Beta program" CTA.

### Inputs & Forms
- Lead-capture form sits in the dark gradient CTA section; inputs are
  pill/rounded with glass treatment on the dark surface, paired with the
  inverted white primary button.

## 5. Layout Principles

### Grid & Structure
- Centered single-column landing layout with a constrained content container
  (Tailwind `container`, centered, ~`2xl: 1400px` max).
- Feature/step rows use even multi-column grids (2 and 4 across) that collapse
  on mobile.

### Whitespace Strategy
- Generous vertical section padding; each section opens with a lavender pill
  eyebrow + oversized heading + short subhead, then content.
- Section-level mood switching (white → `#F4F3FC` lavender → dark gradient)
  does the heavy lifting of visual separation instead of dividers.

### Alignment & Visual Balance
- Hero is **center-aligned** (eyebrow, huge headline, subhead, dual CTAs).
- Content sections lead-align headings; cards and stats balance left text with
  right media.
- Signature device: a single highlighted word/line in light lilac `#DB9EFA`
  within an otherwise white-on-dark hero headline.

### Responsive Behavior & Touch
- Mobile-first collapse of multi-column grids to stacked single column.
- Pill buttons give large, comfortable touch targets (≥44px tall at hero size).

## 6. Design System Notes for Stitch Generation

### Language to Use
- "Modern healthtech landing page, confident and premium, built around one
  saturated electric-violet brand color on generous white space."
- "Alternate bright white, soft-lavender, and dramatic deep-purple gradient
  sections down a long scroll."
- "Oversized expressive grotesque headlines with tight negative letter-spacing;
  calm humanist sans body."

### Color References
- Primary accent: **Electric Violet** `#7C3BED`
- Hero/footer gradient: `#20074B → #340B79 → #5C0986` (diagonal) + lilac/magenta radial glows
- Headline highlight: **Light Lilac** `#DB9EFA`
- Text: **Deep Royal Indigo** `#130F3E`
- Tinted surfaces: `#F4F3FC` (section), `#E5DFFB` (badges)

### Component Prompts
1. "Pill CTA button: solid electric-violet `#7C3BED`, white DM Sans semibold
   label; inverted variant is white bg with indigo `#130F3E` Bricolage Grotesque
   bold label for dark sections."
2. "Section eyebrow badge: small lavender `#E5DFFB` pill with violet `#7C3BED`
   semibold text, above a 60px Bricolage Grotesque 800 heading."
3. "Feature card: white surface, 16px radius, hairline lilac border, subtle
   shadow-sm, with a gradient-filled rounded icon tile (`#7C3BED → #C058F3`)."

### Incremental Iteration
- Keep one violet as the single hero accent — resist adding competing accent
  colors; depth should come from the purple gradient + opacity tiers of white.
- Maintain the white → lavender → dark-gradient section rhythm when adding
  screens so the long page stays structured.
- Pair Bricolage Grotesque (display, heavy + tight tracking) with DM Sans (body)
  consistently; do not introduce a third family.
