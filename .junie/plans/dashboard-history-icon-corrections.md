---
sessionId: session-260802-063658-1699
---

# Requirements

### Overview & Goals
This is a new correction round on top of the existing `.junie/plans/vue3-vuetify3-vuex4-migration.md` Round 3 corrections (Areas A-F, currently `Planned`, not yet implemented). During investigation, several of Round 3's claims turned out to already be fixed in the live code (`AquapiPageHeading`'s buttons and the History modal's close/expand buttons already use `variant="text" color="grey-darken-1"`, and `HistoryChart`'s expand button already uses the real `icon` prop, not the old `v-btn--icon` CSS-class hack) - those items should be marked done rather than re-implemented. Three genuinely open items were found instead, matching the user's latest reports:

1. **Dashboard configurator side panel**: has an unwanted vertical gap between its top edge and the app-bar/toolbar above it (it should sit flush under the header, like the left-hand `AquapiNavDrawer` already does).
2. **History widget period selector**: the "choose time range" dropdown visually shows only one option instead of all 8; its button also looks more "raised"/prominent than the neighboring round expand-icon button and isn't vertically aligned with it.
3. **Icon buttons app-wide**: many icon buttons (Config editor's connect/edit/delete/insert/restore actions, dashboard configurator's close/drag/visibility-toggle, Users table's edit/delete, and the app-bar's login/logout/dark-mode buttons) still render with Vuetify 3's default bold/elevated look, unlike the handful of spots already fixed - they should all get the same subdued, non-elevated treatment.

### Scope
**In Scope**
- Fixing the dashboard configurator drawer's top gap so it sits flush under the app-bar, matching `AquapiNavDrawer`'s already-correct behavior.
- Fixing the History period-selector `v-menu` so all 8 time-range options are reliably visible and selectable.
- Restyling the period-selector's activator button to be subdued and vertically aligned with the neighboring expand-icon button.
- Applying the existing "subdued icon button" treatment (`variant="text"`, muted color, no elevation) to every remaining `v-btn icon` instance identified in Config editor, Dashboard configurator, Users table, and the app-bar.

**Out of Scope**
- Any other Round 3 area (login-as-sole-entry-point, toast notifications, settings default-open accordions, user-dialog v-model contract) - those remain tracked separately in the existing Round 3 plan and are not touched here.
- Any color-palette or icon-set redesign beyond making existing icon buttons visually consistent with the ones already fixed.

### User Stories
- As a user, opening the dashboard configurator shows its panel starting right at the bottom edge of the header, with no visible gap.
- As a user, opening a History widget's time-range dropdown, I can see and pick from all 8 available periods.
- As a user, the time-range button and the "enlarge" button on a History widget look equally subdued and sit on the same visual line.
- As a user, icon buttons throughout the Config editor, dashboard configurator, and Users page look consistently subdued/secondary, matching the already-fixed page-heading and History-modal buttons.

### Functional Requirements
- The dashboard configurator (`AquapiDashboardConfigurator`) drawer's visible top edge is flush with the app-bar's bottom edge, with no gap, matching `AquapiNavDrawer`.
- Opening a History widget's period `v-menu` renders a properly sized/positioned list showing all 8 `periods` entries, each clickable and correctly setting the chart's period.
- The period-selector button uses a subdued (`variant="text"`, muted color), non-elevated style and is the same height/vertically aligned with the neighboring expand-icon button.
- All identified remaining `v-btn icon` instances (Config editor's per-node connect/edit/delete, template insert/delete, snapshot restore/delete; dashboard configurator's close/drag-handle/visibility-toggle; Users table's edit/delete; `Default.vue`'s login/logout/dark-mode toggle) render with the same subdued, non-elevated look as the already-fixed instances, without changing their click behavior.


# Technical Design

### Current Implementation
**Dashboard configurator gap** - `components/dashboard/index.js`'s `AquapiDashboardConfigurator` drawer has `app dark` (no `fixed`), while the working `components/app/AquapiNavDrawer.vue.js` has `app dark fixed`. Both are simultaneously mounted (not `v-if`-gated) and both register with Vuetify 3's layout system via the `app` prop; the discrepancy in props between the two `app`-registered drawers is the most likely source of the extra top offset on the right-hand one, but it must be verified visually against the running app during implementation (headless-browser check, comparing computed `getBoundingClientRect()` of `#dashboard_configurator` vs the app-bar) before deciding between the two candidate fixes.

**History period selector** - `components/dashboard/comps.js`'s `HistoryChart` renders:
```html
<v-menu offset-y open-on-hover>
  <template v-slot:activator="{ on, attrs }">
    <v-btn v-bind="attrs" v-on="on" depressed small class="text-none" :loading="isLoading">
      {{ ... }}
    </v-btn>
  </template>
  <v-list dense class="py-0">
    <v-list-item v-for="(item, index) in periods" ...>
  </v-list>
</v-menu>
```
This is the sole remaining place in the whole SPA using Vuetify 2's activator scoped-slot contract (`{ on, attrs }` + `v-bind="attrs" v-on="on"`) - confirmed via a project-wide search, every other `v-menu`/`v-tooltip` activator (e.g. the language switcher in `layouts/Default.vue`, line ~44) already correctly uses Vuetify 3's `{ props }` + `v-bind="props"`. Since Vuetify 3's `v-menu` never receives `on`/`attrs` in its slot scope, the activator element never gets properly wired/registered, which breaks the menu's activator-relative positioning/sizing logic - this is the most likely root cause of "only one option visible" (the menu's computed height/position collapses to essentially one row instead of sizing to fit all 8 `v-list-item`s), to be confirmed visually during implementation. Additionally, `depressed` is a Vuetify 2 boolean prop with no effect in Vuetify 3 (buttons default to the `elevated` variant unless `variant`/`flat` is set), which explains why this button looks more "raised" than the neighboring, already-fixed expand button (`icon small variant="text" color="grey-darken-1"`, lines ~526-536).

**Icon button audit** - a project-wide search for `v-btn icon` found these still-unstyled (default `elevated`-look) instances, alongside the handful already fixed (`AquapiPageHeading`, History modal close, History expand, the language-switcher button in `Default.vue`):
- `components/config/comps.js`: node connect/edit/delete (`x-small`, ~line 40-48), template insert/delete (~line 425-432), snapshot restore/delete (~line 462-469).
- `components/dashboard/index.js`: configurator close (~line 21), drag-handle (~line 43), visibility-toggle (~line 48).
- `components/users/index.js`: table row edit/delete (~line 32-37).
- `layouts/Default.vue`: login/logout buttons (~line 33-40); the dark-mode toggle (~line 61-63) is intentionally left as-is since it's a primary, always-visible app-bar action, not a secondary/contextual one - to be confirmed with the user only if it looks inconsistent after the rest are fixed.

### Key Decisions
- **Dashboard configurator gap fix**: try aligning `AquapiDashboardConfigurator`'s drawer props with the known-working `AquapiNavDrawer` pattern first (add `fixed`), verify with a headless-browser `getBoundingClientRect()` comparison against the app-bar; if that alone doesn't close the gap, the fallback is to inspect Vuetify 3's computed `--v-layout-*` CSS variables on `#dashboard_configurator` to find the actual source of the extra offset. This is called out as a verification-gated decision rather than assumed, since the two simultaneously-registered `app` drawers make the exact interaction non-obvious from source alone.
- **History menu fix**: rewrite the activator slot to Vuetify 3's `{ props }` contract (`<template v-slot:activator="{ props }"><v-btn v-bind="props" ...>`), consistent with the pattern already used correctly elsewhere in the app - this is a drop-in, low-risk fix since it's an isolated, confirmed-unique occurrence of the old API.
- **Period button styling**: drop the invalid `depressed` prop, add `variant="text" color="grey-darken-1"` (matching the neighboring expand button) and ensure both buttons share the same `size`/height so they align on one line - reuse of the exact styling already proven for the expand button, rather than inventing a new look.
- **Icon button restyling, applied uniformly not selectively**: apply `variant="text" color="grey-darken-1"` (small variants keep their existing `x-small`/`small` sizing) to every identified instance rather than cherry-picking, since the user's request ("generell...dezenter") is explicitly about consistency across the whole app, and the pattern/values are already established by the previously-fixed spots.

### Proposed Changes
1. `components/dashboard/index.js` (`AquapiDashboardConfigurator`): add `fixed` to the drawer (pending headless-browser confirmation it closes the gap; adjust further if not).
2. `components/dashboard/comps.js` (`HistoryChart`): rewrite the period `v-menu`'s activator slot to `{ props }`/`v-bind="props"`; replace `depressed` with `variant="text" color="grey-darken-1"` and align its `size` with the expand button.
3. `components/config/comps.js`: add `variant="text" color="grey-darken-1"` to the 7 identified icon buttons (connect/edit/delete, insert/delete template, restore/delete snapshot).
4. `components/dashboard/index.js`: add the same treatment to the configurator's close/drag-handle/visibility-toggle buttons (careful to keep the drag-handle's existing `class="handle text--grey"` cursor/drag-affordance intact).
5. `components/users/index.js`: add the same treatment to the table's edit/delete buttons.
6. `layouts/Default.vue`: add the same treatment to the login/logout buttons; leave the dark-mode toggle unchanged per the Key Decision above.

### Risks
- The dashboard configurator gap's exact root cause is not 100% certain from source inspection alone (two simultaneous `app`-registered drawers is a known Vuetify-3 layout-interaction area) - the plan explicitly gates the fix on live verification rather than assuming `fixed` alone will resolve it.
- Restyling 15 icon buttons at once increases the surface area for a visual regression; each affected page (Config editor, Dashboard configurator, Users) should be visually spot-checked after the change.


# Testing

### Validation Approach
All changes are frontend-only (no Python/backend touched), so validation is manual/browser-based, consistent with the project's established approach for frontend styling/behavior fixes - a headless-browser (Puppeteer) session against the running app, using a temporary test account that is removed afterward, without altering the real configuration.

### Key Scenarios
- Open the dashboard configurator panel and measure/screenshot the gap between its top edge and the app-bar - confirm it's flush, matching the left-hand nav drawer.
- Open a History widget's period dropdown and confirm all 8 entries are visible and clickable, and that selecting one updates the chart's period.
- Screenshot the period-selector button next to the expand button - confirm both are visually subdued and sit at the same height/line.
- Screenshot the Config editor's node cards, template list, and snapshot list, the dashboard configurator panel, and the Users table - confirm all icon buttons look subdued/non-elevated and their click actions (connect/edit/delete/insert/restore/drag/visibility-toggle/login/logout) still work.

### Edge Cases
- Verify the dashboard configurator's drag-to-reorder and visibility-toggle still function correctly after the restyle (no accidental removal of `class="handle"`/click handlers).
- Verify the History modal's own "enlarge" flow (Round 3's A1 fix) still works unaffected by the period-menu changes in the same file.
- Verify the period dropdown still works correctly for both `renderType='widget'` and `renderType='modal'` instances of `HistoryChart` on the same page.

### Test Changes
- All modified `.js`/`.vue` files checked with `node --input-type=module --check` (existing project convention); no backend code is touched, so no `pytest` run is needed for this change per the agreed testing protocol.


# Delivery Steps

###   Step 1: Fix the dashboard configurator drawer's top gap
The dashboard configurator side panel sits flush under the app-bar with no visible gap, matching the left-hand navigation drawer.
- Add the `fixed` prop to `AquapiDashboardConfigurator`'s `v-navigation-drawer` in `components/dashboard/index.js`, mirroring the already-correct `AquapiNavDrawer.vue.js` pattern.
- Verify via a headless-browser session (temporary test account) by comparing `getBoundingClientRect()` of `#dashboard_configurator` against the app-bar; if a gap remains, inspect the computed Vuetify layout CSS variables on the drawer to find the actual remaining offset source and adjust accordingly.
- Confirm the drawer still opens/closes correctly and the widget list/save button inside it are unaffected.

###   Step 2: Fix the History widget's period-selector dropdown and align its styling
The History widget's time-range dropdown reliably shows and lets the user pick from all 8 periods, and its button is visually subdued and aligned with the neighboring expand button.
- In `components/dashboard/comps.js`'s `HistoryChart`, rewrite the period `v-menu`'s activator slot from the Vuetify 2 `{ on, attrs }`/`v-bind="attrs" v-on="on"` contract to Vuetify 3's `{ props }`/`v-bind="props"`.
- Remove the invalid `depressed` prop from the period button; add `variant="text" color="grey-darken-1"` and align its `size` with the neighboring expand-icon button so both sit on the same line/height.
- Verify via headless browser: open the dropdown on both a widget-mode and modal-mode `HistoryChart`, confirm all 8 entries render and are clickable, and confirm the chart's period updates on selection.

###   Step 3: Apply subdued icon-button styling to remaining Config editor, dashboard configurator, and Users icon buttons
Icon buttons across the Config editor, dashboard configurator, Users table, and app-bar login/logout look consistently subdued/non-elevated, matching the buttons already fixed earlier (page heading, History modal, language switcher).
- Add `variant="text" color="grey-darken-1"` to `components/config/comps.js`'s node connect/edit/delete, template insert/delete, and snapshot restore/delete buttons.
- Add the same treatment to `components/dashboard/index.js`'s configurator close, drag-handle, and visibility-toggle buttons, preserving the drag-handle's existing cursor/drag class.
- Add the same treatment to `components/users/index.js`'s table edit/delete buttons and `layouts/Default.vue`'s login/logout buttons.
- Verify via headless-browser screenshots of the Config editor, dashboard configurator panel, and Users page that all buttons look subdued and every click action (connect/edit/delete/insert/restore/drag/visibility-toggle/login/logout) still works correctly.