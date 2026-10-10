# Sovereign Creative Studio UI Upgrade Design

## Intent

Upgrade Sovereign Creative Studio into a coherent, professional local creative-production application without replacing its product identity or changing its business logic. Restore visible motion in a way that preserves accessibility, strengthen the shell and shared component system, improve the home and high-traffic workflows, and prove the result through automated and browser verification.

## Evidence and root cause

The motion implementation is present and committed (`e599388`, `edc8e5a`). `MotionProvider`, the GSAP hooks, Lenis, page transitions, dialog motion, count-up, shimmer, and reduced-motion guards remain mounted. The Lenovo laptop has Windows “Animation effects” disabled, so ordinary browsers report `prefers-reduced-motion: reduce`; the implementation correctly suppresses nearly all motion. The product therefore needs an explicit in-app preference rather than an operating-system change.

## Product direction

Sovereign remains a dark, local-first creative studio: charcoal surfaces, sky-cyan primary accent, restrained violet support, Plus Jakarta Sans, Lucide icons, and purposeful cinematic depth. The upgrade is a refinement, not a replacement. It favors a precise Swiss-style layout, clear hierarchy, consistent component states, compact professional density, and restrained motion that explains state and navigation.

## Goals

- Add a Motion preference with `Follow system`, `Always on`, and `Off` choices.
- Make that preference control CSS, GSAP, Lenis, canvas, and count-up motion consistently.
- Keep `Follow system` as the default and preserve `prefers-reduced-motion` behavior.
- Consolidate visual tokens for surfaces, elevation, spacing, typography, focus, and motion.
- Upgrade the desktop rail, top bar, mobile navigation, account menu, and page frame.
- Improve the home experience and shared components used across the application.
- Apply the shared system to representative high-traffic surfaces without altering APIs, routes, state, or generation workflows.
- Improve responsive behavior, keyboard navigation, focus visibility, control naming, loading, empty, error, disabled, and success states.
- Verify at 375, 768, 1024, and 1440 CSS pixels, including reduced motion and forced motion.

## Non-goals

- No backend, database, provider, credit, authentication, or generation changes.
- No new cloud dependency, design framework, icon library, animation library, or font.
- No Windows setting changes.
- No wholesale rewrite of every feature component.
- No decorative motion that blocks input, animates layout, or ignores user preference.
- No deletion of existing workflows or routes.

## Architecture

### Motion preference

`MotionProvider` becomes a context provider around the application shell. A small `motion-preference` module owns the stable storage key `scs_motion_preference`, the `system | on | off` type, resolution against `matchMedia`, and the root `data-motion` attribute. `useMotionPreference()` exposes the selected preference, resolved enabled state, and setter. The account menu presents the three choices.

CSS motion keys from the root `data-motion` state rather than directly from the OS media query. GSAP hooks, Lenis, the dot grid, count-up, and spectrum canvas use the same resolved state. Changing the preference takes effect without a reload and cleans up active timelines, tickers, and smooth scrolling.

### Visual system

Existing HSL variables remain the public token interface. Additional semantic tokens cover subdued/raised surfaces, elevation, overlays, focus, content widths, and motion timing. Shared UI primitives own control height, radius, focus, disabled, and state styling so individual screens stop inventing them.

### Shell and responsive model

Desktop keeps the slim rail and top bar. Flyouts gain explicit keyboard/click behavior, stable focus handling, and consistent elevation. Mobile keeps one primary navigation entry point with adequate touch targets and no hidden content beneath fixed chrome. The main frame uses consistent responsive gutters and readable maximum widths.

### Surface upgrades

The home view becomes the reference composition for hierarchy, cards, calls to action, and motion. Gallery, Projects, Avatars, Apps, Video Agent, Music Lab, Credits, and admin/status surfaces inherit shared primitives and state patterns. Feature logic stays in place; changes focus on layout, content hierarchy, and interaction quality.

## Acceptance criteria

- Motion defaults to the operating-system preference.
- `Always on` visibly animates the welcome treatment in a browser even when the OS requests reduced motion.
- `Off` disables CSS, GSAP, Lenis, count-up, canvas, shimmer, and transition motion.
- The setting persists across reload and can be changed by keyboard.
- Existing primary routes and APIs behave as before.
- No horizontal overflow at 375, 768, 1024, or 1440 widths.
- Keyboard users can reach navigation, menus, forms, and primary actions with visible focus.
- Shared loading, empty, error, disabled, hover, active, and success states are consistent.
- Frontend typecheck, lint, production build, and relevant Playwright suites pass.
- Browser verification produces screenshots for home, shell/navigation, a content library, and a creation workflow at desktop and mobile widths.

## Constraints

- Next.js 14, React 18, Tailwind 3, GSAP 3.15, Lenis 1.3, and Lucide remain pinned.
- Source edits stay on branch `ui-upgrade-2026-10` and use named-file commits only.
- The backend remains untouched unless a frontend verification failure proves a pre-existing backend blocker.
- The real app must be rebuilt with `.next-cinematic-fixed` and verified through Playwright after frontend changes.

