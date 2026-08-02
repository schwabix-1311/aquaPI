'use strict'

// Vue 3 removed the global `Vue.component(...)` registration API - a
// component must now be registered on the concrete `app` instance, which
// does not exist yet while these modules are loaded (they self-register
// as a module-load-time side effect). This tiny registry preserves that
// "just import the module and it's globally available" developer
// experience: modules call registerGlobalComponent(name, def) at load
// time, and main.js calls installGlobalComponents(app) once, after
// Vue.createApp(), to actually register them all on the app instance.

const pendingComponents = []

function registerGlobalComponent(name, def) {
	pendingComponents.push({name, def})
}

function installGlobalComponents(app) {
	pendingComponents.forEach(({name, def}) => app.component(name, def))
}

export {registerGlobalComponent, installGlobalComponents}

// vim: set noet ts=4 sw=4:
