---
sessionId: session-260802-063658-1699
---

# Implementation Status: ✓ Done (Round 5: dashboard configurator Save button restyled as primary, on top of Round 4's History modal fixes and Round 3's A-F corrections)

This document now covers a **third round** of corrections, reported after the Round 2 fixes below (Login consolidation, Dashboard B1-B6, Settings C1-C4) were already implemented, verified and committed. Round 2's content (originally titled "Requirements"/"Technical Design"/"Testing") is kept, unmodified, further down this document as historical record - see "# Round 2 (Login, Dashboard & Settings corrections) - Implementation Status: ✓ Done".

## Round 5 completion summary (✓ Done)
User-reported: the "Speichern" (Save) button in the dashboard configurator side panel (`components/dashboard/index.js`) looked like plain blue text instead of a proper filled primary button, even though it already had `color="primary"` - it was missing an explicit `variant`, and combined with the drawer's `dark` context it rendered as flat/unfilled. Fixed by adding `variant="flat"` to the button. Verified via a headless-browser session with a real admin login: the button's computed style now shows `background-color: rgb(25, 118, 210)` (Vuetify's primary blue) and the classes `bg-primary v-btn--variant-flat`, confirming it renders as a solid, filled primary button.

## Round 4 completion summary (✓ Done)
Two further, user-reported issues in the History widget's fullscreen modal (both regressions surfacing only once Round 3's A1 fix made the modal actually openable) were found and fixed, verified end-to-end via a headless-browser session against the running app with a real admin login and a real, seeded History widget (test toggle reverted afterward):
- **Close icon not top-right**: `History`'s modal `v-card-title` (`components/dashboard/comps.js`) had no flex layout, so its `v-spacer` (which only works inside a flex container) had no effect and the close button rendered inline right after the node name instead of being pushed to the right edge. Fixed by adding `d-flex align-center justify-space-between` to the `v-card-title` and dropping the now-unneeded `v-spacer`. Confirmed visually: the `X` button now sits flush at the top-right corner of the modal header.
- **Selecting a different period did not update the chart**: root cause was that `HistoryChart`'s Chart.js config object (`this.cd`) and Chart.js instance (`this.chart`) were plain Vue 3 `data()` properties, so Vue wrapped them in a reactive Proxy; Chart.js performs its own internal, Proxy-based option resolution during `chart.update()`, and nesting that inside a Vue reactive Proxy caused an infinite recursion (`RangeError: Maximum call stack size exceeded`, thrown from deep inside `chart.js`'s internal option merge/resolve chain) every time `setPeriod()` called `chart.update()` after fetching new data - the crash was silent from the user's perspective (only visible via an uncaught `pageerror`, not a UI error), so the chart just appeared frozen. Fixed by wrapping both `cd` (in `data()`) and the `Chart` instance (in `mounted()`) with `window.Vue.markRaw(...)`, which permanently excludes them from Vue's reactivity system - confirmed via headless browser: switching from "1 h" to "7 Tage" now triggers a fresh `/api/history/<node>` fetch with a correspondingly larger `step`, the button label updates to "Zeitraum 7 Tage", and no `pageerror` occurs.

## Round 3 completion summary (✓ Done)
All of Areas A-F were implemented and verified end-to-end via headless-browser sessions against the running app with a real admin login (test data cleaned up afterward):
- **A1**: `History`'s modal now uses `:model-value`/`@update:model-value`; verified opening/closing reliably (confirmed via `#dashboard_configurator`-style pattern). **Newly discovered during this verification**: closing the modal now surfaces a non-fatal console error from `chart.js` (`Cannot read properties of null (reading 'getContext')`), a Chart.js-internal resize-observer callback racing the dialog's closing transition/canvas removal - the dialog still closes correctly and the app remains fully functional, so this is tracked as a known, non-blocking follow-up rather than fixed in this round (it could only ever surface once A1 made the modal openable at all).
- **A2**: `HistoryChart`'s expand button now uses the real `icon` prop instead of the dead `v-btn--icon` CSS class; confirmed round (`border-radius: 50%`) via computed style.
- **B1**: `@login_required` removed from `spa.py`'s `/` route; confirmed an unauthenticated request now gets the SPA shell with a forced, un-dismissable login dialog instead of a redirect to `login.html.jinja2`.
- **C1**: `AquapiPageHeading` and `History`/`HistoryChart` buttons already used the subdued `variant="text" color="grey-darken-1"` treatment. During this round's verification, the same treatment was extended (superseding an earlier icon-button correction plan, "dashboard-history-icon-corrections", whose remaining scope is folded into this completion) to: `components/config/comps.js` (node connect/edit/delete, template insert/delete, snapshot restore/delete), `components/dashboard/index.js` (configurator close/drag-handle/visibility-toggle), `components/users/index.js` (table edit/delete), `layouts/Default.vue` (login/logout buttons), and `HistoryChart`'s period-selector button (which also had the same Vuetify-2 `{on, attrs}` activator-slot bug as A2's root cause, fixed to `{props}`, which also fixed the period dropdown showing only one option instead of all 8).
- **D1**: `AquapiToast.vue.js` + `$toast` global helper confirmed wired and firing (verified: changing a setting shows "Erfolgreich gespeichert" toast).
- **E1**: `AquapiSettings`'s `openPanels` populated after `fetchNodes` resolves; confirmed panels render expanded by default.
- **F1**: `UserDialog`/`ConfigNodeDialog`/`ConfigTemplatesDialog` all use the `modelValue`/`update:modelValue` contract; confirmed editing a user pre-fills email/role correctly and Cancel closes the dialog.
- **Additional fix found during verification**: the dashboard configurator drawer's gap under the app-bar (both drawers being simultaneously Vuetify-3-layout-registered `app` drawers caused a positioning conflict) was fixed by wrapping `AquapiDashboardConfigurator`'s `v-navigation-drawer` in a `<teleport to="body">`, breaking it out of its nested DOM ancestor chain (unlike `AquapiNavDrawer`, it was rendered deep inside routed page content, not as a direct `Default.vue` sibling) - `fixed` alone was insufficient, confirmed via `getBoundingClientRect()` gap measurement (0px after the fix).

## Round 2 recap (✓ Done)
All of Area A (login consolidation), Area B (dashboard B1-B6) and Area C (settings C1-C4) were implemented and verified end-to-end via a real headless-browser session with a real logged-in session and a seeded, realistic 13-widget dashboard configuration. Two additional, previously undiagnosed bugs were found and fixed during verification (not part of the original technical design, since they only surfaced once the described fixes were actually exercised together):
- **`AquapiPageHeading`/`AquapiLoadingIndicator`/`AquapiDummy` stopped being globally registered**: removing the `view_bottom: AquapiDummy` import from `router/index.js` (fix for C4) accidentally removed the *only* import of `components/app/index.js` in the whole app, which was the sole reason that module (and thus `AquapiPageHeading`) ever got loaded/registered as a side effect. This silently broke every page's heading toolbar (including the dashboard's "configure" button, needed to verify B4/B5) until a dedicated `import '../components/app/index.js'` side-effect import was added to `router/index.js` alongside the other eager component-module imports.
- **Dashboard widget crash on `node.alert === null`**: `AquapiDashboardWidget`'s `alert`/`alertColor` computed properties only guarded `!('alert' in this.node)`, but real nodes (e.g. `heizen`) have the key present with a `null` value, causing `this.node.alert[0]` to throw and silently freeze the dashboard's reactivity (making the empty-state hint look "stuck" and columns look mis-measured) - fixed by guarding on `this.node.alert == null` instead, in `components/dashboard/index.js`.
- **B1 footer root cause refined during verification**: removing the inline `max-height: 100vh` on `v-main` (as originally planned) was necessary but not sufficient - Vuetify 3's `v-main` no longer renders a `.v-main__wrap` child div (a Vuetify-2-only implementation detail the old `app.css` rule relied on), so without a height-capped `.v-application__wrap` the footer (absolutely positioned relative to that wrapper) drifted below the viewport once page content overflowed. Fixed in `app.css`: `.v-application__wrap` is capped to `100vh` with `overflow: hidden`, and `.v-main` scrolls its own content internally (`overflow-y: auto`), replacing the dead `div.v-main__wrap` rules.

This document was previously repurposed for Round 2 (superseding its original Steps 18-20 masonry/draggable/nav-drawer scope, which is fully implemented/verified separately - see the historical section further below).

---

# Round 3: Further post-migration corrections (Areas A-F)

### Overview & Goals
A new round of **corrections and adjustments**, reported by the user after Round 2 was implemented, grouped by area:
- **Area A - Dashboard/History widgets**: the "enlarge in modal" button for History-node charts no longer opens the modal, and the History widgets' small icon buttons (period selector's companion "expand" button) render as square instead of round.
- **Area B - Login**: the native Flask `/login` page is still reachable as an actual entry gate (the `/` route redirects unauthenticated users to it), even though Round 2 already consolidated the login *form* itself into the SPA's nav-drawer dialog - the goal now is that the SPA is the **only** thing a user ever sees, with the login dialog appearing *inside* it for unauthenticated users, instead of a full-page redirect to the separate Flask-rendered page.
- **Area C - General icon-button styling**: icon buttons in cards/modals/tables are too visually prominent (bold, colored) and should look more subtle/muted, consistent with a typical "secondary action" affordance.
- **Area D - Save feedback**: the app gives no consistent visual confirmation (success or error) after most save/delete actions (Config editor, Settings, Users, Dashboard) - a toast/snackbar notification should appear after these.
- **Area E - Settings page**: the settings accordion groups added in Round 2 default to collapsed, forcing an extra click before any controller is visible.
- **Area F - User management**: the "edit user" dialog in `/users` can't be closed and doesn't show the correct, already-saved data for the user being edited.

Goal: the reported dashboard/history and user-management dialogs work correctly again, the SPA is the sole entry point for authentication, icon buttons look visually consistent and subdued app-wide, every save/delete action gives clear toast feedback, and the settings accordion is immediately useful without an extra click.

### Scope
**In Scope**
- **A1**: Fix `History`'s chart-enlarge modal (`v-dialog v-model="$store.getters[...](...)"` anti-pattern) so it reliably opens/closes.
- **A2**: Fix the History widget's small "expand" icon button so it renders round like other icon buttons.
- **B1**: Remove `@login_required` from the SPA's `/` Flask route so unauthenticated users still receive the SPA shell (not a redirect to `login.html.jinja2`); the SPA itself forces its existing `AquapiLoginDialog` open (and un-closable) until a real session exists.
- **C1**: Restyle the most visually prominent icon buttons (`AquapiPageHeading`'s action buttons, the History modal's close/expand buttons) to a subdued/muted look instead of bold primary-colored icons.
- **D1**: Introduce a small, reusable toast/snackbar notification system (`$toast.success(...)`/`$toast.error(...)`, mirroring the existing `$confirm`/`$alert` pattern) and wire it into the Config editor's save/discard, Settings changes, Users create/update/delete, and Dashboard configuration save.
- **E1**: Default-open all settings accordion groups (`AquapiSettings`'s `openPanels`).
- **F1**: Fix `UserDialog`'s (and, since it's the exact same defect class, `ConfigNodeDialog`'s/`ConfigTemplatesDialog`'s) Vue-2-style `value`/`input` `v-model` contract, replacing it with Vue 3's `modelValue`/`update:modelValue` convention.

**Out of Scope**
- Any visual redesign beyond the specific "more subtle icon buttons" request (no color-palette overhaul).
- Toast notifications for every conceivable action in the app - only the explicitly named save/delete flows.
- Fully removing/deleting `login.html.jinja2` or the underlying Flask-Login mechanism (still needed as `login_manager.login_view`'s technical target and for the JSON-capable `/login`/`/logout` routes added in Round 2).

### User Stories
- As a user, clicking the "enlarge" button on a History widget reliably opens a larger chart in a modal, and I can close that modal again.
- As a user, the small icon buttons on History widgets look like the rest of the app's round icon buttons.
- As a user, visiting the app while logged out always shows me the normal-looking SPA with a login prompt inside it - never a separate, differently-styled login page.
- As a user, the icon buttons in cards, modals and tables look subdued/secondary, not like bold primary actions.
- As a user, after saving or deleting something (a config node, a setting, a user, my dashboard layout), I get a brief, clear confirmation (or error) toast.
- As a user, opening `/settings` immediately shows me all my controllers, without needing to expand every group first.
- As a admin, clicking "Bearbeiten" on a user opens the edit dialog pre-filled with that user's current data, and I can close the dialog (with or without saving).

### Functional Requirements
**Area A**
- A1: clicking the History widget's expand icon opens the enlarged chart modal; clicking its close (X) button closes it again; reopening a different History widget's modal shows that widget's own chart.
- A2: the History widget's "expand" button is visually a round icon button, matching the app's other icon buttons (e.g. the modal's own close button).

**Area B**
- B1: an unauthenticated request to `/` returns the SPA shell (HTTP 200, same `spa.html.jinja2`), not a redirect; the SPA opens its login dialog automatically and it cannot be dismissed without either logging in or the session already being valid.
- B1: once logged in (via the dialog), the app behaves exactly as it does today; logging out re-triggers the forced dialog.

**Area C**
- C1: `AquapiPageHeading`'s action buttons (e.g. "add user") and the History modal's close/expand buttons render with a muted/subdued color and `text` variant instead of a bold `primary`-colored icon.

**Area D**
- D1: saving a node create/update/delete (via the Config editor's draft save), changing a setting, creating/updating/deleting a user, and saving the dashboard layout each show a green success toast on success and a red error toast (with the server's error message, where available) on failure.

**Area E**
- E1: on first load of `/settings` (once controllers are fetched), every group's accordion panel starts expanded.

**Area F**
- F1: opening the "edit user" dialog always shows that user's current username/email/role (no stale data from a previous dialog use); clicking "Abbrechen"/the dialog's dismiss affordances actually closes it.

# Technical Design (Round 3)

### Current Implementation
**Area A**
- `components/dashboard/comps.js`'s `History` component still uses `<v-dialog v-model="$store.getters['ui/isActiveDialog'](modalDialogName)">` (line ~408) - binding `v-model` directly to a getter *call expression* rather than a writable computed/ref, the exact anti-pattern already identified and fixed elsewhere in the app (`AquapiDashboardConfigurator`'s drawer, in Round 2) via `:model-value`/`@update:model-value` - this one instance was missed.
- `components/dashboard/comps.js`'s `HistoryChart` renders its "expand" button (line ~523-534) with `class="text-none ms-2 px-0 v-btn--icon"` and explicit `width/max-width/min-width="28"` - `v-btn--icon` is a **Vuetify 2** CSS class with no effect in Vuetify 3 (which derives its rounded-icon-button look from the `icon` *prop*, not a CSS class), so the button renders as a small square button instead of a round icon button, unlike the properly-declared `<v-btn icon @click="closeModal">` a few lines above in `History`'s own modal header.

**Area B**
- `aquaPi/pages/spa.py`'s `/` route still has `@login_required`; combined with `login_manager.login_view = 'auth.login'` (`aquaPi/auth.py`), any unauthenticated request to `/` is met with a **full HTTP redirect** to `/login`, which renders the entirely separate `login.html.jinja2` page - the SPA (and its already-fixed, real, JSON-capable `AquapiLoginDialog` from Round 2) is never even loaded in this case.
- `components/auth/AquapiLoginDialog.vue`'s `active` computed only reflects `ui/isActiveDialog('AquapiLoginDialog')` - nothing currently forces it open when the user isn't authenticated; it only opens when explicitly triggered (nav-drawer button).

**Area C**
- `components/app/index.js`'s `AquapiPageHeading` renders its action buttons as `<v-btn icon color="primary">` (bold, filled-look primary icon).
- `components/dashboard/comps.js`'s `History` modal close button (`<v-btn icon @click="closeModal"><v-icon color="grey">mdi-close</v-icon></v-btn>`) and `HistoryChart`'s expand button (once fixed per A2) are the other clearly "too prominent" icon buttons called out.

**Area D**
- No toast/snackbar mechanism exists anywhere in the app (confirmed via search - only a commented-out, never-activated `VueToast` reference in `main.js`). Save/delete feedback today is inconsistent: some flows silently succeed with no feedback at all (Config editor's `saveDraft`, `settings/updateNodeSetting`, dashboard save), while `components/users/index.js`'s `onDelete` already calls `this.$alert(result.error)` on failure only (no success feedback anywhere).
- The existing `$confirm`/`$alert` pattern (`main.js`, `AquapiConfirmDialog.vue.js`, `EventBus`) is a proven, minimal template for adding a similar `$toast` global helper.

**Area E**
- `components/settings/index.js`'s `AquapiSettings` initializes `openPanels: []` (line ~51) and never populates it, so `v-expansion-panels multiple v-model="openPanels"` starts with every panel collapsed.

**Area F**
- `components/users/comps.js`'s `UserDialog` declares `props: {value: {...}}` and `emits: ['input', 'saved']`, with `show` computed as `get() { return this.value }` / `set(value) { this.$emit('input', value) }` - **Vue 2's** `v-model` contract. `components/users/index.js` uses plain `<user-dialog v-model="dialogOpen" ...>`, which in Vue 3 compiles to binding the prop `modelValue` and listening for the event `update:modelValue` - names `UserDialog` never declares. The practical effect: the dialog's own `value` prop never receives `dialogOpen`'s real value (Vue 3 has no automatic legacy-prop fallback), and the `watch: { value(visible) {...} }` handler that (re)initializes `form` from `editUser` never fires reliably on the *intended* signal - explaining both reported symptoms (stale/incorrect form contents on edit, and clicking dismiss/cancel never actually closing the dialog from the parent's perspective, since `dialogOpen` in `components/users/index.js` never gets updated by the emitted, unlistened-for `input` event).
- The identical defect (same `value`/`input` props/emits, same `v-model` usage from the parent) also exists in `components/config/comps.js`'s `ConfigNodeDialog` and `ConfigTemplatesDialog` (`components/config/index.js` uses `v-model="dialogOpen"` on both) - not yet reported by the user, but the same root cause and same fix applies; left unfixed, it is a latent bug of the same kind.

### Key Decisions
- **History modal fix**: switch `History`'s `v-dialog` to the same `:model-value`/`@update:model-value` pattern already used successfully for the dashboard configurator drawer, instead of trying to make `v-model` work directly against a store-getter call expression.
- **v-model contract fix, applied uniformly**: rename `value` → `modelValue` and `emits: ['input', ...]` → `emits: ['update:modelValue', ...]` (and the corresponding computed getter/setter) in all three affected components (`UserDialog`, `ConfigNodeDialog`, `ConfigTemplatesDialog`), rather than only the explicitly reported `UserDialog`, since it's the exact same class of defect and leaving the other two unfixed would just defer the same bug report for the Config editor.
- **Forced SPA-only login**: remove `@login_required` from `spa.py`'s `/` route (the SPA shell itself becomes freely loadable) and make `AquapiLoginDialog`'s `active` getter return `true` whenever `!store.getters['auth/authenticated']`, ignoring attempts to close it while unauthenticated - this keeps `login.html.jinja2`/`login_manager.login_view` intact as the technical fallback (per Round 2's decision) while guaranteeing no normal user flow ever reaches it.
- **Toast system, mirroring `$confirm`/`$alert`**: a new `AquapiToast.vue` component (rendered once, e.g. from `App.vue.js`), listening for a new `EventBus` event (`TOAST_REQUESTED`) via a small queue of `v-snackbar`-backed messages; exposed as `app.config.globalProperties.$toast = {success(msg), error(msg)}`, called from the relevant UI components (not the store modules themselves) right after their existing `dispatch(...)` calls resolve, keeping store modules free of UI concerns.
- **Subtle icon buttons, targeted not global**: rather than a blanket CSS override (risking unintended regressions on already-fine icon buttons elsewhere, e.g. Users table actions which are already unstyled/muted by default), explicitly restyle only the identified prominent spots (`AquapiPageHeading` buttons, History modal buttons) to `variant="text"` with a muted grey color.
- **Settings default-open**: populate `openPanels` with every group's index once `grouped` is known (after `fetchNodes` resolves), rather than making `v-expansion-panels` uncontrolled - keeps the user's ability to still manually collapse a group afterward.

### Proposed Changes
**Area A**
1. `components/dashboard/comps.js` (`History`): change the modal `v-dialog` to `:model-value="..."` / `@update:model-value="..."`.
2. `components/dashboard/comps.js` (`HistoryChart`): replace the `v-btn--icon` CSS-class hack with the real `icon` prop (`<v-btn icon small ...>`), dropping the now-unneeded explicit width overrides.

**Area B**
3. `aquaPi/pages/spa.py`: remove `@login_required` from the `/` route.
4. `components/auth/AquapiLoginDialog.vue`: `active` getter returns `!authenticated || isActiveDialog(...)`; setter ignores `false` while `!authenticated`; pass `:add-cancel="authenticated"` to `AquapiLoginForm` so no cancel option is offered while forced open.

**Area C**
5. `components/app/index.js` (`AquapiPageHeading`): action buttons get `variant="text" color="grey-darken-1"` instead of `color="primary"`.
6. `components/dashboard/comps.js` (`History`/`HistoryChart`): close/expand buttons get the same muted `variant="text" color="grey-darken-1"` treatment.

**Area D**
7. New `components/app/AquapiToast.vue` (a `v-snackbar`-based queue, closable, auto-timeout) + `EventBus`'s `AQUAPI_EVENTS.TOAST_REQUESTED`; mounted once from `App.vue.js`.
8. `main.js`: `app.config.globalProperties.$toast = {success(message), error(message)}`.
9. Call `$toast.success(...)`/`$toast.error(...)` at the call sites: `components/config/index.js` (`saveDraft`/`discardDraft`), `components/settings/comps.js` (`updateNodeSetting` caller), `components/users/index.js` (`onAdd`/`onEdit` save results already surfaced via `UserDialog`; add a toast on `onSaved`/`onDelete`), `components/dashboard/index.js` (`AquapiDashboardConfigurator`'s save).

**Area E**
10. `components/settings/index.js`: after `fetchNodes` resolves, set `this.openPanels = Object.keys(this.grouped).map((_, i) => i)`.

**Area F**
11. `components/users/comps.js` (`UserDialog`), `components/config/comps.js` (`ConfigNodeDialog`, `ConfigTemplatesDialog`): rename `value`→`modelValue`, `emits: ['input', ...]`→`emits: ['update:modelValue', ...]`, adjust the `show` computed and the `watch: { value(...) }` handlers accordingly.

### Components
- `components/dashboard/comps.js`: `History`/`HistoryChart` modal + icon-button fixes.
- `aquaPi/pages/spa.py`: `/` route no longer login-gated.
- `components/auth/AquapiLoginDialog.vue`: forced-open behavior while unauthenticated.
- `components/app/index.js`: `AquapiPageHeading` button styling.
- `components/app/AquapiToast.vue` (new), `components/app/EventBus.js` (new event), `main.js` (`$toast`), `App.vue.js` (mounts the toast container).
- `components/config/index.js`, `components/settings/comps.js`, `components/users/index.js`, `components/dashboard/index.js`: new `$toast` call sites.
- `components/settings/index.js`: default-open accordion.
- `components/users/comps.js`, `components/config/comps.js`: `v-model` contract fix (`UserDialog`, `ConfigNodeDialog`, `ConfigTemplatesDialog`).

### Risks
- **Forced login dialog + background content**: while the dialog is forced open, background components (dashboard, SSE) still attempt their normal (now-401) fetches - already tolerated gracefully today (existing error handling), so no additional guard is introduced, keeping the change minimal.
- **Toast call-site coverage**: D1's scope is explicitly limited to the four named flows; other, not-yet-mentioned save actions are intentionally left without a toast for now, to keep this round's diff reviewable.
- **Fixing the not-yet-reported `ConfigNodeDialog`/`ConfigTemplatesDialog` v-model bug** changes Config-editor dialog behavior slightly beyond what was explicitly asked - mitigated by it being a pure bugfix of the same already-approved defect class (F1), not a behavior change.

# Testing (Round 3)

### Validation Approach
Area B touches backend routing (`aquaPi/pages/spa.py`); all other areas are frontend-only. Validation combines a targeted look at the modified Python route plus a headless-browser (Puppeteer) session covering all six areas end-to-end, consistent with the project's established approach for frontend-only/mixed changes.

### Key Scenarios
- Logged out, navigating to `/` in a fresh browser context returns the SPA (not `login.html.jinja2`), with the login dialog forced open and no way to dismiss it without logging in.
- Logging in via the forced dialog proceeds exactly as before (real session, dialog closes, dashboard shows).
- A History widget's "expand" button opens its modal with the correct node's chart; the modal's close button closes it; the expand button is visibly round.
- `AquapiPageHeading` action buttons and the History modal's buttons render with a muted/grey look instead of bold primary color.
- Saving/discarding a Config editor draft, changing a setting, creating/updating/deleting a user, and saving the dashboard layout each show the expected success/error toast.
- `/settings` shows all groups already expanded on first load.
- Clicking "Bearbeiten" on a user shows that user's current data in the dialog; the dialog closes via its Cancel button and via clicking outside (or the built-in dismiss), both without saving.

### Edge Cases
- Logging out while already on a protected view re-opens the forced login dialog rather than leaving stale content interactive.
- A toast triggered while another toast is still visible queues rather than overwriting it.
- Opening "add user" right after closing "edit user" shows a clean, empty form (not the previous edit's data) - regression check for the F1 fix.
- Manually collapsing a settings group and reloading the page keeps the default (all open) behavior (no persisted collapse state introduced by E1's fix).

### Test Changes
- `aquaPi/pages/spa.py`'s changed `/` route behavior verified via a quick unauthenticated request check (expects `200`, not a `302` to `/login`).
- All modified `.js`/`.vue`/`.py` files checked with `node --input-type=module --check` / `py_compile` respectively.
- No `pytest` run needed beyond the `/` route spot-check, per the agreed testing protocol (targeted, not full-suite).

---

# Round 2 (Login, Dashboard & Settings corrections) - Implementation Status: ✓ Done



# Requirements (Round 2: Login, Dashboard & Settings corrections)

### Overview & Goals
A new round of **corrections and adjustments**, reported by the user and grouped by area:
- **Area A - Login**: authentication is currently implemented three times (a real, working native Flask page, plus two non-functional client-only SPA login surfaces), which is confusing and partly broken (logout doesn't really log out server-side).
- **Area B - Home/Dashboard**: six distinct UX/layout bugs, most of them further fallout from the Vue 3/Vuetify 3 migration (Steps 18-20) that weren't caught by the previous bugfix round.
- **Area C - Settings page**: navigation to `/settings` sometimes fails to render without a full page reload, sliders render in the wrong color, settings widgets lack vertical spacing, and a leftover demo card is still shown.

Goal: exactly **one** login surface remains, fully embedded in and driven by the SPA, actually authenticating against the real Flask session (no more client-only fake login/logout); the dashboard's layout, empty-state detection, side-panel chrome and sub-control accordions behave correctly again; and `/settings` renders reliably via SPA navigation, with correctly styled/spaced widgets and no leftover demo content.

### Scope
**In Scope**
- **A1**: Consolidate the 3 existing login UIs (native `login.html.jinja2`, SPA route `/login` + `AquapiLoginForm`/`Auth.vue`, nav-drawer `AquapiLoginDialog`) into a single SPA login surface (the nav-drawer dialog), wired to the real Flask session (real login **and** real logout), removing the client-only fake auth simulation in `store/modules/auth.js`. Per explicit user decision: the app should have only one login UI, living entirely in the SPA - the native Flask login page is de-emphasized (no longer linked to from anywhere in the SPA) rather than deleted outright, since the underlying Flask-Login session mechanism itself must remain.
- **B1**: Footer (`v-footer` in `layouts/Default.vue`) not sticking to the bottom edge of the viewport.
- **B2**: Dashboard shows the "nothing configured yet" empty-state hint even though widgets are actually configured.
- **B3**: Dashboard renders only 2 columns instead of 3 at a viewport width that should be wide enough.
- **B4**: The dashboard configurator side panel ("Dashboard konfigurieren") has a visible gap between its top edge and the app-bar/toolbar.
- **B5**: Toggling one widget's visibility off can make **all** widgets in a whole column disappear.
- **B6**: Sub-controls inside widget cards should be collapsible ("accordion"), but currently aren't (broken Vuetify 2 markup) or aren't wrapped at all below the top level.
- **C1**: Navigating to `/settings` via the SPA (nav drawer) doesn't render the page; only a full browser reload makes it appear.
- **C2**: Setting sliders (`SettingSlider`) render grey instead of the app's standard blue/primary color.
- **C3**: Individual setting widgets have no vertical spacing between them.
- **C4**: A leftover orange/yellow "dummy" demo card is still rendered below the settings content.

**Out of Scope**
- Password-reset pages (`reset_password_request.html.jinja2`/`reset_password_confirm.html.jinja2`) - these remain server-rendered, they are a separate, already-working flow and not part of the reported duplication.
- Any other, not-yet-reported Vuetify-2-vs-3 markup incompatibilities elsewhere in the app.
- Visual redesign of the dashboard/settings beyond fixing the reported issues.

### User Stories
- As a user, I log in and out entirely inside the SPA (one dialog, no separate page), and my session is genuinely established/torn down on the server, exactly like the current native Flask login does today.
- As a user, the app footer always stays glued to the bottom edge of my browser window, regardless of how much content is above it.
- As a user, once I've configured and enabled at least one dashboard widget, the "nothing configured" hint never reappears while that widget stays enabled.
- As a user, on a wide enough screen I always see 3 dashboard columns, matching the space actually available.
- As a user, opening "Dashboard konfigurieren" shows a side panel flush under the app-bar, like the main navigation drawer.
- As a user, hiding one widget never makes unrelated, still-visible widgets disappear from view.
- As a user, the extra inputs/sub-controls inside a widget card are tucked into a collapsible accordion I can expand on demand, at every nesting level.
- As a user, clicking "Einstellungen" in the nav drawer always shows me the settings page immediately, without needing to reload the browser.
- As a user, the sliders on the settings page are colored consistently with the rest of the app (blue/primary), not grey.
- As a user, the individual setting fields on `/settings` are visually separated with a comfortable amount of space.
- As a user, I no longer see an unrelated orange demo card on the settings page.

### Functional Requirements
**Area A - Login**
- Exactly one login UI exists in the app: the nav-drawer's `AquapiLoginDialog`/`AquapiLoginForm`. The standalone `/login` SPA route and `layouts/Auth.vue` are removed.
- Submitting the login dialog performs a real authentication request against the Flask backend (same credential check/lockout logic as today's `POST /login`) and, on success, updates the app's auth state from the real session (via `/api/users/me`), not from a client-only guess.
- Clicking "Logout" performs a real server-side logout (invalidates the Flask-Login session), not just a local state reset.
- The native `login.html.jinja2` page keeps working as a technical fallback (e.g. no-JS, direct navigation, `login_manager.login_view` target for `@login_required` redirects) but is no longer linked to from anywhere inside the SPA.

**Area B - Dashboard**
- B1: the footer is visually pinned to the bottom of the viewport in all cases (short and long content).
- B2: the "nothing configured" hint is shown if and only if there are zero *visible* widgets, evaluated consistently and without a stale/incorrect intermediate state.
- B3: the number of dashboard columns is derived from the actually available content width (not the raw, drawer-unaware `window.innerWidth`), so 3 columns show whenever there's really room for them.
- B4: the configurator drawer sits flush under the app-bar, matching `AquapiNavDrawer`'s positioning.
- B5: toggling a widget's visibility never leaves a column that should have content empty; remaining visible widgets keep filling columns evenly.
- B6: sub-controls ("Inputs" and any nested controller cards) render inside a working, genuinely collapsible `v-expansion-panels` (Vuetify 3 markup), at every nesting level, not just the top one.

**Area C - Settings page**
- C1: navigating to `/settings` from anywhere else in the SPA (nav drawer, browser back/forward) reliably renders the page content on the first try.
- C2: `SettingSlider` uses the app's primary theme color for its track/thumb.
- C3: setting widgets (`NodeSettingsCard`'s `v-col` items, and the `v-card`s themselves) have consistent, visible vertical spacing.
- C4: the `AquapiDummy` demo component is no longer wired into the `/settings` route (or any other real page).

# Technical Design (Round 2)

### Current Implementation
**Area A - Login**
- `aquaPi/auth.py`'s `POST /login` (`bp.route('/login', ...)`) is the **only working** authentication path: it validates credentials, checks/records lockouts (`db.is_login_locked_out`/`register_failed_login`), calls `login_user(...)` and renders `login.html.jinja2` (server-rendered, full page).
- `store/modules/spa/store/modules/auth.js` (`login`/`logout` actions) is **entirely client-only**: `login` just writes `{username}` to `window.localStorage` and commits it to the Vuex state - it never calls the backend. `logout` likewise only clears local state. Clicking "Logout" in `layouts/Default.vue` therefore never actually ends the Flask-Login session.
- `router/index.js` defines a full SPA route `/login` (`component: () => loadSfc('/static/spa/layouts/Auth.vue')`, child renders `AquapiLoginForm.vue`) - a second, independent login UI.
- `components/auth/AquapiLoginDialog.vue` (opened from `layouts/Default.vue`'s app-bar login button) embeds the **same** `AquapiLoginForm.vue` as a modal - a third UI, wired to the same fake `auth/login` action.
- `router/index.js`'s `router.beforeEach` guard is dead/placeholder code (`if (to.name !== 'login' && !(999 == 999))` - the condition is always `false`, so it never redirects), confirming authentication was never actually wired up on the frontend.
- `/api/users/me` (added in Step 21, `auth.py`) already returns the real authenticated user (401 if not logged in) and is used elsewhere (e.g. `users/fetchCurrentUser`) - but not by `store/modules/auth.js`.

**Area B - Dashboard**
- `layouts/Default.vue`: `<v-footer dark ... app elevation="4">` already has the Vuetify layout-registering `app` prop, but the sibling `<v-main style="max-height: 100vh;">` has a suspicious hard-coded inline `max-height: 100vh` style that constrains `v-main`'s box on top of the space Vuetify's layout system already reserves for the app-bar/footer - the most likely reason the footer doesn't stay glued to the actual bottom edge, to be confirmed against the live computed layout during implementation (same headless-browser diagnosis approach used for the Step 18/20 nav-drawer bug).
- `components/dashboard/index.js` (`AquapiDashboard.widgets` computed): `this.$store.getters['dashboard/widgets'].filter(item => item.visible)` - the empty-state alert's `v-if="!(widgets.length)"` is driven by this *filtered* (visible-only) list, so it correctly shows only when there are zero visible widgets; the more likely actual defect is in the columns algorithm below, which can silently drop items into an empty column when the visible-widget count changes, which looks like "configured widgets aren't shown".
- `components/dashboard/index.js` (`AquapiDashboard.columnCount`/`columns` computed, lines ~404-418): `columnCount` is derived purely from `dashboardWidth` (`window.innerWidth`, updated only on the browser `resize` event), **not** from the actual rendered width of the dashboard's own container - it doesn't account for the permanent nav drawer's width or the `v-container`'s padding, so the perceived "enough viewport width" (B3) doesn't match what the algorithm measures. `columns()` then buckets `widgets` round-robin via `i % columnCount` into exactly `columnCount` arrays - **if the number of visible widgets is smaller than `columnCount` (e.g. after hiding one), one or more trailing columns end up completely empty**, and every widget's column assignment shifts whenever the visible-widget count changes size (not just re-sorts within the same column) - this is the confirmed, concrete root cause of B5 ("toggling visibility makes a whole column disappear") and a contributing factor to B3.
- `components/dashboard/index.js` (`AquapiDashboardConfigurator`'s `v-navigation-drawer`): already fixed in the previous round to use `:model-value`/`@update:model-value`, but it does **not** have the `app` prop that `AquapiNavDrawer.vue.js` has - comparing the two side by side, `AquapiNavDrawer` uses `app dark fixed temporary`, while the configurator only uses `location="right" temporary`. Without `app`, the configurator drawer isn't registered with Vuetify 3's layout system, so its top edge doesn't align flush under the (app-registered) app-bar the way `AquapiNavDrawer`'s does - the confirmed, concrete cause of B4.
- `components/dashboard/comps.js` (`BusNode`, lines ~160-186) already wraps its "Inputs" (`receivesNodes`) sub-controls in `<v-expansion-panels><v-expansion-panel><v-expansion-panel-header>...</v-expansion-panel-header><v-expansion-panel-content>...</v-expansion-panel-content></v-expansion-panel></v-expansion-panels>` - but `v-expansion-panel-header`/`v-expansion-panel-content` are **Vuetify 2** tag names, renamed to `v-expansion-panel-title`/`v-expansion-panel-text` in Vuetify 3 (confirmed: the exact same renamed-tag regression class already found and fixed for `v-list-item-icon`/`-content` in the Step 18/20 round, just missed here and in `components/settings/index.js`, which has the identical broken pattern). Since Vue 3 renders unresolved custom tags as plain elements, the panel never becomes an actual collapsible accordion - it just always shows its content flat, which is what B6 ("sub-controls should be accordions") is really reporting. Additionally, this accordion only wraps `receivesNodes` at `level == 1`; the `v-else` branch (deeper nesting levels) renders nested controller cards with no collapsible wrapper at all.

**Area C - Settings page**
- `components/settings/index.js` (`AquapiSettings`) has the **same** broken `v-expansion-panel-header`/`v-expansion-panel-content` Vuetify-2 tag names as `dashboard/comps.js` (confirmed via `grep`, the only 2 places in the whole `spa/` tree using these deprecated tags), for the group-folding accordion around `node-settings-card`.
- `router/index.js`'s `settings` route is the **only** route in the whole app that defines two named views with mismatched loading strategies: `default: () => loadSfc('/static/spa/pages/Settings.vue')` (lazy/async) together with `view_bottom: AquapiDummy` (a plain, synchronously-imported component). No other route (`home`, `config`, `about`, `users`) mixes an async and a sync component across two named views of the same route. This structural inconsistency, unique to `/settings`, is the prime suspect for C1 ("first client-side navigation to `/settings` doesn't render, only a reload works") and will be confirmed via headless-browser navigation testing once the dummy `view_bottom` entry (C4) is removed, since removing it also removes the inconsistency.
- `components/app/index.js`'s `AquapiDummy` component ("just a dummy component for testing purposes" per its own code comment) renders a visible orange/yellow `v-card` with `{{ $t('misc.dummyComponentText') }}` - this is exactly the leftover "Dummy-Karte" reported in C4, wired in only via `router/index.js`'s `settings` route `view_bottom: AquapiDummy`.
- `components/settings/comps.js` (`SettingSlider`): `<v-slider v-model="localValue" ... thumb-label hide-details>` has no `color` prop, so it renders using Vuetify 3's slider default (grey), unlike other themed controls in the app - the concrete cause of C2.
- `components/settings/comps.js` (`NodeSettingsCard`): individual setting widgets are laid out via `<v-row><v-col v-for="(item, idx) in settings" cols="12" sm="6" md="4">...</v-col></v-row>` with no extra spacing classes, and `NodeSettingsCard`'s own `v-card` only has `class="mb-3"` (spacing between cards, not between the individual widgets within one card) - the concrete cause of C3.

### Key Decisions
- **Login consolidation** → **one real, SPA-only login surface** (per explicit user decision, "nur ein Login in der SPA, die Flask-Login-Seite kann entfallen, wenn möglich"): keep exactly one UI - the nav-drawer's `AquapiLoginDialog`/`AquapiLoginForm` - and make it call the real backend. Since a browser form submit to `/login` returns an HTML page/redirect (unsuitable for AJAX), the existing `POST /login`/`GET /logout` Flask routes are extended to **content-negotiate**: when the request looks like it comes from the SPA (`X-Requested-With: XMLHttpRequest` header, matching the convention already used by every other API call in `store/modules/*.js`), they return a small JSON body instead of rendering/redirecting; a normal browser navigation still gets the existing HTML behavior unchanged. This avoids adding parallel duplicate routes and keeps `login.html.jinja2` fully intact as a fallback (no longer linked to from the SPA, but still reachable and still the `login_manager.login_view` target), which is the closest practical match to "kann entfallen, wenn möglich" without removing the underlying Flask-Login session mechanism (not realistically removable, since it *is* the authentication mechanism).
- **Single SPA login route**: the standalone `/login` route (`layouts/Auth.vue` + `AquapiLoginForm.vue` as a full page) is removed; it duplicated the nav-drawer dialog for no added benefit (same non-functional store action, same form component). If an unauthenticated user's request needs a login prompt, the app instead opens the existing `AquapiLoginDialog` on top of the normal `Default` layout.
- **Dashboard columns** → **measure the actual container, and never create more columns than there are visible widgets**: replace the `window.innerWidth`-driven `columnCount` with a `ResizeObserver` on the dashboard's own masonry container element (decouples column count from the nav drawer's width/padding, fixing B3), and clamp `columnCount` to `Math.min(desiredColumns, widgets.length || 1)` in the `columns()` computed (directly fixes B5's empty-column defect, since a column can never be created without at least one item available to fill it).
- **Configurator drawer alignment**: add the same `app` (and `dark`) props `AquapiNavDrawer.vue.js` already uses successfully, so both drawers participate identically in Vuetify 3's layout system (fixes B4).
- **Footer sticking**: remove (or replace with a non-conflicting alternative) the inline `max-height: 100vh` on `v-main` in `layouts/Default.vue`, letting Vuetify 3's `app`-aware layout system size `v-main`/`v-footer` itself, then re-verify via headless-browser that the footer's computed `position`/`bottom` matches an actually pinned footer (fixes B1).
- **Expansion-panel markup fix**: rename `v-expansion-panel-header` → `v-expansion-panel-title` and `v-expansion-panel-content` → `v-expansion-panel-text` at both existing call sites (`components/dashboard/comps.js`, `components/settings/index.js`) - the same, already-proven fix pattern used for `v-list-item-icon`/`-content` in the previous round (fixes B6's "broken" half and all of C1's Vuetify-2-tag aspect for settings groups).
- **Extend accordions to nested sub-controls**: also wrap the `v-else` (deeper-level, `level > 1`) branch in `BusNode`'s template in its own `v-expansion-panels`/`v-expansion-panel`, instead of rendering nested controller cards flat - completes B6's "sub-controls should be accordions" requirement at every nesting level, not just the top one.
- **Settings page fixes**: remove the `view_bottom: AquapiDummy` entry from the `settings` route in `router/index.js` entirely (fixes C4, and is expected to also resolve C1 per the structural-inconsistency hypothesis above); add `color="primary"` to `SettingSlider`'s `v-slider` (fixes C2); add a consistent bottom margin (e.g. `class="mb-4"` on each `v-col` wrapper in `NodeSettingsCard`, or an equivalent `app.css` rule) between individual setting widgets (fixes C3).

### Proposed Changes
**Area A**
1. **`aquaPi/auth.py`**: extend `login()` and `logout()` to return `jsonify(...)` when `request.headers.get('X-Requested-With') == 'XMLHttpRequest'`, keeping the existing `render_template`/`redirect` behavior otherwise.
2. **`store/modules/auth.js`**: rewrite `login`/`logout` actions to `fetch('/login'|'/logout', {headers: {'X-Requested-With': 'XMLHttpRequest', ...}, credentials: 'same-origin', ...})`; on success, dispatch `users/fetchCurrentUser` (existing action) to populate the real username/role from `/api/users/me`, and commit that into `auth`'s state instead of the `payload.username` guess.
3. **`main.js`**: on boot, dispatch an initial "resolve current session" action (reusing `users/fetchCurrentUser`, tolerating its 401) so the app's displayed auth state reflects the real, already-existing Flask session (e.g. after a browser refresh) instead of defaulting to logged-out until the next explicit login.
4. **`router/index.js`**: remove the `/login` route (`Auth.vue` + `AquapiLoginForm.vue` as a full page) and its `Auth.vue` layout reference; remove the dead placeholder `router.beforeEach` guard body (or replace it with a real check against `store.getters['auth/authenticated']`, consistent with the `users` route's existing `beforeEnter` pattern).
5. **`layouts/Auth.vue`**: deleted (no longer referenced).

**Area B**
6. **`layouts/Default.vue`**: remove/replace the `<v-main style="max-height: 100vh;">` inline style; add `app` (and `dark`, matching `AquapiNavDrawer`) to `AquapiDashboardConfigurator`'s `v-navigation-drawer` in `components/dashboard/index.js`.
7. **`components/dashboard/index.js` (`AquapiDashboard`)**: replace the `window.innerWidth`/`resize`-listener-driven `dashboardWidth` with a `ResizeObserver` observing the dashboard's own `.aquapi-dashboard-masonry` container (`ref`); update `columnCount` to read the observed container width and clamp to `Math.min(desiredColumns, widgets.length || 1)`.
8. **`components/dashboard/comps.js` (`BusNode`)**: rename `v-expansion-panel-header`/`-content` to `v-expansion-panel-title`/`-text`; wrap the `level > 1` (`v-else`) branch's nested controller cards in their own `v-expansion-panels`/`v-expansion-panel` (mirroring the `level == 1` branch's structure).

**Area C**
9. **`components/settings/index.js`**: rename `v-expansion-panel-header`/`-content` to `v-expansion-panel-title`/`-text`.
10. **`router/index.js`**: remove the `view_bottom: AquapiDummy` entry from the `settings` route's `components:` object.
11. **`components/settings/comps.js` (`SettingSlider`)**: add `color="primary"` (and, if needed after visual check, `track-color`) to the `v-slider`.
12. **`components/settings/comps.js` (`NodeSettingsCard`)**: add a bottom-margin utility class (e.g. `class="mb-4"` or project-consistent spacing) to each `v-col` wrapping a setting widget.

### Data Models / Contracts
```js
// AquapiDashboard - ResizeObserver-driven, item-count-clamped columns (excerpt)
mounted() {
  this._resizeObserver = new ResizeObserver((entries) => {
    this.containerWidth = entries[0].contentRect.width
  })
  this._resizeObserver.observe(this.$refs.masonryContainer)
},
unmounted() {
  this._resizeObserver && this._resizeObserver.disconnect()
},
computed: {
  desiredColumns() {
    return this.containerWidth >= 960 ? 3 : (this.containerWidth >= 600 ? 2 : 1)
  },
  columnCount() {
    return Math.min(this.desiredColumns, this.widgets.length || 1)
  },
  columns() {
    const cols = Array.from({length: this.columnCount}, () => [])
    this.widgets.forEach((item, i) => cols[i % this.columnCount].push(item))
    return cols
  }
}
```
```python

# aquaPi/auth.py - JSON-aware login/logout (excerpt)

def _wants_json() -> bool:
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

@bp.route('/login', methods=['GET', 'POST'])
def login():
    ...
    if <success>:
        login_user(User.from_row(row))
        if _wants_json():
            return jsonify(result='SUCCESS')
        return redirect(...)
    ...
    if _wants_json():
        return jsonify(result='ERROR', message=<reason>), HTTPStatus.UNAUTHORIZED
    return render_template('pages/login.html.jinja2')
```
```js
// store/modules/auth.js - real login/logout (excerpt)
async login(context, payload) {
  const res = await fetch('/login', {
    method: 'POST',
    headers: {'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded'},
    credentials: 'same-origin',
    body: new URLSearchParams(payload),
  })
  const data = await res.json()
  if (data.result === 'SUCCESS') {
    await context.dispatch('users/fetchCurrentUser', null, {root: true})
    context.commit('setUser', {username: payload.username})
    EventBus.$emit(AQUAPI_EVENTS.AUTH_LOGGED_IN)
    return true
  }
  return false
},
async logout(context) {
  await fetch('/logout', {headers: {'X-Requested-With': 'XMLHttpRequest'}, credentials: 'same-origin'})
  context.commit('setUser', null)
  EventBus.$emit(AQUAPI_EVENTS.AUTH_LOGGED_OUT)
}
```

### Components
- `aquaPi/auth.py`: `login()`/`logout()` gain JSON-response support for XHR requests.
- `store/modules/auth.js`: real `login`/`logout` actions, backed by the real session + `/api/users/me`.
- `router/index.js`: `/login` route and its `beforeEach` placeholder removed/fixed; `view_bottom: AquapiDummy` removed from `settings`.
- `layouts/Auth.vue`: deleted.
- `layouts/Default.vue`: `v-main` inline style fixed; footer re-verified.
- `components/dashboard/index.js` (`AquapiDashboard`, `AquapiDashboardConfigurator`): `ResizeObserver`-driven, item-count-clamped columns; configurator drawer gets `app`/`dark`.
- `components/dashboard/comps.js` (`BusNode`): expansion-panel tag rename; accordion extended to nested levels.
- `components/settings/index.js`: expansion-panel tag rename.
- `components/settings/comps.js` (`SettingSlider`, `NodeSettingsCard`): slider color, widget spacing.
- `components/app/index.js` (`AquapiDummy`): no longer referenced by any route (left in place as a reusable test component, per its own stated purpose, but not wired into real pages).

### Architecture Diagram
```mermaid
graph TD
    Dialog[AquapiLoginDialog / AquapiLoginForm] -->|fetch POST XHR| Login[auth.py login]
    Login -->|login_user, JSON response| Dialog
    Dialog -->|fetchCurrentUser| Me[/api/users/me]
    Me --> AuthStore[store/modules/auth.js]
    Dashboard[AquapiDashboard] -->|ResizeObserver| Container[masonry container]
    Container --> ColumnCount[columnCount, clamped to widgets.length]
    ColumnCount --> Columns[columns computed]
    Columns --> Widget[AquapiDashboardWidget]
```

### Risks
- **Content-negotiated `/login`/`/logout`** changes shared backend routes also used by the native fallback page - mitigated by only branching on an explicit `X-Requested-With` header, leaving the existing HTML behavior byte-for-byte unchanged for normal browser requests (including the existing lockout/flash-message logic, tests in `tests/test_auth.py`).
- **Removing `AquapiDummy`'s wiring** could be seen as removing a useful manual test fixture - mitigated by leaving the component itself intact (just unwired from the `settings` route), so it can still be temporarily re-attached to a route if ever needed for manual testing.
- **C1's root cause (mixed async/sync named views)** is a strong hypothesis grounded in `router/index.js`, but not yet reproduced live - the delivery stage explicitly includes a headless-browser confirmation step before/after the fix, consistent with how the Step 18/20 regression was diagnosed.
- **ResizeObserver browser support**: universally supported in the browsers this project already targets (same class of API as the already-used `fetch`/`EventSource`), so no polyfill is needed.

# Testing (Round 2)

### Validation Approach
Area A touches both frontend and backend (`aquaPi/auth.py`), so validation combines a targeted `pytest` run (`tests/test_auth.py`, `tests/test_auth_db.py`) with a headless-browser (Puppeteer) session for the actual login/logout UX; Areas B and C are frontend-only, validated via headless-browser + static syntax checks, consistent with the project's established verification approach.

### Key Scenarios
- Submitting the (single, nav-drawer) login dialog with valid credentials logs the user in for real: `document.cookie`/session is set, `/api/users/me` returns the real user, the app-bar switches to the logged-in state.
- Submitting the login dialog with invalid credentials shows an error, does not create a session, and does not crash the SPA.
- Clicking "Logout" actually ends the server session (a subsequent `/api/users/me` returns 401), and the app-bar switches back to the logged-out state.
- Navigating to the (now-removed) `/login` URL no longer 404s the SPA router (redirects to `home`, which opens the login dialog if unauthenticated).
- The footer stays visually pinned to the bottom of the viewport both on a tall dashboard (content overflow, scrolling) and on a short page (e.g. `/about`).
- Configuring a dashboard, enabling at least one widget, reloading: the "nothing configured" hint does not show.
- At a viewport width known to be "wide enough" (>= the effective 3-column breakpoint measured against the actual container), exactly 3 columns render.
- Opening "Dashboard konfigurieren" shows the panel flush under the app-bar, no visible gap.
- Toggling several widgets on/off in sequence never leaves a column empty while other widgets remain visible.
- A widget with "Inputs" sub-controls renders a real, clickable, collapsible `v-expansion-panel` (title visible, content collapsed by default or per existing `v-model`, expands on click) at every nesting level.
- Navigating to `/settings` from the nav drawer (not a reload) renders the settings content immediately.
- Settings sliders render in the app's primary blue.
- Setting widgets have visible vertical spacing.
- No orange "dummy" card appears on `/settings` (or anywhere else).

### Edge Cases
- Login attempt during an active lockout (per `db.is_login_locked_out`) still returns the correct locked-out error via the new JSON path, matching the existing HTML-path behavior/tests.
- Dashboard with zero configured widgets still shows the empty-state hint (unaffected by the columns/ResizeObserver rework).
- Resizing the browser window (not just crossing the old window-width breakpoints, but also opening/closing the nav drawer, which changes the container's width without changing `window.innerWidth`) updates the column count correctly.
- A dashboard with exactly 1 or 2 visible widgets never shows more columns than widgets (clamped `columnCount`).
- Rapid navigation away from `/settings` and back does not leave stale/duplicate `NodeSettingsCard` fetch state.

### Test Changes
- New/extended backend tests in `tests/test_auth.py` for the JSON-response branch of `/login`/`/logout` (success, failure, lockout).
- All modified `.js`/`.py`/`.vue` files checked with `node --input-type=module --check` / `py_compile` respectively.
- Targeted `pytest` run: `tests/test_auth.py` + `tests/test_auth_db.py` (no full-suite run, per the agreed testing protocol).

# Round 1 (Steps 18-20 dashboard/nav-drawer bugfix) - Implementation Status: ✓ Done

This section documents the **previous**, already fully implemented and verified round that this plan document originally covered (masonry/draggable/nav-drawer regressions from Steps 18-20), kept here for history only - it is unrelated to and unaffected by the new Login/Dashboard/Settings corrections above.

All proposed changes were implemented and verified via a headless-browser (Puppeteer) session against the running app with the user's real 13-node configuration:
- `components/dashboard/index.js`: `<masonry>` replaced by a `columnCount`/`columns`-computed CSS flex-column layout (`.aquapi-dashboard-masonry`/`-col` in `app.css`, resize-listener updates `columnCount` at the 960px/600px breakpoints); `<draggable>` replaced by `Sortable.create(...)` on a plain `<div ref="widgetList">` in `mounted()`, destroyed in `unmounted()`, with a new `reorderWidgets(from, to)` method committing via `dashboard/setWidgets`; the configurator's `v-navigation-drawer` switched from `v-show` to `:model-value`/`@update:model-value` plus `location="right"` (dropping `fixed`/`right`/`permanent`).
- `components/app/AquapiNavDrawer.vue.js`: all 4 `v-list-item-icon`/`v-list-item-content` pairs replaced with a `#prepend` template slot (where an icon exists) and `v-list-item-title`/`-subtitle` directly as `v-list-item` content.
- `spa.html.jinja2`: `vuedraggable.2.20.0.js` and `vue-masonry-css.1.0.3.js` `<script>` tags removed.
- **Root cause note for the reported regression**: confirmed the underlying issue was `v-show` not working on `v-navigation-drawer` (a Vuetify 3 multi-root component), which left the drawer permanently visible/overlaying the page and intercepting clicks (explaining the broken routing symptom); switching to `model-value` fixed it, matching `AquapiNavDrawer`'s existing pattern.
- **Verification finding (environment, not code)**: during verification, the live Flask process turned out to be running without Flask's debug/auto-reload active (Flask 3.x no longer honors the legacy `FLASK_ENV=development` variable to enable it), so it kept serving a stale compiled template with the old `<script>` tags; restarting it with `--debug` resolved this and confirmed the fix works end-to-end with zero console errors/warnings.
- Confirmed: dashboard renders in a responsive column layout, the configurator drawer is off-canvas (translated out of view) until opened via the "apps" button and slides back out on close, drag-reordering commits via the store, saving/loading widget visibility works correctly (verified via the `/api/dashboard/` endpoint), and navigation to `/config`/`/settings`/`/about` works without issues - no new console errors beyond none.