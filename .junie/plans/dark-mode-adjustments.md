---
sessionId: session-260802-063658-1699
---

# Requirements

### Overview & Goals
The user has asked to add **"Dark Mode adjustments"** as a new, upcoming round of work on top of the existing detail plan `.junie/plans/vue3-vuetify3-vuex4-migration.md` (currently at Round 6, all previous rounds ✓ Done). The user explicitly said the concrete list of issues will be provided **later** - for now this should only be **recorded as a pending item** on the plan, not investigated or implemented yet.

### Current Implementation (for context, not yet in scope to change)
Dark Mode already exists and works at a basic level, established across several earlier rounds/steps:
- Toggle: `layouts/Default.vue`'s app-bar icon button calls `$root.toggleDarkMode` (defined in `main.js`), which flips `this.$vuetify.theme.global.name` between `'light'`/`'dark'` and dispatches `ui/setDarkMode` (`store/modules/ui.js`).
- Persistence: `ui/setDarkMode` writes to `window.localStorage['aquapi.theme']`; `main.js`'s boot logic reads it back on load.
- Per-component theming: several components branch on `$vuetify.theme.global.current.dark` to pick colors (`AquapiNavDrawer.vue.js`, `layouts/Default.vue`'s app-bar/footer, `components/app/index.js`, `components/dashboard/index.js`, and `HistoryChart`'s chart grid colors in `components/dashboard/comps.js`), several via `$store.state.ui.colors.darkMode.*`/`lightMode.*` palettes defined in `store/modules/ui.js`.
- This is the same area already touched incidentally by Round 5/6 fixes (Save-button `variant`, configurator scrim) and by the Vuetify 3 theme-API migration (master-plan Step 18).

### Scope
**In Scope (this task)**
- Add a new, clearly-marked **pending/placeholder entry** to `.junie/plans/vue3-vuetify3-vuex4-migration.md` noting that a further round of Dark Mode adjustments has been requested, with the concrete issue list still **to be provided by the user**.
- No code changes, no guessed fixes, no assumptions about what's "wrong" with Dark Mode today.

**Out of Scope (deferred until the user provides specifics)**
- Any actual visual/contrast/color fix to Dark Mode.
- Any investigation beyond a light context-gathering pass (done above, for the plan document itself) into which files are involved.

### Functional Requirements
- The plan document contains a new, easy-to-find section (e.g. "Round 7: Dark Mode adjustments - pending details") stating the request, referencing the already-known Dark-Mode-related files as likely candidates once specifics arrive, and explicitly marking it as **not yet specified / not started**.
- The existing Round 6 "✓ Done" status and all prior rounds remain unchanged.


# Technical Design

### Proposed Changes
Append a new top section to `.junie/plans/vue3-vuetify3-vuex4-migration.md`, above the current `Round 6` summary, e.g.:

```markdown
# Round 7: Dark Mode adjustments (pending details)

Status: Requested, not yet specified - awaiting concrete issue list from the user.

The user asked for a further round of Dark Mode adjustments. No specific defects
were described yet; this entry is a placeholder so the request isn't lost.
Once specifics are provided, they will be turned into proper Requirements/
Technical Design/Testing sections and a delivery plan, following the same
pattern as Rounds 3-6 above.

Likely-relevant files, based on where Dark Mode branching already exists today
(for reference only, not a commitment to change them):
- `aquaPi/static/spa/main.js` (`toggleDarkMode`, boot-time theme restore)
- `aquaPi/static/spa/store/modules/ui.js` (`darkMode` state, `colors.darkMode`/`colors.lightMode` palettes)
- `aquaPi/static/spa/layouts/Default.vue` (app-bar/footer colors, toggle button)
- `aquaPi/static/spa/components/app/AquapiNavDrawer.vue.js`, `components/app/index.js`, `components/dashboard/index.js` (`$vuetify.theme.global.current.dark` branches)
- `aquaPi/static/spa/components/dashboard/comps.js` (`HistoryChart`'s chart grid colors)
- `aquaPi/static/css/app.css` / `aquaPi/static/css/vuetify.3.13.0.customized.min.css` (theme-dependent CSS)
```

No other files are touched.

### Risks
- None - this is a documentation-only placeholder, no behavior changes.


# Delivery Steps

###   Step 1: Add a 'Round 7: Dark Mode adjustments (pending details)' placeholder section to the plan document
The plan document `.junie/plans/vue3-vuetify3-vuex4-migration.md` contains a new top section recording the Dark Mode adjustment request without guessing at fixes.
- Insert a new `# Round 7: Dark Mode adjustments (pending details)` section above the current `Round 6` summary.
- State explicitly that the concrete issue list is still to be provided by the user and that no implementation has started.
- List the files already known to be involved in Dark Mode theming today (`main.js`, `store/modules/ui.js`, `layouts/Default.vue`, `components/app/*`, `components/dashboard/*`, the two CSS files) purely as reference context for whoever picks this up later.
- Leave the document's overall `Implementation Status` header and all prior Round 2-6 content unchanged.

###   Step 2: Turn the placeholder into a full Round 7 plan once the user provides specifics
Once the user describes the concrete Dark Mode problems, the placeholder section is replaced with proper Requirements/Technical Design/Testing content and a delivery plan, matching the structure already used for Rounds 3-6.
- Gather the user's specific complaints (which pages/components look wrong, which colors/contrasts are the issue).
- Investigate the exact root cause in the relevant file(s) identified in Stage 1 (or others found during investigation).
- Implement and verify the fix via the project's established headless-browser verification approach, then update the plan document's status and header to reflect Round 7 as done.