import {AQUAPI_EVENTS, EventBus} from './EventBus.js'
import {useUiStore} from '../../store/modules/ui.js'

const AquapiConfirmDialog = {
	name: 'AquapiConfirmDialog',
	template: `
		<v-dialog
			v-model="visible"
			persistent
			max-width="450px"
			:overlay-opacity="uiStore.overlay.opacity"
		>
			<v-card>
				<v-card-title v-if="title">{{ title }}</v-card-title>
				<v-card-text class="pt-4" style="white-space: pre-line;">{{ message }}</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn v-if="!alertOnly" text @click="onCancel">{{ $t('misc.dialog.cancel') }}</v-btn>
					<v-btn color="primary" text @click="onConfirm">{{ alertOnly ? $t('misc.dialog.ok') : $t('misc.dialog.confirm') }}</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	`,

	data() {
		return {
			visible: false,
			title: '',
			message: '',
			alertOnly: false,
			resolve: null,
		}
	},

	computed: {
		uiStore() {
			return useUiStore()
		},
	},

	methods: {
		onRequest(payload) {
			this.title = (payload.options && payload.options.title) || ''
			this.message = payload.message
			this.alertOnly = !!(payload.options && payload.options.alertOnly)
			this.resolve = payload.resolve
			this.visible = true
		},
		onConfirm() {
			this.visible = false
			const resolve = this.resolve
			this.resolve = null
			if (resolve) resolve(true)
		},
		onCancel() {
			this.visible = false
			const resolve = this.resolve
			this.resolve = null
			if (resolve) resolve(false)
		},
	},

	created() {
		EventBus.$on(AQUAPI_EVENTS.CONFIRM_REQUESTED, this.onRequest)
	},
	unmounted() {
		EventBus.$off(AQUAPI_EVENTS.CONFIRM_REQUESTED, this.onRequest)
	},
}

export {AquapiConfirmDialog}

// vim: set noet ts=4 sw=4:
