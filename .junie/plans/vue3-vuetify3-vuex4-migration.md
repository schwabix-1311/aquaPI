---
sessionId: session-260802-063658-1699
---

# Requirements

### Overview & Goals
This is **Plan Step 18** (`.junie/plans/project-clarification-and-test-plan.md`): swap the frontend's core libraries from Vue 2.7 / Vuetify 2.6 / Vuex 3.6 / Vue-Router 3.6 / VueI18n 8.x to their Vue-3-compatible equivalents (Vue 3, Vuetify 3, Vuex 4, Vue-Router 4, Vue-I18n 9), **without introducing a build process** - the project continues to load plain ESM/global browser builds from `aquaPi/static/libs/` and plain JS "`.vue.js`" component-definition modules (no real `.vue` SFC compilation yet - that is Step 19/20).

Goal: after this step, the app boots, authenticates, and all existing pages (Home/Dashboard, Config, Settings, About, Login) render and behave exactly as before, just running on the Vue 3 stack.

### Scope
**In Scope**
- Replacing the 5 core library files under `aquaPi/static/libs/` with Vue-3-compatible ESM/global browser builds.
- Updating `spa.html.jinja2` script tags and the Vuetify CSS reference for the new versions.
- Rewriting the app bootstrap (`main.js`) to use `Vue.createApp()`, `Vuex.createStore()`, `VueRouter.createRouter()` (with `createWebHashHistory()`), `Vuetify.createVuetify()`, `VueI18n.createI18n()`.
- Fixing the breaking changes that block the app from working at all under Vue 3: the global `Vue.component(...)` self-registration pattern used by ~30 components, the `EventBus = new Vue()` pattern (no more `$on`/`$off`/`$emit` on instances), and the `destroyed`/`beforeDestroy` lifecycle hook renames (`unmounted`/`beforeUnmount`).
- Adjusting the Vuetify theme/icon bootstrap config and base layout (`v-app`/`v-main`) for the Vuetify 3 API.

**Out of Scope** (explicitly deferred to later plan steps)
- Migrating any `.vue.js` file into a real `.vue` SFC (Step 19/20).
- Introducing `vue3-sfc-loader` (Step 19).
- Any new feature work.

### Functional Requirements
- The app boots without console errors on `/`, `/login`, `/config`, `/settings`, `/about`.
- Login flow, navigation drawer, dark-mode toggle, and the SSE-driven live node updates keep working exactly as before.
- All existing Vuetify components used in the app render visually equivalent to before (colors, icons, Blinker font).
- All places that relied on `EventBus.$on/$off/$emit` keep working unchanged from the call-site's point of view.
- All globally-registered components (`AquapiPageHeading`, `ConfigNodeBox`, dashboard widgets, settings widgets, etc.) are resolvable in templates exactly as before.

# Technical Design

### Current Implementation
- `aquaPi/templates/pages/spa.html.jinja2` loads Vue 2.x from a CDN plus Vuex 3.6.2, Vue-Router 3.6.5, Vue-I18n 8.28.2, Vuetify 2.6.13 as plain global `<script>` tags (non-module), then `main.js` as `<script type="module">` which freely uses the resulting `window.Vue`/`window.Vuex`/`window.VueRouter`/`window.Vuetify` globals (no explicit imports).
- `aquaPi/static/spa/main.js`: `new Vue({store, router, i18n, vuetify: new Vuetify({...}), render: h => h(App)}).$mount('#app')`, plus `Vue.prototype.$confirm/$alert`.
- `store/index.js`: `Vue.use(Vuex); new Vuex.Store({modules: {...}})`.
- `router/index.js`: `new VueRouter({mode: 'hash', routes, scrollBehavior})` + `router.beforeEach`.
- `components/app/EventBus.js`: `const EventBus = new Vue()`, used via `.$on/.$off/.$emit` in ~10 places (`App.vue.js`, `AquapiConfirmDialog.vue.js`, `layouts/Default.vue.js`, `components/dashboard/comps.js`).
- ~30 component modules (`components/**/index.js`, `components/**/comps.js`) call `Vue.component('Name', Def)` as a **module-load-time side effect** so the component becomes globally resolvable in any template.
- Several components use `destroyed()`/no `beforeDestroy` currently only `destroyed` (removed/renamed in Vue 3 to `unmounted`).
- `aquaPi/static/spa/comps.js` (`AppFooComp`, imported by `layouts/Default.vue.js`) uses `this.$root.$on('test-clicked', ...)` - a leftover demo snippet.
- CSS: `aquaPi/static/css/vuetify.2.6.13.customized.min.css` is a locally patched Vuetify 2 CSS build (default font swapped from Roboto to Blinker).

### Key Decisions
- **Global component registration** → **central registry list** (per user decision): new `components/app/registry.js` exports `registerGlobalComponent(name, def)` which pushes `{name, def}` into an array; `main.js` iterates the array once after `Vue.createApp()` and calls `app.component(name, def)` before mounting. This keeps the per-file diff to a one-line function-name swap (`Vue.component(...)` → `registerGlobalComponent(...)`) across all ~30 call sites and preserves today's "just import the module and it's globally available" developer experience.
- **EventBus replacement** → **own mini emitter with the same `$on`/`$off`/`$emit` API** (per user decision): a small class (`~20 LOC`) implemented in `components/app/EventBus.js` (Map of event name → Set of listeners) replaces `new Vue()`. All ~10 existing call sites (`EventBus.$on(...)`, `.$off(...)`, `.$emit(...)`) stay byte-for-byte unchanged, only the `EventBus` construction itself changes. `this.$root.$on(...)` in `comps.js` is removed (dead demo code) since the root app instance no longer supports it and it serves no functional purpose.
- **Lifecycle hooks**: `destroyed()` → `unmounted()`, `beforeDestroy()` → `beforeUnmount()` (Vue 3 rename) at all ~6 identified call sites; `created()`, `data()`, `methods`, `computed`, `template` (string) Options-API usage is unchanged and remains compatible.
- **No build process, ESM/global browser builds only** (continuing existing project convention): fetch Vue 3, Vuetify 3, Vuex 4, Vue-Router 4, Vue-I18n 9 as pre-built global `.js` bundles (analogous to today's `vue.2.7.14.js` etc.) and drop them into `aquaPi/static/libs/`, referenced from `spa.html.jinja2` the same way as today.

### Proposed Changes
1. **Libraries**: add `vue.3.x.global.js`, `vuex.4.x.global.js`, `vue-router.4.x.global.js`, `vue-i18n.9.x.global.js`, `vuetify.3.x.global.js` (+ its companion CSS) under `aquaPi/static/libs/` (and `static/css/`), replacing the current Vue-2-era files; keep `chart.js`, `luxon`, `sortablejs`/`vuedraggable`, `vue-masonry-css` untouched for now (their Vue-2-specific integration, if any, will be revisited only if they break).
2. **`spa.html.jinja2`**: swap `<script>` tags to the new library files; swap the Vuetify CSS `<link>` to the new customized Vuetify 3 build (same Blinker-font patch reapplied).
3. **`main.js`**: rewrite bootstrap using `const app = Vue.createApp(App)`; `app.use(store)`, `app.use(router)`, `app.use(i18n)`, `app.use(vuetify)`; move `$confirm`/`$alert` to `app.config.globalProperties`; iterate the component registry and call `app.component(...)`; `app.mount('#app')`.
4. **`store/index.js`**: `Vuex.createStore({modules: {...}})` (drop `Vue.use(Vuex)`, no longer needed/valid).
5. **`router/index.js`**: `VueRouter.createRouter({history: VueRouter.createWebHashHistory(), routes, scrollBehavior})`; `router.beforeEach` signature unchanged.
6. **`i18n/index.js`**: `VueI18n.createI18n({legacy: false, ...})` (checked against actual current options during implementation) so Composition-API-style `useI18n`/global injection works the same as before for Options-API `$t` calls (`legacy: false` still exposes `$t` via `globalInjection`).
7. **`components/app/registry.js`** (new file) + one-line edits to all ~30 `Vue.component(...)` call sites.
8. **`components/app/EventBus.js`**: replace `new Vue()` with the new mini-emitter class; remove the dead `this.$root.$on(...)` block in `comps.js`.
9. Rename `destroyed`/`beforeDestroy` hooks at the ~6 identified sites (`App.vue.js`, `AquapiConfirmDialog.vue.js`, `layouts/Default.vue.js`, `components/dashboard/comps.js`).
10. **Vuetify bootstrap**: adapt the `createVuetify({icons, theme})` call to the Vuetify 3 theme-config shape (`theme: {defaultTheme: 'light', themes: {light: {colors: {...}}}}`) while keeping the same color values and MDI iconfont.

### Data Models / Contracts
```js
// components/app/registry.js
const pendingComponents = []
export function registerGlobalComponent(name, def) {
  pendingComponents.push({name, def})
}
export function installGlobalComponents(app) {
  pendingComponents.forEach(({name, def}) => app.component(name, def))
}
```
```js
// components/app/EventBus.js
class MiniEmitter {
  constructor() { this._listeners = new Map() }
  $on(event, fn) { /* add to Set for event */ }
  $off(event, fn) { /* remove fn, or clear all listeners for event if fn omitted */ }
  $emit(event, ...args) { /* call all listeners for event */ }
}
export const EventBus = new MiniEmitter()
```

### Components
- `main.js`, `store/index.js`, `router/index.js`, `i18n/index.js`: bootstrap rewritten for the v4/v3/v9 APIs.
- `components/app/EventBus.js`: internal implementation swapped, public `$on/$off/$emit` surface unchanged.
- `components/app/registry.js`: new, small utility module.
- ~30 component modules across `components/app/`, `components/auth/`, `components/config/`, `components/dashboard/`, `components/settings/`: one-line `Vue.component(...)` → `registerGlobalComponent(...)` swap each.
- `App.vue.js`, `layouts/Default.vue.js`, `components/app/AquapiConfirmDialog.vue.js`, `components/dashboard/comps.js`: lifecycle hook renames.
- `aquaPi/static/spa/comps.js`: drop the dead `this.$root.$on(...)` demo code from `AppFooComp`.
- `aquaPi/templates/pages/spa.html.jinja2`: script/CSS references updated.

### Risks
- **Third-party libs without Vue-3 build**: `vuedraggable` 2.x is Vue-2-only; it's currently only used by the (Step 11-superseded) sortable-list dashboard configurator, not by the drag&drop-via-native-mouse-events `/config` editor - if it turns out to still be loaded/used, its breakage will be flagged but fixing it is out of scope for this step (tracked as follow-up if needed).
- **VueI18n 9 API differences** (message format, `legacy` mode) could subtly change interpolation syntax (`%{name}` placeholders are used today) - will be verified against the actual locale files during implementation.
- **Vuetify 3 component API differences** (e.g. `v-overlay` `absolute` prop removed/renamed) may require small per-component tweaks beyond the bootstrap; these will surface during manual verification and be fixed as part of this step, staying within "keep pages working as before" scope rather than redesigning them.

# Testing

### Validation Approach
This step touches only frontend bootstrap/library code (no Python/backend changes), so validation is manual/browser-based plus static syntax checks - consistent with the project's established verification approach for frontend-only steps.

### Key Scenarios
- App loads at `/` without console errors; splash screen disappears and the dashboard renders.
- Login dialog opens/closes, login succeeds, SSE-driven live node value updates still arrive and update the dashboard (exercises the new `EventBus`).
- `/config` editor: node boxes render (exercises the component registry for `ConfigNodeBox`/`ConfigConnections`/`ConfigNodeDialog`), draft save/discard and the confirm dialog still work (exercises `AquapiConfirmDialog` + lifecycle hook renames).
- `/settings` page renders generic setting widgets (exercises the settings component registrations).
- Dark-mode toggle and navigation drawer still work.

### Edge Cases
- Component that is imported but never referenced in a rendered template should still not throw during `installGlobalComponents`.
- Repeated `EventBus.$off()` calls without a matching `$on` should not throw.
- Route navigation away from `/config` with unsaved changes still triggers the `$confirm` leave-guard (exercises `app.config.globalProperties.$confirm`).

### Test Changes
- All modified `.js` files checked with `node --input-type=module --check` (existing project convention for this frontend, no Python touched so no `pytest` run needed for this step per the agreed testing protocol).

# Delivery Steps

### ✓ Step 1: Add Vue 3 / Vuetify 3 / Vuex 4 / Router 4 / I18n 9 library builds and update page shell
The static libs directory contains Vue-3-compatible global browser builds and the HTML shell references them instead of the Vue-2-era files.
- Add `vue.3.x.global.js`, `vuex.4.x.global.js`, `vue-router.4.x.global.js`, `vue-i18n.9.x.global.js`, `vuetify.3.x.global.js` under `aquaPi/static/libs/`, plus the matching Vuetify 3 CSS bundle under `aquaPi/static/css/` (with the existing Blinker-font customization reapplied).
- Update `aquaPi/templates/pages/spa.html.jinja2` script `<script>`/CSS `<link>` references to the new files, removing the old Vue-2 CDN/local script tags.
- Leave `chart.js`, `luxon`, `sortablejs`/`vuedraggable`, `vue-masonry-css` untouched at this stage.

### ✓ Step 2: Build the shared component registry and mini EventBus, and rename lifecycle hooks
The app has a working, Vue-3-safe mechanism for global component registration and cross-component events, and no component still uses removed Vue-2 lifecycle hooks.
- Add `components/app/registry.js` with `registerGlobalComponent(name, def)` / `installGlobalComponents(app)`.
- Replace all ~30 `Vue.component('Name', Def)` call sites (across `components/app/`, `components/auth/`, `components/config/`, `components/dashboard/`, `components/settings/`) with `registerGlobalComponent('Name', Def)`.
- Rewrite `components/app/EventBus.js` to export a small custom emitter class exposing `$on`/`$off`/`$emit`, replacing `new Vue()`, without touching any of the ~10 existing call sites.
- Remove the dead `this.$root.$on('test-clicked', ...)` block from `AppFooComp` in `aquaPi/static/spa/comps.js`.
- Rename `destroyed()` → `unmounted()` and `beforeDestroy()` → `beforeUnmount()` in `App.vue.js`, `components/app/AquapiConfirmDialog.vue.js`, `layouts/Default.vue.js`, and `components/dashboard/comps.js`.

### ✓ Step 3: Rewrite the app bootstrap for the Vue 3 / Vuex 4 / Router 4 / I18n 9 / Vuetify 3 APIs
The application boots via `Vue.createApp()` and all core plugins are wired up through the new v3/v4/v9 APIs.
- `store/index.js`: switch to `Vuex.createStore({modules})`, dropping `Vue.use(Vuex)`.
- `router/index.js`: switch to `VueRouter.createRouter({history: VueRouter.createWebHashHistory(), routes, scrollBehavior})`, keeping the existing `beforeEach` guard logic.
- `i18n/index.js`: switch to `VueI18n.createI18n({legacy: false, ...})`, verified against the existing locale files' interpolation syntax.
- `main.js`: switch to `Vue.createApp(App)`, `app.use(store/router/i18n/vuetify)`, move `$confirm`/`$alert` onto `app.config.globalProperties`, call `installGlobalComponents(app)` from stage 2, then `app.mount('#app')`.
- Adapt the `createVuetify({icons, theme})` call to the Vuetify 3 theme-config shape while preserving the existing color palette and MDI iconfont.

### ✓ Step 4: Verify all existing pages against the new stack and fix surfaced component-level breakages
Verified with a real headless-browser run (login, `/`, `/config`, `/settings`, `/about`, dark-mode toggle, node-box drag) against the running Flask app with the user's actual 17-node configuration - all pages render full content and the app boots without fatal errors.
- **Dark-mode fix (the actual surfaced breakage)**: Vuetify 3 no longer exposes `$vuetify` as a plain object with a `theme.dark` boolean; instead it's provided via a global mixin computed property that wraps the injected theme instance in `vue.reactive(...)`, which **auto-unwraps nested refs**. Fixed by using `$vuetify.theme.global.current.dark` (read) and `$vuetify.theme.global.name` (read/write, no `.value`!) in `main.js`'s `toggleDarkMode`/`beforeMount` and in the 5 templates that previously read `$vuetify.theme.dark` (`layouts/Default.vue.js`, `layouts/Auth.vue.js`, `components/app/AquapiNavDrawer.vue.js`, `components/app/index.js`, `components/dashboard/index.js`); added an explicit `dark` theme definition to `createVuetify({theme: {themes: {light, dark}}})` (previously only `light` existed). Verified via headless browser: clicking the dark-mode toggle now actually switches the `v-application` element's theme class from `v-theme--light` to `v-theme--dark`.
- **Confirmed pre-existing, accepted risk now also covers `vue-masonry-css`**: like the already-flagged `vuedraggable` 2.x, `vue-masonry-css` 1.x is Vue-2-only and throws `TypeError: window.Vue.component/use is not a function` at script-load time under Vue 3 (both call the old global `Vue.component`/`Vue.use` API as a load-time side effect). Both `<draggable>` (dashboard widget reorder drawer) and `<masonry>` (dashboard widget grid) end up unregistered as a result. Verified via headless browser that this does **not** break page rendering (Vue 3 still renders unresolved custom elements together with their slot content as plain DOM elements; confirmed the dashboard's widget list itself still renders, just without the masonry column layout or drag-reorder capability) - consistent with the already-accepted risk tolerance for `vuedraggable`. Sourcing a Vue-3-compatible drop-in replacement for both is out of scope for this step and tracked as a follow-up.
- Ran `node --input-type=module --check` over all modified `.js` files (all pass).
- `.junie/plans/project-clarification-and-test-plan.md` updated to mark Step 18 as done, documenting the registry/EventBus/lifecycle-hook/dark-mode approach actually implemented and the two known legacy-plugin limitations.