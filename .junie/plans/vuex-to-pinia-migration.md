---
sessionId: session-260802-063658-1699
---

# Implementation Status: ✓ Done

Implemented and end-to-end verified via a real headless-browser session against the live app with a real admin login and the real 17-node configuration.

- **Library**: used Pinia **4.0.2**'s `pinia.iife.js` instead of 3.x - Pinia 3.0.1-3.0.3's iife build has a known upstream bug (`ReferenceError: devtoolsApi is not defined`); Pinia 3.0.0/4.0.2 don't have this issue and 4.0.2 only depends on the `Vue` global, confirmed via a sandboxed load test before adding it to `aquaPi/static/libs/`.
- All 6 store modules converted to Options-style Pinia stores exactly as planned; `store/index.js`/`main.js`/all plain `.js` components/the 4 real `.vue` SFCs rewritten to use `useXStore()` instead of `$store`, including the documented `showDialog`/`hideOthers` no-op-argument preservation.
- **Extra fix found during verification, not in the original file list**: `router/index.js`'s `/users` route `beforeEnter` guard still imported the old Vuex `store` instance and called `store.getters['users/currentUser']`/`store.dispatch(...)` - this file wasn't caught by the initial `$store` grep since it used a plain `import store from '../store/index.js'` alias. Left unfixed, this threw an uncaught `TypeError` during every navigation to `/users`, silently leaving the router stuck on the previous page. Fixed by switching it to `useUsersStore()` like every other file.
- Verified end-to-end: login (nav-drawer dialog) + logout via real server session, dark-mode toggle (`v-theme--light` ↔ `v-theme--dark`), `/config` editor rendering all 16 real node boxes + 18 connections, `/users` admin page rendering both real users (only after the router-guard fix), and the dashboard configurator's widget-visibility-toggle-then-save flow (confirmed the initial "0 widgets" observation was a pre-existing, unrelated timing quirk - `/api/nodes/` is fetched once at app boot before the login request resolves, and nothing re-fetches until the next page load/reload - reproduced identically after reload while already authenticated, where all 17 nodes loaded correctly).
- Removed the now-unused `aquaPi/static/libs/vuex.4.1.0.global.js` file.
- Zero console/page errors in any of the verification runs; all modified `.js` files and the `<script>` blocks of the 4 `.vue` SFCs pass `node --input-type=module --check`.

# Requirements

### Overview & Goals
Replace Vuex 4 with **Pinia**, without introducing a build process - Pinia ships an `iife`/global browser build (`pinia.iife.js`, confirmed available for Pinia 3.x on unpkg, same pattern as the project's existing `vue.3.5.40.global.js`/`vuex.4.1.0.global.js` etc. under `aquaPi/static/libs/`). Per the user's explicit choice, this is a **fully idiomatic rewrite**: every one of the ~79 call sites across ~15 files that currently use `this.$store.state.mod.x` / `$store.getters['mod/getter']` / `$store.dispatch('mod/action', payload)` / `$store.commit('mod/mutation', payload)` (including directly inside templates) is rewritten to call Pinia stores (`useXStore()`) directly - no Vuex-compatibility shim.

### Current Implementation (investigated)
- `aquaPi/static/spa/store/index.js` creates `Vuex.createStore({modules: {ui, auth, dashboard, settings, config, users}, strict: false})`; each module in `store/modules/*.js` is a namespaced Vuex module (`state()`, `getters`, `actions`, `mutations`).
- Cross-module calls use Vuex's `{root: true}` pattern, e.g. `config.js`'s `saveDraft`/`createNode`/etc. all do `dispatch('dashboard/fetchNodes', null, {root: true})`; `auth.js`'s `login`/`logout` dispatch/commit into the `users` module the same way.
- `main.js` mounts the app via `app.use(store)` and uses `this.$store...` inside the root app's own `methods`/`beforeMount`.
- Plain `.js` option-component files (real ES modules, loaded directly by the browser) use `this.$store...` freely: `App.vue.js`, `components/app/AquapiConfirmDialog.vue.js`, `components/app/AquapiNavDrawer.vue.js`, `components/dashboard/index.js` + `comps.js`, `components/settings/index.js` + `comps.js`, `components/config/index.js` + `comps.js`, `components/users/index.js` + `comps.js`.
- 4 real `.vue` SFC files, compiled client-side at runtime by `vue3-sfc-loader` via `aquaPi/static/spa/sfc/loadSfc.js`, also use `$store` directly in their templates/`<script>`: `layouts/Default.vue`, `pages/Config.vue`, `components/auth/AquapiLoginDialog.vue`, `components/auth/AquapiLoginForm.vue`. These SFCs cannot use real relative `import`s for `.js` files (Babel parses their `<script>` as non-module "script" sourceType) - today they work around this via `loadSfc.js`'s `moduleCache` (e.g. `import {EventBus} from 'app/EventBus'`), which will need a new entry per Pinia store they use.
- The other 4 `.vue` SFCs (`pages/Home.vue`, `pages/Settings.vue`, `pages/Users.vue`, `pages/About.vue`) have no store usage today and need no changes.

### Scope
**In Scope**
- Add a Pinia global browser build under `aquaPi/static/libs/` and reference it from `aquaPi/templates/pages/spa.html.jinja2`, removing the Vuex script tag.
- Convert all 6 store modules (`ui`, `auth`, `dashboard`, `settings`, `config`, `users`) from Vuex modules into Pinia `defineStore(...)` stores (Options-style: `state`/`getters`/`actions`, matching the codebase's exclusively Options-API convention - no Composition-API/`<script setup>` is used anywhere in the project).
- Convert every Vuex "mutation" into a Pinia "action" (Pinia has no separate mutations - actions mutate `this.x` directly).
- Convert every cross-module `dispatch('other/x', payload, {root: true})` / `commit('other/x', payload, {root: true})` into a direct call on the other store's instance (`useOtherStore().x(payload)`), which is Pinia's normal, simpler idiom for cross-store composition (Pinia has no nested-module/root concept at all).
- Rewrite all ~79 call sites (see Current Implementation) to use `useXStore()` directly instead of `this.$store...`.
- Add the required new `moduleCache` entries to `sfc/loadSfc.js` for the 4 real `.vue` SFCs that need store access.

**Out of Scope**
- Any change to component behavior/UX beyond what's needed to preserve exact current behavior.
- Any change to the backend API.
- Converting any remaining plain-object `.js` components into real `.vue` SFCs (unrelated, separate historical migration effort).

### Functional Requirements
- Every page/flow that currently works continues to work identically after the migration: login/logout (nav-drawer dialog + form), dashboard (widgets, configurator drawer, node data/alerts, dark mode, locale switch, SSE live updates, app loader overlay), `/config` editor (draft create/update/delete/save/discard, templates, snapshots, node types), `/settings` page, `/users` page (admin-only CRUD), nav-drawer visibility/role-based menu items.
- No `$store` references remain anywhere in the SPA source after the migration; Vuex is fully removed (no script tag, no `Vuex` global usage).
- The subtle pre-existing bug where `$store.dispatch('ui/showDialog', dialogName, true)` silently ignores its 3rd argument (Vuex's `dispatch(type, payload, options)` doesn't forward a 3rd arg to the action) is preserved as-is (i.e. `showDialog` keeps its default `hideOthers=true` behavior at that call site) rather than silently "fixed" as a side effect of the rewrite - see Risks.


# Technical Design

### Key Decisions
- **Options-style Pinia stores** (`defineStore(id, {state, getters, actions})`), not Composition-style (`defineStore(id, () => {...})`): the entire codebase is Options-API only (no `ref`/`reactive`/`<script setup>` anywhere), so Options-style stores are both the closest match to the existing Vuex modules (near copy-paste of `state`/`getters`, mechanical mutation-to-action conversion) and the only style consistent with project conventions.
- **File layout stays put**: `store/index.js` keeps its path but now creates and exports a `Pinia.createPinia()` instance instead of a Vuex store (only `main.js` imports it, so no other import paths change); each `store/modules/*.js` keeps its filename but now exports a `useXStore` function via `Pinia.defineStore('x', {...})` instead of a plain Vuex-module object.
- **Store access pattern in components**: every component that needs a store adds `computed: { xStore() { return useXStore() } }` (Pinia's own recommended `mapStores`-equivalent pattern for Options API), then templates/methods read `this.xStore.someState`/`this.xStore.someGetter`/call `this.xStore.someAction(payload)`. This is a mechanical, consistent rename at every call site: `$store.state.mod.x` → `xStore.x`, `$store.getters['mod/getter']` → `xStore.getter` (parameterized getters returning a function, e.g. `isActiveDialog(dialog)`, work identically in Pinia), `$store.dispatch('mod/action', payload)` → `xStore.action(payload)`, `$store.commit('mod/mutation', payload)` → `xStore.mutation(payload)` (now just another action).
- **Cross-module calls become direct store-to-store calls**: e.g. inside the new `auth` store's `login`/`logout` actions, `import {useUsersStore} from './users.js'` and call `useUsersStore().fetchCurrentUser()` / `.setCurrentUser(null)` directly, replacing `dispatch('users/...', ..., {root: true})`/`commit('users/...', ..., {root: true})`. Same pattern for `config.js`'s many `dispatch('dashboard/fetchNodes', null, {root: true})` calls → `useDashboardStore().fetchNodes()`, and `dashboard.js`'s internal `dispatch('fetchNodes')`/`dispatch('persistConfig', ...)` → `this.fetchNodes()`/`this.persistConfig(...)` (same-store actions can call each other via `this` inside a Pinia action, no change needed there).
- **SFC `moduleCache` additions**: `sfc/loadSfc.js` gets 4 new virtual entries (only for the stores actually used by the 4 real `.vue` SFCs): `'store/ui': {useUiStore}`, `'store/auth': {useAuthStore}`, `'store/dashboard': {useDashboardStore}` (used by `Default.vue`'s `nodes` computed - kept even though currently unused elsewhere, to match existing behavior), `'store/config': {useConfigStore}` (used by `pages/Config.vue`'s `beforeRouteLeave`). SFCs then do `import {useAuthStore} from 'store/auth'` etc., exactly mirroring the existing `import {EventBus} from 'app/EventBus'` pattern.
- **Preserve the `showDialog(dialog, hideOthers=true)` no-op-3rd-arg behavior**: since Pinia actions receive real positional arguments (no more Vuex `dispatch(type, payload, options)` 3-arg split), a literal find-and-replace of `dispatch('ui/showDialog', name, true)` → `uiStore.showDialog(name, true)` would silently change behavior (today's `true` is discarded by Vuex, so `hideOthers` always defaults to `true`). To keep behavior identical, these call sites are rewritten as `uiStore.showDialog(name)` (dropping the previously-inert 3rd argument), documented inline with a short comment referencing this finding.

### Proposed Changes
1. **Library**: fetch Pinia 3.x's `pinia.iife.js` global build, add as `aquaPi/static/libs/pinia.<version>.iife.js`; in `spa.html.jinja2`, replace the `libs/vuex.4.1.0.global.js` `<script>` tag with the new Pinia one (kept right after the Vue script tag, before Vue-Router, matching Pinia's own load-order requirement of needing `Vue` global first).
2. **`store/index.js`**: replace `Vuex.createStore(...)` with `const pinia = Pinia.createPinia(); export default pinia`. The 6 module imports are kept only if still needed for side-effect registration (Pinia stores are lazily created on first `useXStore()` call, so no explicit registration list is required here, unlike Vuex's `modules:` map) - the file becomes very small.
3. **6 store modules** (`store/modules/{ui,auth,dashboard,settings,config,users}.js`): convert to `export const useXStore = Pinia.defineStore('x', {state: () => ({...}), getters: {...}, actions: {...}})`; move every `mutations` entry into `actions` (implementation becomes `actionName(payload) { this.field = ... }` instead of `mutationName(state, payload) { state.field = ... }`); replace every `{root: true}` cross-module `dispatch`/`commit` with a direct `useOtherStore()` import + call.
4. **`main.js`**: `import pinia from './store/index.js'` (rename the imported variable from `store` to `pinia` for clarity), `app.use(pinia)` instead of `app.use(store)`; the root app's own `methods` (`toggleNavDrawer`, `toggleDarkMode`, `setLocale`, `initEventListeners`, `beforeMount`) get a `computed: {uiStore(){return useUiStore()}, usersStore(){return useUsersStore()}, authStore(){return useAuthStore()}}` and their `this.$store...` calls rewritten accordingly.
5. **Plain `.js` component files** (`App.vue.js`, `AquapiConfirmDialog.vue.js`, `AquapiNavDrawer.vue.js`, `dashboard/index.js`, `dashboard/comps.js`, `settings/index.js`, `settings/comps.js`, `config/index.js`, `config/comps.js`, `users/index.js`, `users/comps.js`): add real `import {useXStore} from '../../store/modules/x.js'` at the top (these are genuine ES modules, real imports work fine, unlike the SFCs) plus the `xStore` computed, then rewrite every call site per the Key Decision above.
6. **4 real `.vue` SFCs** (`layouts/Default.vue`, `pages/Config.vue`, `components/auth/AquapiLoginDialog.vue`, `components/auth/AquapiLoginForm.vue`): add the moduleCache-backed imports and `xStore` computed(s), rewrite call sites in both `<template>` and `<script>`.
7. **`sfc/loadSfc.js`**: add the 4 new `moduleCache` entries described above.

### Risks
- The `showDialog(dialog, hideOthers=true)` 3rd-argument no-op (see Key Decisions) is an easy place to accidentally "fix" a latent bug while doing a mechanical find-and-replace; the plan explicitly calls this out so the 2 affected call sites (`AquapiLoginDialog.vue`, `AquapiNavDrawer.vue.js`) are rewritten to preserve current behavior, not silently changed.
- Wide surface area (~15 files, ~79 call sites) increases regression risk purely from typos/missed call sites; mitigated by the project's established headless-browser (Puppeteer) end-to-end verification pass covering every affected page/flow before considering this done.
- Pinia 3.x requires Vue ≥ 3.5.11 (project is on 3.5.40, compatible) and its global/iife build's exact filename/availability will be re-confirmed when actually fetching it during implementation.


# Testing

### Validation Approach
Frontend-only change (no Python/backend touched), validated via the project's established headless-browser (Puppeteer) approach against the live app with a real admin login, consistent with all prior Vue/Vuetify migration rounds documented in `.junie/plans/vue3-vuetify3-vuex4-migration.md`.

### Key Scenarios
- App boot: no console errors, no lingering `Vuex`/`$store` references anywhere (grep-verified), app loader overlay still works (`ui` store).
- Login via the nav-drawer dialog and via the embedded form; logout; dark-mode toggle persists via `localStorage`; language switch works; SSE live node updates still flow into the dashboard.
- Dashboard: widget visibility toggle, configurator drawer open/save/reorder (SortableJS), node data/alert rendering.
- `/config` editor: create/edit/delete/connect nodes in the draft, save/discard, port markers, live-drag-following connections, templates and snapshots dialog (save/insert/restore/delete), unsaved-changes route-leave guard.
- `/settings` page: load/update node settings.
- `/users` page: admin-only visibility, list/create/update/delete users, role-based menu item.

### Edge Cases
- Cross-store actions (`auth.login` → `users.fetchCurrentUser`, `config.saveDraft` → `dashboard.fetchNodes`, etc.) still correctly update the other store's state after conversion to direct store-to-store calls.
- The `showDialog`/`hideOthers` behavior is unchanged at its 2 call sites (verified by confirming no other dialog is force-closed differently than before).

### Test Changes
- All modified `.js` files and the `<script>` blocks of modified `.vue` SFCs checked with `node --input-type=module --check` (existing project convention); no backend code is touched, so no `pytest` run is needed per the agreed testing protocol.


# Delivery Steps

###   Step 1: Add the Pinia library and convert all 6 Vuex modules into Pinia stores
The app boots on Pinia instead of Vuex, with all 6 store modules converted to idiomatic Options-style Pinia stores and cross-module calls rewired as direct store-to-store calls.
- Fetch a Pinia 3.x global/iife browser build, add it as `aquaPi/static/libs/pinia.<version>.iife.js`, and swap the `<script>` tag for it (in place of Vuex) in `aquaPi/templates/pages/spa.html.jinja2`.
- Rewrite `store/index.js` to `Pinia.createPinia()` and export the instance.
- Convert `store/modules/{ui,auth,dashboard,settings,config,users}.js` to `Pinia.defineStore('x', {state, getters, actions})`, folding every `mutations` entry into `actions`, and replacing every `{root: true}` cross-module `dispatch`/`commit` with a direct `useOtherStore()` import/call (e.g. `auth.login` calling `useUsersStore().fetchCurrentUser()`, `config.saveDraft` calling `useDashboardStore().fetchNodes()`).
- Update `main.js` to `app.use(pinia)` and rewrite the root app's own `$store` usages (`toggleNavDrawer`, `toggleDarkMode`, `setLocale`, event listeners, `beforeMount`) to use `useUiStore()`/`useAuthStore()`/`useUsersStore()`.

###   Step 2: Migrate all plain .js component files to use Pinia stores directly
Every real-ES-module component file that previously used `this.$store...` now imports and uses the corresponding `useXStore()` Pinia stores, with identical behavior.
- Update `App.vue.js`, `components/app/AquapiConfirmDialog.vue.js`, `components/app/AquapiNavDrawer.vue.js` to import the needed stores and replace `$store.state/getters/dispatch/commit` call sites with `xStore.*` equivalents.
- Update `components/dashboard/index.js` and `components/dashboard/comps.js` (widgets, node data/alert rendering, configurator drawer).
- Update `components/settings/index.js` and `components/settings/comps.js`.
- Update `components/config/index.js` and `components/config/comps.js` (draft CRUD, templates/snapshots, connections).
- Update `components/users/index.js` and `components/users/comps.js`.
- Preserve the existing no-op 3rd-argument behavior of the two `ui/showDialog` call sites found in `AquapiNavDrawer.vue.js` during this and the next stage.

###   Step 3: Migrate the 4 real .vue SFCs and their moduleCache-based store imports
The 4 `.vue` SFCs that use store access (layout, config page, and the 2 login SFCs) work correctly via the vue3-sfc-loader's moduleCache mechanism instead of `$store`.
- Add `'store/ui'`, `'store/auth'`, `'store/dashboard'`, `'store/config'` entries to `sfc/loadSfc.js`'s `moduleCache`, mirroring the existing `app/EventBus`/`app/i18n` pattern.
- Update `layouts/Default.vue` (app loader overlay, app-bar colors, login/logout, nav items, dark mode).
- Update `pages/Config.vue`'s `beforeRouteLeave` guard.
- Update `components/auth/AquapiLoginDialog.vue` and `components/auth/AquapiLoginForm.vue`.

###   Step 4: End-to-end verification and cleanup
The migrated app is confirmed to work identically to before across every affected page/flow, with no leftover Vuex/$store references.
- Grep the entire `aquaPi/static/spa` tree to confirm zero remaining `$store`/`Vuex` references.
- Run a headless-browser (Puppeteer) session with a real admin login covering: boot/app-loader, login/logout, dark mode, locale switch, SSE live updates, dashboard widgets/configurator, `/config` editor (draft CRUD, templates, snapshots, connections/drag), `/settings`, `/users`.
- Syntax-check all modified `.js`/`.vue` files with `node --input-type=module --check`.
- Update `.junie/plans/vue3-vuetify3-vuex4-migration.md` (or a new dedicated plan doc) with a completion summary of this migration round.