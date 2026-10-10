# Sovereign UI Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the apparent motion regression and deliver a professional, accessible, responsive UI upgrade across Sovereign’s shared shell and primary creative workflows without changing product behavior.

**Architecture:** A persisted three-state motion preference becomes the single authority for CSS, GSAP, Lenis, and canvas motion. Existing semantic tokens and shared React primitives are extended, then the shell, home, and high-traffic surfaces adopt them incrementally; browser tests lock the result down.

**Tech Stack:** Next.js 14, React 18, TypeScript 5.5, Tailwind CSS 3.4, GSAP 3.15, Lenis 1.3, Lucide React, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-10-sovereign-ui-upgrade-design.md`

## Global Constraints

- Preserve all routes, API contracts, state management, generation workflows, authentication, credits, and backend behavior.
- Keep the existing charcoal/sky-cyan/violet identity, Plus Jakarta Sans, Lucide icons, and installed motion libraries.
- Add no dependency and make no Windows setting change.
- `Follow system` is the default motion preference; `Always on` and `Off` are explicit user overrides.
- Motion uses transform/opacity, remains interruptible, never blocks input, and is disabled when the resolved preference is off.
- Use named-file commits only and never push.

## Review Focus

- Missing or corrupt localStorage preference resolves safely to `system`; Task 1 tests it.
- Preference changes while the page is open clean up and recreate Lenis/GSAP work exactly once; Task 2 tests it.
- Menus and flyouts remain usable by keyboard, pointer, and touch without hover dependence; Task 4 tests it.
- Long labels, empty data, API failure, and loading states do not break layout or misrepresent state; Tasks 5 and 6 test them.
- 375px layouts have no horizontal overflow or obscured focus/content; Task 7 tests it.

---

### Task 1: Motion preference contract

**Files:**
- Create: `frontend/src/lib/motion-preference.ts`
- Create: `frontend/e2e/motion-preference.spec.ts`
- Modify: `frontend/playwright.config.ts`

**Interfaces:**
- Produces: `MotionPreference = "system" | "on" | "off"`, `MOTION_STORAGE_KEY`, `parseMotionPreference(value)`, and `resolveMotionEnabled(preference, systemReduced)`.
- Consumes: browser `localStorage` and `matchMedia` only.

- [ ] Write Playwright coverage for default/system resolution, invalid stored values, persistence, and the three selectable states.
- [ ] Run the focused suite and verify it fails because no product preference exists.
- [ ] Implement the pure preference contract with safe parsing and no browser access at module import time.
- [ ] Re-run the focused suite and verify the contract assertions pass.
- [ ] Commit the named files as `feat(ui): define persisted motion preference`.

### Task 2: Unified motion runtime

**Files:**
- Modify: `frontend/src/components/motion/motion-provider.tsx`
- Modify: `frontend/src/components/motion/use-motion.ts`
- Modify: `frontend/src/components/motion/dot-grid.tsx`
- Modify: `frontend/src/components/motion/count-up.tsx`
- Modify: `frontend/src/components/music/spectrum-canvas.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/template.tsx`
- Modify: `frontend/src/app/globals.css`
- Test: `frontend/e2e/motion-preference.spec.ts`

**Interfaces:**
- Consumes: Task 1’s `MotionPreference` contract.
- Produces: `MotionProvider({ children })`, `useMotionPreference()`, and root `data-motion="on|off"` state.

- [ ] Extend the focused test to assert that forced-on motion runs under emulated reduced motion, forced-off motion does not run, and preference changes apply without reload.
- [ ] Run it and verify failure against the OS-only implementation.
- [ ] Convert `MotionProvider` into the single runtime authority and wrap the application in `layout.tsx`.
- [ ] Route GSAP, Lenis, canvas, count-up, page, dialog, shimmer, glow, and spotlight motion through the resolved state with cleanup on changes.
- [ ] Run the focused test plus `npm run typecheck`; verify both pass.
- [ ] Commit the named files as `fix(ui): unify motion preference and runtime`.

### Task 3: Design tokens and shared primitives

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/src/components/ui/button.tsx`
- Modify: `frontend/src/components/ui/card.tsx`
- Modify: `frontend/src/components/ui/input.tsx`
- Modify: `frontend/src/components/ui/textarea.tsx`
- Modify: `frontend/src/components/ui/badge.tsx`
- Modify: `frontend/src/components/ui/skeleton.tsx`
- Modify: `frontend/src/components/ui/empty-state.tsx`
- Modify: `frontend/src/components/ui/load-error.tsx`
- Modify: `frontend/src/components/page-header.tsx`
- Test: `frontend/e2e/ui-upgrade.spec.ts`

**Interfaces:**
- Produces: consistent semantic surfaces, elevation, focus, control sizes, content widths, typography roles, and state styling.
- Consumes: existing `cn`, CVA, HSL token names, and Lucide icons.

- [ ] Add browser assertions for focus visibility, minimum control sizes, error semantics, disabled state, and stable card/input styling.
- [ ] Run the test and verify current primitives fail the new shared contract.
- [ ] Extend tokens and primitives without changing their existing public props.
- [ ] Replace ad-hoc visual constants only where the shared primitive now owns them.
- [ ] Run the focused test and typecheck; verify both pass.
- [ ] Commit as `feat(ui): strengthen design tokens and primitives`.

### Task 4: Application shell and motion control

**Files:**
- Modify: `frontend/src/components/shell/app-rail.tsx`
- Modify: `frontend/src/components/topbar.tsx`
- Modify: `frontend/src/components/mobile-navigation.tsx`
- Modify: `frontend/src/lib/navigation.ts`
- Modify: `frontend/src/app/layout.tsx`
- Test: `frontend/e2e/ui-upgrade.spec.ts`

**Interfaces:**
- Consumes: Task 2’s `useMotionPreference()` and Task 3’s shared control styling.
- Produces: keyboard-safe desktop/mobile navigation, account menu motion selector, consistent page frame, and stable responsive gutters.

- [ ] Add tests for rail/menu keyboard access, outside-click/Escape closing, current-page state, 44px touch targets, and selecting all three motion modes.
- [ ] Run the tests and verify the current hover-oriented shell fails the contract.
- [ ] Implement explicit pointer, keyboard, and touch behavior without changing navigation destinations.
- [ ] Add the accessible three-choice motion control to the account menu.
- [ ] Run focused shell tests and typecheck; verify both pass.
- [ ] Commit as `feat(ui): upgrade responsive application shell`.

### Task 5: Home experience

**Files:**
- Modify: `frontend/src/components/home/welcome-view.tsx`
- Modify: `frontend/src/components/motion/blur-words.tsx`
- Modify: `frontend/src/components/motion/dot-grid.tsx`
- Modify: `frontend/src/components/director/template-carousel.tsx`
- Test: `frontend/e2e/ui-upgrade.spec.ts`

**Interfaces:**
- Consumes: Tasks 2–4 motion, tokens, primitives, and shell.
- Produces: a polished reference page with clear setup progress, one primary next action, reliable media cards, and accessible motion.

- [ ] Add mocked-API tests for loading, partial failure, zero progress, completed progress, long user names, CTA hierarchy, keyboard operation, and responsive overflow.
- [ ] Run them and record the expected failures.
- [ ] Refine hierarchy, spacing, card composition, imagery treatment, progress messaging, and CTA emphasis while preserving links and API calls.
- [ ] Ensure animated decoration is non-essential and off under resolved reduced motion.
- [ ] Run the focused home tests and typecheck; verify both pass.
- [ ] Commit as `feat(ui): refine Sovereign home experience`.

### Task 6: Primary libraries and creation workflows

**Files:**
- Modify: `frontend/src/components/gallery-view.tsx`
- Modify: `frontend/src/components/projects/projects-library-view.tsx`
- Modify: `frontend/src/components/avatars/avatar-gallery-view.tsx`
- Modify: `frontend/src/components/apps/apps-library-view.tsx`
- Modify: `frontend/src/components/video-agent/video-agent-view.tsx`
- Modify: `frontend/src/components/music/music-lab-view.tsx`
- Modify: `frontend/src/components/credits-view.tsx`
- Modify: `frontend/src/components/admin-dashboard-view.tsx`
- Modify: `frontend/src/components/status-view.tsx`
- Test: `frontend/e2e/ui-upgrade.spec.ts`

**Interfaces:**
- Consumes: shared tokens, components, layout, and state language from Tasks 3–5.
- Produces: consistent library grids, creation forms, status summaries, loading/empty/error/success states, and responsive section hierarchy.

- [ ] Add route-level browser checks with mocked API states for each named surface, covering long labels, empty/error/loading data, primary action visibility, keyboard focus, and overflow.
- [ ] Run the focused route matrix and record failures.
- [ ] Apply shared primitives and hierarchy without changing workflow state or request payloads.
- [ ] Correct accessibility and responsive defects discovered by the matrix.
- [ ] Run the route matrix, existing `ui-phase1.spec.ts`, and typecheck; verify all pass.
- [ ] Commit as `feat(ui): unify primary creative workflows`.

### Task 7: Responsive, accessibility, and visual acceptance

**Files:**
- Modify: `frontend/e2e/ui-upgrade.spec.ts`
- Modify: `frontend/e2e/motion-preference.spec.ts`
- Create: `frontend/e2e/visual-acceptance.spec.ts`
- Create: `docs/UI_UPGRADE_2026-10-10.md`
- Modify only when evidence requires it: files from Tasks 2–6.

**Interfaces:**
- Consumes: the completed UI system and routes.
- Produces: reproducible acceptance evidence and a durable operator-facing change record.

- [ ] Add viewport checks at 375×812, 768×1024, 1024×768, and 1440×1000 for horizontal overflow, obscured focus/content, heading hierarchy, and representative screenshots.
- [ ] Add reduced/system/forced-on motion checks and console-error collection.
- [ ] Run the tests and capture any remaining evidence-backed defects.
- [ ] Fix only defects demonstrated by these tests, using a failing assertion before each code change.
- [ ] Run `npm run typecheck`, `npm run lint`, `npm run build`, existing Playwright suites, and the new acceptance suites.
- [ ] Rebuild/start the documented `.next-cinematic-fixed` app and perform the final real-browser smoke test.
- [ ] Document root cause, design decisions, changed surfaces, commands/results, screenshots, known limitations, and rollback guidance.
- [ ] Commit named files as `test(ui): verify responsive accessible upgrade`.

### Task 8: Final review and delivery

**Files:**
- Review: all files changed since the branch merge base.
- Modify only for verified Critical or Important findings.

**Interfaces:**
- Consumes: Tasks 1–7 and their test evidence.
- Produces: review findings, one bounded fix pass, green verification, and integration options.

- [ ] Generate the whole-branch review package and compare implementation against this plan and the design spec.
- [ ] Run a fresh code review focused on behavior preservation, motion cleanup, accessibility, responsive overflow, and test gaps.
- [ ] Re-grade findings by user impact; fix Critical/Important findings with RED→GREEN tests in one pass and ledger deferred minors.
- [ ] Re-run the complete frontend verification suite and inspect staged named-file diffs.
- [ ] Use `superpowers:finishing-a-development-branch` to present merge/keep/discard options; do not push.

