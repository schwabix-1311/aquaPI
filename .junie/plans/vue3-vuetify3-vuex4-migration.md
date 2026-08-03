---
sessionId: session-260802-063658-1699
---

# Implementation Status: ✓ Done (current round: Login, Dashboard & Settings corrections)

All of Area A (login consolidation), Area B (dashboard B1-B6) and Area C (settings C1-C4) below are implemented and verified end-to-end via a real headless-browser session with a real logged-in session and a seeded, realistic 13-widget dashboard configuration. Two additional, previously undiagnosed bugs were found and fixed during verification (not part of the original technical design, since they only surfaced once the described fixes were actually exercised together):
- **`AquapiPageHeading`/`AquapiLoadingIndicator`/`AquapiDummy` stopped being globally registered**: removing the `view_bottom: AquapiDummy` import from `router/index.js` (fix for C4) accidentally removed the *only* import of `components/app/index.js` in the whole app, which was the sole reason that module (and thus `AquapiPageHeading`) ever got loaded/registered as a side effect. This silently broke every page's heading toolbar (including the dashboard's "configure" button, needed to verify B4/B5) until a dedicated `import '../components/app/index.js'` side-effect import was added to `router/index.js` alongside the other eager component-module imports.
- **Dashboard widget crash on `node.alert === null`**: `AquapiDashboardWidget`'s `alert`/`alertColor` computed properties only guarded `!('alert' in this.node)`, but real nodes (e.g. `heizen`) have the key present with a `null` value, causing `this.node.alert[0]` to throw and silently freeze the dashboard's reactivity (making the empty-state hint look "stuck" and columns look mis-measured) - fixed by guarding on `this.node.alert == null` instead, in `components/dashboard/index.js`.
- **B1 footer root cause refined during verification**: removing the inline `max-height: 100vh` on `v-main` (as originally planned) was necessary but not sufficient - Vuetify 3's `v-main` no longer renders a `.v-main__wrap` child div (a Vuetify-2-only implementation detail the old `app.css` rule relied on), so without a height-capped `.v-application__wrap` the footer (absolutely positioned relative to that wrapper) drifted below the viewport once page content overflowed. Fixed in `app.css`: `.v-application__wrap` is capped to `100vh` with `overflow: hidden`, and `.v-main` scrolls its own content internally (`overflow-y: auto`), replacing the dead `div.v-main__wrap` rules.

This document was previously repurposed for this round (superseding its original Steps 18-20 masonry/draggable/nav-drawer scope, which is fully implemented/verified separately - see the historical "Implementation Status" section further below).

# Requirements (current round: Login, Dashboard & Settings corrections)

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

# Technical Design

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

# Testing

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

# Previous Round (Steps 18-20 dashboard/nav-drawer bugfix) - Implementation Status: ✓ Done

This section documents the **previous**, already fully implemented and verified round that this plan document originally covered (masonry/draggable/nav-drawer regressions from Steps 18-20), kept here for history only - it is unrelated to and unaffected by the new Login/Dashboard/Settings corrections above.

All proposed changes were implemented and verified via a headless-browser (Puppeteer) session against the running app with the user's real 13-node configuration:
- `components/dashboard/index.js`: `<masonry>` replaced by a `columnCount`/`columns`-computed CSS flex-column layout (`.aquapi-dashboard-masonry`/`-col` in `app.css`, resize-listener updates `columnCount` at the 960px/600px breakpoints); `<draggable>` replaced by `Sortable.create(...)` on a plain `<div ref="widgetList">` in `mounted()`, destroyed in `unmounted()`, with a new `reorderWidgets(from, to)` method committing via `dashboard/setWidgets`; the configurator's `v-navigation-drawer` switched from `v-show` to `:model-value`/`@update:model-value` plus `location="right"` (dropping `fixed`/`right`/`permanent`).
- `components/app/AquapiNavDrawer.vue.js`: all 4 `v-list-item-icon`/`v-list-item-content` pairs replaced with a `#prepend` template slot (where an icon exists) and `v-list-item-title`/`-subtitle` directly as `v-list-item` content.
- `spa.html.jinja2`: `vuedraggable.2.20.0.js` and `vue-masonry-css.1.0.3.js` `<script>` tags removed.
- **Root cause note for the reported regression**: confirmed the underlying issue was `v-show` not working on `v-navigation-drawer` (a Vuetify 3 multi-root component), which left the drawer permanently visible/overlaying the page and intercepting clicks (explaining the broken routing symptom); switching to `model-value` fixed it, matching `AquapiNavDrawer`'s existing pattern.
- **Verification finding (environment, not code)**: during verification, the live Flask process turned out to be running without Flask's debug/auto-reload active (Flask 3.x no longer honors the legacy `FLASK_ENV=development` variable to enable it), so it kept serving a stale compiled template with the old `<script>` tags; restarting it with `--debug` resolved this and confirmed the fix works end-to-end with zero console errors/warnings.
- Confirmed: dashboard renders in a responsive column layout, the configurator drawer is off-canvas (translated out of view) until opened via the "apps" button and slides back out on close, drag-reordering commits via the store, saving/loading widget visibility works correctly (verified via the `/api/dashboard/` endpoint), and navigation to `/config`/`/settings`/`/about` works without issues - no new console errors beyond none.