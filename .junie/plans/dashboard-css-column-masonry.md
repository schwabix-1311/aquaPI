---
sessionId: session-260802-063658-1699
---

# Implementation Status: ✓ Done

Implemented and verified via headless browser: the round-robin column bucketing in `AquapiDashboard` (`components/dashboard/index.js`) was replaced by the `Masonry` component ported from `origin/suggestion/css-masonry` (commit `7a71896`), and the obsolete `.aquapi-dashboard-masonry`/`-col` CSS rules were removed from `app.css`. Verified with a temporary, seeded 8-widget `localStorage` dashboard config (cleaned up afterward): `column-count` correctly resolves to 3/2/1 at 1400px/800px/500px viewport widths (live, via resize), all widget cards render inside the masonry container with zero console errors, the empty-state hint still renders when no widgets are configured, and the configurator drawer still opens correctly. See `.junie/plans/vue3-vuetify3-vuex4-migration.md`'s "Round 10 completion summary" for the consolidated write-up.

# Requirements

### Overview & Goals
Adopt the dashboard masonry-layout redesign already prototyped and committed on `origin/suggestion/css-masonry` (commit `7a71896`, "Suggestion: real masonry via CSS column-count instead of round-robin bucketing"). The current `/` (dashboard) implementation in `aquaPi/static/spa/components/dashboard/index.js` distributes visible widgets into N flex columns via round-robin bucketing (`i % columnCount`), which can leave one column noticeably taller than the others whenever widget card heights vary a lot (e.g. a tall History chart next to several short sensor widgets). The suggestion branch replaces this with a small, dependency-free `Masonry` component built on native CSS `column-count`, letting the browser balance column heights automatically - the same technique already proven to work without a build process (verified by the suggestion commit's author: widgets distributed 260px/230px/260px per column instead of a fixed round-robin order).

### Scope
**In Scope**
- Port the `Masonry` helper component and its usage in `AquapiDashboard` from `origin/suggestion/css-masonry` (commit `7a71896`) into `dev_thk`, adapted if needed to the few commits `dev_thk` has gained since that suggestion was branched off (`f49cadb`, `6d2d368`, `ec70d96`, `8109af3`, `2044eb8`, `3e2d2b4` - confirmed via `git diff` that none of these touched `components/dashboard/index.js`, and the one that touched `app.css` did not touch the masonry-related rules, so the port is a clean, non-conflicting apply).
- Remove the now-unused round-robin column logic (`containerWidth`, `desiredColumns`, `columnCount`, `columns`, the `masonryContainer` ref + its `ResizeObserver` in `mounted()`/`unmounted()`) and the corresponding `.aquapi-dashboard-masonry`/`.aquapi-dashboard-masonry-col` CSS rules in `aquaPi/static/css/app.css`.

**Out of Scope**
- Any other dashboard behavior (widget visibility toggle, configurator drawer, drag-reorder via SortableJS, widget content/rendering itself) - untouched.
- Any change to breakpoint values - the same `{default: 3, 1264: 3, 960: 2, 600: 1}` breakpoints are kept, just resolved via CSS `column-count` instead of JS bucketing.

### Functional Requirements
- The dashboard (`/`) still shows all visible widgets, laid out in up to 3 columns depending on viewport/container width, using the same breakpoints as before (`>=960px` -> 3 columns, `>=600px` -> 2 columns, else 1 column).
- Columns are now visually balanced by height (native CSS masonry behavior) rather than a fixed round-robin item order - a tall widget in one "virtual" column no longer forces that column to be visibly taller than its neighbors when shorter widgets could have been packed there instead.
- The dashboard's empty-state message/button ("noch keine Elemente ausgewählt"/setup button), widget visibility toggling, and the configurator drawer (open/save/reorder) all continue to work exactly as before.
- No console errors/warnings introduced; resizing the browser window (or toggling the nav drawer, which changes the dashboard's available width) still updates the column count live.


# Technical Design

### Current Implementation
`aquaPi/static/spa/components/dashboard/index.js`'s `AquapiDashboard` component:
- Renders `<div class="aquapi-dashboard-masonry" ref="masonryContainer">` containing one `<div class="aquapi-dashboard-masonry-col">` per column, each populated by a `v-for` over that column's bucket of widgets.
- `data()` tracks `containerWidth` (initialized from `window.innerWidth`).
- `computed.desiredColumns` maps `containerWidth` to 3/2/1 columns at the `960`/`600` breakpoints; `computed.columnCount` clamps that to `widgets.length` so no column is ever left empty; `computed.columns` buckets `this.widgets` round-robin (`i % columnCount`) into that many arrays.
- `mounted()` measures `this.$refs.masonryContainer`'s real width and attaches a `ResizeObserver` that keeps `containerWidth` live-updated; `unmounted()` disconnects it.
- `aquaPi/static/css/app.css` has a matching `.aquapi-dashboard-masonry` (flex row) / `.aquapi-dashboard-masonry-col` (flex: 1 1 0, 24px gap between columns) rule pair, explicitly commented as "Dependency-free replacement for vue-masonry-css (Vue-2-only, removed in the Vue 3 migration bugfix follow-up)".
- Confirmed via `git diff` against `origin/suggestion/css-masonry`'s merge-base (`2044eb8`) that none of `dev_thk`'s subsequent commits (`f49cadb` through `3e2d2b4`) touched `components/dashboard/index.js`, and the one commit that did touch `app.css` (unrelated `.v-main`/`.aquapi-settings` rules) left the masonry CSS block untouched - so the suggestion commit's diff applies cleanly with no adaptation needed.

### Key Decisions
- **Port the suggestion commit's approach as-is** (per the user's explicit instruction "entsprechend des branch ... implementieren"): a new, generic, reusable `Masonry` component (registered globally like all other shared components via `registerGlobalComponent`) replaces the dashboard-specific round-robin logic, rather than inventing a different masonry technique - this is a working, already-manually-verified solution from a parallel migration effort of the same codebase, minimizing new risk.
- **CSS `column-count` over a JS packing algorithm**: the browser's own column-balancing (`column-count` + `break-inside: avoid` on each item) achieves the desired visual result (shortest-column-first packing) without writing/maintaining a bin-packing algorithm in JS - consistent with the project's established preference for dependency-free, minimal-JS CSS solutions (e.g. the earlier CSS-column masonry replacement for `vue-masonry-css` itself).
- **Per-instance `ResizeObserver` on the `Masonry` component itself** (measuring its own wrapper's width, not `window` width) is kept from the suggestion, matching the existing pattern's rationale (nav-drawer toggling / container padding affect the actual available width, not just the raw viewport).

### Proposed Changes
1. `components/dashboard/index.js`: add the new `Masonry` component (props `cols` (`Number`/breakpoint `Object`) and `gutter`; `wrapperStyle` computed sets `column-count`/`column-gap`; `resolveCols(width)` picks the smallest breakpoint key `>= width` or falls back to `cols.default`; `mounted()`/`unmounted()` wire a `ResizeObserver` on `this.$refs.wrapper`), registered via `registerGlobalComponent('Masonry', Masonry)`.
2. `AquapiDashboard`'s template: replace the `<div class="aquapi-dashboard-masonry" ref="masonryContainer">...</div>` block with `<masonry :cols="{default: 3, 1264: 3, 960: 2, 600: 1}" :gutter="24">`, iterating `widgets` directly (`v-for="(item, index) in widgets"`) with `class="mb-6"` + `style="break-inside: avoid;"` on each wrapped `<aquapi-dashboard-widget>`, instead of iterating pre-bucketed `columns`.
3. Remove `containerWidth` from `data()`; remove `desiredColumns`/`columnCount`/`columns` computed properties; remove the `masonryContainer` ref usage and the `_resizeObserver` setup/teardown in `mounted()`/`unmounted()` (dashboard-level `mounted()` keeps only `await this.loadConfig()`; the now-empty `unmounted()` hook is dropped entirely).
4. `aquaPi/static/css/app.css`: remove the `.aquapi-dashboard-masonry`/`.aquapi-dashboard-masonry-col` rule block (and its explanatory comment), since column layout is now handled entirely by the `Masonry` component's inline `column-count`/`column-gap` styles.

### Risks
- CSS `column-count` fills columns top-to-bottom in *document order* (not by measuring rendered height ahead of time, since browsers don't do true "pack into shortest column" optimization the way a JS bin-packer could) - visually this still balances better than fixed round-robin for typical dashboards (per the suggestion's own manual verification: 260/230/260px), but pathological orderings (e.g. one extremely tall widget followed by several short ones) could still end up visually uneven; this is an accepted, documented trade-off of the native-CSS approach, not something this change attempts to solve further.
- `break-inside: avoid` prevents a single widget card from being visually split across two columns, but is a `column-*` CSS feature with generally solid modern-browser support; no polyfill is added, consistent with the project's browser-support baseline (a modern evergreen browser, per its existing ESM/no-build-process approach).


# Delivery Steps

###   Step 1: Add the CSS-column-based Masonry component and wire it into AquapiDashboard
The dashboard renders its widgets through a new, reusable Masonry component driven by native CSS column-count instead of round-robin bucketing.
- In `aquaPi/static/spa/components/dashboard/index.js`, add the `Masonry` component (props `cols`, `gutter`; `resolveCols(width)` breakpoint resolution; `ResizeObserver`-driven `currentCols`; `wrapperStyle` computed setting `column-count`/`column-gap`), registered via `registerGlobalComponent('Masonry', Masonry)`.
- Update `AquapiDashboard`'s template to render `<masonry :cols="{default: 3, 1264: 3, 960: 2, 600: 1}" :gutter="24">`, iterating `widgets` directly and wrapping each `aquapi-dashboard-widget` in a `<div class="mb-6" style="break-inside: avoid;">`.
- Remove the now-unused `containerWidth` data property, `desiredColumns`/`columnCount`/`columns` computed properties, and the `masonryContainer` ref/`ResizeObserver` setup in `mounted()`/`unmounted()`.

###   Step 2: Remove the obsolete flex-column masonry CSS rules
The stylesheet no longer contains the round-robin flex-column masonry rules, since column layout is now handled entirely by the new Masonry component's inline styles.
- Remove the `.aquapi-dashboard-masonry`/`.aquapi-dashboard-masonry-col` rule block (and its explanatory comment) from `aquaPi/static/css/app.css`.
- Syntax-check the modified `app.css` (balanced braces) and `dashboard/index.js` (`node --input-type=module --check`).

###   Step 3: Verify the new masonry layout end-to-end and update the migration plan document
The dashboard visually balances widget columns correctly across breakpoints, with all existing dashboard functionality unaffected, and the change is documented.
- Run a headless-browser (Puppeteer) session against the live app with a real admin login and the real widget configuration: confirm 3/2/1 columns render at wide/medium/narrow viewport widths, widgets visually distribute by height rather than strict round-robin order, and there are no console errors.
- Confirm widget visibility toggling, the configurator drawer's open/save/drag-reorder flow, and the empty-state hint (when no widgets are visible) all continue to work unchanged.
- Update `.junie/plans/vue3-vuetify3-vuex4-migration.md` (or the relevant tracking plan doc) with a summary of this change, referencing the ported `origin/suggestion/css-masonry` commit.