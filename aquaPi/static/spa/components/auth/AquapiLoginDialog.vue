<template>
	<v-dialog
		v-model="active"
		persistent
		max-width="400px"
		:overlay-opacity="$store.state.ui.overlay.opacity"
	>
	<aquapi-login-form :addCancel="authenticated"></aquapi-login-form>
	</v-dialog>
</template>

<script>
// Loaded via moduleCache (not a real relative import), since vue3-sfc-loader
// can't parse a plain .js file's own `import`/`export` statements - see
// the comment in aquaPi/static/spa/sfc/loadSfc.js for details.
import Vue from 'vue'
import {loadSfc} from 'sfc/loadSfc'

export default {
	name: 'AquapiLoginDialog',
	components: {
		// A bare `() => loadSfc(...)` factory only auto-resolves as an async
		// component for Vue Router route components; plain `components:`
		// option entries need an explicit `defineAsyncComponent()` wrapper.
		AquapiLoginForm: Vue.defineAsyncComponent(() => loadSfc('/static/spa/components/auth/AquapiLoginForm.vue'))
	},

	data() {
		return {
			dialogName: 'AquapiLoginDialog'
		};
	},

	computed: {
		authenticated() {
			return this.$store.getters['auth/authenticated']
		},
		active: {
			get() {
				// while unauthenticated, the login dialog is always forced open,
				// so the SPA remains the sole place a user ever sees a login
				// prompt (never a separate, full-page redirect to /login)
				return !this.authenticated || this.$store.getters['ui/isActiveDialog'](this.dialogName)
			},
			set(value) {
				// ignore attempts to close it while unauthenticated - there is
				// no cancel affordance in that state (see :addCancel above)
				if (!value && !this.authenticated) return
				if (value) this.$store.dispatch('ui/showDialog', this.dialogName, true)
				else this.$store.dispatch('ui/hideDialog', this.dialogName)
			}
		}
	},

	// created() {
	//	EventBus.$on(AQUAPI_EVENTS.AUTH_LOGGED_IN, () => {
	//		this.$store.dispatch('ui/hideDialog', this.dialogName)
	//	})
	// },
	//
	// unmounted() {
	//	EventBus.$off(AQUAPI_EVENTS.AUTH_LOGGED_IN)
	// }
}
</script>
