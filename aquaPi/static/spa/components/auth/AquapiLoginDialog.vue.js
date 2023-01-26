import {AquapiLoginForm} from './AquapiLoginForm.vue.js'
import {AQUAPI_EVENTS, EventBus} from '../app/EventBus.js';

const AquapiLoginDialog = {
	name: 'AquapiLoginDialog',
	components: {
		AquapiLoginForm
	},
	template: `
	<v-dialog
		v-model="active"
		persistent
		max-width="400px"
		:overlay-opacity="$store.state.ui.overlay.opacity"
	>
		<aquapi-login-form :addCancel="true"></aquapi-login-form>
	</v-dialog>
  `,

	data() {
		return {
			dialogName: 'AquapiLoginDialog'
		};
	},

	computed: {
		active: {
			get() {
				return this.$store.getters['ui/isActiveDialog'](this.dialogName)
			},
			set(value) {
				if (value) this.$store.dispatch('ui/showDialog', this.dialogName, true)
				else this.$store.dispatch('ui/hideDialog', this.dialogName)
			}
		}
	},

	// created() {
	// 	EventBus.$on(AQUAPI_EVENTS.AUTH_LOGGED_IN, () => {
	// 		this.$store.dispatch('ui/hideDialog', this.dialogName)
	// 	})
	// },
	//
	// destroyed() {
	// 	EventBus.$off(AQUAPI_EVENTS.AUTH_LOGGED_IN)
	// }
}

// Vue.component('AquapiLoginDialog', AquapiLoginDialog)
export {AquapiLoginDialog}
