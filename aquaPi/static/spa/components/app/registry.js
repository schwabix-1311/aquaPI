'use strict'

// Vue 3 removed the global `Vue.component(...)` registration API - a
// component must now be registered on the concrete `app` instance, which
// does not exist yet while these modules are loaded (they self-register
// as a module-load-time side effect). This tiny registry preserves that
// "just import the module and it's globally available" developer
// experience: modules call registerGlobalComponent(name, def) at load
// time, and main.js calls installGlobalComponents(app) once, after
// Vue.createApp(), to actually register them all on the app instance.

// Since Step 20, page/layout SFCs (`Home.vue`, `Config.vue`, `Settings.vue`,
// `Default.vue`, ...) are loaded lazily via `loadSfc()`, which means the
// `.js` modules that register their child components (e.g.
// `components/dashboard/index.js`) may only get imported (and thus only
// call `registerGlobalComponent`) *after* `installGlobalComponents(app)`
// already ran once at boot. So `installGlobalComponents` also remembers
// the `app` instance and any later `registerGlobalComponent` call
// registers directly on it instead of just queueing.
const pendingComponents = []
let installedApp = null

function registerGlobalComponent(name, def) {
	if (installedApp) {
		installedApp.component(name, def)
	} else {
		pendingComponents.push({name, def})
	}
}

function installGlobalComponents(app) {
	pendingComponents.forEach(({name, def}) => app.component(name, def))
	pendingComponents.length = 0
	installedApp = app
}

export {registerGlobalComponent, installGlobalComponents}

// vim: set noet ts=4 sw=4:
