---
sessionId: session-260802-063658-1699
---

# Implementation Status: ✓ Done

All 3 delivery steps implemented and verified via a headless-browser (Puppeteer) session against the running app with a real admin login and the user's real 13-node configuration:
- Node cards widened to 240px; connect/edit/delete icon buttons shrunk to `size="x-small"` (32x32px, down from the previous default-sized icon buttons) - `density="compact"` was tried first but made buttons unusably tiny (12x12px), so it was dropped in favor of `size="x-small"` alone with `size="small"` icons.
- `ConfigTemplatesDialog` fixed: `v-tabs-items`/`v-tab-item` → `v-window`/`v-window-item`, `v-list-item-content`/`v-list-item-action` → `v-list-item` + `#append` slot, `v-overlay absolute` → `v-overlay contained` (with `position: relative` on the parent card). Verified end-to-end: creating a template and a snapshot both work and appear correctly in their respective (now properly tab-switched) lists; test data cleaned up afterward from the database.
- `ConfigConnections` now renders elbow (`M x1,y1 H midX V y2 H x2`) `<path>` elements with explicit `fill="none"` instead of straight `<line>`s; verified 16 real connections render correctly with hover-highlight/delete-icon behavior unchanged.

# Requirements

### Overview & Goals
This is a new correction round for the `/config` graph editor (`aquaPi/static/spa/components/config/index.js` + `comps.js`), continuing the same corrections work tracked in `.junie/plans/vue3-vuetify3-vuex4-migration.md` (currently at Round 7, all previous rounds ✓ Done). The user reported four items, two visual and two functional:

1. **Visual**: node cards (`ConfigNodeBox`) should be wider.
2. **Visual**: the icon buttons on the node cards (connect/edit/delete) should be smaller.
3. **Functional**: saving/inserting Templates "used to work, now doesn't" - needs investigation and a fix.
4. **Functional**: saving/loading Snapshots "used to work, now doesn't" - needs investigation and a fix.
5. **Visual (nice-to-have)**: connection lines between nodes should be angled/orthogonal (elbow-style) instead of straight diagonal lines, so it's visually clear which side of a card is an input vs. an output.

### Root Cause Found (Templates/Snapshots)
Investigation found the actual bug behind items 3 and 4: `ConfigTemplatesDialog` (`components/config/comps.js`, ~lines 381-482), which hosts **both** the Templates tab and the Snapshots tab, still uses `<v-tabs-items>`/`<v-tab-item>` and `<v-list-item-content>`/`<v-list-item-action>` - all **Vuetify 2** template tags that no longer exist in Vuetify 3 (removed during master-plan Step 18's library migration, but this one dialog was missed - the exact same class of bug already found and fixed in `AquapiNavDrawer.vue.js` back in Step 18/20, and in the Round 2 corrections for other dialogs). Since Vue 3 has no built-in behavior for these unknown tags, the `v-model`-driven tab-switching that `v-tabs-items` used to provide never happens, so both tab panes' contents render simultaneously/without the intended layout - this is what makes the Templates and Snapshots sections look and behave "broken" even though the underlying save/insert/restore Vuex actions (`config/createTemplate`, `config/insertTemplate`, `config/createSnapshot`, `config/restoreSnapshot`) and their toast/error handling are all already correctly implemented and unaffected. A secondary, related issue in the same dialog: its `restoring` `<v-overlay absolute ...>` uses the Vuetify-2-only `absolute` prop (no effect in Vuetify 3), so the "restoring snapshot" loading overlay likely doesn't stay confined to the dialog card as intended - to be confirmed and fixed alongside.

### Scope
**In Scope**
- Increase `ConfigNodeBox`'s width (the shared `NODE_BOX_WIDTH` constant in `comps.js`, already the single source of truth used for box sizing, canvas sizing, and connector endpoint calculation).
- Reduce the size/footprint of the connect/edit/delete icon buttons on `ConfigNodeBox`.
- Fix `ConfigTemplatesDialog`'s Vuetify-2 leftovers (`v-tabs-items`/`v-tab-item` → `v-window`/`v-window-item`; `v-list-item-content`/`v-list-item-action` → the already-established Vuetify 3 pattern used in `AquapiNavDrawer.vue.js`; `v-overlay absolute` → the correct Vuetify 3 equivalent) so Template save/insert/delete and Snapshot save/restore/delete work and display correctly.
- Change `ConfigConnections`'s rendering from straight lines to angled/orthogonal (elbow) paths, keeping the existing hover-highlight and hover-delete-icon behavior.

**Out of Scope**
- Any other `/config` editor behavior not mentioned (drag&drop, node dialog, draft save/discard, apply endpoint) - these are already working and untouched.
- Any change to the Templates/Snapshots backend API (`db.py`/`api.py`) - the investigation found the bug is purely in the frontend dialog markup, not the backend logic.

### Functional Requirements
- Node cards in the `/config` canvas render visibly wider than before.
- The connect/edit/delete icon buttons on each node card are visibly smaller/more compact than before.
- Opening the Templates/Snapshots dialog and switching between its two tabs shows only the active tab's content, cleanly laid out (list item title/subtitle plus trailing action buttons, no leftover unstyled custom-element wrappers).
- Saving a new template from the current selection works and the new template appears in the list; inserting a template adds its nodes to the draft canvas; deleting a template removes it from the list.
- Saving a new snapshot works and appears in the list; restoring a snapshot (with its confirm dialog and loading overlay) replaces the current config and closes the dialog; deleting a snapshot removes it from the list.
- Connections between nodes are drawn as angled (horizontal-vertical-horizontal) paths rather than straight diagonal lines, still starting at the right edge of the source card and ending at the left edge of the target card, with the existing hover-to-highlight and hover-delete-icon interactions unchanged.


# Technical Design

### Current Implementation
- `components/config/comps.js`: `NODE_BOX_WIDTH = 190`, `NODE_BOX_HEIGHT = 76` (exported, also imported by `components/config/index.js` for canvas sizing) - single source of truth for box width.
- `ConfigNodeBox`'s header row (~lines 37-49) has three `<v-btn icon x-small variant="text" color="grey-darken-1">` buttons with `<v-icon small>` - already using the app's "subdued" styling from a prior round, just not small enough per this request.
- `ConfigConnections`'s `edges` computed (~lines 160-180) computes `x1,y1` (source's right-middle edge) and `x2,y2` (target's left-middle edge) and renders a plain `<line>` (both the invisible wide hit-line and the visible arrowed line) directly between them - a straight diagonal whenever the two nodes aren't vertically aligned.
- `ConfigTemplatesDialog` (~lines 381-482): uses Vuetify-2-only `<v-tabs-items v-model="tab"><v-tab-item>...</v-tab-item></v-tabs-items>` (no Vue-3 equivalent exists under those tag names - confirmed by comparing against the correctly-migrated `<v-tabs>`/`v-window` pattern used elsewhere, and against `AquapiNavDrawer.vue.js`'s already-fixed `v-list-item`/`#prepend`/`v-list-item-title` pattern which this dialog's `v-list-item-content`/`v-list-item-action` tags don't follow). `saveTemplate`/`insertTemplate`/`deleteTemplate`/`saveSnapshot`/`restoreSnapshot`/`deleteSnapshot` methods (~lines 515-598) are all correctly wired to `config/*` Vuex actions with toast/error handling already in place - confirmed no backend or Vuex-layer bug.

### Key Decisions
- **Card width**: bump `NODE_BOX_WIDTH` from `190` to `240` (a modest, clearly-visible increase); since it's the single constant driving box CSS width, canvas width calculation, and connector endpoint x-coordinates, no other file needs to change.
- **Icon button size**: switch from `x-small` v-btn / `small` v-icon to Vuetify 3's explicit `size="x-small"` on both the `v-btn` and `v-icon`, plus tightening the button's own padding (`density="compact"` / reduced `class` margins) - this is a purely visual, low-risk change confined to `ConfigNodeBox`.
- **Templates/Snapshots dialog fix**: replace `v-tabs-items`/`v-tab-item` with Vuetify 3's `v-window`/`v-window-item` (same `v-model="tab"` contract, drop-in replacement, already the standard pattern for tabbed content in v3); replace `v-list-item-content`/`v-list-item-title`/`v-list-item-subtitle`/`v-list-item-action` structure with a `v-list-item` directly containing `v-list-item-title`/`v-list-item-subtitle` and a `<template #append>` slot wrapping the trailing action buttons - mirroring the exact pattern already proven correct in `AquapiNavDrawer.vue.js`. Replace `v-overlay absolute` with `v-overlay contained` (Vuetify 3's prop for "constrain the overlay to its positioned parent" - the dialog `v-card` needs `position: relative` for this to work, added via a small inline style/class if not already implicit).
- **Angled connectors**: replace the `<line>` elements in `ConfigConnections` with `<path>` elements using an elbow route `M x1,y1 H midX V y2 H x2` (horizontal-vertical-horizontal), where `midX = (x1+x2)/2` (same value already computed today for the delete-icon position) - this keeps the path's start/end segments horizontal (so the existing `marker-end` arrow orientation stays correct) and keeps the delete-icon's midpoint (`midX`, `(y1+y2)/2`) exactly on the path's vertical segment. `fill="none"` must be added explicitly (SVG `<path>` defaults to a black fill, unlike `<line>`), applied to both the invisible wide hit-path and the visible arrowed path.

### Proposed Changes
1. `components/config/comps.js`: change `NODE_BOX_WIDTH` from `190` to `240`.
2. `components/config/comps.js` (`ConfigNodeBox`): reduce the three action buttons' size (`size="x-small"` on both `v-btn` and inner `v-icon`, tighter spacing).
3. `components/config/comps.js` (`ConfigConnections`): compute an elbow `path` string per edge in the `edges` computed property; render `<path :d="edge.path" fill="none" .../>` instead of `<line>` for both the hit-path and the visible arrowed path; keep `midX`/`midY` (now `(y1+y2)/2`) for the hover-delete-icon position.
4. `components/config/comps.js` (`ConfigTemplatesDialog`): replace `v-tabs-items`/`v-tab-item` with `v-window`/`v-window-item`; restructure both `v-list-item`s (templates and snapshots) to the `v-list-item` + `v-list-item-title`/`v-list-item-subtitle` + `#append`-slot pattern; replace `v-overlay absolute` with `v-overlay contained` (plus a `position: relative` class on the surrounding `v-card` if not already present).
5. `aquaPi/static/css/app.css`: adjust `.config-connection-hit`/`.config-connection-line` rules if needed to keep `fill: none` and stroke widths correct for `<path>` instead of `<line>` (verified visually during implementation).

### Risks
- Widening node cards increases the canvas's total width for configs with many nodes spread horizontally - acceptable since `canvasWidth` already scales dynamically and the canvas area already scrolls (`config-canvas-wrapper`).
- The elbow-routing algorithm is a simple fixed-midpoint approach; with many overlapping edges at similar heights, some paths could visually overlap more than the old diagonal lines did - acceptable for this scope (matches the user's explicit request), not solving general graph-layout edge-crossing minimization.
- The `v-overlay contained` fix is the closest Vuetify 3 equivalent to the old `absolute` prop but its exact visual behavior needs to be confirmed live rather than assumed, given Vuetify 3's overlay positioning system changed significantly from v2 (already flagged as a general risk area in the original Step 18 plan).


# Testing

### Validation Approach
All changes are frontend-only (no Python/backend touched), so validation is manual/browser-based via the project's established headless-browser (Puppeteer) approach against the running app with a temporary test session, consistent with all prior correction rounds in `.junie/plans/vue3-vuetify3-vuex4-migration.md`.

### Key Scenarios
- Open `/config` and visually confirm node cards are wider and their connect/edit/delete icon buttons are visibly smaller than before, without breaking click behavior.
- Open the Templates/Snapshots dialog: switch between the "Templates" and "Snapshots" tabs and confirm only the active tab's content is shown.
- Create a template from a selection of nodes, confirm it appears in the list with correct name/node count; insert it back into the draft canvas and confirm the nodes appear (offset-positioned per the existing overlap-avoidance logic); delete it and confirm it's removed from the list.
- Create a snapshot, confirm it appears with a timestamp; restore it (confirming the confirm-dialog and the loading overlay appear/behave correctly) and confirm the draft reloads with the snapshot's nodes; delete a snapshot and confirm it's removed.
- Create two nodes at different vertical positions and connect them; confirm the connection renders as an angled (not diagonal) line, with the arrowhead still pointing correctly into the target, and that hovering it still highlights it and shows a working delete icon at the correct position.

### Edge Cases
- Two nodes at the exact same vertical position (`y1 === y2`): confirm the connector still renders correctly as a plain horizontal line (degenerate elbow case).
- Confirm the wider node cards don't cause newly-instantiated template nodes to overlap more than before (the existing offset-on-insert logic in `instantiate_template()` in `db.py` is unaffected by this frontend-only change, but should be spot-checked).

### Test Changes
- All modified `.js` files checked with `node --input-type=module --check` (existing project convention); no backend code is touched, so no `pytest` run is needed for this change per the agreed testing protocol.


# Delivery Steps

###   Step 1: Widen node cards and shrink their icon buttons
Node cards in the /config canvas are visibly wider and their connect/edit/delete icon buttons are visibly smaller.
- In `components/config/comps.js`, increase `NODE_BOX_WIDTH` from `190` to `240` (single source of truth also used by canvas sizing and connector endpoints in `components/config/index.js`).
- Reduce the three action buttons on `ConfigNodeBox` (connect/edit/delete) to a smaller explicit size (`size="x-small"` on both the `v-btn` and its inner `v-icon`), tightening their spacing.
- Verify visually via headless browser that cards are wider, buttons are smaller, and click behavior (connect/edit/delete) is unaffected.

###   Step 2: Fix the Templates/Snapshots dialog's leftover Vuetify 2 markup
Saving/inserting templates and saving/restoring snapshots work correctly and display cleanly in the /config editor's Templates/Snapshots dialog.
- In `components/config/comps.js`'s `ConfigTemplatesDialog`, replace the Vuetify-2-only `<v-tabs-items>`/`<v-tab-item>` with Vuetify 3's `<v-window>`/`<v-window-item>` (same `v-model="tab"` binding).
- Restructure the templates and snapshots list items from `v-list-item-content`/`v-list-item-action` to a `v-list-item` directly containing `v-list-item-title`/`v-list-item-subtitle` plus a `<template #append>` slot for the trailing action buttons, mirroring the pattern already used in `AquapiNavDrawer.vue.js`.
- Replace the restoring-state `<v-overlay absolute ...>` with the Vuetify 3 `contained` prop (adding a `position: relative` class to its parent card if needed).
- Verify via headless browser: switching tabs shows only one tab's content at a time; create/insert/delete a template and create/restore/delete a snapshot all work end-to-end with correct list updates and toasts.

###   Step 3: Render node connections as angled (orthogonal) paths
Connections between nodes in the /config canvas are drawn as angled elbow paths instead of straight diagonal lines, making input/output sides visually clear.
- In `components/config/comps.js`'s `ConfigConnections`, change the `edges` computed property to build an elbow path string per edge (`M x1,y1 H midX V y2 H x2`), keeping the existing `midX`/`midY` calculation for the hover-delete-icon position.
- Replace the hit-line and visible-line `<line>` elements with `<path>` elements using the new `path` data, adding `fill="none"` to both.
- Adjust `app.css`'s `.config-connection-hit`/`.config-connection-line` rules if needed for correct rendering on `<path>` elements.
- Verify via headless browser: connections between vertically-offset nodes render as angled paths with correctly oriented arrowheads, and hover-highlight plus the hover-delete icon still work at the correct position; confirm same-height connections still render as a plain horizontal line.