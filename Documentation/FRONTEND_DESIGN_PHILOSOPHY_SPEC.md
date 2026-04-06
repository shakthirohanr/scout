# Frontend Design Philosophy and Color Specification

## Purpose
This document defines the current design philosophy implemented in the frontend and translates it into a practical execution spec for coding agents.

Use this as the default visual contract when adding or modifying UI.

## Product Visual Intent
- Tone: operator console for CTF automation (calm, precise, utilitarian).
- Mood: low-noise, information-dense, technical, trustworthy.
- Visual strategy: neutral base surfaces with restrained accenting, clear status signaling, and terminal-first affordances.

## Core Design Philosophy

### 1. Function over ornament
- Prioritize readability and scanning over decorative styling.
- Most surfaces are flat (shadow-none) with border-led separation.
- Interaction feedback relies on subtle color shifts and focus rings, not heavy elevation.

### 2. Dense but structured information
- UI is intentionally high-density for operational work.
- Sections are compartmentalized into bordered cards, strips, and panels.
- Repeated patterns (header, cards, list rows, terminal) create predictable navigation.

### 3. Status visibility is mandatory
- Session and run states are always visible via badges and color coding.
- Error, running, solved, and canceled states should be recognizable at a glance.
- Time, counts, and progress indicators are surfaced near primary actions.

### 4. Terminal-native UX
- Terminal output is treated as a first-class artifact, not a secondary modal.
- Monospace typography and high-contrast terminal themes are part of core identity.
- Search, next/previous navigation, and refresh controls are colocated with terminal output.

### 5. Dark-first workflow with light-mode parity
- Default runtime behavior starts in dark mode, with explicit theme toggle support.
- All additions must preserve parity in dark and light variants.
- Light mode is not "marketing white"; it stays muted and operational.

## Layout and Composition Rules

### Global shell
- Full-height app shell with one primary scroll container for main content.
- Sidebar + content split on desktop; sheet-based navigation on mobile.
- Avoid nested competing scroll areas unless required (terminal and feed regions are intentional exceptions).

### Dashboard structure
- Header band with identity, utility actions, and theme controls.
- Left context rail (challenge list) on large screens.
- Main column sequence:
  - context summary card
  - metrics cards
  - optional session list
  - terminal/log block
  - analysis/support panels

### Card language
- Default shape language is squared edges in dashboard contexts (rounded-none overrides).
- Separation via `border-border/60` and muted surface fills.
- Avoid deep shadows; preserve flat operational look.

## Typography System
- Primary UI typeface: Space Grotesk.
- Monospace typeface: IBM Plex Mono.
- Heading style: compact, semibold, tracking-tight.
- Metadata style: small uppercase labels with increased tracking.
- Body text: concise and subdued with muted-foreground for secondary content.

### AI Agent Font Size Contract
Use these as default sizing rules when creating or editing frontend screens.

- Page title: `text-3xl font-semibold tracking-tight`
- Page subtitle/description: `text-sm text-muted-foreground`
- Section title (card/table section headers): `text-lg`
- Card title (compact cards): `text-base`
- Primary row/body text: `text-sm` to `text-base` depending density
- Metadata/supporting labels: `text-xs` or `text-sm` with muted foreground
- State labels: `text-sm uppercase tracking-[0.14em]` (or existing local equivalent)

Consistency rule:
- If one page in a flow uses the page title + subtitle pattern above, sibling pages in the same flow should match the same classes.

## Interaction and Motion
- Motion is minimal and utilitarian (loading spinners, small transitions).
- Focus states are explicit and accessible (ring-based).
- Hover states are subtle contrast shifts.
- Buttons are compact by default (height ~32px family, with size variants).

## Color System

The frontend currently uses layered color sources:
1. semantic theme tokens (`globals.css`)
2. dashboard surface accents (sage/olive neutrals)
3. state colors (status badge mappings)
4. terminal palette (`terminal.ts`)

### A. Semantic theme tokens

#### Light token base (defined in OKLCH)
- background: `oklch(0.975 0 0)`
- foreground: `oklch(0.205 0 0)`
- card: `oklch(0.995 0 0)`
- primary: `oklch(0.28 0 0)`
- secondary: `oklch(0.94 0 0)`
- muted: `oklch(0.955 0 0)`
- accent: `oklch(0.92 0 0)`
- border/input: `oklch(0.88 0 0)`
- ring: `oklch(0.58 0 0)`

#### Dark token base (defined in HEX)
- background: `#1e1e1e`
- foreground: `#cccccc`
- card: `#252526`
- primary: `#007acc`
- secondary: `#2d2d30`
- muted: `#2a2d2e`
- accent: `#37373d`
- destructive: `#f14c4c`
- border: `color-mix(in srgb, #ffffff 12%, transparent)`

### B. Dashboard accent neutrals (current usage)
These are intentional soft olive/sage surfaces used in dashboard and challenge views.

- panel-soft-1: `#f0f4e6`
- panel-soft-2: `#eef3e6`
- panel-soft-3: `#e7eddc`
- panel-soft-4: `#dfe7d2`

Usage guidance:
- Use as section backgrounds and selected-state fills in light mode.
- Pair with dark mode fallbacks (`dark:bg-card`, `dark:bg-background/40`, `dark:bg-accent/45`).
- Keep these accents limited to context surfaces; do not replace semantic primary actions.

### C. Status palette (badge semantics)
- running/live: sky family (`sky-500` variants)
- solved: slate family (`slate-400` variants)
- gave up: amber family (`amber-500` variants)
- cancelled: slate muted family
- error: rose family (`rose-500` variants)
- unknown: token-based neutral (`border-border`, `bg-muted`)

Status color rule:
- Keep semantic meaning stable across all pages.
- Do not remap status colors per page.

### D. Terminal palette

#### Terminal dark
- background: `#111214`
- foreground: `#e6e7ea`
- cursor: `#c4c7cf`
- selection: `#3f434b99`
- ANSI accents:
  - red: `#ff7782`
  - yellow: `#d6cf6d`
  - blue: `#9eb6ff`
  - magenta: `#e48fff`
  - cyan: `#95c6d8`

#### Terminal light
- background: `#f4f4f5`
- foreground: `#1f2328`
- cursor: `#4b5563`
- selection: `#cdd2d970`
- ANSI accents:
  - red: `#c2334a`
  - yellow: `#877317`
  - blue: `#3b5fb8`
  - magenta: `#8e3bb4`
  - cyan: `#37687f`

Terminal rule:
- Terminal theme must follow resolved app theme.
- Preserve high contrast and legibility of long traces.

## Component-Level Constraints for Coding Agents

### Do
- Prefer semantic token classes (`bg-card`, `text-foreground`, `border-border`) first.
- Use `rounded-none` in dashboard-operational surfaces to match current style language.
- Keep cards border-led and shadow-light (`shadow-none` unless strongly justified).
- Ensure all interactive elements have visible focus states.
- Preserve compact control sizing and dense spacing.
- Add dark mode counterparts for every non-token custom background.

### Do not
- Introduce bright, saturated gradients or glossy effects.
- Add deep elevation stacks, blur-heavy floating panels, or oversized rounded corners in dashboard views.
- Replace established status colors with arbitrary alternatives.
- Build parallel visual systems per page.

## AI Agent Container Sizing Contract

Use these container patterns for Home and Challenges style list/catalog pages.

### Page shell
- Root page wrapper: `flex min-h-full w-full flex-col bg-background px-4 py-6 sm:px-6 lg:px-8`
- Header section wrapper: `mb-6`
- Header content spacing: `space-y-2`
- Main content wrapper: `flex-1 pr-1`

### Primary content surfaces
- Main surface container: `rounded-lg border border-border bg-card shadow-none`
- Empty state container: `mt-8 rounded-lg border border-dashed border-border bg-card px-6 py-10 text-center text-sm text-muted-foreground`

### Alignment rule for sibling pages
- If Home and Challenges are both part of the same navigation group, keep page-level horizontal and vertical paddings identical.
- Avoid ad hoc per-page container drift such as mixing `px-4 py-6 sm:px-6 lg:px-8` with larger alternatives unless there is a documented product reason.

### Agent implementation checklist
- Check root page wrapper classes first.
- Check header block spacing second (`mb-*`, `space-y-*`).
- Check main surface border/radius/shadow tokens third.
- Check empty-state container sizing and text scale last.

## Quick Palette Blocks for Agent Reuse

### Operational neutral set
- `#1e1e1e`
- `#252526`
- `#2d2d30`
- `#cccccc`
- `#007acc`
- `#f14c4c`

### Light dashboard surface set
- `#f0f4e6`
- `#eef3e6`
- `#e7eddc`
- `#dfe7d2`
- `#1f2328`
- `#4b5563`

### Status set
- running: `sky-500` range
- solved: `slate-400` range
- warning/gave-up: `amber-500` range
- error: `rose-500` range
- unknown: token neutral (`muted/border`)

## Accessibility and Quality Gates
- Maintain readable contrast for all text and status badges in both themes.
- Ensure keyboard focus is visible for buttons, links, tabs, and list items.
- Preserve responsive behavior (mobile sheet, desktop split layout).
- Keep one dominant scroll axis per major screen region.

## Implementation Note for Future Work
If introducing new branded accents, extend via semantic tokens first and then map selective panel accents. Do not bypass token architecture with broad hard-coded color usage.